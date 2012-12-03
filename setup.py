#!/usr/bin/python2.7

from distutils.core import setup

setup(name='irssi-icon',
      description='Displays an icon for irssi notifications.',
      author='Ian Good',
      author_email='ian.good@rackspace.com',
      scripts=['irssi-icon.py'],
      data_files=[('/usr/share/irssi/scripts', ['irssi-icon-notify.pl'])])

# vim:et:fdm=marker:sts=4:sw=4:ts=4
