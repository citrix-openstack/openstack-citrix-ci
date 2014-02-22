#!/usr/bin/env python
# -*- coding: utf-8 -*-

import subprocess

from pygerrit.client import GerritClient
from pygerrit.error import GerritError
from pygerrit.events import ErrorEvent, PatchsetCreatedEvent, CommentAddedEvent
from threading import Event
import datetime
import errno
import fnmatch
import logging
import optparse
import os, os.path
import re
import socket
import shutil
from stat import S_ISREG
import sys
import tempfile
import time
import threading
import Queue

import paramiko
import MySQLdb
from nodepool import nodedb, nodepool
from ctxosci import environment
from ctxosci import instructions

from prettytable import PrettyTable

QUEUED=1
RUNNING=2
COLLECTED=3
FINISHED=4
COLLECTING=5

STATES = {
    QUEUED: 'Queued',
    RUNNING: 'Running',
    COLLECTED: 'Collected',
    FINISHED: 'Finished',
    COLLECTING: 'Collecting',
    }

class CONSTANTS:
    GERRIT_HOST = '10.80.2.68'
    GERRIT_USERNAME = 'citrix_xenserver_ci'
    GERRIT_PORT = 29418
    SFTP_HOST = 'int-ca.downloads.xensource.com'
    SFTP_USERNAME = 'svcacct_openstack'
    SFTP_KEY = '/usr/workspace/scratch/openstack/infrastructure.hg/puppet/modules/jenkins/files/downloads-id_rsa'
    SFTP_BASE = '/var/www/html/'
    SFTP_COMMON = 'ca.downloads.xensource.com/OpenStack/xenserver-ci'
    NODEPOOL_CONFIG = '/etc/nodepool/nodepool.yaml'
    NODEPOOL_IMAGE = 'devstack-xenserver'
    NODE_USERNAME = 'jenkins'
    NODE_KEY = '/usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool'
    MAX_RUNNING_TIME = 3*3600+15*60 # 3 hours and 15 minutes
    MYSQL_URL = '127.0.0.1'
    MYSQL_USERNAME = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'openstack_ci'
    POLL = 30
    RUN_TESTS = True
    RECHECK_REGEXP = re.compile("^(citrix recheck|recheck bug|recheck nobug)")
    VOTE = True
    VOTE_PASSED_ONLY = True
    VOTE_NEGATIVE = False
    VOTE_SERVICE_ACCOUNT = False
    VOTE_MESSAGE = "%(result)s using XenAPI driver with XenServer 6.2.\n"+\
                   "* Logs: %(log)s\n\n"+\
                   "XenServer CI contact: openstack@citrix.com."
    REVIEW_REPO_NAME='review'
    PROJECT_CONFIG=['openstack-dev/sandbox', 'openstack/nova', 'openstack/tempest', 'openstack-dev/devstack']

