import mock
import unittest
import time
import datetime

from osci import constants
from osci import utils
from osci.test import Test
from osci.config import Configuration

class TestDBMethods(unittest.TestCase):
    def test_insert_queued(self):
        db = mock.Mock()
        test = Test(change_num="change_num", project_name="project")
        test.created='NOW'
        test.insert(db)
        expected = 'INSERT INTO test(project_name, change_num, change_ref,'+\
                   ' state, created, commit_id) VALUES("project","change_num",'+\
                   '"None","%s","NOW","None")'%constants.QUEUED
        db.execute.assert_called_once_with(expected)

    def test_update(self):
        db = mock.Mock()
        test = Test(change_num="change_num", project_name="project")
        test.created='NOW'
        test.db = db
        self.assertEqual(test.state, constants.QUEUED)
        test.update(state=constants.FINISHED)
        
        self.assertEqual(test.state, constants.FINISHED)
        expected = 'UPDATE test SET updated=CURRENT_TIMESTAMP, state="%s" '+\
                   'WHERE project_name="project" AND change_num="change_num"'
        db.execute.assert_called_once_with(expected%(constants.FINISHED))

    def test_start_test_clears_time(self):
        db = mock.Mock()
        test = Test(change_num="change_num", project_name="project")
        test.created='NOW'
        test.db = db
        self.assertEqual(test.state, constants.QUEUED)
        test.update(state=constants.RUNNING)
        
        self.assertEqual(test.state, constants.RUNNING)
        expected = 'UPDATE test SET updated=CURRENT_TIMESTAMP, state="%s", '+\
                   'test_started=CURRENT_TIMESTAMP, test_stopped=NULL '+\
                   'WHERE project_name="project" AND change_num="change_num"'
        db.execute.assert_called_once_with(expected%(constants.RUNNING))

    def test_stop_test_sets_stop_time(self):
        db = mock.Mock()
        test = Test(change_num="change_num", project_name="project")
        test.created='NOW'
        test.db = db
        test.state=constants.RUNNING
        self.assertEqual(test.state, constants.RUNNING)
        test.update(state=constants.COLLECTING)
        
        self.assertEqual(test.state, constants.COLLECTING)
        expected = 'UPDATE test SET updated=CURRENT_TIMESTAMP, state="%s", '+\
                   'test_stopped=CURRENT_TIMESTAMP '+\
                   'WHERE project_name="project" AND change_num="change_num"'
        db.execute.assert_called_once_with(expected%(constants.COLLECTING))

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
