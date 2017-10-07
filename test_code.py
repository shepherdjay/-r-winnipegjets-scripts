import os
import json
import httplib2

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
    """Logs into google drive and lists all the file resourse that are in the main wpg jets directory."""

    folder = APPLICATION_SECRETS['main_folder']

    try:
        param = {}
        children = service.children().list(folderId=folder, **param).execute()

    except errors.HttpError, error:
        print( 'An error occurred: %s' % error)
        return None

    return collect_file_metadata(children['items'])

def collect_file_metadata(files):
    """this will go through, investigate each item and print ehe details about it"""

    results = []
    for file in files:
        try:
            results.append(service.files().get(fileId=file['id']).execute())

        except errors.HttpError, error:
            print ('An error occurred: %s' % error)

    return results

def split_drive_files(files):
    """This function will take a list of google drive meta file details and 
    figure out which files are responses, the leadeboard, and the histroy file 
    stating which files we've already added to eladerboard totals.

    returns a tuple that is the responses list, the leaderboard file, and history file.
    """

    response_list = []
    leaderboard_file = None
    history_file = None

    for file in files:
        file_type = file['mimeType']
        if 'spreadsheet' in file_type:
            if 'leaderboard' in file['title'].lower():
                leaderboard_file = file
            if 'history' in file['title'].lower():
                history_file = file
            else:
                response_list.append(file)

    return response_list, leaderboard_file, history_file

def _get_all_sheet_lines(file_id):
    """This function will read a spreadsheet, read every line and return the results"""

    try:
        spreadsheet = gc.open_by_key(file_id)
        worksheet = spreadsheet.get_worksheet(0)
        return worksheet.get_all_values()

    except errors.HttpError, error:
        print ('An error occurred: %s' % error)


def read_history_file(history_file):
    """This function will read the history files contents and return a list of the contents"""

    try:
        return _get_all_sheet_lines(history_file['id'])

    except errors.HttpError, error:
        print ('An error occurred: %s' % error)


def update_gwg_leaderboard(files):
    """This function will take a list from the files on the google app, and will
    iterate through the responses that we haven't added into our leaderboards yet.
    We will then update the history file so we don't duplication the add ons.
    """

    responses, leaderboard, history = split_drive_files(files)

    blacklisted_responses = read_history_file(history)

    print ("Current black listed responses are: %s" % blacklisted_responses)


def main():
    """Shows basic usage of the Google Drive API.

    Creates a Google Drive API service object and outputs the names and IDs
    for up to 10 files.
    """

    global gc
    global service

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())

    service = discovery.build('drive', 'v2', http=http)

    # create google cursor for accessing spread sheets
    gc = gspread.authorize(credentials)

    files = get_all_drive_files()

    update_gwg_leaderboard(files)



if __name__ == '__main__':
    load_application_secrets()
    main()