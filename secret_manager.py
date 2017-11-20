import json
APPLICATION_SECRET_FILE = 'application_secret.json'

class SecretManager():
    """Handles the "secrets" file that contains usernames, folderIDs and subreddits."""

    secrets = None

    def __init__(self):
        with open(APPLICATION_SECRET_FILE) as json_data:
            self.secrets = json.load(json_data)

    def get_team_contacts(self, team):
        """takes a number and returns the redditors that are associated to that folder."""
        return self.secrets.get(team).get('admin')

    def get_reddit_name(self, team):
        """takes a number and returns the redditors that are associated to that folder."""
        return self.secrets.get(team).get('reddit')

    def get_teams_parent_folder(self, team):

        return self.secrets.get(team).get('folder')
