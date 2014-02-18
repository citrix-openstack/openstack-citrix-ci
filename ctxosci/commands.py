from ctxosci import node
from ctxosci import remote
from ctxosci import logserver


class GetDom0Logs(object):
    def __init__(self, env=None):
        env = env or dict()
        self.executor = env.get('executor', remote.FakeExecutor())
        self.node = node.Node(env)
        self.logserver = logserver.Logserver(env)

    @classmethod
    def parameters(cls):
        return (
            node.Node.parameters()
            + logserver.Logserver.parameters()
            + ['executor']
        )

    def __call__(self):
        self.executor.run(
            self.logserver.run(
                self.node.run_on_dom0([
                "tar --ignore-failed-read -czf - "
                "/var/log/messages* /var/log/xensource* /var/log/SM*"])))
