import datetime
import time
import logging

from osci import node
from osci import executor
from osci import instructions
from osci import environment
from osci import gerrit
from osci import event_target
from osci import db
from osci import job_queue
from osci import time_services
from osci import config as osci_config


log = logging.getLogger(__name__)


def _add_executor_args(parser):
    parser.add_argument(
        'executor',
        choices=executor.EXECUTOR_NAMES.keys()
    )


class CheckConnection(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = executor.create_executor(env.get('executor'))
        config = osci_config.Configuration()
        self.node = node.Node(dict(
                node_username=config.NODE_USERNAME,
                node_host=env['node_host'],
                node_keyfile=config.NODE_KEY
            )
        )

    @classmethod
    def add_arguments_to(cls, parser):
        _add_executor_args(parser)
        parser.add_argument('node_host', help='Node to connect to')

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
        self.project_name = env.get('project_name')
        self.test_runner_url = env.get(
            'test_runner_url',
            'https://git.openstack.org/stackforge/xenapi-os-testing'
        )

    @classmethod
    def add_arguments_to(cls, parser):
        _add_executor_args(parser)
        node.Node.add_arguments_to(parser)
        parser.add_argument('change_ref')
        parser.add_argument('project_name')
        parser.add_argument('test_runner_url', help="Specify the url for "
                "xenapi-os-testing repository")

    def __call__(self):
        self.executor.run(
            self.node.run(
                instructions.check_out_testrunner(self.test_runner_url)
            )
        )

        if self.project_name == 'stackforge/xenapi-os-testing':
            for instruction in instructions.update_testrunner(self.change_ref):
                self.executor.run(
                    self.node.run(instruction)
                )

        self.executor.run(
            self.node.run(
                environment.get_environment(self.project_name, self.change_ref)
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
        recent_seconds = int(env.get('recent_event_time', self.DEFAULT_EVENT_TIME))
        self.recent_event_time = datetime.timedelta(seconds=recent_seconds)

    @classmethod
    def add_arguments_to(cls, parser):
        parser.add_argument('gerrit_client')
        parser.add_argument('gerrit_host')
        parser.add_argument('event_target')
        parser.add_argument('gerrit_port')
        parser.add_argument('gerrit_username')
        parser.add_argument('dburl')
        parser.add_argument('comment_re')
        parser.add_argument('projects')

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

    def __call__(self):
        self.gerrit_client.connect()
        self.last_event = time_services.now()
        try:
            while self.event_seen_recently():
                self.do_event_handling()
                self.sleep()
            log.info("No events seen in %s seconds" % self.recent_event_time)
        except GerritEventError as e:
            log.exception(e)
        self.gerrit_client.disconnect()
