import sys
import traceback
import argparse
import logging
from time import sleep
from datetime import datetime as dt

from drive_manager import DriveManager
from secret_manager import SecretManager
from praw_login import r

log = None
gdrive = None
gwg_args = None
secrets = None

def get_list_of_entries(files):
    """This function accepts a list of files that we will go through
    and pull the user entries for the GWG. 

    Returns a list of lists that contains all the entries for each response sheet we have. 
    In a perfect world this parameter passed will only have 1 file in it, but this may not 
    always be the case.
    """

    new_data = []
    sorted_files = sorted(files, key=lambda x: x['createdDate'])

    log.debug("Getting new GWG entries...")

    #sort files by creation date so we read oldest files first(earlier games)
    for file in sorted_files:
        data = gdrive.get_file_entries(file)
        if data:
            new_data.append(data)
        else:
            log.error("An error occurred and we are returning None early.")
            return None

    log.debug("Done getting new GWG entires.")
    return new_data

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
    """Returns a list of possible answers for the GWG questions. This list can contain a 
    list of accepted responses since there are cases when an answer can have a tie
    """

    result = []
    for x in range(3):
         #if no ',' in list it creates a list of len=1
        new_ans = data[2+ (x*2)].lower().split(",")

        trimmed = []
        for answer in new_ans:
            trimmed.append(answer.strip())
        result.append(trimmed)
    return result

def get_game_headers(data):
    """Takes a game name, pulls and parses the new headers to include a username
    column.

    Returns the new headers
    """
    results = []

    headers = data['title']
    new_data = headers[:2] + ["username"] + headers[2:]
    results.append(new_data)

    headers = data['result']
    new_data = headers[:2] + [""] + headers[2:]
    results.append(new_data)

    return results

def create_game_history(game):
    """Takes the current game and creates a list of entries for said game.

    Returns the list of data for the passed game.
    """

    log.debug("Creating new history lines for previous game leaderboard.")

    leader_fileid = gdrive.get_drive_filetype('leaderboard')['id']

    if game['name'] in gdrive.get_all_books_sheets(leader_fileid):
        log.error("This game has already been written to the worksheet as a sheet")
        log.error("Assuming this is failure recovery and continuing(?)")
        return True
    else:
        log.debug("adding sheet %s to book" % game['name'])
        new_sheet = {}
        new_sheet['id'] = leader_fileid
        new_sheet['name'] = game['name']
        new_sheet['rows'] = len(game['data'])
        new_sheet['cols'] = 6 # timestamp, username, GWG, q2, q3, comment
        new_sheet['data'] = []
        new_sheet['late'] = []
        new_sheet['stats'] = []

        # get headers
        game_result_data = gdrive.get_games_result(game['name'])
        new_sheet['data'] += get_game_headers(game_result_data)
        
        # magic number positioning
        gwg_answers = get_gwg_answers(game_result_data['result'])
        game_time = dt.strptime(game_result_data['result'][1], "%Y/%m/%d %H:%M")
        game_time_readable = game_time.strftime('%Y/%m/%d %H:%M:%S')

        new_sheet['data'].append("")

        #remove heading, then iterate through the whole list.
        data_line = game['data'][1:]
        num_late_entries = 0
        late_user_data = {'users': [], 'game_start': game_time_readable}

        for data in data_line:
            entry_time = dt.strptime(data[0], "%d/%m/%Y %H:%M:%S")
            date_readable = entry_time.strftime('%Y/%m/%d %H:%M:%S')
            player_points = get_players_points(data, gwg_answers) 
            # legacy support for comment questions concerns (remove in 2018/19 season and just directly accept data[5])
            cqc = "" if len(data) !=6 else data[5]
            new_data_line = ["", date_readable, data[1], data[2], "", data[3], "", data[4], player_points, cqc]

            # check if user got their entry in on time. if not, avoid it.
            if (entry_time <= game_time):
                new_sheet['data'].append(new_data_line)
            else:
                num_late_entries += 1
                late_user_data['users'].append({'name': data[1], 'entry_time': date_readable})
                new_sheet['late'].append(new_data_line)

        new_sheet['stats'].append(["Total entries: " + str(len(data_line))])
        new_sheet['stats'].append(["Late entries: " + str(num_late_entries)])
        new_sheet['stats'].append(["Total valid entries: " + str(len(data_line) - num_late_entries)])
        new_sheet['messages'] = late_user_data

        log.debug("Done with creating new worksheet %s data" % game['name'])
        return new_sheet

