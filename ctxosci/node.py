from ctxosci import remote
from ctxosci import common_ssh_options


class Node(object):

    def __init__(self, env=None):
        env = env or dict()
        self.username = env.get('node_username', 'NODE_USERNAME')
        self.ip = env.get('node_host', 'NODE_HOST')

    @classmethod
    def parameters(cls):
        return ['node_username', 'node_host']

    def command_for_this_node(self):
        return (
            ['ssh']
            + common_ssh_options.COMMON_SSH_OPTS
            + ['{0}@{1}'.format(self.username, self.ip)]
        )

    def commands_for_dom0(self):
        return (
            'sudo -u domzero ssh'.split()
            + common_ssh_options.COMMON_SSH_OPTS
            + 'root@192.168.33.2'.split()
        )

    def run_on_dom0(self, args):
        return (
            self.command_for_this_node()
            + self.commands_for_dom0()
            + remote.escaped(args)
        )

    def run(self, args):
        return self.command_for_this_node() + args
