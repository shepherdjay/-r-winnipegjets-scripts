import os
import sys
import json
import httplib2
import traceback
from datetime import datetime as dt
from time import sleep

sys.path.insert(0, "K:\Documents\GitHub\gspread")
import gspread

from apiclient import discovery, errors
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/drive-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/drive'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_SECRET_FILE = 'application_secret.json'
APPLICATION_NAME = 'GWG Leaderboard Updater'
APPLICATION_SECRETS = None

gc = None
service = None
drive_files = {'responses': None, 'answers': None, 'leaderboard': None}

def load_application_secrets():
    """Loads the application secrets that aren't oauth related"""

    global APPLICATION_SECRETS

    with open(APPLICATION_SECRET_FILE) as json_data:
        APPLICATION_SECRETS = json.load(json_data)

def get_credentials():
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
        print('Storing credentials to ' + credential_path)
    return credentials

def get_all_drive_files():
    """Logs into google drive and lists all the file resource that are in the main wpg jets directory."""

    folder = APPLICATION_SECRETS['main_folder']

    try:
        param = {}
        print ("Getting all of the google drive files...")
        children = service.children().list(folderId=folder, **param).execute()
        print ("Got list of all google drive files")

    except errors.HttpError, error:
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        return None

    return collect_file_metadata(children['items'])

def collect_file_metadata(files):
    """this will go through, investigate each item and print the details about it"""

    results = []
    print ("Collecting all file metadata...")
    for file in files:
        try:
            results.append(service.files().get(fileId=file['id']).execute())

        except errors.HttpError, error:
            print ('An error occurred: %s' % error)
            print (traceback.print_exc())

    print ("Collected all file meta datas.")
    return results

def split_drive_files(files):
    """This function will take a list of google drive meta file details and 
    figure out which files are responses and the leaderboard
    stating which files we've already added to leaderboard totals.

    returns a tuple that is the responses list, the leaderboard file
    """

    response_list = []
    leaderboard_file = None
    answers = None

    print ("Discovering specific files...")
    for file in files:
        file_type = file['mimeType']
        if 'spreadsheet' in file_type:
            filename = file['title'].lower()
            if 'leaderboard' in filename:
                if not leaderboard_file:
                    print("Found leaderboard file!")
                    leaderboard_file = file
                else:
                    print ("Found duplicate leaderboard file. Exiting due to fatal error.")
                    sys.exit(-1)
            elif 'answer' in filename:
                if not answers:
                    answers = file
                    print ("Found answer key!")
                else:
                    print ("Found duplicate answer key. Exiting due to fatal error.")
                    sys.exit(-1)
            else:
                print ("Found a response!")
                response_list.append(file)

    print ("Discovered all files.")
    return response_list, leaderboard_file, answers

