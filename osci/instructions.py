def check_out_testrunner(testrunner_repo='https://git.openstack.org/stackforge/xenapi-os-testing'):
    return (
        '/usr/bin/git clone'
        ' %s'
        ' /home/jenkins/xenapi-os-testing' % testrunner_repo
    ).split()

def update_testrunner(changeref):
    return [
        'pushd xenapi-os-testing'.split(),
        ('/usr/bin/git fetch https://review.openstack.org/stackforge/xenapi-os-testing %s'%changeref).split(),
        '/usr/bin/git checkout FETCH_HEAD'.split(),
        'popd'.split()]

def update_devstackgate(branch):
    return [
        'pushd /opt/git/openstack-infra/devstack-gate'.split(),
        'sudo /usr/bin/git remote update'.split(),
        ('sudo /usr/bin/git checkout %s'%branch).split(),
        'popd'.split()]

def execute_test_runner():
    return '/home/jenkins/xenapi-os-testing/run_tests.sh'.split()
