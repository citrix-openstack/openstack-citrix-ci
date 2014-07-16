import datetime
import mock
import time
import stat
import unittest

from osci import constants
from osci import utils
from osci import swift_upload
from osci.config import Configuration
from osci.db import DB
from osci import time_services


class TestUtilities(unittest.TestCase):
    def test_start_stansa(self):
        prefix = 'test_prefix'
        self.assertIn(prefix, swift_upload._html_start_stansa(prefix))

    def test_file_stansa(self):
        filename = 'test_filename'
        size = 'test_size'
        html = swift_upload._html_file_stansa(filename, size)
        self.assertIn(filename, html)
        self.assertIn(size, html)

    def test_content_encoding_none(self):
        self.assertEqual(None, swift_upload.get_content_encoding('filename.txt'))
        self.assertEqual(None, swift_upload.get_content_encoding('filename'))
        self.assertEqual(None, swift_upload.get_content_encoding('filename.log'))

    def test_content_encoding_gz(self):
        self.assertEqual('gzip', swift_upload.get_content_encoding('filename.txt.gz'))
        self.assertEqual('gzip', swift_upload.get_content_encoding('filename.gz'))
        self.assertEqual('gzip', swift_upload.get_content_encoding('filename.log.gz'))

    def test_content_type_gz(self):
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.txt.gz'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.log.gz'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.conf.gz'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.sh.gz'))
        self.assertEqual('text/html', swift_upload.get_content_type('filename.html.gz'))
        self.assertEqual(None, swift_upload.get_content_type('filename.dat.gz'))

    def test_content_type(self):
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.txt'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.log'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.conf'))
        self.assertEqual('text/plain', swift_upload.get_content_type('filename.sh'))
        self.assertEqual('text/html', swift_upload.get_content_type('filename.html'))
        self.assertEqual(None, swift_upload.get_content_type('filename.dat'))

