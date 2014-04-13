LICENSE = """\
Copyright (c) 2014 Ian Good <ian.good@rackspace.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import os.path
import shutil
import sys
import stat
import socket
import subprocess
import base64
import zlib
import argparse
import pkg_resources
import errno
import signal
import multiprocessing
import SocketServer

from gi.repository import Notify
from gi.repository import GObject as gobject
import pygtk
import gtk


__version__ = pkg_resources.require('irssi-icon')[0].version


class State(object):

    def __init__(self, args):
        self.icon = Icon(self, args)
        if args.ssh:
            self.host = RemoteHost(self.icon, args.ssh, args.ssh_key)
        else:
            self.host = LocalHost()
        self.irssi = Irssi(self, args)

    def main(self):
        self.icon.start()
        self.host.start()
        self.irssi.start()
        gtk.main()

    def close(self):
        self.host.close()

    def icon_clicked(self, action=True):
        self.icon.clear_alert_icon()
        if action:
            self.irssi.click_action()

    def new_irssi_message(self, info, data, whisper=False):
        self.icon.set_alert(info, whisper)
        if whisper:
            self.icon.notify(info, data)


class Irssi(object):

    def __init__(self, state, args):
        self.state = state
        self.onclick = args.onclick

    def start(self):
        self._connect_local_socket()

    def send_clear_message(self):
        s = socket.create_connection(('localhost', 21693))
        try:
            s.send('{0}:CLEAR> '.format(__version__))
        finally:
            s.close()

    def _get_request(self, client):
        request = client.recv(4096)
        client.close()
        data = ''
        if '\r\n' in request:
            request, data = request.split('\r\n', 1)
        command, info = request.split('> ', 1)
        version, command = command.split(':', 1)
        assert version == __version__, 'Plugin version mismatch.'
        return command, info, data

    def _msg_client_data(self, client, cond):
        command, info, data = self._get_request(client)
        if command == 'NEWMSG':
            data = 'New message in {0}'.format(data)
            self.state.new_irssi_message(info, data)
        elif command == 'NEWWHISPER':
            self.state.new_irssi_message(info, data, whisper=True)
        elif command == 'CLEAR':
            self.state.icon_clicked(False)
        return False

    def _msg_sock_connection(self, f, cond):
        client, from_ = f.accept()
        gobject.io_add_watch(client, gobject.IO_IN, self._msg_client_data)
        return True

    def _connect_local_socket(self):
        self._msg_sock = socket.socket(socket.AF_INET)
        self._msg_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._msg_sock.bind(('127.0.0.1', 21693))
        self._msg_sock.listen(5)
        gobject.io_add_watch(self._msg_sock, gobject.IO_IN,
                             self._msg_sock_connection)

    def click_action(self):
        if not self.onclick:
            return
        p = subprocess.Popen(self.onclick, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, shell=True)
        p.communicate()


class Icon(object):

    def __init__(self, state, args):
        self.state = state
        self.icon = None
        self.show_notifications = not args.no_notify
        self._whisper_alert = False
        self._load_icons()

    def start(self):
        Notify.init('irssi-icon')
        self._create_icon()

    def _load_icons(self):
        def load(name):
            from pkg_resources import Requirement, resource_filename
            resource_name = 'icons/{0}.png'.format(name)
            fn = resource_filename(__name__, resource_name)
            return gtk.gdk.pixbuf_new_from_file(fn)
        self._icon_pixbuf = load('main')
        self._important_icon_pixbuf = load('important')
        self._notify_icon_pixbuf = load('notify')

    def _create_icon(self):
        self.icon = gtk.StatusIcon()
        self.icon.connect('popup-menu', self._right_click)
        self.icon.connect('activate', self._left_click)
        self.clear_alert_icon()

    def alert(self, msg):
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        box = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, flags=flags,
                                type=gtk.MESSAGE_WARNING,
                                message_format=msg)
        box.run()
        box.destroy()

    def clear_alert_icon(self):
        self._whisper_alert = False
        self.icon.set_from_pixbuf(self._icon_pixbuf)
        self.icon.set_tooltip('Irssi Icon')

    def set_alert(self, info, whisper):
        if whisper:
            self._whisper_alert = True
            self.icon.set_from_pixbuf(self._important_icon_pixbuf)
            self.icon.set_tooltip('Irssi Icon\nWhisper from ' + info)
        elif not self._whisper_alert:
            self.icon.set_from_pixbuf(self._notify_icon_pixbuf)
            self.icon.set_tooltip('Irssi Icon\nNew messages in ' + info)

    def _hide_notification(self, notification):
        notification.close()
        return False

    def notify(self, info, data):
        if self.show_notifications:
            notification = Notify.Notification.new(info, data, None)
            notification.show()
            gobject.timeout_add(10000, self._hide_notification, notification)

    def _right_click(self, icon, button, timestamp):
        menu = gtk.Menu()

        about = gtk.ImageMenuItem('About')
        quit = gtk.ImageMenuItem('Quit')

        img = gtk.image_new_from_stock(gtk.STOCK_ABOUT, gtk.ICON_SIZE_MENU)
        img.show()
        about.set_image(img)

        img = gtk.image_new_from_stock(gtk.STOCK_QUIT, gtk.ICON_SIZE_MENU)
        img.show()
        quit.set_image(img)

        about.connect('activate', self._show_about_dialog)
        quit.connect('activate', gtk.main_quit)

        menu.append(about)
        menu.append(gtk.SeparatorMenuItem())
        menu.append(quit)

        menu.show_all()

        menu.popup(None, None, gtk.status_icon_position_menu,
                   button, timestamp, icon)

    def _left_click(self, icon):
        self.state.icon_clicked()

    def _show_about_dialog(self, widget):
        about = gtk.AboutDialog()

        about.set_destroy_with_parent(True)
        about.set_name('Irssi Icon')
        about.set_version(__version__)
        about.set_authors(['Ian Good <ian.good@rackspace.com>'])
        about.set_license(LICENSE)

        comments = 'Displays an icon to give notifications from irssi.'
        about.set_comments(comments)

        about.run()
        about.destroy()


class BaseHost(object):

    def start(self):
        raise NotImplementedError()

    def close(self):
        pass

    def _load_plugin_contents(self):
        plugin_name = 'irssi-icon-notify.pl'
        from pkg_resources import Requirement, resource_stream
        res_name = os.path.join('irssiicon', plugin_name)
        from_fp = resource_stream(Requirement.parse('irssi-icon'), res_name)
        try:
            return from_fp.read().replace('<<irssi-icon version>>',
                                          __version__)
        finally:
            from_fp.close()

    def _get_plugin_path(self, home_dir=None):
        scripts_dir = os.path.join('.irssi', 'scripts')
        if home_dir:
            scripts_dir = os.path.join(home_dir, scripts_dir)
        autorun_dir = os.path.join(scripts_dir, 'autorun')
        plugin_name = 'irssi-icon-notify.pl'
        return scripts_dir, autorun_dir, plugin_name


class LocalHost(BaseHost):

    def start(self):
        home_dir = os.path.expanduser('~')
        scripts_dir, autorun_dir, plugin_name = self._get_plugin_path(home_dir)
        plugin_path = os.path.join(scripts_dir, plugin_name)
        autorun_path = os.path.join(autorun_dir, plugin_name)
        plugin_contents = self._load_plugin_contents()
        try:
            os.makedirs(autorun_dir)
        except OSError, (err, msg):
            if err != 17:
                raise
        with open(plugin_path, 'w') as fp:
            fp.write(plugin_contents)
        try:
            os.unlink(autorun_path)
        except OSError, (err, msg):
            if err != 2:
                raise
        os.symlink(plugin_path, autorun_path)


class RemoteHost(BaseHost):

    def __init__(self, state, target, keyfile):
        super(RemoteHost, self).__init__()
        self.state = state
        self.icon = state.icon
        self.target = target
        self.keyfile = keyfile
        self.ssh_pid = None
        self.done = False

    def _restart_forwarding(self, pid, condition):
        self.ssh_pid = None
        if not self.done:
            gobject.timeout_add(5000, self._start_forwarding)

    def _start_forwarding(self):
        args = ['ssh', self.target, '-o', 'PasswordAuthentication no',
                '-N', '-R', '21693:localhost:21693']
        if self.keyfile:
            args[2:2] = ['-i', self.keyfile]
        flags = gobject.SPAWN_SEARCH_PATH | gobject.SPAWN_DO_NOT_REAP_CHILD
        self.ssh_pid, stdin_fd, stdout_fd, stderr_fd = \
            gobject.spawn_async(args, flags=flags)
        gobject.child_watch_add(self.ssh_pid, self._restart_forwarding)

    def _install_plugin(self):
        plugin_contents = self._load_plugin_contents()
        scripts_dir, autorun_dir, plugin_name = self._get_plugin_path()
        plugin_path = os.path.join('~', scripts_dir, plugin_name)
        autorun_path = os.path.join('~', autorun_dir, plugin_name)
        args = ['ssh', self.target, '-o', 'PasswordAuthentication no',
                'cat > {0}; ln -sf {1} {2}'.format(plugin_path, plugin_path,
                                                   autorun_path)]
        if self.keyfile:
            args[2:2] = ['-i', self.keyfile]
        flags = gobject.SPAWN_SEARCH_PATH
        pid, stdin_fd, stdout_fd, stderr_fd = \
            gobject.spawn_async(args, flags=flags, standard_input=True)
        stdin = os.fdopen(stdin_fd, 'w')
        try:
            stdin.write(plugin_contents)
        finally:
            stdin.close()

    def start(self):
        self._install_plugin()
        self._start_forwarding()

    def close(self):
        self.done = True
        if self.ssh_pid:
            os.kill(self.ssh_pid, signal.SIGTERM)


def _parse_args():
    desc = 'Adds a GTK status-bar icon allowing one-click control of irssi.'
    version = '%prog {0}'.format(__version__)
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-v', '--version', action='version', version=version)
    parser.add_argument('-f', '--foreground', action='store_true',
                        dest='foreground', help='Do not run as a daemon.')
    parser.add_argument('--no-notify', action='store_true',
                        help='Disable libnotify notifications.')
    parser.add_argument('--on-click', dest='onclick', metavar='CMD',
                        help='Execute CMD when the icon is clicked.')
    parser.add_argument('--clear', action='store_true', dest='clear',
                        help='Signal a clear event to a running daemon.')
    parser.add_argument('--ssh', metavar='TARGET', default=None,
                        help='Forward the listening port to TARGET, which ' \
                        'is of the form [user@]host[:port]')
    parser.add_argument('--ssh-key', metavar='FILE', default=None,
                        help='If given, FILE is used as an SSH key. If a ' \
                        'key cannot be found, the password must be entered ' \
                        'in a dialog box.')
                         
    return parser.parse_args()


def _daemonize():
    """Daemonize the current process."""

    # Fork once.
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError:
        return

    # Set some options to detach from the terminal.
    os.chdir('/')
    os.setsid()
    os.umask(0)

    # Fork again.
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError:
        return

    # Find the OS /dev/null equivalent.
    nullfile = getattr(os, 'devnull', '/dev/null')
    logfile = '/tmp/irssi-icon.log'

    # Redirect all standard I/O to /dev/null.
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(nullfile, 'r')
    so = open(logfile, 'a+')
    se = open(logfile, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def main():
    args = _parse_args()

    if args.clear:
        Irssi(None, args).send_clear_message()
        sys.exit(0)

    if not args.foreground:
        _daemonize()
    state = State(args)

    try:
        state.main()
    except KeyboardInterrupt:
        pass
    state.close()


# vim:et:sts=4:sw=4:ts=4
