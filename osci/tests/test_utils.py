import datetime
import errno
import json
import mock
import unittest
import time
import stat

from osci import constants
from osci import utils
from osci.config import Configuration
from osci import executor
from osci import localhost
from osci import node


class TestGerrit(unittest.TestCase):
    @mock.patch.object(utils, 'get_commit_json')
    def test_get_patchset_details(self, mock_json):
        db = mock.Mock()
        ret_json='{"project":"openstack-infra/tripleo-ci",'+\
                  '"id":"I15431d8ede45a4fde51d0e6baa9e3cdf50c03920",'+\
                  '"branch":"stable/liberty",'+\
                  '"number":"68139","patchSets":[{"number":"1",'+\
                  '"revision":"b678325a816c60ad3b0141c6cc6890c7c156f649"},'+\
                  '{"number":"2",'+\
                  '"revision":"430973f7d8499be075569624d0501e549a2208f2"}]}'
        mock_json.return_value = json.loads(ret_json)
        details = utils.get_patchset_details('68139', '2')
        self.assertEqual(details['project'], 'openstack-infra/tripleo-ci')
        self.assertEqual(details['number'], '2')
        self.assertEqual(details['revision'], '430973f7d8499be075569624d0501e549a2208f2')
        self.assertEqual(details['branch'], 'stable/liberty')

class TestCopyLogs(unittest.TestCase):
    @mock.patch('os.listdir')
    @mock.patch('os.stat')
    @mock.patch('osci.utils.getSSHObject')
    @mock.patch('osci.utils.mkdir_recursive')
    def test_upload_happy_path(self, mock_mkdir, mock_get_ssh_object, mock_os_stat, mock_os_listdir):
        mock_os_listdir.return_value = ['source_file']
        mock_stat = mock.Mock()
        mock_stat.st_mode = stat.S_IFREG
        mock_os_stat.return_value = mock_stat
        sftp = mock.Mock()
        sftp.listdir.return_value = []
        utils.copy_logs_sftp(sftp, ['source/*'], 'target', 'host', 'username', 'key', upload=True)
        sftp.put.assert_called_with('source/source_file', 'target/source_file')

    @mock.patch('os.listdir')
    @mock.patch('osci.utils.mkdir_recursive')
    def test_download_happy_path(self, mock_mkdir, mock_os_listdir):
        mock_os_listdir.return_value = []
        mock_stat = mock.Mock()
        mock_stat.st_mode = stat.S_IFREG
        sftp = mock.Mock()
        sftp.listdir.return_value = ['match1', 'nomatch']
        sftp.stat.return_value = mock_stat
        utils.copy_logs_sftp(sftp, ['source/match*'], 'target', 'host', 'username', 'key', upload=False)
        sftp.get.assert_called_with('source/match1', 'target/match1')

    @mock.patch('os.listdir')
    @mock.patch('osci.utils.mkdir_recursive')
    def test_source_dir_missing(self, mock_mkdir, mock_os_listdir):
        mock_os_listdir.side_effect = IOError(errno.ENOENT, 'No such file or directory')
        mock_stat = mock.Mock()
        mock_stat.st_mode = stat.S_IFREG
        sftp = mock.Mock()
        sftp.listdir.return_value = ['source_file']
        sftp.stat.return_value = mock_stat
        utils.copy_logs_sftp(sftp, ['source/*'], 'target', 'host', 'username', 'key', upload=True)
        self.assertEqual(0, len(sftp.put.mock_calls))
        self.assertEqual(1, len(mock_os_listdir.mock_calls))

    @mock.patch('os.listdir')
    @mock.patch('osci.utils.mkdir_recursive')
    def test_download_error_continues(self, mock_mkdir, mock_os_listdir):
        mock_os_listdir.return_value = []
        mock_stat = mock.Mock()
        mock_stat.st_mode = stat.S_IFREG
        sftp = mock.Mock()
        sftp.listdir.return_value = ['match1', 'nomatch', 'match2']
        sftp.stat.return_value = mock_stat
        sftp.get.side_effect = IOError(errno.EIO, 'Unknown failure')
        utils.copy_logs_sftp(sftp, ['source/match*'], 'target', 'host', 'username', 'key', upload=False)
        sftp.get.assert_has_calls([mock.call('source/match1', 'target/match1'),
                                   mock.call('source/match2', 'target/match2')])

    @mock.patch('os.listdir')
    @mock.patch('osci.utils.mkdir_recursive')
    def test_unknown_IOError(self, mock_mkdir, mock_os_listdir):
        mock_os_listdir.side_effect = IOError(errno.EIO, 'Unknown failure')
        mock_stat = mock.Mock()
        mock_stat.st_mode = stat.S_IFREG
        sftp = mock.Mock()
        sftp.listdir.return_value = ['source_file']
        sftp.stat.return_value = mock_stat
        self.assertRaises(IOError, utils.copy_logs_sftp, sftp, ['source/*'], 'target', 'host', 'username', 'key', upload=True)

    @mock.patch('osci.utils.getSSHObject')
    @mock.patch('osci.utils.copy_logs_sftp')
    def test_copy_logs_closes_sftp(self, mock_copy_logs_sftp, mock_get_ssh):
        mock_ssh = mock.Mock()
        mock_sftp = mock.Mock()
        mock_get_ssh.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = mock_sftp
        utils.copy_logs(None, None, None, None, None, None)
        mock_ssh.close.assert_called_with()
        mock_sftp.close.assert_called_with()

    def test_mkdir(self):
        target = mock.Mock()
        def mock_chdir(dir):
            if dir.split('/')[-1].startswith('existing'):
                return
            raise IOError()
        target.chdir.side_effect = mock_chdir
        path_elems = '/existing1/existing2/new1/new2'.split('/')
        utils.mkdir_recursive(target, '/'.join(path_elems))
        target.mkdir.assert_has_calls([mock.call('/'.join(path_elems[:-1])),
                                       mock.call('/'.join(path_elems))])


class TestCopyDom0Logs(unittest.TestCase):
    @mock.patch('osci.utils.Executor')
    def test_copying(self, executor_cls):
        xecutor = executor_cls.return_value = executor.FakeExecutor()
        expected_execution = executor.FakeExecutor()
        this_host = localhost.Localhost()
        n = node.Node({
            'node_username': 'user',
            'node_host': 'ip',
            'node_keyfile': 'key'})

        expected_execution.pipe_run(
            n.command_to_get_dom0_files_as_tgz_to_stdout(
                '/var/log/messages* /var/log/SMlog* /var/log/xensource* /opt/nodepool-scripts/*.log'),
            this_host.commands_to_extract_stdout_tgz_to('target'))

        utils.copy_dom0_logs('ip', 'user', 'key', 'target')

        self.assertEquals(
            expected_execution.executed_commands,
            xecutor.executed_commands)
