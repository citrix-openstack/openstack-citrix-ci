class Logserver(object):
    def __init__(self, env):
        env = env or dict()
        self.username = env.get('logserver_username', 'LOGSERVER_USERNAME')
        self.host = env.get('logserver_host', 'LOGSERVER_HOST')

    def run_with_agent(self, args):
        return (
            'ssh -A -o UserKnownHostsFile=/dev/null'
            ' -o StrictHostKeyChecking=no {0}@{1}').format(
            self.username, self.host).split() + args

    @classmethod
    def parameters(self):
        return ['logserver_username', 'logserver_host']
