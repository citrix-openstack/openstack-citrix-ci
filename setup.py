from setuptools import setup


setup(
    name='ctxosci',
    version='0.0dev',
    description='Citrix Openstack ',
    packages=['ctxosci'],
    entry_points={
        'console_scripts': [
            'coci-get-dom0-logs = ctxosci.scripts:get_dom0_logs',
            'coci-check-connection = ctxosci.scripts:check_connection'
        ]
    }
)