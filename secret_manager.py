import json
APPLICATION_SECRET_FILE = 'application_secret.json'

class SecretManager():
    """Handles the "secrets" file that contains usernames, folderIDs and subreddits."""

    secrets = None

    def __init__(self):
        with open(APPLICATION_SECRET_FILE) as json_data:
            self.secrets = json.load(json_data)

    def _get_value(self, team, obj, detail=None):
        if detail:
            return self.secrets.get(str(team)).get(obj).get(detail)
        return self.secrets.get(str(team)).get(obj)

    def get_team_contacts(self, team):
        """takes a number and returns the redditors that are associated to that folder."""
        return self._get_value(team, 'admin') 

    def get_reddit_name(self, team):
        """takes a number and returns the redditors that are associated to that folder."""
        return self._get_value(team, 'reddit')

    def get_teams_parent_folder(self, team):
        """take the teamid and return the fold that this team has all their data stored in"""
        return self._get_value(team, 'folder')

    def get_previous_winners(self, team):
        """get the previous winners details"""
        return self._get_value(team, "details", detail='winners')
