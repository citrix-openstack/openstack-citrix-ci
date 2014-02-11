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
import logging
import optparse
import re
import sys
import time
import datetime
import os

import MySQLdb

""" importing python git commands """
from git import Repo

class CONSTANTS:
    REMOTE=False
    TEST_SCRIPT = '/spare/nsmkernel/usr.src/sdx/controlcenter/build_resources/test_infra/sync_and_test.sh'
    UPLOAD_SCRIPT = '/spare/nsmkernel/usr.src/sdx/controlcenter/build_resources/test_infra/sharefile_upload.py'
    MYSQL_URL = '127.0.0.1'
    MYSQL_USERNAME = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'openstack_ci'
    SSH_PERFORCE = 'root@10.102.31.70'
    TEMP_PATH_FOR_REMOTE = "/tmp"
    POLL = 30
    RECHECK_REGEXP = re.compile("^(recheck bug|recheck nobug)")
    RESULTS_OUT = "/tmp/result.out"
    UPLOAD_FILES = False
    VOTE=False
    VOTE_NEGATIVE=False
    VOTE_MESSAGE = "Nova/Tempest testing %(result)s using XenAPI driver with XenServer 6.2.\n"+\
                   "Please find the results at %(report)s and logs at %(log)s "
    REVIEW_REPO_NAME='review'
    PROJECT_CONFIG={
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
            }
        }

def db_execute(db, sql):
    cur = db.cursor()
    try:
        cur.execute(sql)
        db.commit()
    except:
        db.rollback()

def db_query(db, sql):
    cur = db.cursor()
    cur.execute(sql)
    results = cur.fetchall()
    db.commit()
    return results

class Test():
    def __init__(self, change_num=None, change_ref=None, project_name=None, commit_id=None):
        self.project_name = project_name
        self.change_num = change_num
        self.change_ref = change_ref
        self.state = 'queued'
        self.created = datetime.datetime.now()
        self.commit_id = commit_id
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

        return retVal

    @classmethod
    def createTable(cls, db):
        logging.info('Creating table...')
        sql = 'CREATE TABLE IF NOT EXISTS test'+\
              '('+\
              ' project_name VARCHAR(50),' +\
              ' change_num VARCHAR(10),' +\
              ' change_ref VARCHAR(50),' +\
              ' state VARCHAR(50),'+\
              ' created DATETIME,' +\
              ' commit_id VARCHAR(50),'+\
              ' node_ip VARCHAR(50),'+\
              ' result VARCHAR(10),'+\
              ' logs_url VARCHAR(200),'+\
              ' report_url VARCHAR(200),'+\
              ' PRIMARY KEY (project_name, change_num)'+\
              ')'
        db_execute(db, sql)
        logging.info('...Done')

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
            retRecords.append(Test.fromRecord(result))

        return retRecords
    
    @classmethod
    def retrieve(cls, db, project_name, change_num):
        sql = 'SELECT * FROM test WHERE'+\
              ' project_name="%s"'+\
              ' AND change_num="%s"'
        results = db_query(db, sql%(project_name, change_num))
        if len(results) == 0:
            return None
        
        return Test.fromRecord(results[0])

    def insert(self, db):
        SQL = 'INSERT INTO test(project_name, change_num, change_ref, state, created, commit_id) '+\
              'VALUES("%s","%s","%s","%s","%s","%s")'%(
            self.project_name, self.change_num, self.change_ref,
            self.state, self.created, self.commit_id)
        db_execute(db, SQL)
        logging.info("Job for %s queued"%self.change_num)

    def update(self, db, **kwargs):
        sql = 'UPDATE test SET'
        for key, value in kwargs.iteritems():
            sql += ' %s="%s",'%(key, value)
            setattr(self, key, value)

        assert sql[-1:] == ","
        sql = sql[:-1] # Strip off the last ,
        sql += ' WHERE project_name="%s" AND change_num="%s"'%(self.project_name, self.change_num)
        db_execute(db, sql)

    def delete(self, db):
        if self.state == 'running':
            self.killJob()
        SQL = 'DELETE FROM test WHERE project_name="%s" AND change_num="%s"'
        db_execute(db, SQL%(self.project_name, self.change_num))

    def killJob(self):
        logging.error('KILL JOB NOT IMPLEMENTED')

    def __repr__(self):
        return "%(project_name)s/%(change_ref)s commit:%(commit_id)s state:%(state)s created:%(created)s" %self

    def __getitem__(self, item):
        return getattr(self, item)

