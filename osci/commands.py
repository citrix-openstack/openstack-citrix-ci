import datetime
import time
import logging

from osci import node
from osci import executor
from osci import logserver
from osci import instructions
from osci import environment
from osci import gerrit
from osci import event_target
from osci import db
from osci import job_queue
from osci import time_services


log = logging.getLogger(__name__)


class CheckConnection(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = executor.create_executor(env.get('executor'))
        self.node = node.Node(env)
        self.logserver = logserver.Logserver(env)

    @classmethod
    def parameters(cls):
        return (
            ['executor']
            + node.Node.parameters()
            + logserver.Logserver.parameters()
        )

    def __call__(self):
        checks = [
            (
                'Connection to Node',
                self.node.run(['true'])
            ),
            (
                'Connection from Node to dom0',
                self.node.run_on_dom0(['true'])
            ),
            (
                'Connection to Logserver',
                self.logserver.run(['true'])
            ),
        ]

        for message, args in checks:
            print message
            if 0 == self.executor.run(args):
                print "OK"
            else:
                print "FAIL, aborting"
                return 1

        return 0


class RunTests(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = executor.create_executor(env.get('executor'))
        self.node = node.Node(env)
        self.change_ref = env.get('change_ref')

    @classmethod
    def parameters(cls):
        return ['executor'] + node.Node.parameters() + ['change_ref']

    def __call__(self):
        self.executor.run(
            self.node.scp(
                'tempest_exclusion_list', '/tmp/tempest_exclusion_list')
        )

        self.executor.run(
            self.node.run(instructions.check_out_testrunner())
        )

        self.executor.run(
            self.node.run(
                environment.get_environment(self.change_ref)
                + instructions.execute_test_runner())
        )



class CreateDBSchema(object):
    def __init__(self, env=None):
        logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)
        env = env or dict()
        self.database = None
        self.database = db.DB(env.get('dburl'))

    @classmethod
    def parameters(cls):
        return ['dburl']

    def __call__(self):
        self.database.create_schema()

class GerritEventError(Exception):
    pass

class WatchGerrit(object):
    DEFAULT_SLEEP_TIMEOUT = 5
    DEFAULT_EVENT_TIME = 600
    
    def __init__(self, env=None):
        logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)
        env = env or dict()
        self.database = None
        self.queue = None

        dburl = env.get('dburl')

        if dburl:
            log.info('dburl=%s', dburl)
            self.database = db.DB(dburl)
            self.queue = job_queue.JobQueue(
                database=self.database,
                nodepool=None,
                filesystem=None,
                uploader=None,
                executor=None
            )

        self.gerrit_client = gerrit.get_client(env)
        self.event_filter = gerrit.get_filter(env)
        self.error_filter = gerrit.get_error_filter(env)
        log.info("Event filter: %s", self.event_filter)
        self.event_target = event_target.get_target(dict(env, queue=self.queue))
        self.sleep_timeout = int(env.get('sleep_timeout',
                                         self.DEFAULT_SLEEP_TIMEOUT))
        self.last_event = time_services.now()
        recent_seconds = int(env.get('recent_event_time', self.DEFAULT_EVENT_TIME))
        self.recent_event_time = datetime.timedelta(seconds=recent_seconds)

    @classmethod
    def parameters(cls):
        return [
            'gerrit_client', 'gerrit_host', 'event_target',
            'gerrit_port', 'gerrit_username', 'dburl', 'comment_re',
            'projects']

    def get_event(self):
        event = self.gerrit_client.get_event()
        if event is not None:
            self.last_event = time_services.now()
        return event

    def event_seen_recently(self):
        now = time_services.now()
        return (now - self.last_event) < self.recent_event_time

    def consume_event(self, event):
        self.event_target.consume_event(event)

    def sleep(self):
        time.sleep(self.sleep_timeout)

    def do_event_handling(self):
        event = self.get_event()
        while event:
            if self.event_filter.is_event_matching_criteria(event):
                log.info("Consuming event [%s]", event)
                self.consume_event(event)
            elif self.error_filter.is_event_matching_criteria(event):
                raise GerritEventError('Event [%s] matched error filter'%event)
            event = self.get_event()

    def _retry_connect(self):
        return True

    def __call__(self):
        while self._retry_connect():
            self.gerrit_client.connect()
            try:
                while self.event_seen_recently():
                    self.do_event_handling()
                    self.sleep()
            except GerritEventError, e:
                log.exception(e)
            self.gerrit_client.disconnect()
