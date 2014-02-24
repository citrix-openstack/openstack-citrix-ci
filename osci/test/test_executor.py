import unittest

from osci import executor


class TestExecutorFactory(unittest.TestCase):
    def test_creating_print(self):
        exc = executor.create_executor('print')
        self.assertEquals('PrintExecutor', exc.__class__.__name__)


