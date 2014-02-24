import unittest

from osci import commands
from osci import logserver
from osci import node
from osci import executor
from osci import instructions
from osci import environment


COMMON_SSH_OPTS=(
    '-q -o BatchMode=yes -o UserKnownHostsFile=/dev/null'
    ' -o StrictHostKeyChecking=no')
SSH_TO_LOGSERVER=(
    'ssh {SSH_OPTIONS} LOGSERVER_USERNAME@LOGSERVER_HOST'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SCP=(
    'scp {SSH_OPTIONS}'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SSH_TO_NODE=(
    'ssh {SSH_OPTIONS} NODE_USERNAME@NODE_HOST'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SSH_TO_DOMZERO_FROM_NODE=(
    'sudo -u domzero ssh {SSH_OPTIONS} root@192.168.33.2'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split()
)


class TestGetDom0Logs(unittest.TestCase):
    def test_executed_commands(self):
        cmd = commands.GetDom0Logs()

        cmd()
        print executor.fake_pipe(
            SSH_TO_NODE
            + SSH_TO_DOMZERO_FROM_NODE
            + "tar --ignore-failed-read -czf - SOURCES".split(),
            SSH_TO_LOGSERVER
            +'tar -xzf - -C TARGET_DIR'.split()
        )

        self.maxDiff = 4096
        self.assertEquals(
            executor.fake_pipe(
                SSH_TO_NODE
                + SSH_TO_DOMZERO_FROM_NODE
                + "tar --ignore-failed-read -czf - SOURCES".split(),
                SSH_TO_LOGSERVER
                +'tar -xzf - -C TARGET_DIR'.split()
            ),
            cmd.executor.executed_commands[0])

    def test_stars_escaped(self):
        cmd = commands.GetDom0Logs()
        cmd.sources = '*'

        cmd()

        self.maxDiff = 1024
        self.assertEquals(
            executor.fake_pipe(
                SSH_TO_NODE
                + SSH_TO_DOMZERO_FROM_NODE
                + r"tar --ignore-failed-read -czf - \*".split(),
                SSH_TO_LOGSERVER
                +'tar -xzf - -C TARGET_DIR'.split()
            ),
            cmd.executor.executed_commands[0])

    def test_executor_factory(self):
        cmd = commands.GetDom0Logs(dict(executor='print'))
        self.assertEquals('PrintExecutor', cmd.executor.__class__.__name__)

    def test_target_dir(self):
        cmd = commands.GetDom0Logs(dict(target_dir='target'))
        self.assertEquals('target', cmd.target_dir)

    def test_sources(self):
        cmd = commands.GetDom0Logs(dict(sources='t'))
        self.assertEquals('t', cmd.sources)

    def test_a_node_parameter_included(self):
        self.assertIn('node_username', commands.GetDom0Logs.parameters())

    def test_a_logserver_parameter_included(self):
        self.assertIn('logserver_host', commands.GetDom0Logs.parameters())

    def test_executor_parameter_included(self):
        self.assertIn('executor', commands.GetDom0Logs.parameters())

    def test_targetdir_parameter_included(self):
        self.assertIn('target_dir', commands.GetDom0Logs.parameters())

    def test_sources_parameter_included(self):
        self.assertIn('sources', commands.GetDom0Logs.parameters())


class TestRunTests(unittest.TestCase):
    def test_parameters(self):
        cmd = commands.RunTests
        self.assertEquals(
            ['executor', 'node_username', 'node_host', 'change_ref'],
            cmd.parameters()
        )

    def test_changeref_parsing(self):
        cmd = commands.RunTests(dict(change_ref='ref'))
        self.assertEquals('ref', cmd.change_ref)

    def test_create_executor(self):
        cmd = commands.RunTests(dict(executor='print'))
        self.assertEquals('PrintExecutor', cmd.executor.__class__.__name__)

    def test_default_executor(self):
        cmd = commands.RunTests()
        self.assertEquals('FakeExecutor', cmd.executor.__class__.__name__)

    def test_node_created(self):
        cmd = commands.RunTests()
        self.assertIsNotNone(cmd.node)

    def test_execution(self):
        cmd = commands.RunTests(dict(change_ref='CHANGE'))
        cmd()

        self.maxDiff = 4096

        self.assertEquals(
            [
                SCP + ['tempest_exclusion_list', 'NODE_USERNAME@NODE_HOST:/tmp/tempest_exclusion_list'],
                SSH_TO_NODE + instructions.check_out_testrunner(),
                SSH_TO_NODE
                + environment.get_environment('CHANGE')
                + instructions.execute_test_runner()
            ],
            cmd.executor.executed_commands
        )