def add_user_rankings(data):
    """Takes a users points and games played, compares it to the list of everyone else and returns
    their position relative to everyone else.
    """
    current_rank = 1
    rankings = {}
    new_leaderdata = {}
    starting_key = None

    # goes through the list and count the people that share the common position and games played.
    for username in sorted(data, key=lambda x:(data[x]['curr'],
                                               -data[x]['played']), 
                                 reverse=True):

        key = (data[username]['curr'], data[username]['played'])
        # first time running, save the "best" score
        if not starting_key:
            starting_key = key

        if key not in rankings:
            rankings[key] = {'rank': current_rank, 'tie': False}
        else:
            # can't possibly be tied for first place
            if key == starting_key:
                rankings[key] = {'rank': rankings[key]['rank'], 'tie': True}
            # tied for first place now
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

    #get rid of any whitespace inside username
    username = username.replace(" ", "")

    return username.lower().strip()

def add_new_user_points(new_answers, leaders):
    """takes the new list of entries (new_answers) and adds their total to their 
    current score and/or adds them as a new user entry if they haven't played before

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

    # add remaining people who didn't play in this most previous GWG challenge.
    if leaders:
        for username, points in leaders.items():
            if isinstance(points, dict):
                new_leaderboard[username] = {'curr': int(points['curr']),
                                            'last': 0, 
                                            'played': int(points['played']),
                                            'last_rank': points['rank']}
            else:
                log.critical("I didn't expect this to fire but it did and here we are")
                log.critical("points dump : '%s'" % points)
                log.critical("user dump : '%s'" % user)
                new_leaderboard[username] = {'curr': int(points), 
                                            'last': 0, 
                                            'played': int(curr_points['played']),
                                            'last_rank': 0}
    return add_user_rankings(new_leaderboard)

def update_master_list():
    """This function will check the answer key for if we've already added a certain
    table to the master list.

    If not, adds it and updates the master list, then updates the column to say we've added to master/

    if yes, doesn't update the sheet to the leaderboard.
    """

    written_games = []
    current_leaders = gdrive.get_current_leaders()
    unwritten_games = gdrive.get_unwritten_leaderboard_games()

    for game in unwritten_games:
        newest_results = gdrive.get_history_game_points(game['game'])

        if newest_results:
            current_leaders = add_new_user_points(newest_results, current_leaders)

            # add the row in answer key that needs to be updated as "written"
            written_games.append(game['row'])

    if gdrive.overwrite_leaderboard(current_leaders):
        gdrive.update_answerkey_results(written_games)

    return True

def alert_late_users(game, late_users):
    """Takes a list of games and users that entered their GWG entry late.
    """

    log.debug(f"Sending mail to late users: {late_users} for game {game}.")

    subject = f"You had a late GWG Entry for {game}"

    for user in late_users['users']:
        body = f"""Hi {user['name']},  

You had a late entry for a recent GWG challenge! The game's official puck drop was at {late_users['game_start']} and your entry was at {user['entry_time']}.
Make sure to get this in on time in the future!  

If you think this message was sent in error, please reply to this message with the description of issue you think there may be.

Go Jets Go!"""
        success = False
        attempts = 0
        while not success and attempts < 5:
            try:
                r.redditor(user['name']).message(subject, body)
                success = True
            except Exception as e:
                log.error("Exception trying to mail redditor %s. Waiting 30 and trying again." % user['username'])
                log.error("error: %s" % e)
                log.error(traceback.print_stack())
                attempts += 1
                sleep(30)
    log.debug("Done sending late message mails.")

def update_leaderboard_spreadsheet(new_games):
    """this function will read the leaderboard spreadsheet, update the latest worksheet, add
    a new worksheet for the current game, and return success signal
    """
    for game in new_games:
        gdrive.update_game_start_time(game['name'])
        new_game_history = create_game_history(game)

        gdrive.create_new_sheet(new_game_history)
        alert_late_users(game['name'], new_game_history['messages'])

def convert_response_filename(name):
    """convert a standardized game name string into a string our software expects.

    Eg.   GM 3 (Responses) -> GM3
         GM 62 (Responses) -> GM62
        GWG 62 (Responses) -> GM62
         GWG 3 (Responses) -> GM3
    """
    parts = name.split()
    return "GM" + parts[1]

def get_pending_game_data(game_names):
    """Goes through the pending game names and find their matching file for consumption.
    return a list of files that match the list of pending game_names we are passed
    """

    log.debug("collecting files from pending game names %s" % game_names)

    pending_games = []
    files = gdrive.get_drive_filetype('responses')
    for file in files:
        filename = convert_response_filename(file['title'])
        for game in game_names:
            if game == filename:
                pending_games.append(file)
                break

    log.debug("Done collecting pending game files for games %s" % game_names)
    return pending_games

def _get_leaderboard_update_body():
    leader_link = gdrive.get_drive_filetype('leaderboard')['alternateLink']
    return ("""GWG has been updated! Check it out [here](%s)!  

