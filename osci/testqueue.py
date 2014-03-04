import os
import logging
import tempfile
import paramiko
import shutil
import threading
import Queue

from osci.db import DB
from osci.config import Configuration
from osci.nodepool_manager import NodePool
from osci.test import Test
from osci import constants 
from osci.utils import execute_command, copy_logs, vote
from osci.swift_upload import SwiftUploader

class CollectResultsThread(threading.Thread):
    log = logging.getLogger('citrix.CollectResultsThread')

    collectTests = Queue.Queue()
    
    def __init__(self, testQueue):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.daemon = True
        self.testQueue = testQueue
        collectingTests = Test.getAllWhere(testQueue.db, state=constants.COLLECTING)
        for test in collectingTests:
            self.collectTests.put(test)

    def run(self):
        while True:
            try:
                test = self.collectTests.get(block=True, timeout=30)
                self.testQueue.uploadResults(test)
            except Queue.Empty, e:
                pass
            except Exception, e:
                self.log.exception(e)


class TestQueue():
    log = logging.getLogger('citrix.TestQueue')
    def __init__(self, database):
        self.db = database
        self.nodepool = NodePool(Configuration().NODEPOOL_IMAGE)
        self.collectResultsThread = None

    def startCleanupThread(self):
        self.collectResultsThread = CollectResultsThread(self)
        self.collectResultsThread.start()
        
    def addTest(self, change_ref, project_name, commit_id):
        change_num = change_ref.split('/')[3]
        existing = Test.retrieve(self.db, project_name, change_num)
        if existing:
            self.log.info('Test for previous patchset (%s) already queued - replacing'%(existing))
            existing.delete()
            self.nodepool.deleteNode(existing.node_id)
        test = Test(change_num, change_ref, project_name, commit_id)
        test.insert(self.db)

    def triggerJobs(self):
        allTests = Test.getAllWhere(self.db, state=constants.QUEUED)
        self.log.info('%d tests queued...'%len(allTests))
        if not Configuration().get_bool('RUN_TESTS'):
            return
        for test in allTests:
            test.runTest(self.nodepool)

    def uploadResults(self, test):
        tmpPath = tempfile.mkdtemp(suffix=test.change_num)
        try:
            result = test.retrieveResults(tmpPath)
            if not result:
                logging.info('No result obtained from %s', test)
                return
            
            code, fail_stdout, stderr = execute_command('grep$... FAIL$%s/run_tests.log'%tmpPath,
                                                        delimiter='$',
                                                        return_streams=True)
            self.log.info('Result: %s (Err: %s)', fail_stdout, stderr)
                
            self.log.info('Copying logs for %s', test)
            result_url = SwiftUploader().upload(tmpPath,
                                                test.change_ref.replace('refs/changes/',''))
            self.log.info('Uploaded results for %s', test)
            test.update(result=result,
                        logs_url=result_url,
                        report_url=result_url,
                        failed=fail_stdout)
            test.update(state=constants.COLLECTED)
        finally:
            shutil.rmtree(tmpPath)
        self.nodepool.deleteNode(test.node_id)
        test.update(node_id=0)

    def processResults(self):
        if self.collectResultsThread is None:
            self.log.info('Starting collect thread')
            self.startCleanupThread()
        allTests = Test.getAllWhere(self.db, state=constants.RUNNING)
        self.log.info('%d tests running...'%len(allTests))
        for test in allTests:
            if test.isRunning():
                continue
            
            test.update(state=constants.COLLECTING)
            self.log.info('Tests for %s are done! Collecting'%test)
            CollectResultsThread.collectTests.put(test)

    def postResults(self):
        allTests = Test.getAllWhere(self.db, state=constants.COLLECTED)
        self.log.info('%d tests ready to be posted...'%len(allTests))
        for test in allTests:
            if test.result.find('Aborted') == 0:
                logging.info('Not voting on aborted test %s (%s)',
                             test, test.result)
                test.update(state=constants.FINISHED)
                continue
                
            if Configuration().get_bool('VOTE'):
                message = Configuration().VOTE_MESSAGE % {'result':test.result,
                                                        'report': test.report_url,
                                                        'log':test.logs_url}
                vote_num = "+1" if test.result == 'Passed' else "-1"
                if ((vote_num == '+1') or (not Configuration().get_bool('VOTE_PASSED_ONLY'))):
                    logging.info('Posting results for %s (%s)',
                                 test, test.result)
                    vote(test.commit_id, vote_num, message)
                    test.update(state=constants.FINISHED)

