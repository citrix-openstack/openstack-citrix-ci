def check_out_testrunner():
    return (
        '/usr/bin/git clone'
        ' https://git.openstack.org/stackforge/xenapi-os-testing'
        ' /home/jenkins/xenapi-os-testing'
    ).split()

def update_testrunner(changeref):
    return [
        'pushd xenapi-os-testing'.split(),
        ('/usr/bin/git fetch https://review.openstack.org/stackforge/xenapi-os-testing %s'%changeref).split(),
        '/usr/bin/git checkout FETCH_HEAD'.split(),
        'popd'.split()]

def update_devstackgate(branch):
    return [
        'pushd workspace-cache/devstack-gate'.split(),
        '/usr/bin/git remote update'.split(),
        ('/usr/bin/git checkout %s'%branch).split(),
        'popd'.split()]

def execute_test_runner():
    return '/home/jenkins/xenapi-os-testing/run_tests.sh'.split()
