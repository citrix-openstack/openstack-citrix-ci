import unittest


from osci import localhost


class TestLocalHost(unittest.TestCase):
    def test_extract_stdout_as_tgz_to_dir(self):
        host = localhost.Localhost()

        commands = host.commands_to_extract_stdout_tgz_to('tgtdir')

        self.assertEquals(
            'tar -xzf - -C tgtdir'.split(),
            commands)
