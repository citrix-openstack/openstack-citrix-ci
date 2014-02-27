class EventTarget(object):
    def consume_event(self, event):
        pass


class FakeTarget(EventTarget):
    def __init__(self):
        self.fake_events = []

    def consume_event(self, event):
        self.fake_events.append(event)