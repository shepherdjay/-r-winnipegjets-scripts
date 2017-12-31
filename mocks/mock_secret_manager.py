"""Module containing the definition of a mocked out Secrets dependency. This is for test use only """

class MockSecretManager():
    """Mocked out version of SecretManager for test purposes"""

    def __init__(self):
        self.none = None

    def get_team_contacts(self, team):
       self.none = None

    def get_reddit_name(self, team):
        self.none = None

    def get_teams_parent_folder(self, team):
       self.none = None

    def get_previous_winners(self, team):
        self.none = None