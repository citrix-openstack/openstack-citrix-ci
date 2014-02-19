#!/usr/bin/env python
# -*- coding: utf-8 -*-
from optparse import OptionValueError

# The MIT License
#
# Copyright 2012 Sony Mobile Communications. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

""" Example of using the Gerrit client class. """

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

import paramiko
import MySQLdb
from nodepool import nodedb, nodepool

""" importing python git commands """
from git import Repo

from prettytable import PrettyTable

QUEUED=1
RUNNING=2
COLLECTED=3
FINISHED=4

STATES = {
    QUEUED: 'Queued',
    RUNNING: 'Running',
    COLLECTED: 'Collected',
    FINISHED: 'Finished',
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
    MAX_RUNNING_TIME = 3600*3
    MYSQL_URL = '127.0.0.1'
    MYSQL_USERNAME = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'openstack_ci'
    POLL = 30
    RECHECK_REGEXP = re.compile("^(citrix recheck|recheck bug|recheck nobug)")
    VOTE = True
    VOTE_PASSED_ONLY = True
    VOTE_NEGATIVE = False
    VOTE_SERVICE_ACCOUNT = False
    VOTE_MESSAGE = "%(result)s using XenAPI driver with XenServer 6.2.\n"+\
                   "* Logs: %(log)s\n\n"+\
                   "XenServer CI contact: openstack@citrix.com."
    REVIEW_REPO_NAME='review'
    PROJECT_CONFIG={
        'sandbox':{
            'name':'sandbox',
            'repo_path':"/tmp/opt/stack/gerrit_cache/sandbox",
            'review_repo': "https://review.openstack.org/openstack-dev/sandbox",
            'files_to_check' : [''],
            'files_to_ignore' : []
            },
        'nova':{
            'name':'nova',
            'repo_path':"/tmp/opt/stack/gerrit_cache/nova",
            'review_repo': "https://review.openstack.org/openstack/nova",
            'files_to_check' : [''],
            'files_to_ignore' : ['nova/virt/baremetal',
                                 'nova/virt/disk',
                                 'nova/virt/docker',
                                 'nova/virt/hyperv',
                                 'nova/virt/libvirt',
                                 'nova/virt/vmwareapi',
                                 'nova/tests/virt/baremetal',
                                 'nova/tests/virt/disk',
                                 'nova/tests/virt/docker',
                                 'nova/tests/virt/hyperv',
                                 'nova/tests/virt/libvirt',
                                 'nova/tests/virt/vmwareapi',]
            },
        'tempest':{
            'name':'tempest',
            'repo_path':"/tmp/opt/stack/gerrit_cache/tempest",
            'review_repo': "https://review.openstack.org/openstack/tempest",
            'files_to_check' : [''],
            'files_to_ignore' : []
            },
        'devstack':{
            'name':'devstack',
            'repo_path':"/tmp/opt/stack/gerrit_cache/devstack",
            'review_repo': "https://review.openstack.org/openstack-dev/devstack",
            'files_to_check' : [''],
            'files_to_ignore' : []
            },
        }

def db_execute(db, sql):
    cur = db.cursor()
    try:
        cur.execute(sql)
        db.commit()
    except:
        logging.error('Error running SQL %s'%sql)
        db.rollback()

def db_query(db, sql):
    cur = db.cursor()
    cur.execute(sql)
    results = cur.fetchall()
    db.commit()
    return results

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

class Test():
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
              ' updated TIMESTAMP default CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,' +\
              ' test_started TIMESTAMP,' +\
              ' test_stopped TIMESTAMP,' +\
              ' posted TIMESTAMP,' +\
              ' PRIMARY KEY (project_name, change_num)'+\
              ')'
        db_execute(db, sql)

    @classmethod
    def getAllWhere(cls, db, **kwargs):
        sql = 'SELECT * FROM test'
        if len(kwargs) > 0:
            sql += ' WHERE'
            
            for key, value in kwargs.iteritems():
                sql += ' %s="%s" AND'%(key, value)

            assert sql[-4:] == " AND"
            sql = sql[:-4] # Strip off the last AND
        sql += ' ORDER BY created ASC'
        results = db_query(db, sql)

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
        results = db_query(db, sql%(project_name, change_num))
        if len(results) == 0:
            return None
        
        test = Test.fromRecord(results[0])
        test.db = db

    def insert(self, db):
        self.db = db
        SQL = 'INSERT INTO test(project_name, change_num, change_ref, state, created, commit_id) '+\
              'VALUES("%s","%s","%s","%s","%s","%s")'%(
            self.project_name, self.change_num, self.change_ref,
            self.state, self.created, self.commit_id)
        db_execute(self.db, SQL)
        logging.info("Job for %s queued"%self.change_num)

    def update(self, **kwargs):
        sql = 'UPDATE test SET updated=CURRENT_TIMESTAMP,'
        if self.state == RUNNING and kwargs.get('state', RUNNING) != RUNNING:
            sql += ' test_stopped=CURRENT_TIMESTAMP,'
            
        for key, value in kwargs.iteritems():
            sql += ' %s="%s",'%(key, value)
            setattr(self, key, value)
        if kwargs.get('state', None) == RUNNING:
            sql += ' test_started=CURRENT_TIMESTAMP,'
        if kwargs.get('state', None) == FINISHED:
            sql += ' posted=CURRENT_TIMESTAMP,'

        assert sql[-1:] == ","
        sql = sql[:-1] # Strip off the last ,
        sql += ' WHERE project_name="%s" AND change_num="%s"'%(self.project_name, self.change_num)
        db_execute(self.db, sql)

    def delete(self):
        SQL = 'DELETE FROM test WHERE project_name="%s" AND change_num="%s"'
        db_execute(self.db, SQL%(self.project_name, self.change_num))

    def runTest(self, nodepool):
        if self.node_id:
            node_id = self.node_id
            node_ip = self.node_ip
        else:
            node_id, node_ip = nodepool.getNode()

        if not node_id:
            return
        logging.info("Running test for %s on %s/%s"%(self, node_id, node_ip))

        ssh = getSSHObject(node_ip, CONSTANTS.NODE_USERNAME, CONSTANTS.NODE_KEY)
        if not ssh:
            logging.error('Failed to get SSH object for node %s/%s.  Deleting node.'%(node_id, node_ip))
            nodepool.deleteNode(node_id)
            self.update(node_id=0)
            return

        self.update(node_id=node_id, node_ip=node_ip, result='')

        environment  = 'ZUUL_URL=https://review.openstack.org'
        environment += ' ZUUL_REF=%s'%self.change_ref
        environment += ' PYTHONUNBUFFERED=true'
        environment += ' DEVSTACK_GATE_TEMPEST=1'
        environment += ' DEVSTACK_GATE_TEMPEST_FULL=1'
        environment += ' DEVSTACK_GATE_VIRT_DRIVER=xenapi'
        # Set gate timeout to 2 hours
        environment += ' DEVSTACK_GATE_TIMEOUT=240'
        environment += ' APPLIANCE_NAME=devstack'
        cmd='echo /usr/bin/git clone https://github.com/citrix-openstack/xenapi-os-testing '+\
             '/home/jenkins/xenapi-os-testing > run_tests_env'
        execute_command('ssh -i %s %s@%s %s'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip, cmd))
        cmd='echo "%s /home/jenkins/xenapi-os-testing/run_tests.sh" >> run_tests_env'%environment
        execute_command('ssh -i %s %s@%s %s'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip, cmd))
        # TODO: For some reason invoking this immediately fails...
        time.sleep(5)
        execute_command('ssh$-i$%s$%s@%s$nohup bash /home/jenkins/run_tests_env < /dev/null > run_tests.log 2>&1 &'%(
                CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, node_ip), '$')
        self.update(state=RUNNING)
        
    def isRunning(self):
        if not self.node_ip:
            logging.error('Checking job %s is running but no node IP address'%self)
            return False
        updated = time.mktime(self.updated.timetuple())
        if (time.time() - updated < 300):
            # Allow 5 minutes for the gate PID to exist
            return True
        
        # Absolute maximum running time of 2 hours.  Note that if by happy chance the tests have finished
        # this result will be over-written by retrieveResults
        if (time.time() - updated > CONSTANTS.MAX_RUNNING_TIME):
            logging.error('Timed out job %s (Running for %d seconds)'%(self, time.time()-updated))
            self.update(result='Aborted: Timed out')
            return False
        
        try:
            success = execute_command('ssh -i %s %s@%s ps -p `cat /home/jenkins/workspace/testing/gate.pid`'%(
                    CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, self.node_ip))
            return success
        except Exception, e:
            self.update(result='Aborted: Exception checking for pid')
            logging.exception(e)
            return False

    def retrieveResults(self, dest_path):
        if not self.node_ip:
            logging.error('Attempting to retrieve results for %s but no node IP address'%self)
            return "Aborted: No IP"
        try:
            code, stdout, stderr = execute_command('ssh -i %s %s@%s cat result.txt'%(
                    CONSTANTS.NODE_KEY, CONSTANTS.NODE_USERNAME, self.node_ip), silent=True,
                                                   return_streams=True)
            logging.info('Result: %s (Err: %s)'%(stdout, stderr))
            copy_logs(['/home/jenkins/workspace/testing/logs/*', '/home/jenkins/run_test*'], dest_path,
                      self.node_ip, CONSTANTS.NODE_USERNAME,
                      paramiko.RSAKey.from_private_key_file(CONSTANTS.NODE_KEY),
                      upload=False)
            
            if code != 0:
                # This node is broken somehow... Mark it as aborted
                if self.result and self.result.startswith('Aborted: '):
                    return self.result
                return "Aborted: Unknown"
            
            return stdout.splitlines()[0]
        except Exception, e:
            logging.exception(e)

    def __repr__(self):
        return "%(project_name)s/%(change_num)s state:%(state)s" %self

    def __getitem__(self, item):
        return getattr(self, item)

