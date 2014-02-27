import abc
import logging

from pygerrit import events


log = logging.getLogger(__name__)


class EventFilter(object):
    def is_event_matching_criteria(self, event):
        if event is None:
            return False
        return self._is_event_matching_criteria(event)


class Client(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, env):
        env = env or dict()
        self.fake_events = []
        self.host = env.get('gerrit_host')
        self.port = env.get('gerrit_port')
        self.user = env.get('gerrit_username')

    @abc.abstractmethod
    def get_event(self):
        pass

class FakeClient(Client):
    def __init__(self, env):
        super(FakeClient, self).__init__(env)
        self.fake_events = []

    def fake_insert_event(self, event):
        self.fake_events.append(event)

    def get_event(self):
        event = None

        if self.fake_events:
            event = self.fake_events.pop(0)

        log.debug("Event requested, returning [%s]", event)
        return event


class PyGerritClient(Client):
    def __init__(self, env):
        super(PyGerritClient, self).__init__(env)

    def get_event(self):
        raise NotImplementedError()


class DummyFilter(object):
    def __init__(self, result):
        self.result = result

    def is_event_matching_criteria(self, _event):
        return self.result


class CommentMatcher(EventFilter):
    def __init__(self, matcher):
        self.matcher = matcher

    def _is_event_matching_criteria(self, event):
        comment = event.comment
        if self.matcher.match(comment):
            return True


class ChangeMatcher(EventFilter):
    def __init__(self, projects):
        self.projects = projects

    def _is_event_matching_criteria(self, event):
        if event.change.branch == "master":
            if event.change.project in self.projects:
                return True
        return False


class EventTypeFilter(object):
    def __init__(self, klass):
        self.klass = klass

    def is_event_matching_criteria(self, event):
        if isinstance(event, self.klass):
            return True


class And(object):
    def __init__(self, filters):
        self.filters = filters

    def is_event_matching_criteria(self, event):
        for fltr in self.filters or [DummyFilter(False)]:
            if not fltr.is_event_matching_criteria(event):
                return False
        return True


class Or(object):
    def __init__(self, filters):
        self.filters = filters

    def is_event_matching_criteria(self, event):
        for fltr in self.filters or [DummyFilter(False)]:
            if fltr.is_event_matching_criteria(event):
                return True
        return False


def get_filter(projects, comment_re):
    return Or([
        And([
            EventTypeFilter(events.CommentAddedEvent),
            CommentMatcher(comment_re),
            ChangeMatcher(projects),
        ]),
        And([
            EventTypeFilter(events.PatchsetCreatedEvent),
            ChangeMatcher(projects),
        ])
    ])


def get_client(env):
    if env and 'pygerrit' == env.get('gerrit_client'):
        return PyGerritClient(env)
    return FakeClient(env)
