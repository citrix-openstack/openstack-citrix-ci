import unittest
import mock

from osci import job_queue
from osci import event_target
from osci import gerrit


class TestEventTarget(unittest.TestCase):
    def test_calling_database(self):
        mock_queue = mock.Mock(spec=job_queue.JobQueue)
        target = event_target.QueueTarget(mock_queue)

        event = gerrit.FakeEvent()
        event.patchset.ref = "event.patchset.ref"
        event.change.project = "event.change.project"
        event.patchset.revision = "event.patchset.revision"

        target.consume_event(event)

        mock_queue.addJob.assert_called_once_with(
            "event.patchset.ref",
            "event.change.project",
            "event.patchset.revision"
        )


class TestEventTargetFactory(unittest.TestCase):
    def test_event_target_factory(self):
        obj = event_target.get_target(dict(event_target="fake"))
        self.assertEquals(event_target.FakeTarget, obj.__class__)

    def test_queue_target_database(self):
        obj = event_target.get_target(
            dict(event_target="queue", queue="queue_impl")
        )

        self.assertEquals("queue_impl", obj.queue)

