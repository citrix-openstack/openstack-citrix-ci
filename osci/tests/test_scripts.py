import unittest
import mock

from collections import namedtuple

from osci import scripts


class Command(object):
    @classmethod
    def add_arguments_to(cls, parser):
        parser.add_argument('p1')
        parser.add_argument('p2')


class TestParameterToArg(unittest.TestCase):
    def test_parser_created(self):
        command = Command()

        parser = scripts.get_parser_for(command)

        env = parser.parse_args('p1value p2value'.split())

        self.assertEquals('p1value', env.p1)
        self.assertEquals('p2value', env.p2)

    def test_missing_param(self):
        command = Command()

        parser = scripts.get_parser_for(command)

        with self.assertRaises(SystemExit) as e:
            parser.parse_args('p1value'.split())


def create_somecommand(collector=None):
    collector = [] if collector is None else collector

    class SomeCommand(object):
        def __init__(self, env):
            collector.append(dict(env=env))

        def __call__(self):
            collector.append('executed')
            return 'result'

    return SomeCommand


class SomeArgs(object):
    def __init__(self):
        self.key = 'value'


class TestRunCommand(unittest.TestCase):
    def setUp(self):
        self.patchers = [
            mock.patch('osci.scripts.setup_logging'),
            mock.patch('osci.scripts.get_parser_for')
        ]
        [patcher.start() for patcher in self.patchers]

        self.parser = scripts.get_parser_for.return_value = mock.Mock()
        self.parser.parse_args.return_value = SomeArgs()

    def test_logging_configured(self):
        # pylint: disable=E
        scripts.run_command(create_somecommand())
        self.assertTrue(scripts.setup_logging.called)

    def test_parser_acquired(self):
        command = create_somecommand()
        scripts.run_command(command)
        # pylint: disable=E
        scripts.get_parser_for.assert_called_once_with(command)

    def test_args_parsed(self):
        scripts.run_command(create_somecommand())
        self.parser.parse_args.assert_called_once_with()

    def test_command_instantiated(self):
        collector = []
        scripts.run_command(create_somecommand(collector))
        self.assertIn(
            dict(env=dict(key='value')),
            collector
        )

    def test_command_executed(self):
        collector = []
        scripts.run_command(create_somecommand(collector))
        self.assertIn(
            'executed',
            collector
        )

    def test_command_result(self):
        self.assertEquals(
            'result',
            scripts.run_command(create_somecommand())
        )

    def test_env_can_be_injected(self):
        collector = []
        scripts.run_command(create_somecommand(collector), env=dict(k=1))

        self.assertEquals(dict(env=dict(k=1)), collector[0])

    def tearDown(self):
        [patcher.stop() for patcher in self.patchers]