This is an automated message, please PM me if there are any issues.""" % leader_link)

def _valid_date_in_title(post_time):
    """checks if this thread was posted on game day for PGT"""

    today = dt.now()
    post = dt.fromtimestamp(post_time)

    return today.year == post.year and today.month == post.month and today.day == post.day

def notify_reddit(team):
    """Look for a PGT or a GDT or a ODT and post a comment in there saying the leaderboard is updated."""

    log.debug("attempting to notify reddit of updated leaderboard")
    for submission in r.subreddit(secrets.get_reddit_name(team)).new(limit=10):
        if any(sub in submission.title.lower() for sub in ["pgt", "odt", "gdt", "game day", "post game", "off day"]):
            log.debug("     Found a thread")
            if _valid_date_in_title(submission.created_utc):
                log.debug("        Appropriate thread creation date. Posting...")
                comment = submission.reply(_get_leaderboard_update_body())
                comment.disable_inbox_replies()
                log.debug("         done notifying reddit of updates")
                break

def manage_gwg_leaderboard(pending_games):
    """This function will take a list from the files on the google app, and will
    iterate through the responses that we haven't added into our leaderboards yet.
    """
    latest_entrants = get_list_of_entries(get_pending_game_data(pending_games))

    if not latest_entrants or len(latest_entrants) == 0:
        log.debug("No new entrants needed to be ingested")
    else:
        update_leaderboard_spreadsheet(latest_entrants)

def setup():
    """Handle arguments"""
    global gwg_args
    global log
    global secrets

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test', '-t' ,action='store_true', help='Run in test mode with team -1')
    group.add_argument('--prod', '-p', action='store_true', help='Run in production mode with full subscribed team list')
    parser.add_argument('--debug', '-d', action='store_true', help='debug messages turned on', default=False)
    parser.add_argument('--single', '-s', action='store_true', help='runs only once', default=False)

    gwg_args = parser.parse_args()

    level = logging.INFO
    if gwg_args.debug:
        level = logging.DEBUG

    logging.basicConfig(level=level, filename="gwg_leader.log", filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")
    log = logging.getLogger("gwg_poster")
    log.info("Stared gwg_poster")

    secrets = SecretManager()

def main():
    """Shows basic usage of the Google Drive API.

    Creates a Google Drive API service object and outputs the names and IDs
    for up to 10 files.
    """
    global gdrive
    setup()
    team = None

    if gwg_args.test:
        team = "-1"
        gdrive = DriveManager(secrets, team=team, update=False)
    elif gwg_args.prod:
        team = "52"
        gdrive = DriveManager(secrets, team=team, update=False)
    else:
        log.critical("Something horrible happened because you should always have a single one of the above options on. Quitting.")
        sys.exit()

    while True:
        gdrive.update_drive_files()

        pending_games = gdrive.new_response_data_available()

        if pending_games != []:
            manage_gwg_leaderboard(pending_games)

        if gdrive.new_leaderboard_data():
            update_master_list()
            notify_reddit(team)

        # quit if we are testing instead of running forever or issues --single
        if gwg_args.test or gwg_args.single:
            log.info("Exiting early due to --single --test on cli")
            sys.exit()

        sleep_time = 60*60
        log.info("No new data available for updating with. Sleeping for %s" % sleep_time)
        sleep(sleep_time)

if __name__ == '__main__':
    main()
