from __future__ import print_function

import os
import sys
import json
import httplib2
import traceback
import logging
from datetime import datetime as dt
from dateutil import tz
import dateutil.parser
from time import sleep
from enum import Enum
from urllib.request import urlopen

sys.path.insert(0, "K:\Documents\GitHub\gspread")
sys.path.insert(0, "/home/kyle/gspread")
import gspread

from apiclient import discovery, errors
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/drive-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/drive'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'GWG Leaderboard Updater'
log = None

try:
    import argparse
    flags = tools.argparser.parse_args([])
except ImportError:
    flags = None

# Special google drive keys for certain columns or expected phrases
class SheetKeys(Enum):
    ANSWERKEY_SHEET = 1
    DATE_COLUMN = 1
    READY_COLUMN = 8
    LEADERBOARD_ADDED_COLUMN = 9
    LEADER_WRITTEN_SUCCESS = "yes"

class DriveManager():
    gc = None
    service = None
    drive_files = None
    secrets = None

    def __init__(self, secrets, team="52", debug=False, update=True):
        """init google drive management objects"""
        global log
        level = logging.INFO
        if debug:
            level = logging.DEBUG

        logging.basicConfig(level=level, filename="drive_manager.log", filemode="a+",
                            format="%(asctime)-15s %(levelname)-8s %(message)s")
        log = logging.getLogger("drive_manager")

        self.secrets = secrets
        self.team_folder = team
        if update:
            self.update_drive_files()

    def refresh_gdrive_credentials(self):
        """refreshes google drive credentials so we can talk to google drive again"""

        credentials = self._get_credentials()
        http = credentials.authorize(httplib2.Http())

        credentials.refresh(http)

        # gspread 'cursor' to read workbooks and sheets
        self.gc = gspread.authorize(credentials)
        self.service = discovery.build('drive', 'v2', http=http)

    def _get_sheet_index(self, game):
        """take a string of a worksheet name and steal all the numbers from it.

        Eg. GWG3 returns 3
            GM5 returns 4

        returns int
        """
        return int(''.join(filter(lambda x: x.isdigit(), game)))

    def _get_gameday_data(self, game_day, team):
        """returns the game day data"""
        parts = game_day.split("/")
        today = str(parts[0]) + "-" + str(parts[1]) + "-" + str(parts[2])

        if str(team) == "-1":
            team = "52" 

        attempts = 0
        while attempts < 5:
            try:
                attempts += 1
                data = urlopen("https://statsapi.web.nhl.com/api/v1/schedule?expand=schedule.linescore&startDate=" + today + "&endDate=" + today + "&teamId=" + str(team))
                data = json.load(data)
                return data['dates'][0]['games'][0]['linescore']['periods'][0]['startTime']
            except Exception as e:
                log.error("exception occurred in is_game_day. Trying again shortly")
                log.error('An error occurred: %s' % e)
                log.error(traceback.print_exc())
                sleep(15)

    def _get_start_time(self, game_date, team):
        """retrieves the puck drop time and returns the UTC python object

        Note: Gdrive defaults the timestamp to your local configd for your general overall account. In my case, CST.
        Because of this I am converting this UTC to CST so the dates can be managed directly instead of converted later on 
        and making more code changes.

        inspired by
        https://stackoverflow.com/a/4771733
        """

        game_time = self._get_gameday_data(game_date, team)

        from_zone = tz.gettz('UTC')
        to_zone = tz.gettz('America/Winnipeg')

        # date formated like "2017-11-17T01:08:08Z"
        the_date = dateutil.parser.parse(game_time)
        utc = the_date.replace(tzinfo=from_zone)
        cen = utc.astimezone(to_zone)

        return cen.strftime('%Y/%m/%d %H:%M')

    def _get_sheet_two_columns(self, fileid, sheet_index, column1, column2, remove_headers=4):
        """this will take a look in the leaderboard file for sheet 'game' and return
        all the pairs of usernames and points acheived for that particual round.

        game: the GWG tab that we want to read from the general leaderboard

        returns a dict that contains the results of the GWG challenge
        """
        log.debug("Getting sheet two columsn for %s sheet %s col1 %s col2 %s remcol %s" % (fileid, sheet_index,column1, column2, remove_headers))
        column1_data = self.get_sheet_single_column(fileid, column1, sheet=sheet_index, remove_headers=remove_headers)
        column2_data = self.get_sheet_single_column(fileid, column2, sheet=sheet_index, remove_headers=remove_headers)

        column1_data =[item.strip().lower() for item in column1_data]
        column2_data =[item.strip().lower() for item in column2_data]

        # convert to dict and remove garbage
        result = dict(zip(column1_data, column2_data))
        del result['']
        return result

    def _empty_drive_files(self):
        """returns the clean struct for drive file management."""
        return {'responses': [], 'leaderboard': None, 'other': None, 'forms': []}

    def _extract_GWG_title(self, title):
        """takes a string, extracts the number in the name and returns GMX where X is 1< X <= 82"""
        if not len(title.split()) >= 2:
            return "GM32202" 
        return "GM" + title.split()[1]

    def _get_credentials(self):
        """Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Credentials, the obtained credential.
        """
        home_dir = os.path.expanduser('~')
        credential_dir = os.path.join(home_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir,
                                       'gwg-leaderboard-helper.json')

        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
            flow.user_agent = APPLICATION_NAME
            if flags:
                credentials = tools.run_flow(flow, store, flags)
            else: # Needed only for compatibility with Python 2.6
                credentials = tools.run(flow, store)
            log.debug('Storing credentials to ' + credential_path)
        return credentials

    def _remove_values_from_list(self, the_list, val=""):
        """Goes through the_list passed and removes any items that contain val. Taken generously from SO.

        By default removes entries that contain nothing.
        https://stackoverflow.com/a/1157132
        """
        return [value for value in the_list if value != val]

    def _get_game_list(self, fileid):
        """Gets two columns from the answer table and combines them into a single list. Returns that result"""

        log.debug("Getting game list for file %s" % fileid)
        games = self._remove_values_from_list(self.get_sheet_single_column(fileid, 1, sheet=SheetKeys.ANSWERKEY_SHEET.value))
        readys = self.get_sheet_single_column(fileid, 8, sheet=SheetKeys.ANSWERKEY_SHEET.value)

        if not games or not readys:
            return None

        result = [[a, b.title()] for a, b in zip(games, readys)]

        #return everything except the title
        return result[1:] 

    def get_all_drive_file_metadatas(self):
        """Logs into google drive and lists all the file resource that are in the main wpg jets directory."""

        folder = self.secrets.get_teams_parent_folder(self.team_folder)

        try:
            param = {}
            log.debug("Getting all of the google drive files...")
            children = self.service.children().list(folderId=folder, **param).execute()
            log.debug("received list of all google drive files")

        except errors.HttpError as error:
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            return None

        return self._collect_file_metadata(children['items'])

    def _collect_file_metadata(self, files):
        """this will go through, investigate each item and print the details about it"""

        results = []
        log.debug("Collecting all file metadata...")
        for file in files:
            try:
                results.append(self.service.files().get(fileId=file['id']).execute())

            except errors.HttpError as error:
                log.error('An error occurred: %s' % error)
                log.error(traceback.print_exc())

        log.debug("Collected all file meta datas.")
        return results

    def get_all_sheet_lines(self, file_id, headers=True, sheet=0):
        """This function will read a spreadsheet, read every line and return the results

        headers is the column headers for the excel sheet we read
        sheet is the work sheet that we want to read specifically in a work book
        """

        try:
            log.debug("Reading sheet with id: %s" % file_id)
            spreadsheet = self.gc.open_by_key(file_id)
            worksheet = spreadsheet.get_worksheet(sheet)

            results = worksheet.get_all_values()
            if not headers:
                results = results[1:]

            log.debug("Done reading sheet")
            return results

        except Exception as error:
            log.error('attemped to open with key: %s' % file_id)
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            sys.exit(-1)

    def get_sheet_single_column(self, file_id, column, sheet=0, remove_headers=0):
        """returns column a from the passed spreadsheet file_id
        
            by default assume fist sheet in workbook
        """
        try:
            log.debug("Reading column %s from sheet %s with id: %s" % (column, sheet, file_id))
            spreadsheet = self.gc.open_by_key(file_id)
            worksheet = spreadsheet.get_worksheet(sheet)

            # make everything lowercase
            data = worksheet.col_values(column)[remove_headers:]
            log.debug("Done reading column")
            [row.lower() for row in data]
            return data

        except Exception as error:
            log.error('attemped to open with key: %s on sheet %s' % (file_id, sheet))
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            sys.exit(-1)

    def get_file_entries(self, file_data):
        """This function accepts a list of files that we will go through
        (not blacklisted) pull the people entries for the GWG and return a list of lists
        that contains all the entries for each response sheet we have. In a perfect world
        this parameter passed will only have 1 file in it, but this may not be the case.
        """

        log.debug("Getting file enteries for file %s" % file_data['id'])
        try:
            spreadsheet = self.gc.open_by_key(file_data['id'])
            worksheet = spreadsheet.get_worksheet(0)
            name = self._extract_GWG_title(file_data['title'])
            return {'name': name, 'data':worksheet.get_all_values(), 'id':file_data['id']}

        except Exception as error:
            log.error('attempted to open with key: %s' % file_data['id'])
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            sys.exit(-1)

        log.debug("Done getting file entry.")
        return new_data

    def get_games_result(self, game_id):
        """Check the answer_key spread sheet for a certain game, and returns the tuple for the 
        successful results or None is there isn't a matching game.
        """

        results = {'title': [], 'result': []}
        log.debug("Extracting game %s question results..." % game_id)
        try:
            spreadsheet = self.gc.open_by_key(self.drive_files['leaderboard']['id'])
            worksheet = spreadsheet.get_worksheet(1)
            lines = worksheet.get_all_values()

            # add title bar minus that last 2 elements (since those are the trigger for file running) but add points column.
            new_row = lines[0][:-2] + ["Points"]
            results['title'] = new_row

            # find matching game line
            for line in lines:
                if line[0] == game_id:
                    #add line minus last column since that is the trigger for file being run.
                    results['result'] = line[:-1]

                    log.debug("Done getting game results.")
                    return results
            log.debug("Failure finding game results.")
            return results

        except Exception as error:
            log.error('attemped to open with key: %s' % game_id)
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            return results

    def create_new_sheet(self, sheet_info):
        """Creates a new sheet with the following constraints

        file to edit = sheet_info['id']
        title of new page  = sheet_info['name'] 
        num rows   = sheet_info['rows']
        num cols   = sheet_info['cols']

        returns file create/appendage success
        """

        workbook = None
        new_worksheet = None

        log.debug("adding new sheet %s to fileid %s" % (sheet_info['name'], sheet_info['id']))
        try:
            workbook = self.gc.open_by_key(sheet_info['id'])

            new_worksheet = workbook.add_worksheet(title=sheet_info['name'], 
                                                    rows=1,
                                                    cols=1)
            for line in sheet_info['data']:
                new_worksheet.append_row(line)
            log.debug("Done creating and appending rows to file.")
            return True

        except Exception as error:
            log.error('attemped to write new sheet in binder: %s' % leader_fileid)
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            workbook.del_worksheet(new_worksheet)
            return False

    def get_all_books_sheets(self, bookid):
        """This will return all of the sheet names in the leaderboard book."""

        log.debug("Trying to get all sheets in file %s" % bookid)
        try:
            sh = self.gc.open_by_key(bookid)
            worksheets = sh.worksheets()

            results = []
            for sheet in worksheets:
                results.append(sheet.title)

            log.debug("Success reading all sheets from file")
            return results

        except Exception as error:
            log.error('Attemped to read all sheets in file: %s' % bookid)
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            return None

    def update_drive_files(self):
        """This will take a list of files, and update the global variable that manages all these files."""

        self.refresh_gdrive_credentials()

        log.debug("Updating google drive files...")

        new_drive_files = self._empty_drive_files()
        files = self.get_all_drive_file_metadatas()

        # sort the files
        for file in files:
            file_type = file['mimeType'].lower()
            if 'spreadsheet' in file_type:
                filename = file['title'].lower()
                if 'leaderboard' in filename:
                    if not new_drive_files['leaderboard']:
                        log.debug("Found leaderboard file!")
                        new_drive_files['leaderboard'] = file
                    else:
                        log.debug("Second leaderboard found but we're ignoring it.")
                elif 'response' in filename:
                    log.debug("Found a response!")
                    new_drive_files['responses'].append(file)
                else:
                    log.debug("Found a weird other file named %s" % filename)
                    new_drive_files['other'].append(file)
            if 'form' in file_type:
                log.debug("Found a regular form!")
                new_drive_files['forms'].append(file)

        self.drive_files = new_drive_files
        log.debug("Completed google drive file collection.")
        return True

    def get_leaderboard_ready_files(self):
        """Checks the answer key and checks if all the games in column I in answer
        sheet are set to "Yes".
        """
        new_leaderboard_data = []

        unwritten_files = self.get_unwritten_leaderboard_games()

        # check if the unwritten files are in the answerkey. if not, we can't count them yet
        games_solved = self.get_all_books_sheets(self.drive_files['leaderboard']['id'])

        for entry in unwritten_files:
            if entry['game'][0] in games_solved:
                new_leaderboard_data.append(entry)

        return new_leaderboard_data

    def new_leaderboard_data(self):
        """Checks the answer key and checks if all the games in column I in answer
        sheet are set to "Yes".
        """
        
        return len(self.get_leaderboard_ready_files()) != 0

    def new_response_data_available(self):
        """This function will check the leaderboard for games that say "yes" for 
        leaderboard_ready column and compare this with the whorksheets on the leadeboard page.

        If the sheet isn't there, we will run our software.

        returns true if there is a game to manage
        """

        game_list = self._get_game_list(self.drive_files['leaderboard']['id'])
        completed_sheets = self.get_all_books_sheets(self.drive_files['leaderboard']['id'])

        if not game_list or not completed_sheets:
            return False

        else:
            for game in game_list:
                if game[0] not in completed_sheets and game[1].lower() == "yes":
                    return True
            return False

    def get_drive_filetype(self, filetype):
        """attempts to return the data that we've saved history about in google drive.

        Returns none if nothing matches the filetype passed.
        """
        result = self.drive_files.get(filetype)
        if not result:
            log.error("Tried to retreive %s but it isn't a drive file type we've sorted by." % filetype)
        return result

    def get_unwritten_leaderboard_games(self):
        """This fucntion will read the data in the answer key and return game names that
        haven't been written to the global leaderboard.
        """

        unwritten_games = []
        data = self.get_all_sheet_lines(self.drive_files['leaderboard']['id'], headers=False, sheet=SheetKeys.ANSWERKEY_SHEET.value)

        if not data:
            return []

        # trim empty lines
        data = self._remove_values_from_list(data, [""] * len(data[0]))

        #ranging so we can save the cell ID to overwrite on completion.
        for i in range(len(data)):
            if (data[i][SheetKeys.READY_COLUMN.value].lower() != SheetKeys.LEADER_WRITTEN_SUCCESS.value and 
                data[i][0] != "" and 
                data[i][7].lower() == "yes"):
                unwritten_games.append({'game': data[i], 'row': i + 2})

        return unwritten_games

    def get_history_game_points(self, game):
        """this will take a look in the leaderboard file for sheet 'game' and return
        all the pairs of usernames and points acheived for that particual round.

        game: the GWG tab that we want to read from the general leaderboard

        returns a dict that contains the results of the GWG challenge
        """

        leaderid = self.drive_files['leaderboard']['id']

        # the below only works assuming the games are added/created in order to the leaderboard spreadsheet.
        # note that the ansey key is now in spot 1, so we need to +1 to this position.
        sheet_index = self._get_sheet_index(game[0]) + 1

        return self._get_sheet_two_columns(leaderid, sheet_index, 3, 9, remove_headers=4)

    def convert_rank(self, rank):
        """Takes a rank and returns the position they were in. This function is required in case the
        users old rank contains a T in it. We want to remove it and return just the old value
        """

        rank = str(rank).replace("T", "")
        return int(rank)

    def get_current_leaders(self):
        """Will retreive the current leaderboard in the leaderboard 
        google drive file and return the same pairing that "get_history_game_points"
        does.

        returns a list of usernames and their scores
        """

        leaderid = self.drive_files['leaderboard']['id']


        data = self.get_all_sheet_lines(leaderid, headers=False)

        formatted_data = {}
        for line in data:
            # skip empty lines
            if line[0] == '':
                continue

            username = line[2]
            played = line[5].split("/")[0]
            rank = self.convert_rank(line[0])
            stats = {'rank': rank, 'curr': int(line[3]), 'last': int(line[4]), 'played': played}
            formatted_data[username] = stats
        return formatted_data

    def overwrite_leaderboard(self, new_data):
        """This will take a dict of usernames and points. It will overwrite the entire first worksheet 
        and replace the contents with our data.

        Returns success or not.
        """
        special_users = {"sternsternbutfair": "Winner 16-17",
                        "troyunrau": "Winner 15-16",
                        "zombstrawberry": "Winner 14-15"}

        #TODO: currently if the sheet for leaderboards is filled, this will fail.
        #      write software to check if we have reached the end of the document and if so,
        #      start to append new rows instead of trying to overwrite them.
        try:
            spreadsheet = self.gc.open_by_key(self.drive_files['leaderboard']['id'])
            worksheet = spreadsheet.get_worksheet(0)

            row = 3
            num_games = len(spreadsheet.worksheets()) - 1
            log.debug("Overwritting leaderboard main page")
            for username in sorted(new_data, 
                                   key=lambda x:(new_data[x]['curr'],
                                                 -new_data[x]['played'],
                                                 new_data[x]['last']), 
                                   reverse=True):
                log.debug("Writting row %s/%s" % (row -2, len(new_data)))

                worksheet.update_cell(row, 1, new_data[username]['rank'])
                worksheet.update_cell(row, 2, new_data[username]['delta'])
                worksheet.update_cell(row, 3, username)
                worksheet.update_cell(row, 4, new_data[username]['curr'])
                worksheet.update_cell(row, 5, new_data[username]['last'])
                worksheet.update_cell(row, 6, str(new_data[username]['played']) + "/" + str(num_games))

                prev_winner = special_users.get(username)

                #if its a winner, restate their winningness, otherwise clear the column
                if prev_winner:
                    worksheet.update_cell(row, 7, prev_winner)
                else:
                    worksheet.update_cell(row, 7, "")
                row += 1
            log.debug("Done overwritting data")
            return True

        except Exception as error:
            log.error('attemped to open file with key: %s' % (self.drive_files['leaderboard']['id']))
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            sys.exit(-1)

    def update_answerkey_results(self, rows):
        """takes the game we just added to the eladerboard and updates the answer key so
        that we dont try to re add this to our leaderboard total again later.
        """

        leader_sheet_id = self.drive_files['leaderboard']['id']

        try:
            spreadsheet = self.gc.open_by_key(leader_sheet_id)
            worksheet = spreadsheet.get_worksheet(SheetKeys.ANSWERKEY_SHEET.value)

            for row in rows:
                log.debug("Overwritting answer key results column for game %s" % (int(row) - 1))
                worksheet.update_cell(row, SheetKeys.LEADERBOARD_ADDED_COLUMN.value, SheetKeys.LEADER_WRITTEN_SUCCESS.value)
            log.debug("Done overwritting data")
            return True

        except Exception as error:
            log.error('attemped to open with key: %s on sheet %s' % (leader_sheet_id, SheetKeys.ANSWERKEY_SHEET.value))
            log.error('An error occurred: %s' % error)
            log.error(traceback.print_exc())
            sys.exit(-1)

    def get_gameday_form(self, form_num):
        """attempts to get a form named GWG formnum. Returns None if there isn't one."""
        form_num = str(form_num)
        for form in self.drive_files['forms']:
            if form_num in form['title'].lower() and "(responses)" not in form['title'].lower():
                return form
        return None

    def update_game_start_time(self, game_id):
        """Takes a GMXX, finds the line and updates the start time to the time of puck drop for validation of game entries."""

        log.debug("Updating game time for game %s" % game_id)
        sheet_key = self.drive_files['leaderboard']['id']

        try:
            spreadsheet = self.gc.open_by_key(sheet_key)
            worksheet = spreadsheet.get_worksheet(1)
            lines = worksheet.get_all_values()

            # find matching game line
            for x in range(len(lines)):
                line = lines[x]
                if line[0] == game_id:

                    # 2018/01/01
                    if len(line[1]) != 10:
                        return True

                    #add line minus last column since that is the trigger for file being run.
                    raw_date = line[1]
                    actual_starttime = self._get_start_time(raw_date, self.team_folder)
                    worksheet.update_cell(x + 1, 2, actual_starttime)
                    return True
            log.debug("Failure finding game time to update.")
            return False

        except Exception as error:
            log.error('attemped to overwrite new game time on sheet %s game %s' % (sheet_key, game_id))
            log.error('Error occurred: %s' % error)
            log.error(traceback.print_exc())
            return False
