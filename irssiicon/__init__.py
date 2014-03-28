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

import dbus
import gobject
import pygtk
import gtk


__version__ = pkg_resources.require('irssi-icon')[0].version


class State(object):

    def __init__(self, args):
        self.icon = Icon(self, args)
        self.irssi = Irssi(self, args)

    def main(self):
        self.icon.start()
        self.irssi.start()
        gtk.main()

    def icon_clicked(self, action=True):
        self.icon.clear_alert_icon()
        if action:
            self.irssi.click_action()

    def new_irssi_message(self, extra, whisper=False):
        self.icon.set_alert(extra, whisper)

    def check_irssi_plugin(self):
        base = os.path.join(os.path.expanduser('~'), '.irssi')
        scripts = os.path.join(base, 'scripts')
        autorun = os.path.join(scripts, 'autorun')
        plugin_name = 'irssi-icon-notify.pl'
        return os.path.exists(os.path.join(scripts, plugin_name))

    def setup_irssi_plugin(self):
        base = os.path.join(os.path.expanduser('~'), '.irssi')
        scripts = os.path.join(base, 'scripts')
        autorun = os.path.join(scripts, 'autorun')
        plugin_name = 'irssi-icon-notify.pl'
        try:
            os.makedirs(autorun)
        except OSError, (err, msg):
            if err != 17:
                raise
        from pkg_resources import Requirement, resource_stream
        res_name = os.path.join('irssiicon', plugin_name)
        from_fp = resource_stream(Requirement.parse('irssi-icon'), res_name)
        try:
            with open(os.path.join(scripts, plugin_name), 'w') as to_fp:
                shutil.copyfileobj(from_fp, to_fp)
        finally:
            from_fp.close()
        try:
            os.unlink(os.path.join(autorun, plugin_name))
        except OSError, (err, msg):
            if err != 2:
                raise
        os.symlink(os.path.join(scripts, plugin_name),
                   os.path.join(autorun, plugin_name))


class Irssi(object):

    _screen_session_name = 'irssi'
    _irssi_execute = ['irssi']

    def __init__(self, state, args):
        self.state = state
        self.start_irssi = not args.no_irssi
        self.onclick = args.onclick
        self.sockfile = args.sockfile

    def start(self):
        if self.start_irssi:
            self.start_if_not_running()
        self._connect_local_socket(self.sockfile)

    def send_clear_message(self):
        s = socket.socket(socket.AF_UNIX)
        s.connect(self.sockfile)
        s.send('CLEAR\r\n')
        s.close()

    def _msg_client_data(self, client, cond):
        words = client.recv(256).split(None, 2)
        if words[0] == 'NEWMSG':
            channel = words[2] if len(words) >= 3 else None
            self.state.new_irssi_message(channel.strip())
        elif words[0] == 'NEWWHISPER':
            sender = words[1] if len(words) >= 2 else None
            self.state.new_irssi_message(sender.strip(), whisper=True)
        elif words[0] == 'CLEAR':
            self.state.icon_clicked(False)
        client.close()
        return False

    def _msg_sock_connection(self, f, cond):
        client, from_ = f.accept()
        gobject.io_add_watch(client, gobject.IO_IN, self._msg_client_data)
        return True

    def _connect_local_socket(self, sockfile):
        try:
            os.unlink(sockfile)
        except OSError:
            pass
        self._msg_sock = socket.socket(socket.AF_UNIX)
        self._msg_sock.bind(sockfile)
        self._msg_sock.listen(5)
        gobject.io_add_watch(self._msg_sock, gobject.IO_IN,
                             self._msg_sock_connection)

    def _is_running(self):
        args = ['screen', '-ls', self._screen_session_name]
        p = subprocess.Popen(args, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        out, err = p.communicate()
        return out.startswith('There is a screen on:')

    def _start_irssi_screen(self):
        args = ['screen', '-S', self._screen_session_name, '-d', '-m'] + \
            self._irssi_execute
        p = subprocess.Popen(args, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
        p.communicate()

    def start_if_not_running(self):
        if not self._is_running():
            self._start_irssi_screen()

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
        self._whisper_alert = False
        self._load_icons()

    def start(self):
        self._create_icon()
        if not self.state.check_irssi_plugin():
            self._ask_about_irssi_plugin()

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

    def _ask_about_irssi_plugin(self):
        msg = 'The irssi plugin required for proper functionality has not ' \
              'been installed. Do this now?'
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        box = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO, flags=flags,
                                type=gtk.MESSAGE_WARNING,
                                message_format=msg)
        response = box.run()
        box.destroy()
        if response == gtk.RESPONSE_YES:
            self.state.setup_irssi_plugin()
        else:
            sys.exit(1)

    def clear_alert_icon(self):
        self._whisper_alert = False
        self.icon.set_from_pixbuf(self._icon_pixbuf)
        self.icon.set_tooltip('Irssi Icon')

    def set_alert(self, extra, whisper):
        if whisper:
            self._whisper_alert = True
            self.icon.set_from_pixbuf(self._important_icon_pixbuf)
            if extra:
                self.icon.set_tooltip('Irssi Icon\nWhisper from ' + extra)
        elif not self._whisper_alert:
            self.icon.set_from_pixbuf(self._notify_icon_pixbuf)
            if extra:
                self.icon.set_tooltip('Irssi Icon\nNew messages in ' + extra)

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
        about.set_version(_VERSION)
        about.set_authors(['Ian Good <ian.good@rackspace.com>'])
        about.set_license(LICENSE)

        comments = 'Displays an icon to give notifications from irssi.'
        about.set_comments(comments)

        about.run()
        about.destroy()


def _parse_args():
    desc = 'Adds a GTK status-bar icon allowing one-click control of irssi.'
    version = '%prog {0}'.format(__version__)
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-v', '--version', action='version', version=version)
    parser.add_argument('-f', '--foreground', action='store_true',
                        dest='foreground', help='Do not run as a daemon.')
    parser.add_argument('--no-irssi', action='store_true', dest='no_irssi',
                        help='Do not check for or start irssi automatically.')
    parser.add_argument('--on-click', dest='onclick', metavar='CMD',
                        help='Execute CMD when the icon is clicked.')
    parser.add_argument('--socket-file', dest='sockfile', metavar='FILE',
                        help='Communicate with irssi plugin on FILE socket.',
                        default='/tmp/irssi-icon.socket')
    parser.add_argument('--clear', action='store_true', dest='clear',
                        help='Signal a clear event to a running daemon.')
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

    # Redirect all standard I/O to /dev/null.
    sys.stdout.flush()
    sys.stderr.flush()
    si = file(nullfile, 'r')
    so = file(nullfile, 'a+')
    se = file(nullfile, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def main():
    args = _parse_args()

    if args.clear:
        Irssi(None, args).send_clear_message()
        sys.exit(0)

    state = State(args)
    if not args.foreground:
        _daemonize()

    state.main()


# vim:et:sts=4:sw=4:ts=4
