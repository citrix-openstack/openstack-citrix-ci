import unittest

from ctxosci import commands


COMMON_SSH_OPTS='-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
SSH_TO_LOGSERVER=(
    'ssh -A {SSH_OPTIONS} LOGSERVER_USERNAME@LOGSERVER_HOST'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SSH_TO_NODE=(
    'ssh -A {SSH_OPTIONS} NODE_USERNAME@NODE_HOST'.format(
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
            + ["tar --ignore-failed-read -czf - "
               "/var/log/messages* /var/log/xensource* /var/log/SM*"],
            cmd.executor.executed_commands[0])

