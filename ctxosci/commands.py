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
                    self.node.run_on_dom0(
                    "tar --ignore-failed-read -czf - {0}".format(
                        self.sources).split()
                    )
                ) + '| tar -xzf - -C {0}'.format(self.target_dir).split()
            )
        )


class CheckConnection(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = remote.create_executor(env.get('executor'))
        self.node = node.Node(env)
        self.logserver = logserver.Logserver(env)

    @classmethod
    def parameters(cls):
        return (
            ['executor']
            + node.Node.parameters()
            + logserver.Logserver.parameters()
        )

    def __call__(self):
        checks = [
            (
                'Connection to log server',
                self.logserver.run_with_agent(['true'])
            ),
            (
                'Connection from log server to Node',
                self.logserver.run_with_agent(
                    remote.escaped(
                        self.node.run(['true'])
                    ))
            ),
            (
                'Connection from log server to Node to dom0',
                self.logserver.run_with_agent(
                    remote.escaped(
                        self.node.run_on_dom0(['true'])
                    ))
            )
        ]

        for message, args in checks:
            print message
            if 0 == self.executor.run(args):
                print "OK"
            else:
                print "FAIL, aborting"
                return

