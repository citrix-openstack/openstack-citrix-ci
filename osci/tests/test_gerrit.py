import mock
import unittest
from pygerrit import events

from osci import gerrit


class CommentAddedEvent(events.CommentAddedEvent):
    def __init__(self):
        self.comment = 'COMMENT'
        self.project = 'PROJECT'
        self.author = gerrit.FakeAuthor()
        self.author.name = 'NAME'
        self.author.email = 'EMAIL'
        self.author.username = 'USERNAME'


class PatchesCreatedEvent(events.PatchsetCreatedEvent):
    def __init__(self, project='project', branch='master'):
        self.change = gerrit.FakeChange()
        self.change.project = project
        self.change.branch = branch


class TestCommentMatcher(unittest.TestCase):
    def test_matching_success(self):
        matcher = mock.Mock()
        matcher.search.return_value = True

        event_matcher = gerrit.CommentMatcher('')
        event_matcher.matcher = matcher

        self.assertTrue(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

        matcher.search.assert_called_once_with('COMMENT')

    def test_matching_fail(self):
        matcher = mock.Mock()
        matcher.search.return_value = False

        event_matcher = gerrit.CommentMatcher('')
        event_matcher.matcher = matcher

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

        matcher.search.assert_called_once_with('COMMENT')

    def test_none_event(self):
        event_matcher = gerrit.CommentMatcher('')
        self.assertFalse(event_matcher.is_event_matching_criteria(None))


class TestAuthorMatcher(unittest.TestCase):
    def test_matching_success(self):
        event_matcher = gerrit.AuthorMatcher('USERNAME')

        self.assertTrue(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

    def test_matching_fail(self):
        event_matcher = gerrit.AuthorMatcher('')

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

    def test_none_event(self):
        event_matcher = gerrit.AuthorMatcher('')
        self.assertFalse(event_matcher.is_event_matching_criteria(None))


class TestChangeMatcher(unittest.TestCase):
    def test_good_project_good_branch(self):
        event_matcher = gerrit.ChangeMatcher(['project'])

        self.assertTrue(
            event_matcher.is_event_matching_criteria(
                PatchesCreatedEvent()))

    def test_bad_branch(self):
        event_matcher = gerrit.ChangeMatcher(['project'])

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                PatchesCreatedEvent(branch='blah')))

    def test_bad_project(self):
        event_matcher = gerrit.ChangeMatcher(['project'])

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                PatchesCreatedEvent(project='blah')))

    def test_none_event(self):
        event_matcher = gerrit.ChangeMatcher(['project'])

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                None))


class SomeClass(object):
    pass


class TestGerritClientFactory(unittest.TestCase):
    def test_create_client(self):
        client = gerrit.get_client(dict(
            gerrit_client='pygerrit',
            gerrit_host='HOST',
            gerrit_port='67',
            gerrit_username='USER',
            ))

        self.assertEquals('HOST', client.host)
        self.assertEquals(67, client.port)
        self.assertEquals('USER', client.user)

        self.assertEquals('PyGerritClient', client.__class__.__name__)


class TestEventTypeFilter(unittest.TestCase):
    def test_class_filtering_fail(self):
        event_filter = gerrit.EventTypeFilter(SomeClass)

        self.assertFalse(event_filter.is_event_matching_criteria(dict()))

    def test_class_filtering_ok(self):
        event_filter = gerrit.EventTypeFilter(dict)

        self.assertTrue(event_filter.is_event_matching_criteria(dict()))

    def test_note_event(self):
        event_filter = gerrit.EventTypeFilter(dict)

        self.assertFalse(event_filter.is_event_matching_criteria(None))



class TestAndFilter(unittest.TestCase):
    def test_true(self):
        self.assertTrue(gerrit.And(
            [ gerrit.DummyFilter(True)]
        ).is_event_matching_criteria('SOMETHING'))

    def test_false(self):
        self.assertFalse(gerrit.And(
            [ gerrit.DummyFilter(False)]
        ).is_event_matching_criteria('SOMETHING'))

    def test_empty(self):
        self.assertFalse(
            gerrit.And([]).is_event_matching_criteria('SOMETHING'))


class TestOrFilter(unittest.TestCase):
    def test_true(self):
        self.assertTrue(gerrit.Or(
            [ gerrit.DummyFilter(True)]
        ).is_event_matching_criteria('SOMETHING'))

    def test_false(self):
        self.assertFalse(gerrit.Or(
            [ gerrit.DummyFilter(False)]
        ).is_event_matching_criteria('SOMETHING'))

    def test_empty(self):
        self.assertFalse(
            gerrit.Or([]).is_event_matching_criteria('SOMETHING'))

    def test_one_false_one_true(self):
        self.assertTrue(
            gerrit.Or([
                gerrit.DummyFilter(False),
                gerrit.DummyFilter(True)
            ]).is_event_matching_criteria('SOMETHING'))


class TestPyGerritClient(unittest.TestCase):
    @mock.patch('pygerrit.client.GerritClient')
    def test_connect_creates_class(self, gerrit_client_class):
        impl = gerrit_client_class.return_value = mock.Mock()

        client = gerrit.PyGerritClient(dict(
            gerrit_host='host',
            gerrit_port=22,
            gerrit_username='username'
        ))

        gerrit_client_class.assert_called_once_with(
            host='host',
            username='username',
            port=22
        )

        self.assertEquals(impl, client.impl)

    def test_connect_starts_stream(self):
        client = gerrit.PyGerritClient(dict())

        client.impl = mock.Mock()

        client.connect()

        client.impl.start_event_stream.assert_called_once_with()

    def test_connect_gets_version(self):
        client = gerrit.PyGerritClient(dict())

        client.impl = mock.Mock()

        client.connect()

        client.impl.gerrit_version.assert_called_once_with()


class TestGetFilter(unittest.TestCase):

    @mock.patch('re.compile')
    def test_get_filter(self, compile):
        compile.return_value = 'compiled'
        f = gerrit.get_filter(
            dict(projects='p1,p2,p3', comment_re='comment_re', ignore_username='ignore_username'))

        self.assertEquals('ignore_username', f.filters[0].filters[1].fltr.author)
        self.assertEquals('compiled', f.filters[0].filters[2].matcher)
        self.assertEquals(['p1', 'p2', 'p3'], f.filters[0].filters[3].projects)

        self.assertEquals(
            '('
                '(event is CommentAddedEvent)'
                ' AND ( NOT (author equals ignore_username))'
                ' AND (comment matches comment_re)'
                ' AND (branch==master, project in [p1,p2,p3])'
            ') OR ('
                '(event is PatchsetCreatedEvent)'
                ' AND (branch==master, project in [p1,p2,p3])'
            ')', str(f))



class FakeCommentEvent(gerrit.events.CommentAddedEvent):
    def __init__(self, comment):
        self.comment = comment
        self.patchset = gerrit.FakePatchSet()
        self.change = gerrit.FakeChange()
        self.change.branch = "master"
        self.change.project = "nova"
        self.author = gerrit.FakeAuthor()
        self.author.username = 'author_username'


class TestCitrixFilter(unittest.TestCase):
    def test_passing(self):
        e = FakeCommentEvent("hello")

        f = gerrit.get_filter(dict(
            projects='nova',
            comment_re='hello',
            ignore_authors='none',
        ))

        self.assertTrue(f.is_event_matching_criteria(e))
