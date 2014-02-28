import re
import StringIO
import ConfigParser
import os.path
import json

class Configuration(object):
    CONFIG_FILE = '~/osci.config'

    # Make the configuration a singleton
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Configuration, cls).__new__(
                                cls, *args, **kwargs)
        return cls._instance

    defaults={
        'GERRIT_HOST': '10.80.2.68',
        'GERRIT_USERNAME': 'citrix_xenserver_ci',
        'GERRIT_PORT': '29418',
        'SFTP_HOST': 'int-ca.downloads.xensource.com',
        'SFTP_USERNAME': 'svcacct_openstack',
        'SFTP_KEY': '/usr/workspace/scratch/openstack/infrastructure.hg/puppet/modules/jenkins/files/downloads-id_rsa',
        'SFTP_BASE': '/var/www/html/',
        'SFTP_COMMON': 'ca.downloads.xensource.com/OpenStack/xenserver-ci',
        'NODEPOOL_CONFIG': '/etc/nodepool/nodepool.yaml',
        'NODEPOOL_IMAGE': 'devstack-xenserver',
        'NODE_USERNAME': 'jenkins',
        'NODE_KEY': '/usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool',
        'MAX_RUNNING_TIME': str(3*3600+15*60), # 3 hours and 15 minutes
        'MYSQL_URL': '127.0.0.1',
        'MYSQL_USERNAME': 'root',
        'MYSQL_PASSWORD': '',
        'MYSQL_DB': 'openstack_ci',
        'POLL': '30',
        'RUN_TESTS': 'True',
        'RECHECK_REGEXP': '^(citrix recheck|xenserver recheck|recheck bug|recheck nobug).*',
        'VOTE': 'True',
        'VOTE_PASSED_ONLY': 'True',
        'VOTE_NEGATIVE': 'False',
        'VOTE_SERVICE_ACCOUNT': 'False',
        'VOTE_MESSAGE': "%(result)s using XenAPI driver with XenServer 6.2: Logs at %(log)s\n\n"+\
                      "Standard recheck supported; use \"xenserver recheck\" to trigger only "+\
                      "xenserver re-check.  XenServer CI contact: openstack@citrix.com.",
        'REVIEW_REPO_NAME': 'review',
        'PROJECT_CONFIG': 'openstack-dev/sandbox,openstack/nova,openstack/tempest,openstack-dev/devstack',
        }

    def _conf_file_contents(self):
        if os.path.exists(Configuration.CONFIG_FILE):
            with open(Configuration.CONFIG_FILE, 'r') as config:
                return config.read()
        return "";

    def __init__(self):
        # Insert a dummy section header, so XYZ='abc' can be used in the config file
        self.config = ConfigParser.ConfigParser(self.defaults)
        ini_str = '[root]\n' + self._conf_file_contents()
        ini_fp = StringIO.StringIO(ini_str)
        self.config.readfp(ini_fp)

    def __getattr__(self, attr):
        return self.config.get('root', attr)

    def get(self, attr):
        return self.__getattr__(attr)

    def get_bool(self, attr):
        val = self.get(attr)
        if val.lower() in ("yes", "y", "true"): return True
        if val.lower() in ("no",  "n", "false"): return False
        raise Exception('Invalid value for boolean: %s'%val)

