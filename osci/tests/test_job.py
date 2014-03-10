import mock
import unittest
import time
import datetime

from osci import constants
from osci import utils
from osci.job import Job
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

        job = Job(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(job)
            job.created=PAST
            job.db = db

        self.assertEqual(job.state, constants.QUEUED)

        job.update(db, state=constants.FINISHED)

        with db.get_session() as session:
            job, = session.query(Job).all()

        self.assertEquals(NOW, job.updated)
        self.assertEquals(constants.FINISHED, job.state)
        self.assertEquals("project", job.project_name)
        self.assertEquals("change_num", job.change_num)

    @mock.patch('osci.time_services.now')
    def test_start_test_clears_time(self, now):
        now.return_value = NOW
        db = DB('sqlite://')
        db.create_schema()
        job = Job(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(job)
            job.created=PAST
            job.db = db

        job.update(db, state=constants.RUNNING)

        with db.get_session() as session:
            job, = session.query(Job).all()
        self.assertEquals(job.updated, NOW)
        self.assertEquals(job.state, constants.RUNNING)
        self.assertEquals(job.test_started, NOW)
        self.assertEquals(job.test_stopped, None)
        self.assertEquals("project", job.project_name)
        self.assertEquals("change_num", job.change_num)

    @mock.patch('osci.time_services.now')
    def test_stop_test_sets_stop_time(self, now):
        now.return_value = NOW
        db = DB('sqlite://')
        db.create_schema()
        job = Job(change_num="change_num", project_name="project")
        with db.get_session() as session:
            session.add(job)
            job.created=PAST
            job.db = db
            job.state=constants.RUNNING

        job.update(db, state=constants.COLLECTING)

        with db.get_session() as session:
            job, = session.query(Job).all()
        self.assertEqual(job.state, constants.COLLECTING)
        self.assertEquals(NOW, job.updated)
        self.assertEquals(constants.COLLECTING, job.state)
        self.assertEquals(NOW, job.test_stopped)
        self.assertEquals("project", job.project_name)
        self.assertEquals("change_num", job.change_num)

class TestRun(unittest.TestCase):
    @mock.patch.object(Job, 'update')
    @mock.patch.object(utils, 'getSSHObject')
    def test_runTest_deletes_existing_node(self, mock_getSSHObject, mock_update):
        job = Job(change_num="change_num", project_name="project")
        job.node_id='existing_node'

        nodepool = mock.Mock()
        nodepool.getNode.return_value = (None, None)

        job.runJob("DB", nodepool)

        nodepool.deleteNode.assert_called_once_with('existing_node')
        mock_update.assert_called_once_with("DB", node_id=0)
        self.assertEqual(0, mock_getSSHObject.call_count)

    @mock.patch.object(Job, 'update')
    @mock.patch.object(utils, 'getSSHObject')
    def test_runTest_deletes_bad_node(self, mock_getSSHObject, mock_update):
        job = Job(change_num="change_num", project_name="project")

        nodepool = mock.Mock()
        nodepool.getNode.return_value = ('new_node', 'ip')
        mock_getSSHObject.return_value = None

        job.runJob("DB", nodepool)

        nodepool.deleteNode.assert_called_once_with('new_node')
        mock_update.assert_called_once_with("DB", node_id=0)

    @mock.patch.object(time, 'sleep')
    @mock.patch.object(Job, 'update')
    @mock.patch.object(utils, 'execute_command')
    def test_runTest_happy_path(self, mock_execute_command,
                                mock_update, mock_sleep):
        job = Job(change_num="change_num", project_name="project")

        nodepool = mock.Mock()
        nodepool.getNode.return_value = ('new_node', 'ip')
        ssh = mock.Mock()

        job.runJob("DB", nodepool)

        # The node should not be deleted(!)
        self.assertEqual(0, nodepool.deleteNode.call_count)
        # Two calls - one to set the node ID and the other to set the state to running
        update_call1 = mock.call("DB", node_id='new_node', result='', node_ip='ip')
        update_call2 = mock.call("DB", state=constants.RUNNING)
        mock_update.assert_has_calls([update_call1, update_call2])

class TestRunning(unittest.TestCase):
    def test_isRunning_no_ip(self):
        job = Job(change_num="change_num", project_name="project")

        self.assertFalse(job.isRunning("DB"))

    def test_isRunning_early_wait(self):
        job = Job(change_num="change_num", project_name="project")
        job.node_ip = 'ip'
        job.updated = datetime.datetime.now()
        self.assertTrue(job.isRunning("DB"))

    @mock.patch.object(Job, 'update')
    def test_isRunning_timeout(self, mock_update):
        job = Job(change_num="change_num", project_name="project")
        job.node_ip = 'ip'
        delta = datetime.timedelta(seconds=int(Configuration().MAX_RUNNING_TIME))
        job.updated = datetime.datetime.now() - delta
        self.assertFalse(job.isRunning("DB"))
        mock_update.assert_called_with("DB", result='Aborted: Timed out')

    @mock.patch.object(Job, 'update')
    @mock.patch.object(utils, 'execute_command')
    def test_isRunning_pid_fail(self, mock_execute_command, mock_update):
        job = Job(change_num="change_num", project_name="project")
        job.node_ip = 'ip'
        delta = datetime.timedelta(seconds=350)
        job.updated = datetime.datetime.now() - delta
        mock_execute_command.side_effect=Exception('SSH error getting PID')
        self.assertFalse(job.isRunning("DB"))

        mock_update.assert_called_with("DB", result='Aborted: Exception checking for pid')
        self.assertEqual(1, mock_execute_command.call_count)

    @mock.patch.object(Job, 'update')
    @mock.patch.object(utils, 'execute_command')
    def test_isRunning_happy_path(self, mock_execute_command, mock_update):
        job = Job(change_num="change_num", project_name="project")
        job.node_ip = 'ip'
        delta = datetime.timedelta(seconds=350)
        job.updated = datetime.datetime.now() - delta

        mock_execute_command.return_value = False
        self.assertFalse(job.isRunning("DB"))
        self.assertEqual(0, mock_update.call_count)

        mock_execute_command.return_value = True
        self.assertTrue(job.isRunning("DB"))
        self.assertEqual(0, mock_update.call_count)


class TestRetrieveResults(unittest.TestCase):
    def setUp(self):
        self.job = Job()

    def run_retrieve_results(self):
        return self.job.retrieveResults('ignored')

    def test_no_ip(self):
        self.job.node_ip = None

        result = self.run_retrieve_results()

        self.assertEquals(constants.NO_IP, result)

    @mock.patch('osci.job.utils')
    def test_status_can_be_retrieved(self, fake_utils):
        self.job.node_ip = 'ip'
        fake_utils.execute_command.return_value = (
            0, 'Reported status\nAnd some\nRubbish', 'err')

        result = self.run_retrieve_results()

        self.assertEquals('Reported status', result)

    @mock.patch('osci.job.utils')
    def test_logs_copied(self, fake_utils):
        self.job.node_ip = 'ip'
        fake_utils.execute_command.return_value = (
            0, 'Reported status\nAnd some\nRubbish', 'err')

        result = self.run_retrieve_results()

        fake_utils.execute_command.assert_called_once_with(
            'ssh -q -o BatchMode=yes'
            ' -o UserKnownHostsFile=/dev/null'
            ' -o StrictHostKeyChecking=no'
            ' -i /usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool'
            ' jenkins@ip cat result.txt',
            silent=True, return_streams=True)

    @mock.patch('osci.job.utils')
    def test_dom0_logs_copied(self, fake_utils):
        self.job.node_ip = 'ip'
        fake_utils.execute_command.return_value = (
            0, 'Reported status\nAnd some\nRubbish', 'err')

        result = self.run_retrieve_results()

        fake_utils.copy_dom0_logs.assert_called_once_with(
            'ip',
            'jenkins',
            '/usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool',
            'ignored'
        )

    @mock.patch('osci.job.utils')
    def test_dom0_log_copy_fails(self, fake_utils):
        self.job.node_ip = 'ip'
        fake_utils.execute_command.return_value = (
            0, 'Reported status\nAnd some\nRubbish', 'err')

        fake_utils.copy_dom0_logs.side_effect = Exception()

        result = self.run_retrieve_results()

        self.assertEquals(constants.COPYFAIL, result)

    @mock.patch('osci.job.utils')
    def test_status_cannot_be_retrieved_old_status_used(self, fake_utils):
        self.job.node_ip = 'ip'
        self.job.result = 'Aborted: previous result'

        fake_utils.execute_command.return_value = (
            1, 'Reported status\nAnd some\nRubbish', 'err')

        result = self.run_retrieve_results()

        self.assertEquals('Aborted: previous result', result)

    @mock.patch('osci.job.utils')
    def test_status_cannot_be_retrieved_old_status_not_used(self, fake_utils):
        self.job.node_ip = 'ip'
        self.job.result = 'previous result'

        fake_utils.execute_command.return_value = (
            1, 'Reported status\nAnd some\nRubbish', 'err')

        result = self.run_retrieve_results()

        self.assertEquals(constants.NORESULT, result)

    @mock.patch('osci.job.utils')
    def test_exception_raised(self, fake_utils):
        self.job.node_ip = 'ip'

        fake_utils.execute_command.side_effect = Exception()

        result = self.run_retrieve_results()

        self.assertEquals(constants.COPYFAIL, result)
