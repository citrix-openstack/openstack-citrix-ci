import mock
import unittest
import time
import datetime
import ConfigParser
import io
from osci import config

class TestConfig(unittest.TestCase):
    def setUp(self):
        # Always start with a blank config otherwise
        # the mocked tests might pollute the happy path
        self.conf = config.Configuration()
        self.conf.reread()
        
    def test_config(self):
        self.assertEqual(self.conf.POLL, '30')

    def test_config_get(self):
        self.assertEqual(self.conf.get('POLL'), '30')

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_file(self, mock_conf_file):
        mock_conf_file.return_value = 'POLL=45'
        self.conf.reread()
        self.assertEqual(self.conf.POLL, '45')

    def test_config_get_bool(self):
        self.assertEqual(self.conf.get_bool('RUN_TESTS'), True)

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_get_bool_file(self, mock_conf_file):
        mock_conf_file.return_value = 'RUN_TESTS=False'
        self.conf.reread()
        self.assertEqual(self.conf.get_bool('RUN_TESTS'), False)

    def test_config_get_int(self):
        self.assertEqual(self.conf.get_int('POLL'), 30)

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_get_int_file(self, mock_conf_file):
        mock_conf_file.return_value = 'POLL=10'
        self.conf.reread()
        self.assertEqual(self.conf.get_int('POLL'), 10)