class DB:
    log = logging.getLogger('citrix.db')
    def __init__(self, host, user, passwd):
        self.conn = None
        self.host = host
        self.user = user
        self.passwd = passwd
        self.connect()
    
    def connect(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception, e:
                self.log.exception(e)
        self.conn = MySQLdb.connect(self.host, self.user, self.passwd)

    def execute(self, sql, retry=True):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            self.conn.commit()
        except (AttributeError, MySQLdb.OperationalError):
            if retry:
                self.connect()
                self.execute(sql, False)
        except:
            self.log.error('Error running SQL %s'%sql)
            self.conn.rollback()

    def query(self, sql, retry=True):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            results = cur.fetchall()
            self.conn.commit()
            return results
        except (AttributeError, MySQLdb.OperationalError):
            if retry:
                self.connect()
                return self.query(sql, False)

def getSSHObject(ip, username, key_filename):
    if ip is None:
        raise Exception('Seriously?  The host must have an IP address')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
    key = paramiko.RSAKey.from_private_key_file(key_filename)
    try:
        ssh.connect(ip, username=username, pkey=key)
        return ssh
    except Exception, e:
        logging.error('Unable to connect to %s using %s and key %s'%(ip, username, key_filename))
        logging.exception(e)
        return None

class DeleteNodeThread(threading.Thread):
    log = logging.getLogger('citrix.DeleteNodeThread')

    deleteNodeQueue = Queue.Queue()
    
    def __init__(self, pool):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.pool = pool
        self.daemon = True

    def run(self):
        while True:
            try:
                self.pool.reconfigureManagers(self.pool.config)
                with self.pool.getDB().getSession() as session:
                    while True:
                        # Get a new DB Session every 30 seconds (exception will be caught below)
                        node_id = self.deleteNodeQueue.get(block=True, timeout=30)
                        node = session.getNode(node_id)
                        if node:
                            self.pool.deleteNode(session, node)
            except Queue.Empty, e:
                pass
            except Exception, e:
                self.log.exception(e)

class CollectResultsThread(threading.Thread):
    log = logging.getLogger('citrix.CollectResultsThread')

    collectTests = Queue.Queue()
    
    def __init__(self, testQueue):
        threading.Thread.__init__(self, name='DeleteNodeThread')
        self.daemon = True
        self.testQueue = testQueue
        collectingTests = Test.getAllWhere(testQueue.db, state=COLLECTING)
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

class Test():
    log = logging.getLogger('citrix.test')

    def __init__(self, change_num=None, change_ref=None, project_name=None, commit_id=None):
        self.db = None
        self.project_name = project_name
        self.change_num = change_num
        self.change_ref = change_ref
        self.state = QUEUED
        self.created = datetime.datetime.now()
        self.commit_id = commit_id
        self.node_id = None
        self.node_ip = None
        self.result = None
        self.logs_url = None
        self.report_url = None

    @classmethod
    def fromRecord(cls, record):
        retVal = Test()
        i = 0
        retVal.project_name=record[i]; i+=1
        retVal.change_num=record[i]; i+=1
        retVal.change_ref=record[i]; i+=1
        retVal.state=record[i]; i+=1
        retVal.created=record[i]; i+=1
        retVal.commit_id=record[i]; i+=1
        retVal.node_id=record[i]; i+=1
        retVal.node_ip=record[i]; i+=1
        retVal.result=record[i]; i+=1
        retVal.logs_url=record[i]; i+=1
        retVal.report_url=record[i]; i+=1
        retVal.updated=record[i]; i+=1
        retVal.test_started=record[i]; i+=1
        retVal.test_stopped=record[i]; i+=1

        return retVal

    @classmethod
    def createTable(cls, db):
        sql = 'CREATE TABLE IF NOT EXISTS test'+\
              '('+\
              ' project_name VARCHAR(50),' +\
              ' change_num VARCHAR(10),' +\
              ' change_ref VARCHAR(50),' +\
              ' state INT,'+\
              ' created DATETIME,' +\
              ' commit_id VARCHAR(50),'+\
              ' node_id INT,'+\
              ' node_ip VARCHAR(50),'+\
              ' result VARCHAR(50),'+\
              ' logs_url VARCHAR(200),'+\
              ' report_url VARCHAR(200),'+\
              ' updated TIMESTAMP' +\
              ' test_started TIMESTAMP,' +\
              ' test_stopped TIMESTAMP,' +\
              ' failed TEXT,' +\
              ' PRIMARY KEY (project_name, change_num)'+\
              ')'
        db.execute(sql)

    @classmethod
    def getAllWhere(cls, db, **kwargs):
        sql = 'SELECT * FROM test'
        if len(kwargs) > 0:
            sql += ' WHERE'
            
            for key, value in kwargs.iteritems():
                sql += ' %s="%s" AND'%(key, value)

            assert sql[-4:] == " AND"
            sql = sql[:-4] # Strip off the last AND
        sql += ' ORDER BY updated ASC'
        results = db.query(sql)

        retRecords = []
        for result in results:
            test = Test.fromRecord(result)
            test.db = db
            retRecords.append(test)

        return retRecords
    
    @classmethod
    def retrieve(cls, db, project_name, change_num):
        sql = 'SELECT * FROM test WHERE'+\
              ' project_name="%s"'+\
              ' AND change_num="%s"'
        results = db.query(sql%(project_name, change_num))
        if len(results) == 0:
            return None
        
        test = Test.fromRecord(results[0])
        test.db = db

        return test

    def insert(self, db):
        self.db = db
        SQL = 'INSERT INTO test(project_name, change_num, change_ref, state, created, commit_id) '+\
              'VALUES("%s","%s","%s","%s","%s","%s")'%(
            self.project_name, self.change_num, self.change_ref,
            self.state, self.created, self.commit_id)
        self.db.execute(SQL)
        self.log.info("Job for %s queued"%self.change_num)

    def update(self, **kwargs):
        sql = 'UPDATE test SET updated=CURRENT_TIMESTAMP,'
        if self.state == RUNNING and kwargs.get('state', RUNNING) != RUNNING:
            sql += ' test_stopped=CURRENT_TIMESTAMP,'
            
        for key, value in kwargs.iteritems():
            sql += ' %s="%s",'%(key, value)
            setattr(self, key, value)
        if kwargs.get('state', None) == RUNNING:
            sql += ' test_started=CURRENT_TIMESTAMP,test_stopped=NULL,'

        assert sql[-1:] == ","
        sql = sql[:-1] # Strip off the last ,
        sql += ' WHERE project_name="%s" AND change_num="%s"'%(self.project_name, self.change_num)
        self.db.execute(sql)

    def delete(self):
        SQL = 'DELETE FROM test WHERE project_name="%s" AND change_num="%s"'
        self.db.execute(SQL%(self.project_name, self.change_num))

    def runTest(self, nodepool):
        if self.node_id:
            node_id = self.node_id
            node_ip = self.node_ip
        else:
            node_id, node_ip = nodepool.getNode()

        if not node_id:
            return
        self.log.info("Running test for %s on %s/%s"%(self, node_id, node_ip))

        ssh = getSSHObject(node_ip, CONSTANTS.NODE_USERNAME, CONSTANTS.NODE_KEY)
        if not ssh:
            self.log.error('Failed to get SSH object for node %s/%s.  Deleting node.'%(node_id, node_ip))
            nodepool.deleteNode(node_id)
            self.update(node_id=0)
            return

        self.update(node_id=node_id, node_ip=node_ip, result='')

        cmd='echo %s >> run_tests_env' % ' '.join(instructions.check_out_testrunner())
        execute_command('ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s@%s %s'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip, cmd))
        cmd='echo "%s %s" >> run_tests_env' % (
            ' '.join(environment.get_environment(self.change_ref)),
            ' '.join(instructions.execute_test_runner()))
        execute_command('ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s@%s %s'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip, cmd))
        # TODO: For some reason invoking this immediately fails...
        time.sleep(5)
        execute_command('ssh$-q$-o$BatchMode=yes$-o$UserKnownHostsFile=/dev/null$-o$StrictHostKeyChecking=no$-i$%s$%s@%s$nohup bash /home/jenkins/run_tests_env < /dev/null > run_tests.log 2>&1 &'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip), '$')
        self.update(state=RUNNING)
        
    def isRunning(self):
        if not self.node_ip:
            self.log.error('Checking job %s is running but no node IP address'%self)
            return False
        updated = time.mktime(self.updated.timetuple())
        if (time.time() - updated < 300):
            # Allow 5 minutes for the gate PID to exist
            return True
        
        # Absolute maximum running time of 2 hours.  Note that if by happy chance the tests have finished
        # this result will be over-written by retrieveResults
        if (time.time() - updated > CONSTANTS.MAX_RUNNING_TIME):
            self.log.error('Timed out job %s (Running for %d seconds)'%(self, time.time()-updated))
            self.update(result='Aborted: Timed out')
            return False
        
        try:
            success = execute_command('ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s@%s ps -p `cat /home/jenkins/workspace/testing/gate.pid`'%(
                    CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, self.node_ip), silent=True)
            self.log.info('Gate-is-running on job %s (%s) returned: %s'%(
                          self, self.node_ip, success))
            return success
        except Exception, e:
            self.update(result='Aborted: Exception checking for pid')
            self.log.exception(e)
            return False

    def retrieveResults(self, dest_path):
        if not self.node_ip:
            self.log.error('Attempting to retrieve results for %s but no node IP address'%self)
            return "Aborted: No IP"
        try:
            code, stdout, stderr = execute_command('ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i %s %s@%s cat result.txt'%(
                    CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, self.node_ip), silent=True,
                                                   return_streams=True)
            self.log.info('Result: %s (Err: %s)'%(stdout, stderr))
            self.log.info('Downloading logs for %s'%self)
            copy_logs(['/home/jenkins/workspace/testing/logs/*', '/home/jenkins/run_test*'], dest_path,
                      self.node_ip, CONSTANTS.NODE_USERNAME,
                      paramiko.RSAKey.from_private_key_file(CONSTANTS.NODE_KEY),
                      upload=False)
            
            if code != 0:
                # This node is broken somehow... Mark it as aborted
                if self.result and self.result.startswith('Aborted: '):
                    return self.result
                return "Aborted: No result found"
            
            return stdout.splitlines()[0]
        except Exception, e:
            self.log.exception(e)

    def __repr__(self):
        return "%(project_name)s/%(change_num)s state:%(state)s" %self

    def __getitem__(self, item):
        return getattr(self, item)