class TestSwiftUploader(unittest.TestCase):
    def setUp(self):
        self.mock_stat_file = mock.Mock()
        self.mock_stat_file.st_mode = stat.S_IFREG
        self.mock_stat_file.st_size = 1024
        self.mock_stat_dir = mock.Mock()
        self.mock_stat_dir.st_mode = stat.S_IFDIR

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os')
    def test_upload_failed_auth(self, mock_os, mock_pyrax):
        class AuthenticationFailed(Exception):
            pass
        swift_upload.pyrax.exceptions.AuthenticationFailed = AuthenticationFailed
        swift_upload.pyrax.set_credentials.side_effect = swift_upload.pyrax.exceptions.AuthenticationFailed
        self.assertRaises(AuthenticationFailed, swift_upload.SwiftUploader().upload, 'a', 'b')

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os')
    @mock.patch('osci.swift_upload.SwiftUploader.upload_one_file')
    def test_upload_no_files(self, mock_one_file, mock_os, mock_pyrax):
        mock_os.listdir.return_value=[]
        mock_container = mock.Mock()
        mock_pyrax.cloudfiles.create_container.return_value = mock_container
        mock_container.cdn_uri = 'uri'
        result = swift_upload.SwiftUploader().upload('localdir', 'prefix')
        self.assertEqual(result, 'uri/prefix/results.html')
        # Nothing should have been uploaded
        self.assertEqual(0, mock_one_file.call_count)

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os.listdir')
    @mock.patch('osci.swift_upload.os.stat')
    @mock.patch('osci.swift_upload.SwiftUploader.upload_one_file')
    def test_upload_ordered(self, mock_one_file, mock_os_stat, mock_os_listdir, mock_pyrax):
        mock_os_listdir.return_value=['b', 'd', 'c', 'a']
        mock_os_stat.return_value = self.mock_stat_file
        mock_container = mock.Mock()
        mock_pyrax.cloudfiles.create_container.return_value = mock_container
        mock_container.cdn_uri = 'uri'
        result = swift_upload.SwiftUploader().upload('localdir', 'prefix')
        self.assertEqual(result, 'uri/prefix/results.html')
        expected_calls = [mock.call(mock_container, 'localdir/a', 'prefix/a')]
        expected_calls.append(mock.call(mock_container, 'localdir/b', 'prefix/b'))
        expected_calls.append(mock.call(mock_container, 'localdir/c', 'prefix/c'))
        expected_calls.append(mock.call(mock_container, 'localdir/d', 'prefix/d'))
        mock_one_file.assert_has_calls(expected_calls)

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os.listdir')
    @mock.patch('osci.swift_upload.os.stat')
    @mock.patch('osci.swift_upload.SwiftUploader.upload_one_file')
    def test_upload_subdir(self, mock_one_file, mock_os_stat, mock_os_listdir, mock_pyrax):
        mock_os_listdir.side_effect=[['subdir'], ['file']]
        mock_os_stat.side_effect = lambda x: self.mock_stat_dir if x[-3:] == 'dir' else self.mock_stat_file
        mock_container = mock.Mock()
        mock_pyrax.cloudfiles.create_container.return_value = mock_container
        mock_container.cdn_uri = 'uri'
        result = swift_upload.SwiftUploader().upload('localdir', 'prefix')
        self.assertEqual(result, 'uri/prefix/results.html')
        expected_calls = [mock.call(mock_container, 'localdir/subdir/file', 'prefix/subdir/file')]
        mock_one_file.assert_has_calls(expected_calls)

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os.listdir')
    @mock.patch('osci.swift_upload.os.stat')
    @mock.patch('osci.swift_upload.SwiftUploader.upload_one_file')
    def test_upload_run_tests_first(self, mock_one_file, mock_os_stat, mock_os_listdir, mock_pyrax):
        mock_os_listdir.return_value=['b', 'c', 'run_tests.log', 'a']
        mock_os_stat.return_value = self.mock_stat_file
        mock_container = mock.Mock()
        mock_pyrax.cloudfiles.create_container.return_value = mock_container
        mock_container.cdn_uri = 'uri'
        result = swift_upload.SwiftUploader().upload('localdir', 'prefix')
        self.assertEqual(result, 'uri/prefix/results.html')
        expected_calls = [mock.call(mock_container, 'localdir/run_tests.log', 'prefix/run_tests.log')]
        expected_calls.append(mock.call(mock_container, 'localdir/a', 'prefix/a'))
        expected_calls.append(mock.call(mock_container, 'localdir/b', 'prefix/b'))
        expected_calls.append(mock.call(mock_container, 'localdir/c', 'prefix/c'))
        mock_one_file.assert_has_calls(expected_calls)

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.swift_upload.os.listdir')
    @mock.patch('osci.swift_upload.os.stat')
    @mock.patch('osci.swift_upload.SwiftUploader.upload_one_file')
    def test_upload_html(self, mock_one_file, mock_os_stat, mock_os_listdir, mock_pyrax):
        mock_os_listdir.return_value=['b', 'c', 'run_tests.log', 'a.txt']
        mock_os_stat.return_value = self.mock_stat_file
        mock_container = mock.Mock()
        mock_pyrax.cloudfiles.create_container.return_value = mock_container
        mock_container.cdn_uri = 'uri'
        result = swift_upload.SwiftUploader().upload('localdir', 'prefix')

        # Rather than parse the whole HTML - just verify that we've got the filename and size
        store_call = mock_container.store_object.call_args
        store_args, _ = store_call
        self.assertEqual('prefix/results.html', store_args[0])
        self.assertIn('Test results for prefix', store_args[1])
        self.assertIn('<a href="run_tests.log">run_tests.log</a>', store_args[1])
        self.assertIn('1024', store_args[1])

    @mock.patch('osci.swift_upload.pyrax')
    def test_upload_one_happy_path(self, mock_pyrax):
        mock_pyrax.utils.get_checksum.return_value = 'calc_checksum'
        mock_container = mock.Mock()
        source = 'source.txt'
        target = 'target.txt'
        mock_obj = mock.Mock()
        mock_obj.etag = 'calc_checksum'
        mock_container.upload_file.return_value = mock_obj
        swift_upload.SwiftUploader().upload_one_file(mock_container,
                                                     source, target)
        mock_container.upload_file.assert_called_with('source.txt', 'target.txt',
                                                      etag='calc_checksum',
                                                      content_encoding=None,
                                                      content_type='text/plain')

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.config.Configuration.get_int')
    def test_upload_one_failed(self, mock_get_int, mock_pyrax):
        mock_pyrax.utils.get_checksum.return_value = 'calc_checksum'
        mock_container = mock.Mock()
        mock_get_int.return_value = 1
        source = 'source.txt'
        target = 'target.txt'
        mock_obj_ok = mock.Mock()
        mock_obj_ok.etag = 'calc_checksum'
        mock_obj_fail = mock.Mock()
        mock_obj_fail.etag = 'bad_checksum'
        mock_container.upload_file.side_effect = [mock_obj_fail, mock_obj_ok]
        swift_upload.SwiftUploader().upload_one_file(mock_container,
                                                     source, target)
        expected = mock.call('source.txt', 'target.txt', etag='calc_checksum',
                             content_encoding=None, content_type='text/plain') 
        mock_container.upload_file.assert_has_calls([expected, expected])

    @mock.patch('osci.swift_upload.pyrax')
    @mock.patch('osci.config.Configuration.get_int')
    def test_upload_fails(self, mock_get_int, mock_pyrax):
        mock_pyrax.utils.get_checksum.return_value = 'calc_checksum'
        mock_container = mock.Mock()
        mock_get_int.return_value = 0
        source = 'source.txt'
        target = 'target.txt'
        mock_obj_fail = mock.Mock()
        mock_obj_fail.etag = 'bad_checksum'
        mock_container.upload_file.return_value = mock_obj_fail
        self.assertRaises(swift_upload.UploadException,
                          swift_upload.SwiftUploader().upload_one_file,
                          mock_container, source, target)
        expected = mock.call('source.txt', 'target.txt', etag='calc_checksum',
                             content_encoding=None, content_type='text/plain') 
        mock_container.upload_file.assert_has_calls([expected])
