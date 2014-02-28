import mock
import unittest
import time
import datetime
import ConfigParser
import io
from osci import config

class TestConfig(unittest.TestCase):
    def test_config(self):
        conf = config.Configuration()
        self.assertEqual(conf.POLL, '30')

    def test_config_get(self):
        conf = config.Configuration()
        self.assertEqual(conf.get('POLL'), '30')

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_file(self, mock_conf_file):
        mock_conf_file.return_value = 'POLL=45'
        conf = config.Configuration()
        self.assertEqual(conf.POLL, '45')

    def test_config_get_bool(self):
        conf = config.Configuration()
        self.assertEqual(conf.get_bool('RUN_TESTS'), True)

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_get_bool_file(self, mock_conf_file):
        mock_conf_file.return_value = 'RUN_TESTS=False'
        conf = config.Configuration()
        self.assertEqual(conf.get_bool('RUN_TESTS'), False)