class NodePool():
    log = logging.getLogger('citrix.nodepool')
    def __init__(self, image):
        self.pool = nodepool.NodePool(CONSTANTS.NODEPOOL_CONFIG)
        config = self.pool.loadConfig()
        self.pool.reconfigureDatabase(config)
        self.pool.setConfig(config)
        self.image = image
        self.deleteNodeThread = DeleteNodeThread(self.pool)
        self.deleteNodeThread.start()

    def getNode(self):
        with self.pool.getDB().getSession() as session:
            for node in session.getNodes():
                if node.image_name != self.image:
                    continue
                if node.state != nodedb.READY:
                    continue
                # Allocate this node
                node.state = nodedb.HOLD
                return node.id, node.ip
        return None, None

    def deleteNode(self, node_id):
        if not node_id:
            return
        self.log.info('Adding node %s to the list to delete'%node_id)
        DeleteNodeThread.deleteNodeQueue.put(node_id)
                
def mkdir_recursive(target, target_dir):
    try:
        target.chdir(target_dir)
    except:
        mkdir_recursive(target, os.path.dirname(target_dir))
        target.mkdir(target_dir)

def copy_logs(source_masks, target_dir, host, username, key, upload=True):
    logger = logging.getLogger('citrix.copy_logs')
    transport = paramiko.Transport((host, 22))
    try:
        transport.connect(username=username, pkey=key)
    except socket.error, e:
        logger.exception(e)
        return
    sftp = paramiko.SFTPClient.from_transport(transport)

    if upload:
        source = os
        target = sftp
        sftp_method = sftp.put
    else:
        source = sftp
        target = os
        sftp_method = sftp.get
        
    mkdir_recursive(target, target_dir)

    existing_files = target.listdir(target_dir)
    for filename in existing_files:
        target.remove(os.path.join(target_dir, filename))

    for source_mask in source_masks:
        try:
            source_dir = os.path.dirname(source_mask)
            source_glob = os.path.basename(source_mask)
            for filename in source.listdir(source_dir):
                if not fnmatch.fnmatch(filename, source_glob):
                    continue
                source_file = os.path.join(source_dir, filename)
                if S_ISREG(source.stat(source_file).st_mode):
                    logger.info('Copying %s to %s'%(source_file, target_dir))
                    try:
                        sftp_method(os.path.join(source_dir, filename),
                                    os.path.join(target_dir, filename))
                    except IOError, e:
                        logger.exception(e)
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise e
            logger.exception(e)
            # Ignore this exception to try again on the next directory
    sftp.close()

