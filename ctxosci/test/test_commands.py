import unittest

from ctxosci import commands
from ctxosci import logserver
from ctxosci import node


COMMON_SSH_OPTS='-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
SSH_TO_LOGSERVER=(
    'ssh -A {SSH_OPTIONS} LOGSERVER_USERNAME@LOGSERVER_HOST'.format(
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

        self.assertEquals(
            SSH_TO_LOGSERVER
            + SSH_TO_NODE
            + SSH_TO_DOMZERO_FROM_NODE
            + ["tar --ignore-failed-read -czf - SOURCES"]
            + ['| tar -xzf - -C TARGET_DIR'],
            cmd.executor.executed_commands[0])

    def test_stars_escaped(self):
        cmd = commands.GetDom0Logs()
        cmd.sources = '*'

        cmd()

        self.assertEquals(
            SSH_TO_LOGSERVER
            + SSH_TO_NODE
            + SSH_TO_DOMZERO_FROM_NODE
            + [r"tar --ignore-failed-read -czf - \\*"]
            + ['| tar -xzf - -C TARGET_DIR'],
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
