from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'porter_orchestrator'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*_launch.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antony Austin',
    maintainer_email='antony@virtusco.in',
    description='Orchestration layer for Porter Robot',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'state_machine = porter_orchestrator.porter_state_machine:main',
            'health_monitor = porter_orchestrator.lidar_health_monitor:main',
        ],
    },
)
