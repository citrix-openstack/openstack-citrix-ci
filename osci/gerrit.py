import abc
import logging
import re

from pygerrit import client
from pygerrit import events


log = logging.getLogger(__name__)


class FakeEvent(object):
    def __init__(self):
        self.patchset = FakePatchSet()
        self.change = FakeChange()


class FakeChange(object):
    def __init__(self):
        self.project = None
        self.branch = None


class FakePatchSet(object):
    def __init__(self):
        self.ref = None
        self.revision = None


class EventFilter(object):
    __metaclass__ = abc.ABCMeta

    def is_event_matching_criteria(self, event):
        if event is None:
            return False

        return self._is_event_matching_criteria(event)

    @abc.abstractmethod
    def _is_event_matching_criteria(self, event):
        pass


class Client(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, env):
        env = env or dict()
        self.fake_events = []
        self.host = env.get('gerrit_host')
        self.port = int(env.get('gerrit_port', '29418'))
        self.user = env.get('gerrit_username')

    @abc.abstractmethod
    def connect(self):
        pass

    def get_event(self):
        event = self._get_event()
        log.debug("Returning event [%s]", event)
        return event

    @abc.abstractmethod
    def _get_event(self):
        pass


class FakeClient(Client):
    def __init__(self, env):
        super(FakeClient, self).__init__(env)
        self.fake_events = []
        self.fake_connect_calls = []
        self.fake_disconnect_calls = []

    def connect(self):
        self.fake_connect_calls.append(self.connect)

    def disconnect(self):
        self.fake_disconnect_calls.append(self.disconnect)

    def fake_insert_event(self, event):
        self.fake_events.append(event)

    def _get_event(self):
        if self.fake_events:
            return self.fake_events.pop(0)


class PyGerritClient(Client):
    def __init__(self, env):
        super(PyGerritClient, self).__init__(env)
        self.impl = client.GerritClient(
            host=self.host,
            username=self.user,
            port=self.port
        )

    def connect(self):
        version = self.impl.gerrit_version()
        log.debug( "Connected to gerrit version [%s]", version)
        self.impl.start_event_stream()

    def disconnect(self):
        log.debug( "Stopping event stream")
        self.impl.stop_event_stream()

    def _get_event(self):
        return self.impl.get_event(block=False)


class DummyFilter(object):
    def __init__(self, result):
        self.result = result

    def is_event_matching_criteria(self, _event):
        return self.result


class CommentMatcher(EventFilter):
    def __init__(self, regexp):
        self.regexp = regexp
        self.matcher = re.compile(regexp)

    def _is_event_matching_criteria(self, event):
        comment = event.comment
        if self.matcher.search(comment):
            return True

    def __str__(self):
        return 'comment matches {0}'.format(self.matcher)


class ChangeMatcher(EventFilter):
    def __init__(self, projects):
        self.projects = projects
        self.branch = "master"

    def _is_event_matching_criteria(self, event):
        if event.change.branch == self.branch:
            if event.change.project in self.projects:
                return True
        return False

    def __str__(self):
        return 'branch=={0}, project in [{1}]'.format(
            self.branch, ",".join(self.projects))


class EventTypeFilter(EventFilter):
    def __init__(self, klass):
        self.klass = klass

    def _is_event_matching_criteria(self, event):
        if isinstance(event, self.klass):
            return True

    def __str__(self):
        return 'event is {0}'.format(self.klass.__name__)


class And(EventFilter):
    def __init__(self, filters):
        self.filters = filters

    def _is_event_matching_criteria(self, event):
        for fltr in self.filters or [DummyFilter(False)]:
            if not fltr.is_event_matching_criteria(event):
                return False
        return True

    def __str__(self):
        return ' AND '.join(["(%s)" % f for f in self.filters])


class Or(EventFilter):
    def __init__(self, filters):
        self.filters = filters

    def _is_event_matching_criteria(self, event):
        for fltr in self.filters or [DummyFilter(False)]:
            if fltr.is_event_matching_criteria(event):
                return True
        return False

    def __str__(self):
        return ' OR '.join(["(%s)" % f for f in self.filters])


def get_filter(env):
    comment_re = env and env.get('comment_re')
    projects = env.get('projects').split(',') if env and env.get('projects') else None
    if not all([comment_re, projects]):
        return DummyFilter(True)

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


def get_error_filter(env):
    return EventTypeFilter(events.ErrorEvent)


def get_client(env):
    if env and 'pygerrit' == env.get('gerrit_client'):
        return PyGerritClient(env)
    return FakeClient(env)
