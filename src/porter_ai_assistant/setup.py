# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Setup script for porter_ai_assistant ROS 2 package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'porter_ai_assistant'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
        (os.path.join('share', package_name, 'data'),
            glob(os.path.join('data', '*.yaml')) +
            glob(os.path.join('data', '*.json'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antony Austin',
    maintainer_email='antony@virtusco.in',
    description='On-device AI assistant for Porter Robot using Qwen 2.5 1.5B GGUF',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'assistant_node = porter_ai_assistant.assistant_node:main',
            'orchestrator_node = porter_ai_assistant.orchestrator_node:main',
        ],
    },
)
