import time

from osci import node
from osci import executor
from osci import logserver
from osci import instructions
from osci import environment
from osci import gerrit
from osci import event_target


class GetDom0Logs(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = executor.create_executor(env.get('executor'))
        self.node = node.Node(env)
        self.logserver = logserver.Logserver(env)
        self.target_dir = env.get('target_dir', 'TARGET_DIR')
        self.sources = env.get('sources', 'SOURCES')

    @classmethod
    def parameters(cls):
        return (
            ['executor']
            + node.Node.parameters()
            + ['sources']
            + logserver.Logserver.parameters()
            + ['target_dir']
        )

    def __call__(self):
        self.executor.pipe_run(
            self.node.run_on_dom0(
                "tar --ignore-failed-read -czf - {0}".format(
                    self.sources).split()
            ),
            self.logserver.run(
                'tar -xzf - -C {0}'.format(self.target_dir).split()
            )
        )


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


class WatchGerrit(object):
    DEFAULT_SLEEP_TIMEOUT = 5

    def __init__(self, env=None):
        env = env or dict()
        self.gerrit_client = gerrit.get_client(env)
        self.event_filter = gerrit.DummyFilter(True)
        self.event_target = event_target.FakeTarget()
        self.sleep_timeout = env.get(
            'sleep_timeout', self.DEFAULT_SLEEP_TIMEOUT)

    @classmethod
    def parameters(cls):
        return [
            'gerrit_client', 'event_target', 'gerrit_host',
            'gerrit_port', 'gerrit_username']

    def get_event(self):
        return self.gerrit_client.get_event()

    def get_filtered_event(self):
        event = self.get_event()
        if self.event_filter.is_event_matching_criteria(event):
            return event

    def consume_event(self, event):
        self.event_target.consume_event(event)

    def sleep(self):
        time.sleep(3)
        return True

    def do_event_handling(self):
        event = self.get_filtered_event()
        if event:
            self.consume_event(event)

    def __call__(self):
        self.gerrit_client.connect()
        while self.sleep():
            self.do_event_handling()
