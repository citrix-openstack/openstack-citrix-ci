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
        ]
    }
)