def get_all_sheet_lines(file_id):
    """This function will read a spreadsheet, read every line and return the results"""

    try:
        print ("Reading sheet with id: %s" % file_id)
        spreadsheet = gc.open_by_key(file_id)
        worksheet = spreadsheet.get_worksheet(0)
        print ("Done reading sheet")
        return worksheet.get_all_values()

    except Exception as error:
        print ('attemped to open with key: %s' % file_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sys.exit(-1)

def get_sheet_single_column(file_id, column):
    """returns column a from the passed spreadsheet file_id"""
    try:
        print ("Reading column %s from sheet with id: %s" % (column, file_id))
        spreadsheet = gc.open_by_key(file_id)
        worksheet = spreadsheet.get_worksheet(0)
        print ("Done reading column")
        return worksheet.col_values(column)

    except Exception as error:
        print ('attemped to open with key: %s' % file_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sys.exit(-1)

def extract_GWG_title(title):
    """takes a string, extracts the number in the name and returns GMX where X is 1< X <= 82"""
    parts = title.split(" ")
    return "GM" + parts[1]

def get_list_of_enteries(files):
    """This function accepts a list of files that we will go through
    (not blacklisted) pull the people entries for the GWG and return a list of lists
    that contains all the entries for each response sheet we have. In a perfect world
    this parameter passed will only have 1 file in it, but this may not be the case.
    """

    new_data = []
    sorted_files = sorted(files, key=lambda x: x['createdDate'])

    print ("Getting new GWG entries...")

    #sort files by creation date so we read oldest files first(earlier games)
    for file in sorted_files:
        try:
            spreadsheet = gc.open_by_key(file['id'])
            worksheet = spreadsheet.get_worksheet(0)
            name = extract_GWG_title(file['title'])
            new_data.append({'name': name, 'data':worksheet.get_all_values(), 'id':file['id']})
            print ("Found a new result package.")

        except Exception as error:
            print ('attempted to open with key: %s' % file_id)
            print ('An error occurred: %s' % error)
            print (traceback.print_exc())
            sys.exit(-1)
    print ("Done getting new GWG entires.")
    return new_data

def get_game_results(game_id):
    """Check the answer_key spread sheet for a certain game, and returns the tuple for the 
    successful results or None is there isn't a matching game.
    """

    results = {'title': [], 'result': []}
    print ("Extracting game %s question results..." % game_id)
    try:
        spreadsheet = gc.open_by_key(drive_files['answers']['id'])
        worksheet = spreadsheet.get_worksheet(0)
        lines = worksheet.get_all_values()

        # add title bar minus that last element (since that is the trigger for file running) but add points column.
        new_row = lines[0][:-1] + ["Points"]
        results['title'] = new_row

        # find matching game line
        for line in lines:
            if line[0] == game_id:
                #add line minus last column since that is the trigger for file being run.
                results['result'] = line[:-1]

                print ("Done getting game results.")
                return results
        print ("Failure.")
        return results

    except Exception as error:
        print ('attemped to open with key: %s' % game_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        return results

def format_results_data(data):
    """returns a formatted string that we like for presentation of results per game."""
    return data[:2] + ["username"] + data[2:] + ["N/A"]

def get_players_points(player, answers):
    """Calculates the total points that a player may have gotten in the GWG challenge.

    returns the sum
    """
    total = 0

    if (answers[0].lower() == player[2].lower()):
        total += 1
    if (answers[1].lower() == player[3].lower()):
        total += 1
    if (answers[2].lower() == player[4].lower()):
        total +=1

    return total

def add_last_game_history(leader_fileid, game):
    """takes the current game, makes a new worksheet in the google sheet that contains
     the previous games results and the answer key.
    """

    gwg_answers = []
    sh = None
    new_worksheet = None

    print ("Adding previous game to leaderboard.")
    try:
        sh = gc.open_by_key(leader_fileid)

        # technically could call the function we made, but might as well not
        #    since we handle sh more in this function later on.
        worksheet_list = sh.worksheets()

        if game['name'] in worksheet_list:
            print ("this game has already been written to the binder as a worksheet")
            print ("Assuming this is a failure recovery and continuing.")
            return True
        else:
            print ("adding worksheet %s to workbook" % game['name'])

            rows = len(game['data'])
            cols = 5 # timestamp, username, GWG, q2, q3
            new_worksheet = sh.add_worksheet(title=game['name'], rows=1, cols=1)
            game_result_data = get_game_results(game['name'])

            if not game_result_data['result']:
                sh.del_worksheet(new_worksheet)
                print ("Results of %s are not in yet, exiting without doing anything." % game['name'])
                return False

            #append the top bar and the questions for the match
            print ("Appending rows...")

            new_worksheet.append_row(format_results_data(game_result_data['title']))
            new_worksheet.append_row(format_results_data(game_result_data['result']))

            # magic number positioning
            gwg_answers = [game_result_data['result'][2], game_result_data['result'][4], game_result_data['result'][6]]
            game_time = dt.strptime(game_result_data['result'][1], "%m/%d/%Y %H:%M")

            new_worksheet.append_row("")

            #remove heading, then iterate through the whole list.
            data_line = game['data'][1:]
            num_late_entries = 0
            for data in data_line:
                player_points = get_players_points(data, gwg_answers) 
                new_data_line = ["", "", data[1], data[2], "", data[3], "", data[4], player_points]

                # check if user got their entry in on time. if not, avoid it.
                entry_time = dt.strptime(data[0], "%m/%d/%Y %H:%M:%S")
                if (entry_time <= game_time):
                    new_worksheet.append_row(new_data_line)
                else:
                    num_late_entries += 1
            new_worksheet.append_row(["Total entries: " + str(len(data_line))])
            new_worksheet.append_row(["Late entries: " + str(num_late_entries)])
            new_worksheet.append_row(["Total valid entries: " + str(len(data_line) - num_late_entries)])

            print ("Done with new worksheet %s" % game['name'])
            return True

    except Exception as error:
        print ('attemped to write new sheet in binder: %s' % leader_fileid)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sh.del_worksheet(new_worksheet)
        return False

def update_master_list(temp):
    return True

def update_leaderboard_spreadsheet(new_entries):
    """this function will read the leaderboard spreadsheet, update the latest worksheet, add
    a new worksheet for the current game, and return success signal
    """

    leaderboard_id = drive_files['leaderboard']['id']

    leader_data = get_all_sheet_lines(leaderboard_id)

    for game in new_entries:
        if add_last_game_history(leaderboard_id, game):
            update_master_list(leaderboard_id)
        else:
            print ("Unable to add last games history, may have partially written data.")

def convert_response_filename(name):
    """convert a standardized game name string into a string our software expects.

    Eg. GM 3 (Responses) -> GM3
        GM 62 (Respsonses) -> GM62
    """

    parts = name.split(" ")
    return "GM" + parts[1]

def trim_already_managed_games():
    """this will go through the responses we have and compare them to the 
    sheets already created in the main leadeboard spreadsheet. If it already exists, 
    remove it from the list.

    returns the trimmed list.
    """
    print ("Trimming already managed games")
    current_sheets = get_all_sheets_titles(drive_files['leaderboard']['id'])

    pending_games = []
    for file in drive_files['responses']:
        filename = convert_response_filename(file['title'])
        if filename not in current_sheets:
            pending_games.append(file)

    print ("Done trimming %s games for %s pending" % (len(drive_files['responses']) - len(pending_games), len(pending_games)))
    return pending_games

def manage_gwg_leaderboard():
    """This function will take a list from the files on the google app, and will
    iterate through the responses that we haven't added into our leaderboards yet.
    """

    new_games = trim_already_managed_games()

    if not new_games or len(new_games) == 0:
        print ("No responses left to process. Ending.")
        sys.exit()
    else:
        latest_entrants = get_list_of_enteries(new_games)

        if not latest_entrants or len(latest_entrants) == 0:
            print ("No new entrants needed to be ingested, exiting early.")
            sys.exit()
        else:
            update_leaderboard_spreadsheet(latest_entrants)

def remove_values_from_list(the_list, val):
    """https://stackoverflow.com/a/1157132"""
    return [value for value in the_list if value != val]

def get_game_list(fileid):
    """Gets two columns from the anwser table and combines them into a single list. Returns that result"""

    games = remove_values_from_list(get_sheet_single_column(fileid, 1), "")
    readys = get_sheet_single_column(fileid, 8)

    if not games or not readys:
        return None

    result = [[a, b.title()] for a, b in zip(games, readys)]

    #return everything except the title
    return result[1:]  

def get_all_sheets_titles(fileid):
    """This will return all of the sheet names in the leaderboard book."""

    print ("Trying to get all sheets in file %s" % fileid)
    try:
        sh = gc.open_by_key(fileid)
        worksheets = sh.worksheets()

        results = []
        for sheet in worksheets:
            results.append(sheet.title)

        print "Success reading all sheets from file"
        return results

    except Exception as error:
        print ('Attemped to read all sheets in file: %s' % fileid)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        return None

def new_data_available():
    """This function will check the leaderboard for games that say "yes" for 
    leaderboard_ready column and compare this will the whotsheets on the leadeboard page.

    If the sheet isn't there, we will run our software.

    returns true if there is a game to manage
    """

    game_list = get_game_list(drive_files['answers']['id'])
    completed_sheets = get_all_sheets_titles(drive_files['leaderboard']['id'])

    if not game_list or not completed_sheets:
        return False

    else:
        for game in game_list:
            if game[0] not in completed_sheets and game[1].lower() == "yes":
                return True
        return False

def update_global_file_list(files):
    """This will take a list of files, and update the global variable that manages all these files."""

    global drive_files
    #TODO: update this such that we detect if we have two leaderboard files etc etc
    drive_files = {'responses': [], 'answers': None, 'leaderboard': None}

    print ("Updating google drive files...")

    for file in files:
        file_type = file['mimeType']
        if 'spreadsheet' in file_type:
            filename = file['title'].lower()
            if 'leaderboard' in filename:
                if not drive_files['leaderboard']:
                    print("Found leaderboard file!")
                    drive_files['leaderboard'] = file
            elif 'answer' in filename:
                if not drive_files['answers']:
                    drive_files['answers'] = file
                    print ("Found answer key!")
            else:
                print ("Found a response!")
                drive_files['responses'].append(file)

    print ("Done updating google drive files files.")
    return True


def main():
    """Shows basic usage of the Google Drive API.

    Creates a Google Drive API service object and outputs the names and IDs
    for up to 10 files.
    """

    global gc
    global service

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())

    # create google cursor for accessing spread sheets
    gc = gspread.authorize(credentials)

    # google drive api manager thing
    service = discovery.build('drive', 'v2', http=http)

    while True:

        #refresh the files every iteration to have new files if they are added.
        drive_files = get_all_drive_files()
        update_global_file_list(drive_files)

        if new_data_available():
            manage_gwg_leaderboard()
            sys.exit()
        else:
            sys.exit()
            sleep(60*60)

if __name__ == '__main__':
    load_application_secrets()
    main()
