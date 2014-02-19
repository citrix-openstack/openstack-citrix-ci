from ctxosci import server
from ctxosci import common_ssh_options


class Logserver(server.Server):
    def __init__(self, env):
        env = env or dict()
        self.username = env.get('logserver_username', 'LOGSERVER_USERNAME')
        self.host = env.get('logserver_host', 'LOGSERVER_HOST')

    def run_with_agent(self, args):
        return (
            'ssh -A'.split()
            + common_ssh_options.COMMON_SSH_OPTS
            + ['{0}@{1}'.format(self.username, self.host)]
            + args
        )

    def command_for_this_node(self):
        return (
            ['ssh']
            + common_ssh_options.COMMON_SSH_OPTS
            + ['{0}@{1}'.format(self.username, self.host)]
        )

    def run(self, args):
        return self.command_for_this_node() + args

    @classmethod
    def parameters(self):
        return ['logserver_username', 'logserver_host']
