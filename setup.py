from setuptools import setup


setup(
    name='ctxosci',
    version='0.0dev',
    description='Citrix Openstack ',
    packages=['ctxosci'],
    entry_points={
        'console_scripts': [
            'osci-cp-dom0-to-logserver = ctxosci.scripts:cp_dom0_logserver',
            'osci-check-connection = ctxosci.scripts:check_connection',
            'osci-run-tests = ctxosci.scripts:run_tests',
        ]
    }
)