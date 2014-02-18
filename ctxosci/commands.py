from ctxosci import node
from ctxosci import remote
from ctxosci import logserver


class GetDom0Logs(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = remote.create_executor(env.get('executor'))
        self.node = node.Node(env)
        self.logserver = logserver.Logserver(env)
        self.target_dir = env.get('target_dir', 'TARGET_DIR')
        self.sources = env.get('sources', 'SOURCES')

    @classmethod
    def parameters(cls):
        return (
            ['executor']
            + node.Node.parameters()
            + ['sources']
            + logserver.Logserver.parameters()
            + ['target_dir']
        )

    def __call__(self):
        self.executor.run(
            self.logserver.run_with_agent(
                remote.escaped(
                    self.node.run_on_dom0([
                    "tar --ignore-failed-read -czf - {0}".format(self.sources)
                    ])
                ) + ['| tar -xzf - -C {0}'.format(self.target_dir)]
            )
        )
