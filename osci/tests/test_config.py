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

    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_config_multiple(self, mock_conf_file):
        mock_conf_file.return_value = 'POLL=10\nRUN_TESTS=False'
        self.conf.reread()
        self.assertEqual(self.conf.POLL, '10')
        self.assertEqual(self.conf.RUN_TESTS, 'False')

    @mock.patch.object(config.os, 'stat')
    @mock.patch.object(config.os.path, 'exists')
    @mock.patch.object(config.Configuration, 'reread')
    def test_check_reload(self, conf_reread, os_exists, os_stat):
        os_exists.return_value = True
        mock_stat = mock.Mock()
        mock_stat.st_mtime = 1
        os_stat.return_value = mock_stat
        self.conf._last_read = 0
        self.conf.check_reload()
        conf_reread.assert_called_once_with()
