from setuptools import setup


setup(
    name='osci',
    version='0.0dev',
    description='Citrix Openstack ',
    packages=['osci'],
    entry_points={
        'console_scripts': [
            'osci-cp-dom0-to-logserver = osci.scripts:cp_dom0_logserver',
            'osci-check-connection = osci.scripts:check_connection',
            'osci-run-tests = osci.scripts:run_tests',
            'osci-manage = osci.manage:main',
            'osci-watch-gerrit = osci.scripts:watch_gerrit',
            'osci-upload = osci.swift_upload:main',
            'osci-create-dbschema = osci.scripts:create_dbschema',
            'osci-view = osci.reports:main',
        ]
    }
)
