import os
import logging
import paramiko
import threading
import Queue

from osci.db import DB
from osci.config import Configuration
from osci.job import Job
from osci import constants
from osci.utils import execute_command, copy_logs, vote
from osci import filesystem_services


class CollectResultsThread(threading.Thread):
    log = logging.getLogger('citrix.CollectResultsThread')

    collectJobs = Queue.Queue()

    def __init__(self, jobQueue):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.daemon = True
        self.jobQueue = jobQueue
        collectingJobs = Job.getAllWhere(jobQueue.db, state=constants.COLLECTING)
        for job in collectingJobs:
            self.collectJobs.put(job)

    def run(self):
        while True:
            try:
                job = self.collectJobs.get(block=True, timeout=30)
                self.jobQueue.uploadResults(job)
            except Queue.Empty, e:
                pass
            except Exception, e:
                self.log.exception(e)


class JobQueue(object):
    log = logging.getLogger('citrix.JobQueue')
    def __init__(self, database, nodepool, filesystem, uploader, executor):
        self.db = database
        self.nodepool = nodepool
        self.collectResultsThread = None
        self.jobs_enabled = Configuration().get_bool('RUN_TESTS')
        self.filesystem = filesystem
        self.uploader = uploader
        self.executor = executor

    def startCleanupThread(self):
        self.collectResultsThread = CollectResultsThread(self)
        self.collectResultsThread.start()

    def addJob(self, change_ref, project_name, commit_id):
        change_num = change_ref.split('/')[3]
        existing = Job.retrieve(self.db, project_name, change_num)
        if existing:
            self.log.info('Job for previous patchset (%s) already queued - replacing'%(existing))
            existing.delete(self.db)
            self.nodepool.deleteNode(existing.node_id)
        job = Job(change_num, change_ref, project_name, commit_id)
        with self.db.get_session() as session:
            self.log.info("Job for %s queued"%job.change_num)
            session.add(job)

    def triggerJobs(self):
        for job in self.get_queued_enabled_jobs():
            job.runJob(self.nodepool)

    def get_queued_enabled_jobs(self):
        allJobs = Job.getAllWhere(self.db, state=constants.QUEUED)
        self.log.info('%d jobs queued...'%len(allJobs))
        if self.jobs_enabled:
            return allJobs
        return []

    def uploadResults(self, job):
        tmpPath = self.filesystem.mkdtemp(suffix=job.change_num)

        try:
            result = job.retrieveResults(tmpPath)
            if not result:
                logging.info('No result obtained from %s', job)
                return

            code, fail_stdout, stderr = self.executor('grep$... FAIL$%s/run_tests.log'%tmpPath,
                                                      delimiter='$',
                                                      return_streams=True)
            self.log.info('Result: %s (Err: %s)', fail_stdout, stderr)

            self.log.info('Copying logs for %s', job)
            result_url = self.uploader.upload(tmpPath,
                                                job.change_ref.replace('refs/changes/',''))
            self.log.info('Uploaded results for %s', job)
            job.update(result=result,
                       logs_url=result_url,
                       report_url=result_url,
                       failed=fail_stdout)
            job.update(state=constants.COLLECTED)
        finally:
            self.filesystem.rmtree(tmpPath)
        self.nodepool.deleteNode(job.node_id)
        job.update(node_id=0)

    def processResults(self):
        if self.collectResultsThread is None:
            self.log.info('Starting collect thread')
            self.startCleanupThread()
        allJobs = Job.getAllWhere(self.db, state=constants.RUNNING)
        self.log.info('%d jobs running...'%len(allJobs))
        for job in allJobs:
            if job.isRunning(self.db):
                continue

            job.update(self.db, state=constants.COLLECTING)
            self.log.info('Tests for %s are done! Collecting'%job)
            self.collectResultsThread.collectJobs.put(job)

    def postResults(self):
        allJobs = Job.getAllWhere(self.db, state=constants.COLLECTED)
        self.log.info('%d jobs ready to be posted...'%len(allJobs))
        for job in allJobs:
            if job.result.find('Aborted') == 0:
                logging.info('Not voting on aborted job %s (%s)',
                             job, job.result)
                job.update(state=constants.FINISHED)
                continue

            if Configuration().get_bool('VOTE'):
                message = Configuration().VOTE_MESSAGE % {'result':job.result,
                                                        'report': job.report_url,
                                                        'log':job.logs_url}
                vote_num = "+1" if job.result == 'Passed' else "-1"
                if ((vote_num == '+1') or (not Configuration().get_bool('VOTE_PASSED_ONLY'))):
                    logging.info('Posting results for %s (%s)',
                                 job, job.result)
                    vote(job.commit_id, vote_num, message)
                    job.update(state=constants.FINISHED)

