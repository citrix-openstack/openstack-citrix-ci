import unittest
import textwrap

from ctxosci import environment


class TestEnvironment(unittest.TestCase):
    def test_env_value(self):
        change_ref = 'SOME_CHANGEREF'

        expected_env = textwrap.dedent("""
        TEMPEST_EXCLUSION_LIST=/tmp/tempest_exclusion_list
        TEMPEST_EXCLUSION_LOG=/tmp/tempest_exclusion_log
        ZUUL_URL=https://review.openstack.org
        ZUUL_REF=SOME_CHANGEREF
        PYTHONUNBUFFERED=true
        DEVSTACK_GATE_TEMPEST=1
        DEVSTACK_GATE_TEMPEST_FULL=1
        DEVSTACK_GATE_VIRT_DRIVER=xenapi
        DEVSTACK_GATE_TIMEOUT=180
        APPLIANCE_NAME=devstack
        ENABLED_SERVICES=g-api,g-reg,key,n-api,n-crt,n-obj,n-cpu,n-sch,horizon,mysql,rabbit,sysstat,dstat,pidstat,s-proxy,s-account,s-container,s-object,n-cond
        """)

        self.assertEquals(expected_env.split(), environment.get_environment(change_ref))