def getNode():
    return None

class TestQueue():
    def __init__(self, host, username, password, database_name):
        self.db = MySQLdb.connect(host=host,
                                  user=username,
                                  passwd=password)
        self.initDB(database_name)
        
    def initDB(self, database):
        cur = self.db.cursor()
        try:
            logging.info('Using database...')
            cur.execute('USE %s'%database)
        except:
            logging.info('Creating + using database...')
            cur.execute('CREATE DATABASE %s'%database)
            cur.execute('USE %s'%database)
            
        Test.createTable(self.db)
    
    def addTest(self, change_ref, project_name, commit_id):
        change_num = change_ref.split('/')[3]
        existing = Test.retrieve(self.db, project_name, change_num)
        if existing:
            if existing.change_ref == change_ref:
                logging.info('Test already queued as %s'%(existing))
                return
            logging.info('Test for previous patchset (%s) already queued - replacing'%(existing))
            existing.delete(self.db)
        test = Test(change_num, change_ref, project_name, commit_id)
        test.insert(self.db)

    def triggerJobs(self):
        allTests = Test.getAllWhere(self.db, state='queued')
        count = len(allTests)
        for test in allTests:
            node_ip = getNode()
            if node_ip is None:
                logging.debug('Waiting for node for %d jobs...'%count)
                return
            count -= 1
            test.update(self.db, node_ip=node_ip)
            logging.info('Running job for %s'%test)
            test.update(self.db, state='running')

    def processResults(self):
        allTests = Test.getAllWhere(self.db, state='running')
        for test in allTests:
            logging.info('Collected results for %s'%test)
            test.update(self.db, result='Passed', log_url='http://logs', summary_url='http://summary')
            test.update(self.db, state='collected')
            deleteNode(test.node_ip)

    def postResults(self):
        allTests = Test.getAllWhere(self.db, state='collected')
        if not CONSTANTS.VOTE:
            logging.info('Not voting on %d tests which are ready to be voted on'%(len(allTests)))
            return

        for test in allTests:
            logging.info('Posted results for %s'%test)
            test.update(self.db, state='collected')

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
        if submitted_project.endswith(project_name):
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
    
