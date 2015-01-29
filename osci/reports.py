from __future__ import print_function

import argparse
import logging
import re
import time

from prettytable import PrettyTable

from osci.nodepool_manager import NodePool
from osci.config import Configuration
from osci.job_queue import JobQueue
from osci import constants
from osci.job import Job
from osci import db


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                      default=False, help='enable verbose (debug) logging')

    subparsers = parser.add_subparsers()
    parser_list = subparsers.add_parser('list')
    parser_list.set_defaults(func=func_list)
    parser_list.add_argument('--states', dest='states',
                             action='store', default=None,
                             help="Only include jobs in this state. "+\
                             "Comma separated from %s"%(
                                 ', '.join(constants.STATES.values())))
    parser_list.add_argument('--recent', dest='recent',
                             action='store', default="24",
                             help="Include only recent jobs (hours)")

    parser_show = subparsers.add_parser('show')
    parser_show.set_defaults(func=func_show)
    parser_show.add_argument('change_ref',
                             help="One time job on a change-ref "+\
                             "e.g. refs/changes/55/7155/1")

    parser_fail = subparsers.add_parser('failures')
    parser_fail.set_defaults(func=func_failures)
    parser_fail.add_argument('--recent', dest='recent',
                             action='store', default="24",
                             help="Include only recent jobs (hours)")
    parser_fail.add_argument('--with-fail', dest='withfail',
                             action='store', default=None,
                             help="Include only jobs with this failure")
    parser_fail.add_argument('--max-fails', dest='max_fails',
                             action='store', default="10",
                             help="Include only jobs with at most this number of failures")
    parser_fail.add_argument('--min-dup', dest='min_dup',
                             action='store', default="2",
                             help="Include only fails with at least this number of duplicates")

    return parser

def func_list(options, queue):
    table = PrettyTable(["ID", "Project", "Change", "State", "IP", "Result",
                         "Age (hours)", "Duration"])
    table.align = 'l'
    now = time.time()
    all_jobs = Job.getRecent(queue.db, int(options.recent))
    state_dict = {}
    result_dict = {}
    if options.states and len(options.states) > 0:
        states = options.states.split(',')
    else:
        # Default should be everything except obsolete jobs
        states = constants.STATES.values()
        states.remove(constants.STATES[constants.OBSOLETE])

    for job in all_jobs:
        updated = time.mktime(job.updated.timetuple())
        age_hours = (now - updated) / 3600
        state_count = state_dict.get(constants.STATES[job.state], 0) + 1
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
        table.add_row([job.id, job.project_name, job.change_ref,
                       constants.STATES[job.state], node_ip, job.result,
                       age, duration])
    output_str = str(state_dict)+"\n"
    output_str = output_str + str(result_dict)+"\n"
    output_str = output_str + str(table)
    return output_str

def func_show(options, queue):
    output_str = ''
    jobs = Job.getAllWhere(queue.db, change_ref=options.change_ref)
    for job in jobs:
        table = PrettyTable()
        table.add_column('Key', ['ID', 'Project name', 'Change num', 'Change ref',
                                 'state', 'created', 'Commit id', 'Node id',
                                 'Node ip', 'Result', 'Logs', 'Report',
                                 'Updated', 'Gerrit URL', 'Failures'])
        url = 'https://review.openstack.org/%s'%job.change_num
        table.add_column('Value',
                         [job.id, job.project_name, job.change_num, job.change_ref,
                          constants.STATES[job.state], job.created,
                          job.commit_id, job.node_id, job.node_ip,
                          job.result, job.logs_url, job.report_url,
                          job.updated, url, job.failed])
        table.align = 'l'
        output_str = output_str + str(table)+'\n'
    return output_str

def func_failures(options, queue):
    output_str = ''
    table = PrettyTable(["ID", "Project", "Change", "State", "Result", "Age",
                             "Duration", "URL"])
    table.align = 'l'
    now = time.time()
    all_jobs = Job.getRecent(queue.db, int(options.recent))
    all_failed_tests = {}
    for job in all_jobs:
        if not job.result or (job.result != 'Failed' and
                              job.result.find('Aborted') != 0):
            continue
        updated = time.mktime(job.updated.timetuple())
        age_hours = (now - updated) / 3600
        age = '%.02f' % (age_hours)

        duration = '-'
        if job.test_started and job.test_stopped:
            started = time.mktime(job.test_started.timetuple())
            stopped = time.mktime(job.test_stopped.timetuple())
            duration = "%.02f"%((stopped - started)/3600)

        job_failed = job.failed if job.failed is not None else ''
        failed_tests = [m.group(0) for m in re.finditer('tempest.[^ ()]+', job_failed)]

        if options.withfail is not None:
            if len(options.withfail) == 0:
                if len(failed_tests) != 0:
                    continue
            else:
                if options.withfail not in job.failed:
                    continue

        table.add_row([job.id, job.project_name, job.change_num,
                       constants.STATES[job.state], job.result, age,
                       duration, job.logs_url])

        if len(failed_tests) == 0:
            failed_tests = ['No tempest failures detected']
        elif int(options.max_fails) > 0 and len(failed_tests) > int(options.max_fails):
            failed_tests = ['More than %s failures'%options.max_fails]

        for failed_test in failed_tests:
            # Treat JSON and XML as the same since we're only interested in driver failures
            failed_test = failed_test.replace('JSON', '')
            failed_test = failed_test.replace('XML', '')
            cur_count = all_failed_tests.get(failed_test, 0)
            all_failed_tests[failed_test] = cur_count + 1

    if options.min_dup:
        msg='Fewer than %s duplicates'%options.min_dup
        for failed_test in list(all_failed_tests.keys()):
            if all_failed_tests[failed_test] < int(options.min_dup):
                cur_count = all_failed_tests.get(msg, 0)
                all_failed_tests[msg] = cur_count + 1
                del all_failed_tests[failed_test]

    output_str += str(table) + '\n'
    output_str += '\n'
    output_str += 'Failures\n'
    output_str += '-------------------\n'

    single_count =0
    sorted_tests = sorted(all_failed_tests, key=all_failed_tests.get, reverse=True)
    for failed_test in sorted_tests:
        output_str += "%3d %s\n"%(all_failed_tests[failed_test], failed_test)
    return output_str

def main():
    parser = get_parser()
    options = parser.parse_args()

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
        filesystem=None,
        uploader=None,
        executor=None)

    print(options.func(options, queue))
