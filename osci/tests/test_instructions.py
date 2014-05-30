import unittest

from osci import instructions


class TestCheckOutTestRunner(unittest.TestCase):
    def test_command(self):
        self.assertEquals(
            "/usr/bin/git clone"
            " https://git.openstack.org/stackforge/xenapi-os-testing"
            " /home/jenkins/xenapi-os-testing".split(),
            instructions.check_out_testrunner())

    def test_execute_test_runner(self):
        self.assertEquals(
            '/home/jenkins/xenapi-os-testing/run_tests.sh'.split(),
            instructions.execute_test_runner()
        )
