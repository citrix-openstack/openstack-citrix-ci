import unittest
import textwrap

from osci import node
from osci import executor


class TestNode(unittest.TestCase):
    def test_command_for_this_node(self):
        n = node.Node(dict(
            node_username='USER',
            node_host='IP'
        ))

        self.assertEquals(
            "ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null"
            " -o StrictHostKeyChecking=no USER@IP".split(),
            n.command_for_this_node())

    def test_get_logs(self):
        n = node.Node()

        cmds = n.command_to_get_dom0_files_as_tgz_to_stdout('a b c')
        expected = textwrap.dedent("""
        ssh -q
        -o BatchMode=yes
        -o UserKnownHostsFile=/dev/null
        -o StrictHostKeyChecking=no
        NODE_USERNAME@NODE_HOST
        sudo -u domzero ssh -q
        -o BatchMode=yes
        -o UserKnownHostsFile=/dev/null
        -o StrictHostKeyChecking=no
        root@192.168.33.2
        tar --ignore-failed-read -czf - a b c
        """).strip().split()
        self.assertEquals(expected, cmds)

