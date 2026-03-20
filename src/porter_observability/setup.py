"""Setup script for porter_observability package."""

import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'porter_observability'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antony Austin',
    maintainer_email='antony@virtusco.dev',
    description='Virtus Observability Stack on-robot package',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'log_bridge = porter_observability.log_bridge:main',
            'metrics_emitter = porter_observability.metrics_emitter:main',
            'event_journal = porter_observability.event_journal:main',
        ],
    },
)