class NodePool():
    def __init__(self, image):
        self.pool = nodepool.NodePool(CONSTANTS.NODEPOOL_CONFIG)
        config = self.pool.loadConfig()
        self.pool.reconfigureDatabase(config)
        self.pool.setConfig(config)
        self.image = image

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
        self.pool.reconfigureManagers(self.pool.config)
        with self.pool.getDB().getSession() as session:
            node = session.getNode(node_id)
            if node:
                self.pool.deleteNode(session, node)
                
def mkdir_recursive(target, target_dir):
    try:
        target.chdir(target_dir)
    except:
        mkdir_recursive(target, os.path.dirname(target_dir))
        target.mkdir(target_dir)

def copy_logs(source_masks, target_dir, host, username, key, upload=True):
    transport = paramiko.Transport((host, 22))
    try:
        transport.connect(username=username, pkey=key)
    except socket.error, e:
        logging.exception(e)
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
                    sftp_method(os.path.join(source_dir, filename),
                                os.path.join(target_dir, filename))
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise e
            logging.exception(e)
            # Ignore this exception to try again on the next directory
    sftp.close()

class TestQueue():
    def __init__(self, host, username, password, database_name):
        self.db = MySQLdb.connect(host=host,
                                  user=username,
                                  passwd=password)
        self.initDB(database_name)
        self.nodepool = NodePool(CONSTANTS.NODEPOOL_IMAGE)
        
    def initDB(self, database):
        cur = self.db.cursor()
        try:
            cur.execute('USE %s'%database)
        except:
            cur.execute('CREATE DATABASE %s'%database)
            cur.execute('USE %s'%database)
            
        Test.createTable(self.db)
    
    def addTest(self, change_ref, project_name, commit_id):
        change_num = change_ref.split('/')[3]
        existing = Test.retrieve(self.db, project_name, change_num)
        if existing:
            logging.info('Test for previous patchset (%s) already queued - replacing'%(existing))
            existing.delete()
            self.nodepool.deleteNode(existing.node_id)
        test = Test(change_num, change_ref, project_name, commit_id)
        test.insert(self.db)

    def triggerJobs(self):
        allTests = Test.getAllWhere(self.db, state=QUEUED)
        logging.info('%d tests queued...'%len(allTests))
        for test in allTests:
            test.runTest(self.nodepool)

    def processResults(self):
        allTests = Test.getAllWhere(self.db, state=RUNNING)
        logging.info('%d tests running...'%len(allTests))
        for test in allTests:
            if test.isRunning():
                continue
            
            logging.info('Tests for %s are done! Collecting'%test)
            tmpPath = tempfile.mkdtemp(suffix=test.change_num)
            try:
                result = test.retrieveResults(tmpPath)
                if not result:
                    logging.info('No result obtained from %s'%test)
                    return
                result_path = os.path.join(CONSTANTS.SFTP_COMMON, test.change_ref)
                copy_logs(['%s/*'%tmpPath], os.path.join(CONSTANTS.SFTP_BASE, result_path),
                          CONSTANTS.SFTP_HOST, CONSTANTS.SFTP_USERNAME,
                          paramiko.RSAKey.from_private_key_file(CONSTANTS.SFTP_KEY))
                logging.info('Uploaded results for %s'%test)
                test.update(result=result,
                            logs_url='http://%s/'%result_path,
                            report_url='http://%s/'%result_path)
                test.update(state=COLLECTED)
            finally:
                shutil.rmtree(tmpPath)
            self.nodepool.deleteNode(test.node_id)
            test.update(node_id=0)

    def postResults(self):
        allTests = Test.getAllWhere(self.db, state=COLLECTED)
        logging.info('%d tests ready to be posted...'%len(allTests))
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
        if get_project_config(event.change.project) != None:
            logging.info("Event %s is matching event criteria"%event)
            return True
    return False