class TestQueue():
    log = logging.getLogger('citrix.TestQueue')
    def __init__(self, host, username, password, database_name):
        self.db = DB(host=host,
                     user=username,
                     passwd=password)
        self.initDB(database_name)
        self.nodepool = NodePool(CONSTANTS.NODEPOOL_IMAGE)
        self.collectResultsThread = CollectResultsThread(self)
        self.collectResultsThread.start()
        
    def initDB(self, database):
        try:
            self.db.execute('USE %s'%database)
        except:
            self.db.execute('CREATE DATABASE %s'%database)
            self.db.execute('USE %s'%database)
            
        Test.createTable(self.db)
    
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
        allTests = Test.getAllWhere(self.db, state=QUEUED)
        self.log.info('%d tests queued...'%len(allTests))
        if not CONSTANTS.RUN_TESTS:
            return
        for test in allTests:
            test.runTest(self.nodepool)

    def uploadResults(self, test):
        tmpPath = tempfile.mkdtemp(suffix=test.change_num)
        try:
            result = test.retrieveResults(tmpPath)
            if not result:
                logging.info('No result obtained from %s'%test)
                return
            
            code, fail_stdout, stderr = execute_command('grep$... FAIL$%s/run_tests.log'%tmpPath,
                                                        delimiter='$',
                                                        return_streams=True)
            self.log.info('Result: %s (Err: %s)'%(fail_stdout, stderr))
                
            self.log.info('Copying logs for %s'%(test))
            result_path = os.path.join(CONSTANTS.SFTP_COMMON, test.change_ref)
            copy_logs(['%s/*'%tmpPath], os.path.join(CONSTANTS.SFTP_BASE, result_path),
                      CONSTANTS.SFTP_HOST, CONSTANTS.SFTP_USERNAME,
                      paramiko.RSAKey.from_private_key_file(CONSTANTS.SFTP_KEY))
            self.log.info('Uploaded results for %s'%test)
            test.update(result=result,
                        logs_url='http://%s/'%result_path,
                        report_url='http://%s/'%result_path,
                        failed=fail_stdout)
            test.update(state=COLLECTED)
        finally:
            shutil.rmtree(tmpPath)
        self.nodepool.deleteNode(test.node_id)
        test.update(node_id=0)

    def processResults(self):
        allTests = Test.getAllWhere(self.db, state=RUNNING)
        self.log.info('%d tests running...'%len(allTests))
        for test in allTests:
            if test.isRunning():
                continue
            
            self.log.info('Tests for %s are done! Collecting'%test)
            test.update(state=COLLECTING)
            CollectResultsThread.collectTests.put(test)

    def postResults(self):
        allTests = Test.getAllWhere(self.db, state=COLLECTED)
        self.log.info('%d tests ready to be posted...'%len(allTests))
        for test in allTests:
            if test.result.find('Aborted') == 0:
                logging.info('Not voting on aborted test %s (%s)'%(test, test.result))
                test.update(state=FINISHED)
                continue
                
            if CONSTANTS.VOTE:
                message=CONSTANTS.VOTE_MESSAGE%{'result':test.result, 'report': test.report_url, 'log':test.logs_url}
                vote_num = "+1" if test.result == 'Passed' else "-1"
                if ((vote_num == '+1') or (not CONSTANTS.VOTE_PASSED_ONLY)):
                    logging.info('Posting results for %s (%s)'%(test, test.result))
                    vote(test.commit_id, vote_num, message)
                    test.update(state=FINISHED)


