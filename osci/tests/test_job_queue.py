import datetime
import unittest
import logging
import mock
import Queue

from osci import config
from osci import constants
from osci import db
from osci import job_queue
from osci import job
from osci import filesystem_services
from osci import utils
from osci import swift_upload
from osci import time_services


class FakeNodePool(object):
    def __init__(self):
        self.node_ids = set()

    def deleteNode(self, node_id):
        assert node_id in self.node_ids, "node %s does not exist" % node_id
        self.node_ids.discard(node_id)

    def getHeldNodes(self):
        return self.node_ids


class QueueHelpers(object):
    def _make_queue(self):
        database = db.DB('sqlite://')
        database.create_schema()

        return job_queue.JobQueue(
            database=database,
            nodepool=FakeNodePool(),
            filesystem=filesystem_services.FakeFilesystem(),
            uploader=None,
            executor=None)


class TestInit(unittest.TestCase, QueueHelpers):
    def test_nodepool_can_be_injected(self):
        q = job_queue.JobQueue(
            database="database",
            nodepool="nodepool",
            filesystem="filesystem",
            uploader="uploader",
            executor="executor")

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)
        self.assertEquals("filesystem", q.filesystem)
        self.assertEquals("uploader", q.uploader)
        self.assertEquals("executor", q.executor)

    def test_add_test(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        test, = job.Job.getAllWhere(q.db)
        self.assertTrue(test.queued)

    def test_add_test_if_job_already_exists(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')
        with q.db.get_session() as session:
            j, = session.query(job.Job).all()
            j.node_id = 666
        q.nodepool.node_ids.add(666)

        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        j1,j2, = job.Job.getAllWhere(q.db)
        if j1.state == constants.OBSOLETE:
            old_j = j1
            new_j = j2
        else:
            old_j = j2
            new_j = j1
        self.assertTrue(new_j.queued)
        self.assertEquals(new_j.state, constants.QUEUED)
        self.assertEquals(old_j.state, constants.OBSOLETE)
        self.assertEquals(old_j.node_id, 666)

    def test_get_queued_items_non_empty(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(1, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_non_empty_disabled(self):
        q = self._make_queue()

        q.addJob('refs/changes/61/65261/7', 'project', 'commit')
        q.jobs_enabled = False
        self.assertEquals(0, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_empty(self):
        q = self._make_queue()
        self.assertEquals(0, len(q.get_queued_enabled_jobs()))

    def test_delete_thread_obsolete(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        q.addJob('refs/changes/61/65262/7', 'project', 'commit2')
        q.addJob('refs/changes/61/65263/7', 'project', 'commit3')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs[0].state = constants.OBSOLETE
            jobs[0].node_id = 0
            jobs[1].state = constants.RUNNING
            jobs[1].node_id = 1
            jobs[2].state = constants.OBSOLETE
            jobs[2].node_id = 2
        q.nodepool.node_ids.add(1)
        q.nodepool.node_ids.add(2)

        # Only node 2 should be deleted
        dnt = job_queue.DeleteNodeThread(q)
        dnt.update_finished_jobs()
        nodes = dnt.get_nodes()
        self.assertEquals(len(nodes), 1)
        self.assertIn(2, nodes)

    def test_delete_thread_clears_node(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
        q.nodepool.node_ids.add(1)

        dnt = job_queue.DeleteNodeThread(q)
        nodes = dnt.get_nodes()
        self.assertEquals(0, len(nodes))
        dnt.update_finished_jobs()
        nodes = dnt.get_nodes()
        self.assertIn(1, nodes)
        job1, = job.Job.getAllWhere(q.db)
        self.assertEquals(0, job1.node_id)

    @mock.patch('osci.job_queue.time.sleep')
    def test_delete_thread_cycle(self, mock_sleep):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
            jobs[0].result = 'Passed'
        q.nodepool.node_ids.add(1)

        dnt = job_queue.DeleteNodeThread(q)
        dnt._continue = mock.Mock()
        dnt._continue.side_effect = [True, False]
        dnt.run()
        
        job1, = job.Job.getAllWhere(q.db)
        self.assertEquals(0, job1.node_id)
        self.assertEquals(0, len(q.nodepool.node_ids))
        mock_sleep.assert_called_with(60)

    @mock.patch('osci.job_queue.time.sleep')
    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_delete_thread_keep_none(self, mock_conf_file, mock_sleep):
        mock_conf_file.return_value = 'KEEP_FAILED=0'
        config.Configuration().reread()

        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
            jobs[0].result = 'Failed'
        q.nodepool.node_ids.add(1)

        dnt = job_queue.DeleteNodeThread(q)
        dnt._continue = mock.Mock()
        dnt._continue.side_effect = [True, False]
        dnt.run()

        job1, = job.Job.getAllWhere(q.db)
        self.assertEquals(0, job1.node_id)
        self.assertEquals(0, len(q.nodepool.node_ids))
        mock_sleep.assert_called_with(60)

    @mock.patch('osci.job_queue.time.sleep')
    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_delete_thread_keeps_newest_failed(self, mock_conf_file, mock_sleep):
        mock_conf_file.return_value = 'KEEP_FAILED=1'
        config.Configuration().reread()

        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        q.addJob('refs/changes/61/65262/7', 'project', 'commit2')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs.sort(key=lambda x: x.id)
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
            jobs[0].result = 'Failed'
            jobs[0].updated = time_services.now() - datetime.timedelta(seconds=1)
            jobs[1].state = constants.FINISHED
            jobs[1].node_id = 2
            jobs[1].result = 'Failed'
            jobs[1].updated = time_services.now()
        q.nodepool.node_ids.add(1)
        q.nodepool.node_ids.add(2)

        dnt = job_queue.DeleteNodeThread(q)
        dnt._continue = mock.Mock()
        dnt._continue.side_effect = [True, False]
        dnt.run()
        
        jobs = job.Job.getAllWhere(q.db)
        jobs.sort(key=lambda x: x.id)
        self.assertEquals(0, jobs[0].node_id)
        self.assertEquals(2, jobs[1].node_id)
        self.assertEquals(1, len(q.nodepool.node_ids))
        self.assertIn(2, q.nodepool.node_ids)
        mock_sleep.assert_called_with(60)

    @mock.patch('osci.job_queue.time.sleep')
    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_delete_thread_keeps_multiple_failed(self, mock_conf_file, mock_sleep):
        mock_conf_file.return_value = 'KEEP_FAILED=2'
        config.Configuration().reread()

        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        q.addJob('refs/changes/61/65262/7', 'project', 'commit2')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs.sort(key=lambda x: x.id)
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
            jobs[0].result = 'Failed'
            jobs[0].updated = time_services.now() - datetime.timedelta(seconds=1)
            jobs[1].state = constants.FINISHED
            jobs[1].node_id = 2
            jobs[1].result = 'Failed'
            jobs[1].updated = time_services.now()
        q.nodepool.node_ids.add(1)
        q.nodepool.node_ids.add(2)

        dnt = job_queue.DeleteNodeThread(q)
        dnt._continue = mock.Mock()
        dnt._continue.side_effect = [True, False]
        dnt.run()
        
        jobs = job.Job.getAllWhere(q.db)
        jobs.sort(key=lambda x: x.id)
        self.assertEquals(1, jobs[0].node_id)
        self.assertEquals(2, jobs[1].node_id)
        self.assertEquals(2, len(q.nodepool.node_ids))
        self.assertIn(1, q.nodepool.node_ids)
        self.assertIn(2, q.nodepool.node_ids)
        mock_sleep.assert_called_with(60)

    @mock.patch('osci.job_queue.time.sleep')
    @mock.patch.object(config.Configuration, '_conf_file_contents')
    def test_delete_thread_discards_old_failed(self, mock_conf_file, mock_sleep):
        mock_conf_file.return_value = 'KEEP_FAILED=10\nKEEP_FAILED_TIMEOUT=3600'
        config.Configuration().reread()

        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        q.addJob('refs/changes/61/65262/7', 'project', 'commit2')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs.sort(key=lambda x: x.id)
            jobs[0].state = constants.FINISHED
            jobs[0].node_id = 1
            jobs[0].result = 'Failed'
            jobs[0].updated = time_services.now() - datetime.timedelta(hours=2)
            jobs[1].state = constants.FINISHED
            jobs[1].node_id = 2
            jobs[1].result = 'Failed'
            jobs[1].updated = time_services.now() - datetime.timedelta(minutes=1)
        q.nodepool.node_ids.add(1)
        q.nodepool.node_ids.add(2)

        dnt = job_queue.DeleteNodeThread(q)
        dnt._continue = mock.Mock()
        dnt._continue.side_effect = [True, False]
        dnt.run()
        
        jobs = job.Job.getAllWhere(q.db)
        jobs.sort(key=lambda x: x.id)
        self.assertEquals(0, jobs[0].node_id)
        self.assertEquals(2, jobs[1].node_id)
        self.assertEquals(1, len(q.nodepool.node_ids))
        self.assertIn(2, q.nodepool.node_ids)
        mock_sleep.assert_called_with(60)


class TestUploadResults(unittest.TestCase, QueueHelpers):
    def test_job_has_no_results(self):
        q = self._make_queue()

        t = mock.Mock(spec=job.Job)
        t.retrieveResults.return_value = False

        q.uploadResults(t)

        self.assertEquals({}, q.filesystem.contents)

    def test_job_has_results(self):
        q = self._make_queue()
        q.executor = mock.Mock(spec=utils.execute_command)
        q.executor.return_value = ("code", "fail_stdout", "fail_stderr")
        q.uploader = mock.Mock(spec=swift_upload.SwiftUploader)
        q.nodepool.node_ids = [12]

        t = job.Job()
        t.node_id = 12
        t.retrieveResults = mock.Mock()
        t.retrieveResults.return_value = "jobresult"
        t.change_num = 98
        t.change_ref = 'refs/changes/1/2/3'
        t.id = 33

        q.uploadResults(t)

        self.assertEquals(
            {}, q.filesystem.contents, msg="Filesystem not cleaned up")
        self.assertEquals(
            [12], q.nodepool.node_ids, msg="Node must still exist")
        self.assertEquals(
            constants.COLLECTED, t.state, msg="Node must be collected")
        q.uploader.upload.assert_called_once_with(
            "RANDOMPATH-98", "1/2/3/33"
        )


class FakeQueue(object):
    def __init__(self):
        self.items = []

    def put(self, stuff):
        self.items.append(stuff)

