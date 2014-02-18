import unittest

from ctxosci import node


class TestNode(unittest.TestCase):
    def test_command_for_this_node(self):
        n = node.Node(dict(
            node_username='USER',
            node_host='IP'
        ))

        self.assertEquals(
            "ssh -o UserKnownHostsFile=/dev/null"
            " -o StrictHostKeyChecking=no USER@IP".split(),
            n.command_for_this_node())
