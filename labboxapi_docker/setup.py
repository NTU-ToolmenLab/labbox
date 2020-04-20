from setuptools import setup

setup(
    name='DockerServer',
    packages=['DockerServer'],
    include_package_data=True,
    install_requires=[
        'flask',
        'docker',
    ],
)
