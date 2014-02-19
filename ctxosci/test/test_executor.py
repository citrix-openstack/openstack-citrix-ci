import unittest

from ctxosci import remote


class TestExecutorFactory(unittest.TestCase):
    def test_creating_print(self):
        executor = remote.create_executor('print')
        self.assertEquals('PrintExecutor', executor.__class__.__name__)


