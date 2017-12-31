import sys
sys.path.insert(0, './mocks')

import unittest
from gwg_leader_updater import GWGLeaderUpdater

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
        self.assertEqual("foo","foo")

if __name__ == '__main__':
    unittest.main()