def is_event_matching_criteria(event):
    if isinstance(event, CommentAddedEvent):
        comment = event.comment
        if not CONSTANTS.RECHECK_REGEXP.match(comment):
            return False
        logging.debug("Comment matched: %s"%comment)
    elif not isinstance(event, PatchsetCreatedEvent):
        return False
    if event.change.branch=="master":
        if is_project_configured(event.change.project):
            logging.info("Event %s is matching event criteria"%event)
            return True
    return False

def is_project_configured(submitted_project):
    return submitted_project in CONSTANTS.PROJECT_CONFIG

def execute_command(command, delimiter=' ', silent=False, return_streams=False):
    command_as_array = command.split(delimiter)
    if not silent:
        logging.debug("Executing command: %s"%command_as_array) 
    p = subprocess.Popen(command_as_array,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = p.communicate()
    if p.returncode != 0:
        if not silent:
            logging.error("Error: Could not execute command. Failed with code %d and errors: %s"%(p.returncode, errors))
    if not silent:
        logging.debug("Output:%s"%output)
    
    if return_streams:
        return p.returncode, output, errors
    return p.returncode == 0

def vote(commitid, vote_num, message):
    #ssh -p 29418 review.example.com gerrit review -m '"Test failed on MegaTestSystem <http://megatestsystem.org/tests/1234>"'
    # --verified=-1 c0ff33
    logging.info("Going to vote commitid %s, vote %s, message %s" % (commitid, vote_num, message))
    if not CONSTANTS.VOTE_NEGATIVE and vote_num == "-1":
        logging.error("Did not vote -1 for commitid %s, vote %s" % (commitid, vote_num))
        vote_num = "0"
        message += "\n\nNegative vote suppressed"
    vote_cmd = "ssh$-q$-o$BatchMode=yes$-o$UserKnownHostsFile=/dev/null$-o$StrictHostKeyChecking=no$-p$%d$%s@%s$gerrit$review"%(CONSTANTS.GERRIT_PORT, CONSTANTS.GERRIT_USERNAME, CONSTANTS.GERRIT_HOST)
    vote_cmd = vote_cmd + "$-m$'" + message + "'"
    if CONSTANTS.VOTE_SERVICE_ACCOUNT:
        vote_cmd = vote_cmd + "$--verified=" + vote_num
    vote_cmd = vote_cmd + "$" + commitid
    is_executed = execute_command(vote_cmd,'$')
    if not is_executed:
        logging.error("Error: Could not vote. Voting failed for change: " + commitid)
    else:
        logging.info("Successfully voted " + str(vote_num) + " for change: " + commitid)

def queue_event(queue, event):
    logging.info("patchset values : %s" %event)
    if is_project_configured(event.change.project):
        queue.addTest(event.patchset.ref,
                      event.change.project,
                      event.patchset.revision)

def check_for_change_ref(option, opt_str, value, parser):
    if not parser.values.change_ref:
        raise optparse.OptionValueError("can't use %s, Please provide --change_ref/-c before %s" % (opt_str, opt_str))
    setattr(parser.values, option.dest, value)

def _main():
    usage = "usage: %prog [options]"
    
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose',
                      action='store_true',default=False,
                      help='enable verbose (debug) logging')
    parser.add_option('-c', '--change-ref', dest='change_ref',
                      action="store", type="string",
                      help="to be provided if required to do one time job on a change-ref")
    parser.add_option('-x', '--commit-id', dest='commitid',
                      action="callback", callback=check_for_change_ref, type="string",
                      help="to be provided if required to do one time job on a change-id")
    parser.add_option('-j', '--project', dest='project',
                      action="callback", callback=check_for_change_ref, type="string",
                      help="project of the change-ref provided")
    parser.add_option('--list', dest='list',
                      action='store_true', default=False,
                      help="List the tests recorded by the system")
    parser.add_option('--states', dest='states',
                      action='store', default=None,
                      help="(Use with --list): States to list recorded by the system")
    parser.add_option('--failures', dest='failures',
                      action='store_true', default=False,
                      help="List the failures recorded by the system")
    parser.add_option('--recent', dest='recent',
                      action='store', default=None,
                      help="(Use with --list or --failures): Only show jobs less than this many hours old")
    parser.add_option('--show', dest='show',
                      action='store_true', default=False,
                      help="Show details for a specific test recorded by the system")

    (options, _args) = parser.parse_args()
    if options.change_ref and (not options.project or not options.commitid):
        parser.error('Can only use --change_ref with --project')

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(format=u'%(asctime)s %(levelname)s %(name)s %(message)s',
                        level=level)
    logging.getLogger('paramiko.transport').setLevel(logging.WARNING)
    logging.getLogger('paramiko.transport.sftp').setLevel(logging.WARNING)
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARNING)

    queue = TestQueue(CONSTANTS.MYSQL_URL, CONSTANTS.MYSQL_USERNAME, CONSTANTS.MYSQL_PASSWORD, CONSTANTS.MYSQL_DB)


    if options.show:
        t = PrettyTable()
        t.add_column('Key', ['Project name', 'Change num', 'Change ref',
                             'state', 'created', 'Commit id', 'Node id',
                             'Node ip', 'Result', 'Logs', 'Report', 'Updated',
                             'Gerrit URL'])
        test = Test.getAllWhere(queue.db, change_ref=options.change_ref, project_name=options.project)[0]
        url = 'https://review.openstack.org/%s'%test.change_num
        t.add_column('Value', [test.project_name, test.change_num, test.change_ref,
                               STATES[test.state], test.created, test.commit_id,
                               test.node_id, test.node_ip, test.result, test.logs_url,
                               test.report_url, test.updated, url])
        t.align = 'l'
        print t
        return


    if options.change_ref:
        # Execute tests and vote
        if options.project not in CONSTANTS.PROJECT_CONFIG:
            logging.info("Project specified does not match criteria")
            return
        queue.addTest(options.change_ref, options.project, options.commitid)

    if options.list:
        t = PrettyTable(["Project", "Change", "State", "IP", "Result", "Age (hours)", "Duration"])
        t.align = 'l'
        now = time.time()
        allTests = Test.getAllWhere(queue.db)
        state_dict = {}
        result_dict = {}
        if options.states and len(options.states) > 0:
            states = options.states.split(',')
        else:
            states = None
        for test in allTests:
            updated = time.mktime(test.updated.timetuple())
            age_hours = (now - updated) / 3600
            if options.recent:
                if age_hours > int(options.recent):
                    continue
            state_count = state_dict.get(STATES[test.state], 0)+1
            state_dict[STATES[test.state]] = state_count
            result_count = result_dict.get(test.result, 0)+1
            result_dict[test.result] = result_count

            if states and STATES[test.state] not in states:
                continue
            if test.node_id:
                node_ip = test.node_ip
            else:
                node_ip = '(%s)'%test.node_ip
            age = '%.02f' % (age_hours)
            duration = '-'

            if test.test_started and test.test_stopped:
                started = time.mktime(test.test_started.timetuple())
                stopped = time.mktime(test.test_stopped.timetuple())
                if started < stopped:
                    duration = "%.02f"%((stopped - started)/3600)
            t.add_row([test.project_name, test.change_ref, STATES[test.state], node_ip, test.result, age, duration])
        print state_dict
        print result_dict
        print t
        return
    
    if options.failures:
        t = PrettyTable(["Project", "Change", "State", "Result", "Age", "Duration", "URL"])
        t.align = 'l'
        now = time.time()
        allTests = Test.getAllWhere(queue.db)
        for test in allTests:
            if not test.result or (test.result != 'Failed' and test.result.find('Aborted') != 0):
                continue
            updated = time.mktime(test.updated.timetuple())
            age_hours = (now - updated) / 3600
            if options.recent:
                if age_hours > int(options.recent):
                    continue
            if test.node_id:
                node_ip = test.node_ip
            else:
                node_ip = '(%s)'%test.node_ip
            age = '%.02f' % (age_hours)
            duration = '-'
            
            if test.test_started and test.test_stopped:
                started = time.mktime(test.test_started.timetuple())
                stopped = time.mktime(test.test_stopped.timetuple())
                duration = "%.02f"%((stopped - started)/3600)
            t.add_row([test.project_name, test.change_num, STATES[test.state], test.result, age, duration, test.logs_url])
        print t
        return
    
    # Starting the loop for listening to Gerrit events
    try:
        logging.info("Connecting to gerrit host %s"%CONSTANTS.GERRIT_HOST)
        logging.info("Connecting to gerrit username %s"%CONSTANTS.GERRIT_USERNAME)
        logging.info("Connecting to gerrit port %d"%CONSTANTS.GERRIT_PORT)
        gerrit = GerritClient(host=CONSTANTS.GERRIT_HOST,
                              username=CONSTANTS.GERRIT_USERNAME,
                              port=CONSTANTS.GERRIT_PORT)
        logging.info("Connected to Gerrit version [%s]",
                     gerrit.gerrit_version())
        gerrit.start_event_stream()
    except GerritError as err:
        logging.error("Gerrit error: %s", err)
        return 1

    errors = Event()
    try:
        while True:
            event = gerrit.get_event(block=False)
            while event:
                logging.debug("Event: %s", event)
                """ Logic starts here """
                if is_event_matching_criteria(event):
                    queue_event(queue, event)

                if isinstance(event, ErrorEvent):
                    logging.error(event.error)
                    errors.set()
                event = gerrit.get_event(block=False)
            try:
                queue.postResults()
                queue.processResults()
                queue.triggerJobs()
            except Exception, e:
                logging.exception(e)
                # Ignore exception and try again; keeps the app polling
            time.sleep(CONSTANTS.POLL)
    except KeyboardInterrupt:
        logging.info("Terminated by user")
    finally:
        logging.debug("Stopping event stream...")
        gerrit.stop_event_stream()

    if errors.isSet():
        logging.error("Exited with error")
        return 1

if __name__ == "__main__":
    sys.exit(_main())
