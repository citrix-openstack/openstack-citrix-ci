import unittest
from collections import namedtuple

from ctxosci import scripts


class Command(object):
    @classmethod
    def parameters(cls):
        return ['p1', 'p2']

class TestParameterToArg(unittest.TestCase):
    def test_parser_created(self):
        command = Command()

        parser = scripts.get_parser_for(command)

        env = parser.parse_args('p1value p2value'.split())

        self.assertEquals('p1value', env.p1)
        self.assertEquals('p2value', env.p2)

    def test_missing_param(self):
        command = Command()

        parser = scripts.get_parser_for(command)

        with self.assertRaises(SystemExit) as e:
            parser.parse_args('p1value'.split())

