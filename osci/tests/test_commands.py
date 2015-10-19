import datetime
import unittest
import mock
from nose import tools

from osci import commands
from osci import executor
from osci import instructions
from osci import environment
from osci import gerrit


COMMON_SSH_OPTS=(
    '-q -o BatchMode=yes -o UserKnownHostsFile=/dev/null'
    ' -o StrictHostKeyChecking=no')
SSH_TO_LOGSERVER=(
    'ssh {SSH_OPTIONS} LOGSERVER_USERNAME@LOGSERVER_HOST'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SSH_TO_NODE=(
    'ssh {SSH_OPTIONS} -i .ssh/jenkins NODE_USERNAME@NODE_HOST'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split())
SSH_TO_DOMZERO_FROM_NODE=(
    'sudo -u domzero ssh {SSH_OPTIONS} root@192.168.33.2'.format(
        SSH_OPTIONS=COMMON_SSH_OPTS).split()
)


def assert_parameters(expected_parameters, cmd):
    params = []
    def collect_arg(arg, *ignored, **kwignored):
        params.append(arg)

    mock_parser = mock.Mock()
    mock_parser.add_argument.side_effect = collect_arg

    cmd.add_arguments_to(mock_parser)
    tools.assert_equals(     # pylint: disable=no-member
        expected_parameters,
        params
    )


class TestRunTests(unittest.TestCase):
    def test_arguments(self):
        assert_parameters(
            [
                'executor',
                'node_username',
                'node_host',
                'change_ref',
                'project_name',
                'test_runner_url',
            ],
            commands.RunTests
        )

    def test_test_runner_parsing(self):
        cmd = commands.RunTests(dict(test_runner_url='testrunner'))
        self.assertEquals('testrunner', cmd.test_runner_url)

    def test_changeref_parsing(self):
        cmd = commands.RunTests(dict(change_ref='ref'))
        self.assertEquals('ref', cmd.change_ref)

    def test_create_executor(self):
        cmd = commands.RunTests(dict(executor='print'))
        self.assertEquals('PrintExecutor', cmd.executor.__class__.__name__)

    def test_default_executor(self):
        cmd = commands.RunTests()
        self.assertEquals('FakeExecutor', cmd.executor.__class__.__name__)

    def test_node_created(self):
        cmd = commands.RunTests()
        self.assertIsNotNone(cmd.node)

    def test_execution(self):
        cmd = commands.RunTests(dict(
            project_name='PROJECT', change_ref='CHANGE'))
        cmd()

        self.maxDiff = 4096

        self.assertEquals(
            [
                SSH_TO_NODE + instructions.check_out_testrunner(),
                SSH_TO_NODE
                + environment.get_environment('PROJECT', 'CHANGE')
                + instructions.execute_test_runner()
            ],
            cmd.executor.executed_commands
        )

    def test_execution_with_explicit_test_runner(self):
        cmd = commands.RunTests(dict(
            project_name='PROJECT', change_ref='CHANGE', test_runner_url='AA'))
        cmd()

        self.maxDiff = 4096

        self.assertEquals(
            [
                SSH_TO_NODE + instructions.check_out_testrunner('AA'),
                SSH_TO_NODE
                + environment.get_environment('PROJECT', 'CHANGE')
                + instructions.execute_test_runner()
            ],
            cmd.executor.executed_commands
        )

    def test_execution_update_testrunner(self):
        cmd = commands.RunTests(dict(project_name='openstack/xenapi-os-testing', change_ref='CHANGE'))
        cmd()

        self.maxDiff = 4096

        expected = [
                SSH_TO_NODE + instructions.check_out_testrunner()]
        for instruction in instructions.update_testrunner('CHANGE'):
            expected.append(SSH_TO_NODE + instruction)
        expected.extend([
                SSH_TO_NODE + environment.get_environment('openstack/xenapi-os-testing', 'CHANGE')
                + instructions.execute_test_runner()
            ])

        self.assertEquals(expected, cmd.executor.executed_commands)


class TestWatchGerrit(unittest.TestCase):
    def test_fake_gerrit_is_used(self):
        cmd = commands.WatchGerrit()
        self.assertEquals('FakeClient', cmd.gerrit_client.__class__.__name__)

    @mock.patch('osci.gerrit.get_client')
    def test_gerrit_client_factory_called(self, get_client):
        get_client.return_value = 'Client'
        cmd = commands.WatchGerrit()
        self.assertEquals('Client', cmd.gerrit_client)

    def test_event_target(self):
        cmd = commands.WatchGerrit(dict(event_target='fake'))
        self.assertEquals('FakeTarget', cmd.event_target.__class__.__name__)

    @mock.patch('osci.db.DB')
    def test_database_created(self, dbclass):
        dbclass.return_value = 'dbimpl'
        cmd = commands.WatchGerrit(dict(event_target='fake', dburl='someurl'))
        dbclass.assert_called_once_with('someurl')
        self.assertEquals('dbimpl', cmd.database)

    @mock.patch('osci.db.DB')
    def test_queue_created(self, dbclass):
        dbclass.return_value = 'dbimpl'
        cmd = commands.WatchGerrit(dict(event_target='fake', dburl='someurl'))
        dbclass.assert_called_once_with('someurl')
        self.assertEquals('dbimpl', cmd.database)

        self.assertIsNotNone(cmd.queue)
        self.assertEquals('dbimpl', cmd.queue.db)

    def test_passing_gerrit_parameters(self):
        cmd = commands.WatchGerrit(dict(
            gerrit_host='GHOST',
            gerrit_port='29418',
            gerrit_username='GUSER',
        ))

        self.assertEquals('GHOST', cmd.gerrit_client.host)
        self.assertEquals(29418, cmd.gerrit_client.port)
        self.assertEquals('GUSER', cmd.gerrit_client.user)

    def test_get_event(self):
        cmd = commands.WatchGerrit()
        cmd.gerrit_client.fake_insert_event('EVENT')
        self.assertEquals('EVENT', cmd.get_event())

    def test_filter_ignores_non_matching(self):
        cmd = commands.WatchGerrit()
        cmd.consume_event = mock.Mock()
        cmd.event_filter = gerrit.DummyFilter(False)
        cmd.gerrit_client.fake_insert_event('EVENT')
        cmd.do_event_handling()
        self.assertEquals(0, len(cmd.consume_event.mock_calls))

    def test_handling_no_event_available(self):
        cmd = commands.WatchGerrit()
        cmd.consume_event = mock.Mock()
        cmd.event_filter = gerrit.DummyFilter(False)
        cmd.do_event_handling()
        self.assertEquals(0, len(cmd.consume_event.mock_calls))

    def test_parameters(self):
        assert_parameters(
            [
                'gerrit_client', 'gerrit_host', 'event_target',
                'gerrit_port', 'gerrit_username', 'dburl',
                'comment_re', 'projects'
            ],
            commands.WatchGerrit()
        )

    def test_consume_event(self):
        cmd = commands.WatchGerrit(dict(event_target='fake'))
        cmd.consume_event('EVENT')

        self.assertEquals(
            ['EVENT'], cmd.event_target.fake_events
        )

    @mock.patch('osci.commands.time_services.now')
    def test_event_seen_recently(self, mock_now):
        cmd = commands.WatchGerrit(dict(event_target='fake'))

        cmd.last_event = datetime.datetime(2000,1,1,0,0,0,0)

        cmd.recent_event_time = datetime.timedelta(minutes=10)
        mock_now.return_value = cmd.last_event + datetime.timedelta(seconds=5)
        self.assertTrue(cmd.event_seen_recently())
        mock_now.return_value = cmd.last_event + datetime.timedelta(hours=1)
        self.assertFalse(cmd.event_seen_recently())

class TestWatchGerritMainLoop(unittest.TestCase):
    def setUp(self):
        self.cmd = cmd = commands.WatchGerrit()
        self.patchers = [
            mock.patch.object(cmd, 'sleep'),
            mock.patch.object(cmd, 'do_event_handling'),
            mock.patch.object(cmd, 'event_seen_recently'),
            ]
        [patcher.start() for patcher in self.patchers]

    def test_call_connects(self):
        cmd = self.cmd
        cmd.event_seen_recently.return_value = False
        cmd()
        self.assertEquals(1,
                          len(cmd.gerrit_client.fake_connect_calls))
        self.assertEquals(1,
                          len(cmd.gerrit_client.fake_disconnect_calls))

    def test_call_runs_main(self):
        cmd = self.cmd
        cmd.event_seen_recently.side_effect = [True, False]
        cmd()
        cmd.do_event_handling.assert_called_once_with()

    def tearDown(self):
        [patcher.stop() for patcher in self.patchers]


class TestSleep(unittest.TestCase):
    @mock.patch('time.sleep')
    def test_sleep_called(self, sleep):
        cmd = commands.WatchGerrit(dict(sleep_timeout=3))
        cmd.sleep()
        sleep.assert_called_once_with(3)


class TestEventHandling(unittest.TestCase):
    def setUp(self):
        self.cmd = cmd = commands.WatchGerrit()
        self.patchers = [
            mock.patch.object(cmd, 'get_event'),
            mock.patch.object(cmd, 'consume_event'),
            ]
        [patcher.start() for patcher in self.patchers]

    def test_event_handling(self):
        cmd = self.cmd
        cmd.get_event.side_effect = ['EVENT', None]

        cmd.do_event_handling()

        cmd.consume_event.assert_called_once_with('EVENT')
        cmd.get_event.assert_has_calls([mock.call(), mock.call()])

    def test_event_handling_no_event(self):
        cmd = self.cmd
        cmd.get_event.return_value = None
        cmd.do_event_handling()
        self.assertEquals([], cmd.consume_event.mock_calls)

    def tearDown(self):
        [patcher.stop() for patcher in self.patchers]
