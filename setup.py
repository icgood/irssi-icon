
from setuptools import setup, find_packages

setup(name='irssi-icon',
      version='1.4',
      description='Displays an icon for irssi notifications.',
      author='Ian Good',
      author_email='ian.good@rackspace.com',
      url='https://github.com/icgood/irssi-icon',
      packages=find_packages(),
      install_requires=['setuptools'],
      package_data={'irssiicon': ['irssi-icon-notify.pl', 'icons/*.png']},
      entry_points={'console_scripts': [
              'irssi-icon = irssiicon:main',
          ]})

# vim:et:fdm=marker:sts=4:sw=4:ts=4
