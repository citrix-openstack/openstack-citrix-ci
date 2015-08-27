import os
import logging
import paramiko
import time
import threading

from osci.db import DB, and_
from osci.config import Configuration
from osci.job import Job
from osci import constants
from osci.utils import execute_command, copy_logs, vote
from osci import filesystem_services
from osci import time_services


class DeleteNodeThread(threading.Thread):
    log = logging.getLogger('citrix.DeleteNodeThread')

    def __init__(self, jobQueue):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.jobQueue = jobQueue
        self.pool = self.jobQueue.nodepool
        self.daemon = True

    def update_finished_jobs(self):
        # Remove the node_id from all finished nodes
        keep_failed = Configuration().get_int('KEEP_FAILED')
        keep_failed_timeout = Configuration().get_int('KEEP_FAILED_TIMEOUT')
        earliest_failed = time_services.time() - keep_failed_timeout

        with self.jobQueue.db.get_session() as session:
            finished_node_jobs = session.query(Job).filter(and_(Job.state.in_([constants.COLLECTED,
                                                                               constants.FINISHED,
                                                                               constants.OBSOLETE]),
                                                           Job.node_id != 0))

            # Construct a list of all jobs that could be kept because they failed
            keep_jobs = []
            if keep_failed > 0:
                for job in finished_node_jobs:
                    if job.result == 'Failed':
                        updated = time.mktime(job.updated.timetuple())
                        if updated < earliest_failed:
                            self.log.debug('Not keeping %s; too old', job)
                            continue
                        keep_jobs.append(job)
                # Only keep the <KEEP_FAILED> most recent failures
                keep_jobs.sort(key=lambda x: x.updated)
                self.log.debug('Keeping %s, discarding %s', keep_jobs[-keep_failed:], keep_jobs[:-keep_failed])
                keep_jobs = keep_jobs[-keep_failed:]

            for job in finished_node_jobs:
                if job in keep_jobs:
                    continue
                job.update(self.jobQueue.db, node_id=0)

    def get_nodes(self):
        # Find all node IDs that are currently in use
        nodes_in_use = set()
        with self.jobQueue.db.get_session() as session:
            jobs_with_node = session.query(Job).filter(Job.node_id != 0)
            for job in jobs_with_node:
                nodes_in_use.add(job.node_id)

        # Subtract the in-use nodes from the held nodes to find the list to delete
        held_set = self.pool.getHeldNodes()
        return held_set - nodes_in_use

    def _continue(self):
        return True

    def run(self):
        while self._continue():
            try:
                self.update_finished_jobs()
                delete_list = self.get_nodes()
                self.log.debug('Nodes to delete: %s'%delete_list)
                for node_id in delete_list:
                    self.pool.deleteNode(node_id)
                time.sleep(60)
            except Exception, e:
                self.log.exception(e)


class CollectResultsThread(threading.Thread):
    log = logging.getLogger('citrix.CollectResultsThread')

    def __init__(self, jobQueue):
        threading.Thread.__init__(self, name='CollectResultsThread')
        self.daemon = True
        self.jobQueue = jobQueue

    def get_jobs(self):
        ret_list = []
        collectingJobs = Job.getAllWhere(self.jobQueue.db,
                                         state=constants.COLLECTING)
        for job in collectingJobs:
            ret_list.append(job)
        return ret_list

    def _continue(self):
        return True

    def run(self):
        while self._continue():
            try:
                collect_list = self.get_jobs()
                self.log.debug('Nodes to collect: %s'%collect_list)
                for job in collect_list:
                    self.jobQueue.uploadResults(job)
                time.sleep(10)
            except Exception, e:
                self.log.exception(e)


