
from setuptools import setup, find_packages

from irssiicon import _VERSION

setup(name='irssi-icon',
      version=_VERSION,
      description='Displays an icon for irssi notifications.',
      author='Ian Good',
      author_email='ian.good@rackspace.com',
      py_modules=['irssiicon'],
      data_files=[('/usr/share/irssi/scripts', ['irssi-icon-notify.pl'])],
      entry_points={'console_scripts': [
              'irssi-icon = irssiicon:main',
          ]})

# vim:et:fdm=marker:sts=4:sw=4:ts=4
