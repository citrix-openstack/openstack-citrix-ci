def check_out_testrunner():
    return (
        '/usr/bin/git clone'
        ' https://git.openstack.org/stackforge/xenapi-os-testing'
        ' /home/jenkins/xenapi-os-testing'
    ).split()

def execute_test_runner():
    return (
        '/home/jenkins/xenapi-os-testing/run_tests.sh'.split()
    )
