#!/usr/bin/env python2.7
LICENSE = """\
Copyright (c) 2012 Ian Good <ian.good@rackspace.com>

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
import sys
import stat
import socket
import subprocess
import base64
import zlib
import argparse

import dbus
import gobject
import pygtk
import gtk

_VERSION = '0.0'

# {{{ class State
class State(object):

    def __init__(self, args):
        self.icon = Icon(self, args)
        self.irssi = Irssi(self, args)

    def main(self):
        self.icon.start()
        self.irssi.start()
        gtk.main()

    def icon_clicked(self):
        self.icon.clear_alert_icon()
        self.irssi.click_action()

    def new_irssi_message(self, extra, whisper=False):
        self.icon.set_alert(extra, whisper)

# }}}

# {{{ class Irssi
class Irssi(object):

    _screen_session_name = 'irssi'
    _irssi_execute = ['irssi']

    def __init__(self, state, args):
        self.state = state
        self.onclick = args.onclick
        self.sockfile = args.sockfile

    def start(self):
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
            self.state.icon_clicked()
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
                                           stdout=subprocess.PIPE,
                                           shell=True)
        p.communicate()

# }}}

# {{{ class Icon
class Icon(object):

    _emblem_dir = '/usr/share/icons/gnome/48x48/emblems'

    def __init__(self, state, args):
        self.state = state
        self.icon = None
        self._whisper_alert = False
        self._load_icon(args)
        self._create_icon()

    def start(self):
        pass

    def _load_icon(self, args):
        if args.icon:
            self._icon_pixbuf = gtk.gdk.pixbuf_new_from_file(args.icon)
        else:
            self._icon_pixbuf = ICON_PIXBUF
        self._add_icon_emblems()

    def _make_emblem_composite(self, bg, fg):
        third_x = bg.props.width / 3
        third_y = bg.props.height / 3
        fg.composite(bg, 0, 0, fg.props.width, fg.props.height,
                     third_x, third_y, 0.666, 0.666,
                     gtk.gdk.INTERP_HYPER, 255)

    def _add_icon_emblems(self):
        imp = gtk.gdk.pixbuf_new_from_file(self._emblem_dir + '/emblem-important.png')
        new = gtk.gdk.pixbuf_new_from_file(self._emblem_dir + '/emblem-generic.png')

        self._important_icon_pixbuf = self._icon_pixbuf.copy()
        self._new_icon_pixbuf = self._icon_pixbuf.copy()

        self._make_emblem_composite(self._important_icon_pixbuf, imp)
        self._make_emblem_composite(self._new_icon_pixbuf, new)

    def _create_icon(self):
        self.icon = gtk.StatusIcon()
        self.icon.connect('popup-menu', self._right_click)
        self.icon.connect('activate', self._left_click)
        self.clear_alert_icon()

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
            self.icon.set_from_pixbuf(self._new_icon_pixbuf)
            if extra:
                self.icon.set_tooltip('Irssi Icon\nNew messages in ' + extra)

    def _right_click(self, icon, button, timestamp):
        menu = gtk.Menu()

        restart = gtk.ImageMenuItem('Restart')
        about = gtk.ImageMenuItem('About')
        quit = gtk.ImageMenuItem('Quit')

        img = gtk.image_new_from_stock(gtk.STOCK_REFRESH, gtk.ICON_SIZE_MENU)
        img.show()
        restart.set_image(img)

        img = gtk.image_new_from_stock(gtk.STOCK_ABOUT, gtk.ICON_SIZE_MENU)
        img.show()
        about.set_image(img)

        img = gtk.image_new_from_stock(gtk.STOCK_QUIT, gtk.ICON_SIZE_MENU)
        img.show()
        quit.set_image(img)

        about.connect('activate', self._show_about_dialog)
        quit.connect('activate', gtk.main_quit)

        menu.append(restart)
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

        about.set_comments('Displays an icon to give notifications from irssi.')

        about.run()
        about.destroy()

# }}}

# {{{ ICON_PIXBUF
ICON_PIXBUF = gtk.gdk.pixbuf_new_from_data(zlib.decompress(base64.b64decode(
'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'
'Pl+7fyVfWjWVeByuZvnd+j/36f/lv5d/A6EoiJ4='
    )), gtk.gdk.COLORSPACE_RGB, True, 8, 48, 48, 192)
# }}}

# {{{ _parse_args()
def _parse_args():
    parser = argparse.ArgumentParser(description='Adds a GTK status-bar icon allowing one-click control of irssi.')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s '+_VERSION)
    parser.add_argument('-f', '--foreground', action='store_true', dest='foreground',
                        help='Run this application in the foreground, do not daemonize.')
    parser.add_argument('--icon', dest='icon', metavar='FILE',
                        help='Use FILE as the status-bar icon.')
    parser.add_argument('--on-click', dest='onclick', metavar='CMD',
                        help='Execute CMD when the icon is clicked.')
    parser.add_argument('--socket-file', dest='sockfile', metavar='FILE',
                        help='Communicate with irssi plugin on FILE socket.',
                        default='/tmp/irssi-icon.socket')
    parser.add_argument('--click', action='store_true', dest='click',
                        help='Signal a click event to a running daemon.')
    return parser.parse_args()
# }}}

# {{{ _daemonize()
# Daemonize the current process.
def _daemonize():

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
# }}}

if __name__ == '__main__':
    args = _parse_args()

    if args.click:
        Irssi(None, args).send_clear_message()
        sys.exit(0)

    state = State(args)
    if not args.foreground:
        _daemonize()

    state.main()

# vim:et:fdm=marker:sts=4:sw=4:ts=4
