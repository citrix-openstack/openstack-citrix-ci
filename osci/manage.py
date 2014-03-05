import logging
import optparse
import re
import time

from prettytable import PrettyTable
from pygerrit.client import GerritClient
from pygerrit.error import GerritError
from pygerrit.events import ErrorEvent, PatchsetCreatedEvent, CommentAddedEvent
from threading import Event

from osci.nodepool_manager import NodePool
from osci.config import Configuration
from osci.job_queue import JobQueue
from osci import constants
from osci.job import Job
from osci import utils
from osci import db
from osci import filesystem_services
from osci import swift_upload


def is_event_matching_criteria(event):
    if isinstance(event, CommentAddedEvent):
        comment = event.comment
        comment_regexp = re.compile(Configuration().RECHECK_REGEXP, re.IGNORECASE)
        if not comment_regexp.match(comment):
            return False
        logging.debug("Comment matched: %s", comment)
    elif not isinstance(event, PatchsetCreatedEvent):
        return False
    if event.change.branch == "master":
        if is_project_configured(event.change.project):
            logging.info("Event %s is matching event criteria", event)
            return True
    return False

def is_project_configured(submitted_project):
    return submitted_project in Configuration().PROJECT_CONFIG.split(',')

def queue_event(queue, event):
    logging.info("patchset values : %s", event)
    if is_project_configured(event.change.project):
        queue.addJob(event.patchset.ref,
                      event.change.project,
                      event.patchset.revision)

def get_parser():
    usage = "usage: %prog [options]"

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      default=False, help='enable verbose (debug) logging')
    parser.add_option('-c', '--change-ref', dest='change_ref', action="store",
                      type="string", help="One time job on a change-ref "+\
                      "e.g. refs/changes/55/7155/1")
    parser.add_option('--list', dest='list',
                      action='store_true', default=False,
                      help="List the jobs recorded by the system")
    parser.add_option('--states', dest='states',
                      action='store', default=None,
                      help="(Use with --list): States to list")
    parser.add_option('--failures', dest='failures',
                      action='store_true', default=False,
                      help="List the failures recorded by the system")
    parser.add_option('--recent', dest='recent',
                      action='store', default=None,
                      help="List jobs less than this many hours old")
    parser.add_option('--show', dest='show',
                      action='store_true', default=False,
                      help="Show details for a specific job")

    return parser

