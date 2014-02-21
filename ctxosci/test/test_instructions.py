import unittest

from ctxosci import instructions


class TestCheckOutTestRunner(unittest.TestCase):
    def test_command(self):
        self.assertEquals(
            "/usr/bin/git clone"
            " https://github.com/citrix-openstack/xenapi-os-testing"
            " /home/jenkins/xenapi-os-testing".split(),
            instructions.check_out_testrunner())

    def test_execute_test_runner(self):
        self.assertEquals(
            '/home/jenkins/xenapi-os-testing/run_tests.sh'.split(),
            instructions.execute_test_runner()
        )
