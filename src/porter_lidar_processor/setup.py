"""Setup script for porter_lidar_processor package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'porter_lidar_processor'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # Ament resource index
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # Package manifest
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*_launch.py'))),
        # Config files
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antony Austin',
    maintainer_email='antony@virtusco.in',
    description='Porter Robot LIDAR scan processor — filters, smoothing, ROI.',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'processor_node = porter_lidar_processor.processor_node:main',
        ],
    },
)
