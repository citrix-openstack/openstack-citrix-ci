from osci import server
from osci import executor
from osci import common_ssh_options


class Node(server.Server):

    USERNAME = 'node_username'
    HOST = 'node_host'

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
            + executor.escaped(args)
        )

    def command_to_get_dom0_files_as_tgz_to_stdout(self, sources):
        return self.run_on_dom0(
            "tar --ignore-failed-read -czf - {0}".format(
                sources).split()
        )

