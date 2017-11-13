import json
import argparse
from datetime import date
from urllib.request import urlopen
from datetime import datetime

from drive_manager import DriveManager
from praw_login import r, DEFAULT_USERS, USER_NAME

gwg_args = None
gdrive = None
game_history = None
participating_teams = [52]

def _update_todays_game(team):
    """Updates todays date with and game day info."""

    global game_history

    today = date.today()
    today = str(today.year) + "-" + str(today.month) + "-" + str(today.day)

    if gwg_args.test:
        team = 52
        today = "2017-11-16"

    try:
        data = urlopen("https://statsapi.web.nhl.com/api/v1/schedule?site=en_nhlCA&expand=schedule.teams,schedule.linescore,schedule.broadcasts.all&startDate=" + today + "&endDate=" + today + "&teamId=" + str(team))
        game_history = json.load(data)['dates']
        
    except Exception as e:
        game_history = None
        print ("exception occurred in is_game_day")
        print (str(e))

def is_game_day(team):
    """Checks if the Winnipeg jets are playing today. If so, returns true."""

    _update_todays_game(team)

    return game_history != []

def _get_team_name(home=True):
    """gets the team name of the requested home/away pairing"""
    team_type = "home"
    if not home:
        team_type = "away"

    return game_history[0]['games'][0]['teams'][team_type]['team']['teamName']

def _get_game_number(team):
    """Returns what game number it is for team team."""

    win = loss = otl = 0

    if game_history[0]['games'][0]['teams']['home']['team']['id'] == team:
        win = game_history[0]['games'][0]['teams']['home']['leagueRecord']['wins']
        loss = game_history[0]['games'][0]['teams']['home']['leagueRecord']['losses']
        otl = game_history[0]['games'][0]['teams']['home']['leagueRecord']['ot']

    else:
        win = game_history[0]['games'][0]['teams']['away']['leagueRecord']['wins']
        loss = game_history[0]['games'][0]['teams']['away']['leagueRecord']['losses']
        otl = game_history[0]['games'][0]['teams']['away']['leagueRecord']['ot']

    # +1 because 'next' game.
    return str(win + loss + otl + 1)

def _get_date():
    """Returns todays date as a nice string"""

    today = date.today()
    return str(today.day) + "-" + str(today.month) + "-" + str(today.year)

def generate_post_title(team=52):
    """Creates the title of the post

    team is the team that this bot runs for

    Result is something like
    Jets @ Canucks 10/12/17 GWG Challenge #4
    """

    home = _get_team_name()
    away = _get_team_name(home=False)
    game_number = _get_game_number(team)
    game_date = _get_date()

    return away + " @ " + home + " " + game_date + " GWG Challenge #" + str(game_number)

def generate_post_contents(gwg_link):
    """create the threads body. include the form link for participation."""
    
    return  ("""[Link to current GWG challenge](%s)  \n\n

Please comment here immediately ('done' or a general comment about the challenge) following their GWG form submission to add a layer of security on your entry. If you don't comment and someone else types your user name into the form for an entry your GWG entry will be void! Avoid this by commenting so we can cross reference the form submission time with the Reddit comment time. \n\n
Every Correct answer you get gives you a point in the standings and at the end of the season the point leader will get a custom flair (Thanks KillEmAll!)!  \n\n
If at the end of the season two people are tied the win will go to whoever had the least GWG entries in total! If they both had the same amount of games played we will tie break on   \n\n
[Current Standings](https://docs.google.com/spreadsheets/d/1N_xQCv7pMJKb3yV2KYe0a2ukUV3o73Npv2b3lX2QZD8/edit?usp=sharing)  \n\n
As always, if you find any issues please PM me directly and we will sort out any/all issues.  \n\n
NOTE: LATE ENTIRES WILL NOT BE ACCEPTED ANYTIME AFTER SCHEDULED GAME START UNLESS THERE IS AN OFFICAL GAME DELAY OF SOME SORT""" % gwg_link)

def get_gwg_contact(team):
    """take a team and returns a list of people that should be contacted if there is an issues with 
    the gwg form not being ready on time.
    """

    contacts = {
        -1: DEFAULT_USERS,
        52: DEFAULT_USERS,
    }

    return contacts.get(team, DEFAULT_USERS)

def get_reddit_from_team_id(team):
    """returns a subreddit from a passed teamid"""

    teams = {
            -1.: "tehgoogler", 
            52: "winnipegjets"}

    return teams.get(team, None)

def alert_gwg_owners(team):
    """Direct messages the owners of the GWG challenge that there isn't a form available
    for todays game and that their players are angry!!!
    """

    owners = get_gwg_contact(team)
    subject = "GWG form not created yet for \\r\\" + get_reddit_from_team_id(team)
    body = "Hey you! Log in and make a form for todays GWG challenge, ya bum!"

    for owner in owners:
        r.redditor(owner).message(subject, body)
    return True

def create_new_gwg_post(team=-1):
    """Submits, creates and posts the GWG challenge post."""

    gwg_form = gdrive.get_gameday_form(_get_game_number(team))

    # message my owner and cry that we don't have a form to post
    if not gwg_form:
        alert_gwg_owners(team)
        return False

    url = gwg_form['embedLink']
    title = generate_post_title()
    contents = generate_post_contents(url)
    r.subreddit(get_reddit_from_team_id(team)).submit(title, selftext=contents)
    return True

def already_posted_gwg(team):
    """Checks if we've already posted the GWG thread in the team team sub"""
    today = date.today()

    for submission in r.redditor(USER_NAME).submissions.new():
        posted_time = datetime.fromtimestamp(submission.created_utc)
        posted_time = date(posted_time.year, posted_time.month, posted_time.day)

        if (submission.subreddit_name_prefixed.lower() == "r/" + team.lower() and 
            posted_time == today and
            "GWG" in submission.title):
            print ("We posted the GWG already! Ignore this beast!")
            return True
    return False

def main():
    global gwg_args

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test', '-t' ,action='store_true', help='Run in test mode with team -1')
    group.add_argument('--prod', '-p', action='store_true', help='Run in production mode with full subscribed team list')
    gwg_args = parser.parse_args()

    if gwg_args.test:
        gwg_poster_runner(-1)
    else:
        for team in participating_teams:
            gwg_poster_runner(team)

def gwg_poster_runner(team=-1):
    """Checks if we need to post a new thread and if so, does it."""

    if is_game_day(team) and not already_posted_gwg(get_reddit_from_team_id(team)):
        # defer gdrive polling until we know we need to poll
        init_gdrive(team=str(team))

        create_new_gwg_post(team=team)
    else:
        print ("Doing nothing since it isn't game day.")

def init_gdrive(team="-1"):
    global gdrive
    gdrive = DriveManager(team=team, silent=True)

if __name__ == '__main__':
   main()
