import sys

sys.path.insert(0, './mocks')

import unittest
from unittest.mock import patch, MagicMock
from gwg_leader_updater import GWGLeaderUpdater
import prawcore.exceptions

# import test mocks
from mock_drive_manager import MockDriveManager
from mock_secret_manager import MockSecretManager


class TestGWGLeaderUpdater(unittest.TestCase):

    # setup and teardown methods
    # these get ran before EVERY test method below
    def setUp(self):
        print("setup method called")
        gwg_args = lambda: None
        gwg_args.test = True
        gwg_args.debug = False
        gwg_args.single = False
        gwg_args.prod = False

        self.gwg_leader_updater = GWGLeaderUpdater(MockDriveManager(), MockSecretManager(), gwg_args)

    def tearDown(self):
        test = "teardown"

    # test cases
    def test_sample(self):
        print("in test")
        self.assertEqual("foo", "foo")

    @patch('gwg_leader_updater.r')
    def test_alert_late_user_happy_path(self, mock_reddit: MagicMock):
        # GIVEN: A Valid late user
        game = 'Testing Game'
        late_users = {
            'game_start': '18:00 CT',
            'users': [
                {'name': 'standard_reddit_user',
                 'entry_time': '18:01 CT'}]}

        # WHEN: Sending user mail
        self.gwg_leader_updater.alert_late_users(game=game, late_users=late_users)

        # THEN: Mail should successfully send on first try
        mock_reddit.redditor.assert_called_once_with('standard_reddit_user')
        self.assertEqual(1, mock_reddit.redditor.return_value.message.call_count)

    @patch('gwg_leader_updater.sleep', return_value=None)
    @patch('gwg_leader_updater.r')
    def test_alert_late_user_invalid_username(self, mock_reddit: MagicMock, patched_sleep):
        # GIVEN: A Invalid late user
        game = 'Testing Game'
        late_users = {
            'game_start': '18:00 CT',
            'users': [
                {'name': 'fake reddit user',
                 'entry_time': '18:01 CT'}]}
        mock_reddit.redditor.return_value.message.return_value = prawcore.exceptions.NotFound

        # WHEN: Sending user mail
        self.gwg_leader_updater.alert_late_users(game=game, late_users=late_users)

        # THEN: Mail should attempt send once
        self.assertEqual(1, mock_reddit.redditor.call_count)
        self.assertEqual(1, mock_reddit.redditor.return_value.message.call_count)

    @patch('gwg_leader_updater.sleep', return_value=None)
    @patch('gwg_leader_updater.r')
    def test_alert_late_user_valid_username_delay(self, mock_reddit: MagicMock, patched_sleep):
        # GIVEN: A Valid late user and some network issues
        game = 'Testing Game'
        late_users = {
            'game_start': '18:00 CT',
            'users': [
                {'name': 'standard_reddit_user',
                 'entry_time': '18:01 CT'}]}
        mock_reddit.redditor.return_value.message.side_effect = [Exception, None]

        # WHEN: Sending user mail
        self.gwg_leader_updater.alert_late_users(game=game, late_users=late_users)

        # THEN: Mail should successfully send on second try
        self.assertEqual(2, mock_reddit.redditor.call_count)
        self.assertEqual(2, mock_reddit.redditor.return_value.message.call_count)


if __name__ == '__main__':
    unittest.main()
