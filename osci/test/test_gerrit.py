import mock
import unittest
from pygerrit import events

from osci import gerrit


class CommentAddedEvent(events.CommentAddedEvent):
    def __init__(self):
        self.comment = 'COMMENT'
        self.project = 'PROJECT'


class FakeChange(object):
    def __init__(self, project, branch):
        self.branch = branch
        self.project = project


class PatchesCreatedEvent(events.PatchsetCreatedEvent):
    def __init__(self, project='project', branch='master'):
        self.change = FakeChange(project, branch)


class TestCommentMatcher(unittest.TestCase):
    def test_matching_success(self):
        matcher = mock.Mock()
        matcher.match.return_value = True

        event_matcher = gerrit.CommentMatcher(matcher)

        self.assertTrue(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

        matcher.match.assert_called_once_with('COMMENT')

    def test_matching_fail(self):
        matcher = mock.Mock()
        matcher.match.return_value = False

        event_matcher = gerrit.CommentMatcher(matcher)

        self.assertFalse(
            event_matcher.is_event_matching_criteria(
                CommentAddedEvent()))

        matcher.match.assert_called_once_with('COMMENT')


class TestPatchsetMatcher(unittest.TestCase):
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


class SomeClass(object):
    pass


class TestEventTypeFilter(unittest.TestCase):
    def test_class_filtering_fail(self):
        event_filter = gerrit.EventTypeFilter(SomeClass)

        self.assertFalse(event_filter.is_event_matching_criteria(dict()))

    def test_class_filtering_ok(self):
        event_filter = gerrit.EventTypeFilter(dict)

        self.assertTrue(event_filter.is_event_matching_criteria(dict()))


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


