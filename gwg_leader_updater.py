import sys
import traceback
import argparse
import logging
from time import sleep
from datetime import datetime as dt

from drive_manager import DriveManager

log = None
gdrive = None
gwg_args = None

def get_list_of_enteries(files):
    """This function accepts a list of files that we will go through
    (not blacklisted) pull the people entries for the GWG and return a list of lists
    that contains all the entries for each response sheet we have. In a perfect world
    this parameter passed will only have 1 file in it, but this may not be the case.
    """

    new_data = []
    sorted_files = sorted(files, key=lambda x: x['createdDate'])

    log.debug("Getting new GWG entries...")

    #sort files by creation date so we read oldest files first(earlier games)
    for file in sorted_files:
        new_data.append(gdrive.get_file_entries(file))

    log.debug("Done getting new GWG entires.")
    return new_data

def format_results_data(data):
    """returns a formatted string that we like for presentation of results per game."""
    return data[:2] + ["username"] + data[2:] + ["N/A"]

def get_players_points(player, answers):
    """Calculates the total points that a player may have gotten in the GWG challenge.

    returns the sum
    """
    total = 0

    # check if there is multiple values that are winners or 
    for x in range(3):
        if player[2 + x].lower() in answers[x]:
            total += 1

    return total

def get_gwg_answers(data):
    """Returns a list of possible answers for the GWG questions"""

    result = []
    for x in range(3):
         #if no ',' creates a list of len=1
        new_ans = data[2+ (x*2)].lower().split(",")

        trimmed = []
        for answer in new_ans:
            trimmed.append(answer.strip())
        result.append(trimmed)

    return result

def create_game_history(game):
    """takes the current game, makes a new worksheet in the google sheet that contains
     the previous games results and the answer key.
    """

    log.debug("Creating new history lines for previous game leaderboard.")

    leader_fileid = gdrive.get_drive_filetype('leaderboard')['id']

    if game['name'] in gdrive.get_all_books_sheets(leader_fileid):
        log.error("This game has already been written to the worksheet as a sheet")
        log.error("Assuming this is a failure recovery and continuing(?)")
        return True
    else:
        log.debug("adding sheet %s to book" % game['name'])
        new_sheet = {}
        new_sheet['id'] = leader_fileid
        new_sheet['name'] = game['name']
        new_sheet['rows'] = len(game['data'])
        new_sheet['cols'] = 5 # timestamp, username, GWG, q2, q3
        new_sheet['data'] = []

        game_result_data = gdrive.get_games_result(game['name'])

        new_sheet['data'].append(format_results_data(game_result_data['title']))
        new_sheet['data'].append(format_results_data(game_result_data['result']))

        # magic number positioning
        gwg_answers = get_gwg_answers(game_result_data['result'])
        game_time = dt.strptime(game_result_data['result'][1], "%m/%d/%Y %H:%M")

        new_sheet['data'].append("")

        #remove heading, then iterate through the whole list.
        data_line = game['data'][1:]
        num_late_entries = 0

        for data in data_line:
            player_points = get_players_points(data, gwg_answers) 
            new_data_line = ["", "", data[1], data[2], "", data[3], "", data[4], player_points]

            # check if user got their entry in on time. if not, avoid it.
            entry_time = dt.strptime(data[0], "%m/%d/%Y %H:%M:%S")
            if (entry_time <= game_time):
                new_sheet['data'].append(new_data_line)
            else:
                num_late_entries += 1
        new_sheet['data'].append(["Total entries: " + str(len(data_line))])
        new_sheet['data'].append(["Late entries: " + str(num_late_entries)])
        new_sheet['data'].append(["Total valid entries: " + str(len(data_line) - num_late_entries)])

        log.debug("Done with creating new worksheet %s data" % game['name'])

        return new_sheet

def add_user_rankings(data):
    """Takes a users points and games played, compares it to the list of everyone else and returns
    their position relative to everyone else.

    user: user we are trying to rank
    everyone: everyones data
    last_rank: last rank that was used. Are we a new rank or a tied rank?
    """
    current_rank = 1
    rankings = {}
    new_leaderdata = {}

    # goes through the list and count the people that share the common position and games played.
    for username in sorted(data, key=lambda x:(data[x]['curr'],
                                               -data[x]['played']), 
                                 reverse=True):
        key = (data[username]['curr'], data[username]['played'])

        if key not in rankings:
            rankings[key] = {'rank': current_rank, 'tie': False}
        else:
            rankings[key] = {'rank': rankings[key]['rank'] + 1, 'tie': True}
        current_rank += 1

    # apply rank to users and calculate their number of spots moved from last round
    for username, scores in data.items():
        key = (scores['curr'], scores['played'])
        delta = str(gdrive.convert_rank(scores['last_rank']) - gdrive.convert_rank(rankings[key]['rank']))
        if rankings[key]['tie']:
            new_leaderdata[username] = {'curr': scores['curr'], 
                                    'last': scores['last'], 
                                    'played': scores['played'],
                                    'rank': "T" + str(rankings[key]['rank']),
                                    'delta': delta}

        else:
            new_leaderdata[username] = {'curr': scores['curr'], 
                                    'last': scores['last'], 
                                    'played': scores['played'],
                                    'rank': rankings[key]['rank'],
                                    'delta': delta}

    return new_leaderdata

def _trim_username(username):
    """takes a username and removes the leading /u/ or u/ from it. also lowercases the username and returns the result"""

    # check for full string first
    if "/u/" in username:
        username = username.replace("/u/", "")
    # then substring format
    if "u/" in username:
        username = username.replace("u/", "")

    return username.lower().strip()

