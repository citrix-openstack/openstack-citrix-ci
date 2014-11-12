from osci import common_ssh_options


class Server(object):
    USERNAME = None
    HOST = None
    KEYFILE = None

    def __init__(self, env=None):
        env = env or dict()
        self.username = env.get(self.USERNAME, self.USERNAME.upper())
        self.host = env.get(self.HOST, self.HOST.upper())
        self.keyfile = env.get(self.KEYFILE, None)

    @classmethod
    def add_arguments_to(cls, parser):
        parser.add_argument(cls.USERNAME)
        parser.add_argument(cls.HOST)

    def command_for_this_node(self):
        return (
            ['ssh']
            + common_ssh_options.COMMON_SSH_OPTS
            + [part for part in ['-i', self.keyfile] if self.keyfile]
            + ['{0}@{1}'.format(self.username, self.host)]
        )

    def run(self, args):
        return self.command_for_this_node() + args

    def scp(self, localfile, remotefile):
        return (
            ['scp']
            + common_ssh_options.COMMON_SSH_OPTS
            + [localfile, '{0}@{1}:{2}'.format(self.username, self.host, remotefile)]
        )

