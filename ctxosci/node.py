class Node(object):

    def __init__(self, env=None):
        env = env or dict()
        self.username = env.get('node_username', 'NODE_USERNAME')
        self.ip = env.get('node_host', 'NODE_HOST')

    def command_for_this_node(self):
        return (
            'ssh -A -o UserKnownHostsFile=/dev/null'
            ' -o StrictHostKeyChecking=no {0}@{1}').format(
            self.username, self.ip).split()

    def commands_for_dom0(self):
        return (
            'sudo -u domzero ssh'
            ' -o UserKnownHostsFile=/dev/null'
            ' -o StrictHostKeyChecking=no root@192.168.33.2').split()

    def run_on_dom0(self, args):
        return self.command_for_this_node() + self.commands_for_dom0() + args
