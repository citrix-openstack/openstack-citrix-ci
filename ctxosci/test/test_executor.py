import unittest

from ctxosci import executor


class TestExecutorFactory(unittest.TestCase):
    def test_creating_print(self):
        executor = executor.create_executor('print')
        self.assertEquals('PrintExecutor', executor.__class__.__name__)


