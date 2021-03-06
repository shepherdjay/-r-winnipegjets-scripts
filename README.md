Install Instructions
=

This repo uses Submodules to bring in a modified GSpread dependency. First thing you must do after cloning is run:

~~~~bash
git submodule init
git submodule update
~~~~

Enable API access to your reddit account by following the documentation [here](http://praw.readthedocs.io/en/latest/getting_started/authentication.html#oauth).

Those instructions will ask you to register an Application with Reddit. You want to do `script application` and the callback URI is [http://localhost:8080](http://localhost:8080).

After that is complete, fill in the details below in a new file named `praw_login.py` with your creds and username/password below

```python
import praw

r = praw.Reddit(client_id=<YOUR-CLIENT-ID>,
                client_secret=<YOUR-CLIENT-SECRET>,
                user_agent=<YOUR-USER-AGENT>,
                username=<REDDIT-USERNAME>,
                password=<REDDIT-PASSWORD>)

USER_NAME = <REDDIT-USERNAME>
```

In the -r-winnipeg-jets-scripts directory run the following to pull in the pip packages:

~~~~ bash
pip install -r requirements.txt
~~~~

You'll need to set up google drive API credentials which you can do by following the instructions [here](https://developers.google.com/drive/v3/web/quickstart/python). Be sure to start from the beginning as you need to enable API calls to/from your account.

Note that you will need to change the `SCOPES` variable in the quick start to  `https://www.googleapis.com/auth/drive` to allow read and write access to the files we manage for GWG. You will also need to set your redirect URI.

Once those are all set up you'll need to configure your own copy of the application_secret.json file. You can use application_secret.json.temp as a template. It should work out of the box. Here are additional notes about the keys and values:

- "-1" represents the team id for the associated data. In our case a "test" team which will automatically be converted to the Winnipeg jets team number 52 (for more info on number standards see team id's listed [here](https://statsapi.web.nhl.com/api/v1/teams/). We use the NHL API so we adhere team ids to their internal values.
- "folder" the folder id for the google drive folder that contains all the goodies (VIPs will be shared access to the current testing folder)
- "admin" a list of users to contact if someone forgets to create a GWG form, and also notify when we successfully create the GWG form.
- "reddit" the subreddit that the team id needs to post to. Eg. "winnipegjets" for the winnipegjets reddit. I would recommend making a reddit of your own username and putting your username in this setting as I've done with my own.
- "details" currently only supports previous winners under the "winners" key. built for any extended functionality we may want


Args for gwg bot

`--prod` used for production posting to reddit. no additional data needed

`--test YYYY-MM-DD` used to test the GWG poster for day YYYY-MM-DD. You'll need to have a file in the testing directory that is named GWG X where X is the game number that the day corresponds to. We calculate what game number we are posting for by calculating our record on game day and + 1. (There may be a bug in the code using date in the past since it may contain the current record instead of the record at that point of time)

--prod will fail right now with your applications_secret.json because there isn't a mapping for team 52 in it. This is because the gwg_poster uses the var `participating_teams` as the teams to look for in `application_secret.json` which we need to refactor.


gwg_poster.py flow
===
Software will run multiple times a time. If it is game day and we haven't posted a GWG in an appropriate reddit it attempts to grab a file on google drive with name YYY XX where YYY is some string (usually GWG) and XX is game number.

If it exists, we post to the appropriate sub and ping the admin of the GWG so they are aware of the success of the posting.

If it doesn't exist, we ping the Admin of the GWG so they are notified that there isn't a GWG challenge for the bot to post.


gwg_leader_updater.py flow
==
Software continuously runs. First thing it does is collect all the files in a GWG folder. Then, checks for new answers in the leaderboard file (sheet 1, column H) that an admin has set to 'yes'. When this is manual set to 'yes' the admin is acknowledging that they have filled out the row in the answer key for the previous game and that we are ready to score the GWG.

If there is a new row for GMX (X is game number) that is not present as a tab in the leaderboard file this means we score the game. We create a new tab called GMX (from the new answer key that the admin has set) and then collect the scores, combine them with the current data on sheet 0 of leaderboard, sort, calculate the positional change, then overwrite the leaderboard.

Once the leaderboard is updated, the software writes 'yes' into sheet 1 column I to tell everyone (and itself) that we've added this rows GWG to the leaderboard and have finished successfully.

The reason this software runs continuously (currently every hour) is so that any admin can go in at any time, update the answer key and the software will automatically detect that the key is updated, and update the results. It will then try to post in a game day thread, post game thread, or off day thread that the leaderboards have been updated to notify all the game players!


drive_manager.py
==
This class has blown up and needs refactoring. Currently manages all of the google drive spread sheet and file reading. REALLY needs proper error handling as right now there is lazy retry and no proper error handle management.

There is a bug as of Nov 25 2017 such that the credentials are expiring and are unable to be refreshed properly. See issues for more details
