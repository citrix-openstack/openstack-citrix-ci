import logging
import optparse
import re
import time

from prettytable import PrettyTable
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


def get_parser():
    usage = "usage: %prog [options]"

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      default=False, help='enable verbose (debug) logging')
    parser.add_option('-c', '--change-ref', dest='change_ref', action="store",
                      type="string", help="One time job on a change-ref "+\
                      "e.g. refs/changes/55/7155/1")

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

    queue = JobQueue(
        database=database,
        nodepool=NodePool(Configuration().NODEPOOL_IMAGE),
        filesystem=filesystem_services.RealFilesystem(),
        uploader=swift_upload.SwiftUploader(),
        executor=utils.execute_command)
    
    if options.change_ref:
        change_num, patchset = options.change_ref.split('/')[-2:]
        patch_details = utils.get_patchset_details(change_num, patchset)
        # Verify we got the right patch back
        queue.addJob(patch_details['ref'], patch_details['project'], patch_details['revision'])
        return

    queue.startCleanupThreads()

    try:
        while True:
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