def test_changes(change_ref, submitted_project, commitid, stacksh="SKIP"):
    logging.info("Calling test procedures to test changeref: %s, project: %s" % (change_ref, submitted_project))
    if CONSTANTS.REMOTE:
        p = subprocess.Popen(['ssh', CONSTANTS.SSH_PERFORCE , CONSTANTS.TEST_SCRIPT, stacksh, change_ref, 
                              submitted_project],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        p = subprocess.Popen([CONSTANTS.TEST_SCRIPT, stacksh, change_ref, 
                              submitted_project],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    output, errors = p.communicate()
    if errors:
        logging.error("Error: Could not test changes for change: " + change_ref + ". Failed with message: " + errors)
        return False
    else:
        logging.info("Successfully tested changes for change: " + change_ref)
        result = parse_result()
        if 'LOG' not in result or 'REPORT' not in result:
            logging.error("Error: Could not read result...")
            return False
        else:
            logging.info("Report of test run: " + result['REPORT'])
             
        if CONSTANTS.UPLOAD_FILES:
            if CONSTANTS.REMOTE:
                logging.info("Uploading test output...")
                p = subprocess.Popen(['ssh', CONSTANTS.SSH_PERFORCE, '/var/nsmkernel/usr.src/usr/local/bin/python',
                                      CONSTANTS.UPLOAD_SCRIPT,result['LOG'], result['REPORT']],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, errors = p.communicate()
                if errors:
                    logging.error("Error: Could not upload test output: " + errors)
                    return False
                else:
                    logging.debug("Successfully uploaded test output...")
                    
                result = parse_result()
                log_url = result['LOGURL']
                report_url = result['REPORTURL']
            else:
                log_url = sharefile_upload.logs_upload(result['LOG'], result['REPORT'])

            # Now Vote
            
            if 'failure' in result['REPORT']:
                vote_num = "-1"
                vote_result = "FAILED"
            else:
                vote_num = "+1"
                vote_result = "PASSED"
            vote(commitid, vote_num, CONSTANTS.VOTE_MESSAGE%{'result': vote_result,
                                                             'report': report_url,
                                                             'log': log_url})
        return True
    
def execute_command(command, delimiter=' '):
    command_as_array = command.split(delimiter)
    logging.debug("Executing command: " + str(command)) 
    p = subprocess.Popen(command_as_array,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = p.communicate()
    if p.returncode != 0:
        logging.error("Error: Could not exuecute command " + str(command)  + ". Failed with errors " + str(errors))
        return False
    logging.debug("Output command: " + str(output))
    
    return True

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
#git fetch https://review.openstack.org/openstack/neutron refs/changes/24/57524/9 && git checkout FETCH_HEAD
#git fetch https://review.openstack.org/openstack/tempest refs/changes/97/58697/16 && git checkout FETCH_HEAD

    """ Check the files and see if they are matching criteria"""

    if not os.path.exists(local_repo_path):
        os.makedirs(local_repo_path)
    os.chdir(local_repo_path)
    if not os.path.exists(os.path.join(local_repo_path, '.git')):
        logging.info("Initial clone of repo (may take a long time)")
        execute_command("git clone -o "+CONSTANTS.REVIEW_REPO_NAME+" "+review_repo_url+" "+local_repo_path)

#git fetch https://review.openstack.org/openstack/neutron refs/changes/24/57524/9 &&    
    logging.info("Fetching the changes submitted")
    is_executed = execute_command("git checkout master")
    if not is_executed:
        return False, None
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
    if CONSTANTS.VOTE:
        if not CONSTANTS.VOTE_NEGATIVE and vote_num == "-1":
            logging.error("Did not vote -1 for commitid %s, vote %s" % (commitid, vote_num))
            return
        vote_cmd = """ssh$-i$/opt/stack/.ssh/service_account$-p$29418$review.openstack.org$gerrit$review"""
        vote_cmd = vote_cmd + "$-m$'\"" + message + "\"'$--verified=" + vote_num + "$" + commitid
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

def parse_result():
    result = {}
    if CONSTANTS.REMOTE:
        p = subprocess.Popen(['ssh', CONSTANTS.SSH_PERFORCE, 'cat', CONSTANTS.RESULTS_OUT],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#        p = subprocess.Popen(['cat', CONSTANTS.TEMP_PATH_FOR_REMOTE+"/1.html"],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, errors = p.communicate()
        if errors:
            logging.error("Error: Understanding the result: " + errors)
        else:
            logging.debug("Successfully parsed the result.\n****RESULT****\n " + output)
            
            lines = output.splitlines()
            for line in lines:
                (key,value) = line.split('=')
                result[key]=value.rstrip()
    else:
        file_path = CONSTANTS.RESULTS_OUT
        f = open(file_path, 'r')
        for line in f:
            (key,value) = line.split('=')
            result[key]=value.rstrip()
        f.close()
    return result

def check_for_change_ref(option, opt_str, value, parser):
    if not parser.values.change_ref:
        raise OptionValueError("can't use %s, Please provide --change_ref/-c before %s" % (opt_str, opt_str))
    setattr(parser.values, option.dest, value)

def _main():
    usage = "usage: %prog [options]"
    
    parser = optparse.OptionParser(usage=usage)
    # 198.101.231.251 is review.openstack.org. For some vague reason the dns entry from inside pygerrit is not resolved.
    # It throws an error "ERROR Gerrit error: Failed to connect to server: [Errno 101] Network is unreachable"
    parser.add_option('-g', '--gerrit-hostname', dest='hostname',
                      default='198.101.231.251',
                      help='gerrit server hostname (default: %default)')
    parser.add_option('-p', '--port', dest='port',
                      type='int', default=29418,
                      help='port number (default: %default)')
    parser.add_option('-u', '--username', dest='username',
                      help='username', default='bob-ball')
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

    (options, _args) = parser.parse_args()
    if options.change_ref and not options.project:
        parser.error('Can only use --change_ref with --project')

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(format=u'%(asctime)s %(levelname)s %(message)s',
                        level=level)

    queue = TestQueue(CONSTANTS.MYSQL_URL, CONSTANTS.MYSQL_USERNAME, CONSTANTS.MYSQL_PASSWORD, CONSTANTS.MYSQL_DB)

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
    
    # Starting the loop for listening to Gerrit events
    try:
        logging.info("Connecting to gerrit host " + options.hostname)
        logging.info("Connecting to gerrit username " + options.username)
        logging.info("Connecting to gerrit port " + str(options.port))
        gerrit = GerritClient(host=options.hostname,
                              username=options.username,
                              port=options.port)
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
            queue.triggerJobs()
            queue.processResults()
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
