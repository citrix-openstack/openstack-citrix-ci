def check_out_testrunner():
    return (
        '/usr/bin/git clone'
        ' https://git.openstack.org/stackforge/xenapi-os-testing'
        ' /home/jenkins/xenapi-os-testing'
    ).split()

def update_testrunner(changeref):
    return [
        '/usr/bin/git fetch https://review.openstack.org/stackforge/xenapi-os-testing %s'.split(),
        '/usr/bin/git checkout FETCH_HEAD'.split()]

def execute_test_runner():
    return '/home/jenkins/xenapi-os-testing/run_tests.sh'.split()
