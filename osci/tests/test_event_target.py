import unittest
import mock

from osci import testqueue
from osci import event_target
from osci import gerrit


class TestEventTarget(unittest.TestCase):
    def test_calling_database(self):
        mock_queue = mock.Mock(spec=testqueue.TestQueue)
        target = event_target.QueueTarget(mock_queue)

        event = gerrit.FakeEvent()
        event.patchset.ref = "event.patchset.ref"
        event.change.project = "event.change.project"
        event.patchset.revision = "event.patchset.revision"

        target.consume_event(event)

        mock_queue.addTest.assert_called_once_with(
            "event.patchset.ref",
            "event.change.project",
            "event.patchset.revision"
        )