class JobQueue(object):
    log = logging.getLogger('citrix.JobQueue')
    def __init__(self, database, nodepool, filesystem, uploader, executor):
        self.db = database
        self.nodepool = nodepool
        self.collectResultsThread = None
        self.deleteNodeThread = None
        self.filesystem = filesystem
        self.uploader = uploader
        self.executor = executor

    def startCleanupThreads(self):
        if self.collectResultsThread is None:
            self.collectResultsThread = CollectResultsThread(self)
            self.collectResultsThread.start()
        if self.deleteNodeThread is None:
            self.deleteNodeThread = DeleteNodeThread(self)
            self.deleteNodeThread.start()

    def addJob(self, change_ref, project_name, commit_id):
        change_num = change_ref.split('/')[3]
        existing_jobs = Job.retrieve(self.db, project_name, change_num)
        for existing in existing_jobs:
            self.log.info('Job for previous patchset (%s) already queued - replacing'%(existing))
            existing.update(self.db, state=constants.OBSOLETE)
        job = Job(change_num, change_ref, project_name, commit_id)
        with self.db.get_session() as session:
            self.log.info("Job for %s queued"%job.change_num)
            session.add(job)

    def triggerJob(self, job_id):
        allJobs = Job.getAllWhere(self.db, id=job_id)
        for job in allJobs:
            job.runJob(self.db, self.nodepool)

    def recheckJob(self, job_id):
        allJobs = Job.getAllWhere(self.db, id=job_id)
        for job in allJobs:
            self.addJob(job.change_ref, job.project_name, job.commit_id)

    def triggerJobs(self):
        for job in self.get_queued_enabled_jobs():
            job.runJob(self.db, self.nodepool)

    def get_queued_enabled_jobs(self):
        allJobs = Job.getAllWhere(self.db, state=constants.QUEUED)
        self.log.info('%d jobs queued...'%len(allJobs))
        if Configuration().get_bool('RUN_TESTS'):
            return allJobs
        return []

    def getJobDurationStr(self, job):
        job_dur = job.test_stopped - job.test_started
        dur_day = job_dur.days
        dur_sec = job_dur.seconds
        dur_hour, dur_sec = divmod(dur_sec, 3600)
        dur_min, dur_sec  = divmod(dur_sec, 60)
        dur_str  = "{:0>2d} d ".format(dur_day) if dur_day != 0 else ""
        dur_str += "{:0>2d} h ".format(dur_hour) if ((dur_hour != 0) or (dur_str != "")) else ""
        dur_str += "{:0>2d} m ".format(dur_min) if ((dur_min != 0) or (dur_str != "")) else ""
        dur_str += "{:0>2d} s".format(dur_sec)
        return dur_str

    def uploadResults(self, job):
        tmpPath = self.filesystem.mkdtemp(suffix=job.change_num)

        try:
            self.filesystem.mkdir('%s/logs'%tmpPath)
            result = job.retrieveResults('%s/logs'%tmpPath)
            if not result:
                logging.info('No result obtained from %s', job)
                return

            code, fail_stdout, stderr = self.executor('grep$... FAIL$%s/logs/run_tests.log'%tmpPath,
                                                      delimiter='$',
                                                      return_streams=True)
            self.log.info('Result: %s (Err: %s)', fail_stdout, stderr)

            self.log.info('Copying logs for %s', job)
            result_url = self.uploader.upload(['%s/logs/run_tests.log'%tmpPath, '%s/logs'%tmpPath],
                                              job.change_ref.replace('refs/changes/','')+'/%s'%job.id)
            self.log.info('Uploaded results for %s', job)
            job.update(self.db, result=result,
                       logs_url=result_url,
                       report_url=result_url,
                       failed=fail_stdout)
            job.update(self.db, state=constants.COLLECTED)
        finally:
            self.filesystem.rmtree(tmpPath)

    def processResults(self):
        allJobs = Job.getAllWhere(self.db, state=constants.RUNNING)
        self.log.info('%d jobs running...'%len(allJobs))
        for job in allJobs:
            if job.isRunning(self.db):
                continue

            job.update(self.db, state=constants.COLLECTING)
            self.log.info('Tests for %s are done! Collecting'%job)

    def postResults(self):
        allJobs = Job.getAllWhere(self.db, state=constants.COLLECTED)
        self.log.info('%d jobs ready to be posted...'%len(allJobs))
        for job in allJobs:
            if job.result.find('Aborted') == 0:
                logging.info('Not voting on aborted job %s (%s)',
                             job, job.result)
                job.update(self.db, state=constants.FINISHED)
                continue

            if Configuration().get_bool('VOTE'):
                result = "SUCCESS" if job.result == 'Passed' else "FAILURE"
                job_duration = self.getJobDurationStr(job)
                message = Configuration().VOTE_MESSAGE % {'result':result,
                                                        'log':job.logs_url,
                                                        'duration': job_duration}
                vote_num = "+1" if job.result == 'Passed' else "-1"
                if ((vote_num == '+1') or (not Configuration().get_bool('VOTE_PASSED_ONLY'))):
                    logging.info('Posting results for %s (%s)',
                                 job, job.result)
                    vote(job.commit_id, vote_num, message)
                    job.update(self.db, state=constants.FINISHED)

    def flush(self):
        Job.deleteWhere(self.db)
