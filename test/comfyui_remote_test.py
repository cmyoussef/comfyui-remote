# Dneg Imports
import hum


class ComfyuiRemoteTest(hum.test.TestCase):
    @classmethod
    def setUpClass(cls):
        """Do something before all the tests run, ie:

        - set the shot
        - perform a shotbuild
        - import a fixture
        """
        pass

    @classmethod
    def tearDownClass(cls):
        """Clean up after all the tests"""
        pass

    def tearDown(self):
        """Clean up after each test in this case"""
        pass

    @hum.tag("example")
    def test_something(self):
        """An example test"""
        self.assertTrue(True)
