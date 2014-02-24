import re

class Configuration():
    GERRIT_HOST = '10.80.2.68'
    GERRIT_USERNAME = 'citrix_xenserver_ci'
    GERRIT_PORT = 29418
    SFTP_HOST = 'int-ca.downloads.xensource.com'
    SFTP_USERNAME = 'svcacct_openstack'
    SFTP_KEY = '/usr/workspace/scratch/openstack/infrastructure.hg/puppet/modules/jenkins/files/downloads-id_rsa'
    SFTP_BASE = '/var/www/html/'
    SFTP_COMMON = 'ca.downloads.xensource.com/OpenStack/xenserver-ci'
    NODEPOOL_CONFIG = '/etc/nodepool/nodepool.yaml'
    NODEPOOL_IMAGE = 'devstack-xenserver'
    NODE_USERNAME = 'jenkins'
    NODE_KEY = '/usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool'
    MAX_RUNNING_TIME = 3*3600+15*60 # 3 hours and 15 minutes
    MYSQL_URL = '127.0.0.1'
    MYSQL_USERNAME = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'openstack_ci'
    POLL = 30
    RUN_TESTS = True
    RECHECK_REGEXP = re.compile("^(citrix recheck|recheck bug|recheck nobug)", re.IGNORECASE)
    VOTE = True
    VOTE_PASSED_ONLY = True
    VOTE_NEGATIVE = False
    VOTE_SERVICE_ACCOUNT = False
    VOTE_MESSAGE = "%(result)s using XenAPI driver with XenServer 6.2: Logs at %(log)s\n\n"+\
                   "Recheck supported; use \"citrix recheck\" to trigger only xenserver re-check.  XenServer CI contact: openstack@citrix.com."
    REVIEW_REPO_NAME='review'
    PROJECT_CONFIG=['openstack-dev/sandbox', 'openstack/nova', 'openstack/tempest', 'openstack-dev/devstack']
