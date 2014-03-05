import abc


class EventTarget(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def consume_event(self, event):
        pass


class FakeTarget(EventTarget):
    def __init__(self):
        self.fake_events = []

    def consume_event(self, event):
        self.fake_events.append(event)


class QueueTarget(EventTarget):
    def __init__(self, queue):
        self.queue = queue

    def consume_event(self, event):
        self.queue.addJob(event.patchset.ref,
                          event.change.project,
                          event.patchset.revision)
