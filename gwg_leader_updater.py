import os
import sys
import json
import httplib2
import traceback

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
drive_files = {'responses': None, 'answers': None, 'leaderboard': None, 'history': None}

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
        print ("Done.")

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

    print ("Done.")
    return results

def split_drive_files(files):
    """This function will take a list of google drive meta file details and 
    figure out which files are responses, the leaderboard, and the history file 
    stating which files we've already added to leaderboard totals.

    returns a tuple that is the responses list, the leaderboard file, and history file.
    """

    response_list = []
    leaderboard_file = None
    history_file = None
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

            elif 'history' in filename:
                if not history_file:
                    print ("Found history file!")
                    history_file = file
                else:
                    print ("Found duplicate history file. Exiting due to fatal error.")
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

    print ("Done discovering files.")
    return response_list, leaderboard_file, history_file, answers

def get_all_sheet_lines(file_id):
    """This function will read a spreadsheet, read every line and return the results"""

    try:
        print ("Reading sheet with id: %s" % file_id)
        spreadsheet = gc.open_by_key(file_id)
        worksheet = spreadsheet.get_worksheet(0)
        print ("Done")
        return worksheet.get_all_values()

    except Exception as error:
        print ('attemped to open with key: %s' % file_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sys.exit(-1)

def get_sheet_single_column(file_id):
    """returns column a from the passed spreadsheet file_id"""
    try:
        print ("Reading column 1 from sheet with id: %s" % file_id)
        spreadsheet = gc.open_by_key(file_id)
        worksheet = spreadsheet.get_worksheet(0)
        print ("Done")
        return worksheet.col_values(1)

    except Exception as error:
        print ('attemped to open with key: %s' % file_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sys.exit(-1)

def remove_used_responses(history_id):
    """This function will go through the lists of responses and remove any that 
    have already been accounted for in the leaderboards as stated by the history
    file.

    returns a list of meta file data that needs to be consumed
    """

    pending_files = []

    blacklisted_responses = get_sheet_single_column(history_id)

    print ("Removing files from list that have already been consumed...")
    for file in drive_files['responses']:
        if str(file['id']) not in blacklisted_responses:
            pending_files.append(file)

    print ("Done.")
    drive_files['responses'] = pending_files
    return True

def extract_GWG_title(title):
    """takes a string, extracts the number in the name and returns GMX where X is 1< X <= 82"""
    parts = title.split(" ")
    return "GM" + parts[1]

def get_list_of_enteries():
    """This function accepts a list of files that we will go through
    (not blacklisted) pull the people entries for the GWG and return a list of lists
    that contains all the entries for each response sheet we have. In a perfect world
    this parameter passed will only have 1 file in it, but this may not be the case.
    """

    new_data = []
    sorted_files = sorted(drive_files['responses'], key=lambda x: x['createdDate'])

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
    print ("Done.")
    return new_data

def get_game_results(game_id):
    """Check the answer_key spread sheet for a certain game, and returns the tuple for the 
    successful results or None is there isn't a matching game.
    """

    results = []
    print ("Extracting game %s question results..." % game_id)
    try:
        spreadsheet = gc.open_by_key(drive_files['answers']['id'])
        worksheet = spreadsheet.get_worksheet(0)
        lines = worksheet.get_all_values()

        # add title bar minus that last element (since that is the trigger for file running)
        results.append(lines[0][:-1])

        # find matching game line
        for line in lines:
            if line[0] == game_id:
                #add line minus last column since that is the trigger for file being run.
                results.append(line[:-1])

                print ("Done getting game results.")
                return results
        print ("Failure.")
        return None

    except Exception as error:
        print ('attemped to open with key: %s' % game_id)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        return None

def add_last_game_history(leader_fileid, game):
    """takes the current game, makes a new worksheet in the google sheet that contains
     the previous games results and the answer key.
    """

    print ("Adding previous game to leaderboard.")
    try:
        sh = gc.open_by_key(leader_fileid)

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
            results = get_game_results(game['name'])

            if not results:
                print ("Exiting due to fatal error of not having results of a game for updating leaderboards.")
                sys.exit(-1)

            #append the top bar and the questions for the match
            print ("Appending rows...")
            for result in results:
                new_line = [result[0], result[1], "username"] +  result[2:]
                new_worksheet.append_row(new_line)

            new_worksheet.append_row("")

            #remove heading, then iterate through the whole list.
            data_list = game['data'][1:]
            for data_line in data_list:
                new_data_line = ["", "", data_line[1], data_line[2], "", data_line[3], "", data_line[4]]
                new_worksheet.append_row(new_data_line)

            print ("Done with new worksheet %s" % game['name'])
            return True

    except Exception as error:
        print ('attemped to write new sheet in binder: %s' % leader_fileid)
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        return False

def update_master_list(temp):
    return True

def add_fileid_history_to_history(game):
    """Open the history file and append to the end of it the current file ID that we've
    just read.
    """

    print ("Adding file %s to history file %s." % (game['id'], drive_files['history']['id']))
    try:
        spreadsheet = gc.open_by_key(drive_files['history']['id'])
        worksheet = spreadsheet.get_worksheet(0)
        worksheet.append_row(game['id'])
        print ("Done.")
        return None

    except Exception as error:
        print ('attemped to open with key: %s' % game['id'])
        print ('An error occurred: %s' % error)
        print (traceback.print_exc())
        sys.exit(-1)

def update_leaderboard_spreadsheet(new_entries):
    """this function will read the leaderboard spreadsheet, update the latest worksheet, add
    a new worksheet for the current game, and return success signal
    """

    leaderboard_id = drive_files['leaderboard']['id']

    leader_data = get_all_sheet_lines(leaderboard_id)

    for game in new_entries:
        if add_last_game_history(leaderboard_id, game):
            add_fileid_history_to_history(game)
            update_master_list(leaderboard_id)
        else:
            print ("Unable to add last games history, may have partially written data.")
            print ("Currently, manual verificatoin is required. Sorry.")
            sys.exit(-1)

def manage_gwg_leaderboard():
    """This function will take a list from the files on the google app, and will
    iterate through the responses that we haven't added into our leaderboards yet.
    We will then update the history file so we don't duplication the add ons.
    """

    remove_used_responses(drive_files['history']['id'])

    if len(drive_files['responses']) == 0:
        print ("No files left to process. Ending.")
        sys.exit()
    else:
        
        latest_entrants = get_list_of_enteries()

        if not latest_entrants or len(latest_entrants) == 0:
            print ("No new entrants needed to be ingested, exiting early.")
            sys.exit()
        else:
            update_leaderboard_spreadsheet(latest_entrants)

def new_data_available():
    """This function will check the leaderboard for games that say "yes" for 
    leaderboard_ready column and compare this will the whotsheets on the leadeboard page.

    If the sheet isn't there, we will run our software.

    returns true if there is a game to manage
    """

    return True

def update_global_file_list(files):
    """This will take a list of files, and update the global variable that manages all these files."""

    global drive_files
    #TODO: update this such that we detect if we have two leaderboard files etc etc
    drive_files = {'responses': [], 'answers': None, 'leaderboard': None, 'history': None}


    print ("Updating google drive files...")

    for file in files:
        file_type = file['mimeType']
        if 'spreadsheet' in file_type:
            filename = file['title'].lower()
            if 'leaderboard' in filename:
                if not drive_files['leaderboard']:
                    print("Found leaderboard file!")
                    drive_files['leaderboard'] = file
            elif 'history' in filename:
                if not drive_files['history']:
                    print ("Found history file!")
                    drive_files['history'] = file
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
            sleep(60*60)

if __name__ == '__main__':
    load_application_secrets()
    main()