def add_new_user_points(new_answers, leaders):
    """takes the new list of entier (new_answers) and adds their total to their 
    current score and/or adds them as a new user entry if they haven'r played before

    returns a list with all the new updates.
    """
    new_leaderboard = {}
    if new_answers:
        for username, points in new_answers.items():

            username = _trim_username(username)
            curr_points = leaders.pop(username, None)
            if curr_points:
                new_leaderboard[username] = {'curr': int(points) + int(curr_points['curr']),
                                             'last': int(points), 
                                             'played': int(curr_points['played']) + 1,
                                             'last_rank': curr_points['rank']}
            else:
                new_leaderboard[username] = {'curr': int(points), 
                                            'last': 0, 
                                            'played': 1, 
                                            'last_rank': 0}

    # add remining people who didn't play in this most previous GWG challenge.
    if leaders:
        for username, points in leaders.items():
            if isinstance(points, dict):
                new_leaderboard[username] = {'curr': int(points['curr']),
                                            'last': 0, 
                                            'played': int(points['played']),
                                            'last_rank': points['rank']}
            else:
                log.error("I didnt expect this to fire but it did and here I am")
                log.error("points : %s" % points)
                new_leaderboard[username] = {'curr': int(points), 
                                            'last': 0, 
                                            'played': int(curr_points['played']),
                                            'last_rank': 0}

    new_leaderboard = add_user_rankings(new_leaderboard)

    return new_leaderboard

def update_master_list():
    """This function will check the anwser key for if we've already added a certain
    table to the master list.

    If not, adds it and updates the master list, then updates the column to say we've added to master/

    if yes, doesn't update the sheet to the leaderboard.
    """

    written_games = []
    current_leaders = gdrive.get_current_leaders()
    unwritten_games = gdrive.get_unwritten_leaderboard_games()

    for game in unwritten_games:
        newest_results = gdrive.get_history_game_points(game['game'])

        current_leaders = add_new_user_points(newest_results, current_leaders)

        # add the row in answer key that needs to be updated as "written"
        written_games.append(game['row'])

    if gdrive.overwrite_leaderboard(current_leaders):
        gdrive.update_answerkey_results(written_games)

    return True

def update_leaderboard_spreadsheet(new_games):
    """this function will read the leaderboard spreadsheet, update the latest worksheet, add
    a new worksheet for the current game, and return success signal
    """
    for game in new_games:
        gdrive.create_new_sheet(create_game_history(game))

def convert_response_filename(name):
    """convert a standardized game name string into a string our software expects.

    Eg.   GM 3 (Responses) -> GM3
         GM 62 (Responses) -> GM62
        GWG 62 (Responses) -> GM62
         GWG 3 (Responses) -> GM3
    """
    parts = name.split()
    return "GM" + parts[1]

def trim_already_managed_games():
    """this will go through the responses we have and compare them to the 
    sheets already created in the main leadeboard spreadsheet. If it already exists, 
    remove it from the list.

    returns the trimmed list.
    """
    log.debug("Trimming already managed games")
    current_sheets = gdrive.get_all_books_sheets(gdrive.get_drive_filetype('leaderboard')['id'])

    pending_games = []
    files = gdrive.get_drive_filetype('responses')
    for file in files:
        filename = convert_response_filename(file['title'])
        if filename not in current_sheets:
            pending_games.append(file)

    log.debug("Done trimming %s games for %s pending" % (len(files) - len(pending_games), len(pending_games)))
    return pending_games

def manage_gwg_leaderboard():
    """This function will take a list from the files on the google app, and will
    iterate through the responses that we haven't added into our leaderboards yet.
    """
    new_games = trim_already_managed_games()

    if not new_games or len(new_games) == 0:
        log.debug("No responses left to process. Ending.")
        return False
    else:
        latest_entrants = get_list_of_enteries(new_games)

        if not latest_entrants or len(latest_entrants) == 0:
            log.debug("No new entrants needed to be ingested")
        else:
            update_leaderboard_spreadsheet(latest_entrants)

def setup():
    """Handle arguments"""
    global gwg_args
    global log

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test', '-t' ,action='store_true', help='Run in test mode with team -1')
    group.add_argument('--prod', '-p', action='store_true', help='Run in production mode with full subscribed team list')
    parser.add_argument('--debug', '-d', action='store_true', help='debug messages turned on', default=False)

    gwg_args = parser.parse_args()

    level = logging.INFO
    if gwg_args.debug:
        level = logging.DEBUG

    logging.basicConfig(level=level, filename="gwg_leader.log", filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")
    log = logging.getLogger("gwg_poster")
    log.info("Stared gwg_poster")

def main():
    """Shows basic usage of the Google Drive API.

    Creates a Google Drive API service object and outputs the names and IDs
    for up to 10 files.
    """
    global gdrive
    setup()

    if gwg_args.test:
        gdrive = DriveManager(team="-1")
    elif gwg_args.prod:
        gdrive = DriveManager(team="52")
    else:
        log.critical("Something horrible happened because you should always have a single one of the above options on. Quitting.")
        sys.exit()

    while True:
        if gdrive.new_response_data_available():
            gdrive.update_drive_files()
            manage_gwg_leaderboard()

        if gdrive.new_leaderboard_data():
            update_master_list()
        
        sleep_time = 60*60
        log.info("No new data available for updating with. Sleeping for %s" % sleep_time)
        sleep(sleep_time)

if __name__ == '__main__':
    main()
