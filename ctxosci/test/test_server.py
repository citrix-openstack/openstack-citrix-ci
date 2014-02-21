import unittest
from ctxosci import server
from ctxosci import common_ssh_options


class Server(server.Server):
    USERNAME = 'username'
    HOST = 'host'


class TestServer(unittest.TestCase):
    def test_run(self):
        srv = Server()
        self.assertEquals(
            (
                'ssh {ssh_options} USERNAME@HOST cmd1 cmd2'.format(
                    ssh_options=' '.join(common_ssh_options.COMMON_SSH_OPTS))
            ).split(),
            srv.run(['cmd1', 'cmd2']))
