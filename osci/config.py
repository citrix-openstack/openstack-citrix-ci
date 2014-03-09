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
            cls._instance.reread()
        return cls._instance

    defaults={
        'GERRIT_EVENT_TIMEOUT': str(30*60), # If no event after 30 minutes then error
        'GERRIT_HOST': '10.80.2.68',
        'GERRIT_USERNAME': 'citrix_xenserver_ci',
        'GERRIT_PORT': '29418',
        'MAX_RUNNING_TIME': str(3*3600+15*60), # 3 hours and 15 minutes
        'DATABASE_URL': 'mysql://root:@127.0.0.1/openstack_ci',
        'NODEPOOL_CONFIG': '/etc/nodepool/nodepool.yaml',
        'NODEPOOL_IMAGE': 'XSDSVM',
        'NODE_USERNAME': 'jenkins',
        'NODE_KEY': '/usr/workspace/scratch/openstack/infrastructure.hg/keys/nodepool',
        'POLL': '30',
        'PROJECT_CONFIG': 'openstack/nova,openstack/tempest,openstack-dev/devstack',
        'RUN_TESTS': 'True',
        'RECHECK_REGEXP': '^(citrix recheck|xenserver recheck|recheck xenserver|recheck bug|recheck nobug).*',
        'REVIEW_REPO_NAME': 'review',
        'SWIFT_CONTAINER': 'CILogs',
        'SWIFT_USERNAME': 'citrix.nodepool2',
        'SWIFT_UPLOAD_ATTEMPTS': '5',
        'SWIFT_API_KEY': ' ',
        'VOTE': 'True',
        'VOTE_PASSED_ONLY': 'True',
        'VOTE_NEGATIVE': 'False',
        'VOTE_SERVICE_ACCOUNT': 'False',
        'VOTE_MESSAGE': "%(result)s using XenAPI driver with XenServer 6.2: Logs at %(log)s\n\n"+\
                      "Standard recheck supported; use \"recheck xenserver\" to trigger only "+\
                      "xenserver re-check.  XenServer CI contact: openstack@citrix.com.",
        }

    def _conf_file_contents(self):
        filename = os.path.expanduser(Configuration.CONFIG_FILE)
        filename = os.path.expandvars(filename)
        if os.path.exists(filename):
            with open(filename, 'r') as config:
                return config.read()
        return "";

    def reread(self):
        # Insert a dummy section header, so XYZ='abc' can be used in the config file
        self.config = ConfigParser.RawConfigParser(self.defaults)
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

    def get_int(self, attr):
        val = self.get(attr)
        return int(val)