def main():
    parser = get_parser()
    (options, _) = parser.parse_args()

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(
        format=u'%(asctime)s %(levelname)s %(name)s %(message)s',
        level=level)

    # Lower the warning levels of a number of loggers
    for logger_name in ['paramiko.transport', 'paramiko.transport.sftp',
                        'requests.packages.urllib3.connectionpool',
                        'swiftclient']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    database = db.DB(Configuration().DATABASE_URL)
    database.create_schema()

    queue = JobQueue(
        database=database,
        nodepool=NodePool(Configuration().NODEPOOL_IMAGE),
        filesystem=filesystem_services.RealFilesystem(),
        uploader=swift_upload.SwiftUploader(),
        executor=utils.execute_command)

    if options.show:
        table = PrettyTable()
        table.add_column('Key', ['Project name', 'Change num', 'Change ref',
                                 'state', 'created', 'Commit id', 'Node id',
                                 'Node ip', 'Result', 'Logs', 'Report',
                                 'Updated', 'Gerrit URL'])
        job = Job.getAllWhere(queue.db, change_ref=options.change_ref)[0]
        url = 'https://review.openstack.org/%s'%job.change_num
        table.add_column('Value',
                         [job.project_name, job.change_num, job.change_ref,
                          constants.STATES[job.state], job.created,
                          job.commit_id, job.node_id, job.node_ip,
                          job.result, job.logs_url, job.report_url,
                          job.updated, url])
        table.align = 'l'
        print table
        return

    if options.change_ref:
        change_num, patchset = options.change_ref.split('/')[-2:]
        patch_details = utils.get_patchset_details(change_num, patchset)
        # Verify we got the right patch back
        assert patch_details['ref'] == options.change_ref
        queue.addJob(patch_details['ref'], patch_details['project'], patch_details['revision'])
        return

    if options.list:
        table = PrettyTable(["Project", "Change", "State", "IP", "Result",
                             "Age (hours)", "Duration"])
        table.align = 'l'
        now = time.time()
        all_jobs = Job.getAllWhere(queue.db)
        state_dict = {}
        result_dict = {}
        if options.states and len(options.states) > 0:
            states = options.states.split(',')
        else:
            states = None
        for job in all_jobs:
            updated = time.mktime(job.updated.timetuple())
            age_hours = (now - updated) / 3600
            if options.recent:
                if age_hours > int(options.recent):
                    continue
            state_count = state_dict.get(constants.STATES[job.state], 0)+1
            state_dict[constants.STATES[job.state]] = state_count
            result_count = result_dict.get(job.result, 0)+1
            result_dict[job.result] = result_count

            if states and constants.STATES[job.state] not in states:
                continue
            if job.node_id:
                node_ip = job.node_ip
            else:
                node_ip = '(%s)'%job.node_ip
            age = '%.02f' % (age_hours)
            duration = '-'

            if job.test_started and job.test_stopped:
                started = time.mktime(job.test_started.timetuple())
                stopped = time.mktime(job.test_stopped.timetuple())
                if started < stopped:
                    duration = "%.02f"%((stopped - started)/3600)
            table.add_row([job.project_name, job.change_ref,
                           constants.STATES[job.state], node_ip, job.result,
                           age, duration])
        print state_dict
        print result_dict
        print table
        return

    if options.failures:
        table = PrettyTable(["Project", "Change", "State", "Result", "Age",
                             "Duration", "URL"])
        table.align = 'l'
        now = time.time()
        all_jobs = Job.getAllWhere(queue.db)
        for job in all_jobs:
            if not job.result or (job.result != 'Failed' and
                                   job.result.find('Aborted') != 0):
                continue
            updated = time.mktime(job.updated.timetuple())
            age_hours = (now - updated) / 3600
            if options.recent:
                if age_hours > int(options.recent):
                    continue
            if job.node_id:
                node_ip = job.node_ip
            else:
                node_ip = '(%s)'%job.node_ip
            age = '%.02f' % (age_hours)
            duration = '-'

            if job.test_started and job.test_stopped:
                started = time.mktime(job.test_started.timetuple())
                stopped = time.mktime(job.test_stopped.timetuple())
                duration = "%.02f"%((stopped - started)/3600)
            table.add_row([job.project_name, job.change_num,
                           constants.STATES[job.state], job.result, age,
                           duration, job.logs_url])
        print table
        return

    # Starting the loop for listening to Gerrit events
    try:
        logging.info("Connecting to gerrit host %s",
                     Configuration().GERRIT_HOST)
        logging.info("Connecting to gerrit username %s",
                     Configuration().GERRIT_USERNAME)
        logging.info("Connecting to gerrit port %s",
                     Configuration().GERRIT_PORT)
        gerrit = GerritClient(host=Configuration().GERRIT_HOST,
                              username=Configuration().GERRIT_USERNAME,
                              port=Configuration().get_int('GERRIT_PORT'))
        logging.info("Connected to Gerrit version [%s]",
                     gerrit.gerrit_version())
        gerrit.start_event_stream()
    except GerritError as err:
        logging.error("Gerrit error: %s", err)
        return 1

    last_event = time.time()
    errors = Event()
    try:
        while True:
            event = gerrit.get_event(block=False)
            while event:
                logging.debug("Event: %s", event)
                last_event = time.time()

                if is_event_matching_criteria(event):
                    queue_event(queue, event)

                if isinstance(event, ErrorEvent):
                    logging.error(event.error)
                    errors.set()
                event = gerrit.get_event(block=False)
            if ((time.time() - last_event) > Configuration().get_int('GERRIT_EVENT_TIMEOUT')):
                msg = 'No events from gerrit in required time.  Exiting.'
                raise RuntimeError(msg)
            try:
                queue.postResults()
                queue.processResults()
                queue.triggerJobs()
            except Exception, e:
                logging.exception(e)
                # Ignore exception and try again; keeps the app polling
            time.sleep(Configuration().get_int('POLL'))
    except KeyboardInterrupt:
        logging.info("Terminated by user")
    finally:
        logging.debug("Stopping event stream...")
        gerrit.stop_event_stream()

    if errors.isSet():
        logging.error("Exited with error")
        return 1