def get_project_config(submitted_project):
    for project_name in CONSTANTS.PROJECT_CONFIG.keys():
        if submitted_project.endswith('/%s'%project_name):
            project_config = CONSTANTS.PROJECT_CONFIG[project_name]
            return project_config
    return None

def are_files_matching_criteria_event(event):
    change_ref = event.patchset.ref
    submitted_project = event.change.project
    logging.info("Checking for file match criteria changeref: %s, project: %s" %
                 (change_ref, submitted_project))
    
    project_config = get_project_config(event.change.project)
    if project_config != None:
        files_matched, commitid = are_files_matching_criteria(project_config['repo_path'],
                                                              project_config["review_repo"],
                                                              project_config["files_to_check"],
                                                              project_config["files_to_ignore"],
                                                              change_ref)
        if files_matched:
                return True
    return False
    
def execute_command(command, delimiter=' ', silent=False, return_streams=False):
    command_as_array = command.split(delimiter)
    if not silent:
        logging.debug("Executing command: " + str(command)) 
    p = subprocess.Popen(command_as_array,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = p.communicate()
    if p.returncode != 0:
        if not silent:
            logging.error("Error: Could not execute command " + str(command)  + ". Failed with errors " + str(errors))
    if not silent:
        logging.debug("Output: " + str(output))
    
    if return_streams:
        return p.returncode, output, errors
    return p.returncode == 0

def is_file_matching_criteria(submitted_file, files_to_check, files_to_ignore):
    while True:
        if submitted_file in files_to_check:
            return True
        if submitted_file in files_to_ignore:
            return False
        
        if os.path.sep in submitted_file:
            submitted_file = os.path.dirname(submitted_file)
        else:
            break
    return '' in files_to_check

def are_files_matching_criteria(local_repo_path, review_repo_url, files_to_check, files_to_ignore, change_ref):
    """ Check out the even from the depot """
    """git show --name-only  --pretty="format:" HEAD # displays the files"""
    """  Issue checkout using command line"""

    """ Check the files and see if they are matching criteria"""

    # Would love to short-circuit here, but can't because we want the commit ID
    #if len(files_to_ignore) == 0 and files_to_check == ['']:
    #    return True, commit_id

    if not os.path.exists(local_repo_path):
        os.makedirs(local_repo_path)
    os.chdir(local_repo_path)
    if not os.path.exists(os.path.join(local_repo_path, '.git')):
        logging.info("Initial clone of repo (may take a long time)")
        execute_command("git clone -o "+CONSTANTS.REVIEW_REPO_NAME+" "+review_repo_url+" "+local_repo_path)

    logging.info("Fetching the changes submitted")
    is_executed = execute_command("git checkout master")
    if not is_executed:
        return False, None
    
    #git fetch https://review.openstack.org/openstack/neutron refs/changes/24/57524/9 &&    
    is_executed = execute_command("git fetch " + review_repo_url + " " + change_ref)
    if not is_executed:
        return False, None
    is_executed = execute_command("git checkout FETCH_HEAD")
    if not is_executed:
        return False, None
    
    repo = Repo(local_repo_path)

    # TODO patch the inspection repo with the commit in patch
    # resetting firs the reference to master branch
    review_remote = None
    for remote in repo.remotes:
        if remote.name == CONSTANTS.REVIEW_REPO_NAME:
            review_remote=remote
            break
    if not review_remote:
        logging.error("Unable to find review repo. It is used to check if files are matched")
        return False, None
    
    headcommit = repo.head.commit
    commitid = headcommit.hexsha
    submitted_files = headcommit.stats.files.keys()
    for submitted_file in submitted_files:
        if is_file_matching_criteria(submitted_file, files_to_check, files_to_ignore):
            logging.info("Some files changed match the test criteria")
            return True, commitid

    return False, None

def vote(commitid, vote_num, message):
    #ssh -p 29418 review.example.com gerrit review -m '"Test failed on MegaTestSystem <http://megatestsystem.org/tests/1234>"'
    # --verified=-1 c0ff33
    logging.info("Going to vote commitid %s, vote %s, message %s" % (commitid, vote_num, message))
    if not CONSTANTS.VOTE_NEGATIVE and vote_num == "-1":
        logging.error("Did not vote -1 for commitid %s, vote %s" % (commitid, vote_num))
        vote_num = "0"
        message += "\n\nNegative vote suppressed"
    vote_cmd = "ssh$-p$%d$%s@%s$gerrit$review"%(CONSTANTS.GERRIT_PORT, CONSTANTS.GERRIT_USERNAME, CONSTANTS.GERRIT_HOST)
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
    change_ref = event.patchset.ref
    project_config = get_project_config(event.change.project)
    if project_config != None:
        project_name = project_config['name']
        commitid = event.patchset.revision
        queue.addTest(change_ref, project_name, commitid)

def check_for_change_ref(option, opt_str, value, parser):
    if not parser.values.change_ref:
        raise OptionValueError("can't use %s, Please provide --change_ref/-c before %s" % (opt_str, opt_str))
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
    parser.add_option('--failures', dest='failures',
                      action='store_true', default=False,
                      help="List the failures recorded by the system")
    parser.add_option('--show', dest='show',
                      action='store_true', default=False,
                      help="Show details for a specific test recorded by the system")

    (options, _args) = parser.parse_args()
    if options.change_ref and not options.project:
        parser.error('Can only use --change_ref with --project')

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(format=u'%(asctime)s %(levelname)s %(message)s',
                        level=level)

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
        project_config = CONSTANTS.PROJECT_CONFIG[options.project]
        files_matched, commitid = are_files_matching_criteria(project_config['repo_path'],
                                                              project_config["review_repo"],
                                                              project_config["files_to_check"],
                                                              project_config["files_to_ignore"],
                                                              options.change_ref)
        if files_matched:
            queue.addTest(options.change_ref, options.project, commitid)
        else:
            logging.error("Changeref specified does not match file match criteria")
        return

    if options.list:
        t = PrettyTable(["Project", "Change", "State", "IP", "Result", "Age (hours)", "Duration"])
        t.align = 'l'
        now = time.time()
        allTests = Test.getAllWhere(queue.db)
        state_dict = {}
        result_dict = {}
        for test in allTests:
            if test.node_id:
                node_ip = test.node_ip
            else:
                node_ip = '(%s)'%test.node_ip
            updated = time.mktime(test.updated.timetuple())
            age = '%.02f' % ((now - updated) / 3600)
            duration = '-'
            
            if test.test_started and test.test_stopped:
                started = time.mktime(test.test_started.timetuple())
                stopped = time.mktime(test.test_stopped.timetuple())
                duration = "%.02f"%((stopped - started)/3600)
            t.add_row([test.project_name, test.change_ref, STATES[test.state], node_ip, test.result, age, duration])
            state_count = state_dict.get(STATES[test.state], 0)+1
            state_dict[STATES[test.state]] = state_count
            result_count = result_dict.get(test.result, 0)+1
            result_dict[test.result] = result_count
        print state_dict
        print result_dict
        print t
        return
    
    if options.failures:
        t = PrettyTable(["Project", "Change", "State", "Result", "Duration", "URL"])
        t.align = 'l'
        now = time.time()
        allTests = Test.getAllWhere(queue.db, result='Failed')
        for test in allTests:
            if test.node_id:
                node_ip = test.node_ip
            else:
                node_ip = '(%s)'%test.node_ip
            updated = time.mktime(test.updated.timetuple())
            age = '%.02f' % ((now - updated) / 3600)
            duration = '-'
            
            if test.test_started and test.test_stopped:
                started = time.mktime(test.test_started.timetuple())
                stopped = time.mktime(test.test_stopped.timetuple())
                duration = "%.02f"%((stopped - started)/3600)
            t.add_row([test.project_name, test.change_num, STATES[test.state], test.result, duration, test.logs_url])
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
                    if are_files_matching_criteria_event(event):
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
