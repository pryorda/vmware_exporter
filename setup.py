from setuptools import setup, find_packages
import vmware_exporter

setup(
    name='vmware_exporter',
    version=vmware_exporter.__version__,
    author=vmware_exporter.__author__,
    description='VMWare VCenter Exporter for Prometheus',
    long_description=open('README.md').read(),
    url='https://github.com/pryorda/vmware_exporter',
    download_url=("https://github.com/pryorda/vmware_exporter/tarball/%s" %
                  vmware_exporter.__version__),
    keywords=['VMWare', 'VCenter', 'Prometheus'],
    license=vmware_exporter.__license__,
    packages=find_packages(exclude=['*.test', '*.test.*']),
    include_package_data=True,
    install_requires=open('requirements.txt').readlines(),
    entry_points={
        'console_scripts': [
            'vmware_exporter=vmware_exporter.vmware_exporter:main'
        ]
    }
)
