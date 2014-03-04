import mock
import unittest
import time
import datetime

from osci import constants
from osci import utils
from osci.job import Test
from osci.config import Configuration
from osci.db import DB
from osci import time_services


PAST = datetime.datetime(1980, 1, 1, 1, 2, 3)
NOW = datetime.datetime(2001, 1, 1, 1, 2, 3)

class TestDBMethods(unittest.TestCase):

    @mock.patch('osci.time_services.now')
    def test_update(self, now):
        now.return_value = NOW

        db = DB('sqlite://')
        db.create_schema()

        test = Test(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(test)
            test.created=PAST
            test.db = db

        self.assertEqual(test.state, constants.QUEUED)

        test.update(state=constants.FINISHED)

        with db.get_session() as session:
            test, = session.query(Test).all()

        self.assertEquals(NOW, test.updated)
        self.assertEquals(constants.FINISHED, test.state)
        self.assertEquals("project", test.project_name)
        self.assertEquals("change_num", test.change_num)

    @mock.patch('osci.time_services.now')
    def test_start_test_clears_time(self, now):
        now.return_value = NOW
        db = DB('sqlite://')
        db.create_schema()
        test = Test(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(test)
            test.created=PAST
            test.db = db

        test.update(state=constants.RUNNING)

        with db.get_session() as session:
            test, = session.query(Test).all()
        self.assertEquals(test.updated, NOW)
        self.assertEquals(test.state, constants.RUNNING)
        self.assertEquals(test.test_started, NOW)
        self.assertEquals(test.test_stopped, None)
        self.assertEquals("project", test.project_name)
        self.assertEquals("change_num", test.change_num)

    @mock.patch('osci.time_services.now')
    def test_stop_test_sets_stop_time(self, now):
        now.return_value = NOW
        db = DB('sqlite://')
        db.create_schema()
        test = Test(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(test)
            test.created=PAST
            test.db = db
            test.state=constants.RUNNING

        test.update(state=constants.COLLECTING)

        with db.get_session() as session:
            test, = session.query(Test).all()
        self.assertEqual(test.state, constants.COLLECTING)
        self.assertEquals(NOW, test.updated)
        self.assertEquals(constants.COLLECTING, test.state)
        self.assertEquals(NOW, test.test_stopped)
        self.assertEquals("project", test.project_name)
        self.assertEquals("change_num", test.change_num)

class TestRun(unittest.TestCase):
    @mock.patch.object(Test, 'update')
    @mock.patch.object(utils, 'getSSHObject')
    def test_runTest_deletes_existing_node(self, mock_getSSHObject, mock_update):
        test = Test(change_num="change_num", project_name="project")
        test.node_id='existing_node'

        nodepool = mock.Mock()
        nodepool.getNode.return_value = (None, None)

        test.runTest(nodepool)

        nodepool.deleteNode.assert_called_once_with('existing_node')
        mock_update.assert_called_once_with(node_id=0)
        self.assertEqual(0, mock_getSSHObject.call_count)

    @mock.patch.object(Test, 'update')
    @mock.patch.object(utils, 'getSSHObject')
    def test_runTest_deletes_bad_node(self, mock_getSSHObject, mock_update):
        test = Test(change_num="change_num", project_name="project")

        nodepool = mock.Mock()
        nodepool.getNode.return_value = ('new_node', 'ip')
        mock_getSSHObject.return_value = None

        test.runTest(nodepool)

        nodepool.deleteNode.assert_called_once_with('new_node')
        mock_update.assert_called_once_with(node_id=0)

    @mock.patch.object(time, 'sleep')
    @mock.patch.object(Test, 'update')
    @mock.patch.object(utils, 'execute_command')
    @mock.patch.object(utils, 'getSSHObject')
    def test_runTest_happy_path(self, mock_getSSHObject, mock_execute_command,
                                mock_update, mock_sleep):
        test = Test(change_num="change_num", project_name="project")

        nodepool = mock.Mock()
        nodepool.getNode.return_value = ('new_node', 'ip')
        ssh = mock.Mock()
        mock_getSSHObject.return_value = ssh

        test.runTest(nodepool)

        # The node should not be deleted(!)
        self.assertEqual(0, nodepool.deleteNode.call_count)
        # Two calls - one to set the node ID and the other to set the state to running
        update_call1 = mock.call(node_id='new_node', result='', node_ip='ip')
        update_call2 = mock.call(state=constants.RUNNING)
        mock_update.assert_has_calls([update_call1, update_call2])
        ssh.close.assert_called()

class TestRunning(unittest.TestCase):
    def test_isRunning_no_ip(self):
        test = Test(change_num="change_num", project_name="project")

        self.assertFalse(test.isRunning())

    def test_isRunning_early_wait(self):
        test = Test(change_num="change_num", project_name="project")
        test.node_ip = 'ip'
        test.updated = datetime.datetime.now()
        self.assertTrue(test.isRunning())

    @mock.patch.object(Test, 'update')
    def test_isRunning_timeout(self, mock_update):
        test = Test(change_num="change_num", project_name="project")
        test.node_ip = 'ip'
        delta = datetime.timedelta(seconds=int(Configuration().MAX_RUNNING_TIME))
        test.updated = datetime.datetime.now() - delta
        self.assertFalse(test.isRunning())
        mock_update.assert_called_with(result='Aborted: Timed out')

    @mock.patch.object(Test, 'update')
    @mock.patch.object(utils, 'execute_command')
    def test_isRunning_pid_fail(self, mock_execute_command, mock_update):
        test = Test(change_num="change_num", project_name="project")
        test.node_ip = 'ip'
        delta = datetime.timedelta(seconds=350)
        test.updated = datetime.datetime.now() - delta
        mock_execute_command.side_effect=Exception('SSH error getting PID')
        self.assertFalse(test.isRunning())

        mock_update.assert_called_with(result='Aborted: Exception checking for pid')
        self.assertEqual(1, mock_execute_command.call_count)

    @mock.patch.object(Test, 'update')
    @mock.patch.object(utils, 'execute_command')
    def test_isRunning_happy_path(self, mock_execute_command, mock_update):
        test = Test(change_num="change_num", project_name="project")
        test.node_ip = 'ip'
        delta = datetime.timedelta(seconds=350)
        test.updated = datetime.datetime.now() - delta

        mock_execute_command.return_value = False
        self.assertFalse(test.isRunning())
        self.assertEqual(0, mock_update.call_count)

        mock_execute_command.return_value = True
        self.assertTrue(test.isRunning())
        self.assertEqual(0, mock_update.call_count)
