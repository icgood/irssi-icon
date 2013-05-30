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
import os.path
import shutil
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

_VERSION = '1.1'

# {{{ class State
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

    def check_socat(self):
        try:
            with open(os.devnull, 'w') as ignore:
                subprocess.check_call(['socat', '-V'],
                                      stdout=ignore,
                                      stderr=ignore)
        except subprocess.CalledProcessError:
            return False
        else:
            return True

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
                                           stdout=subprocess.PIPE,
                                           shell=True)
        p.communicate()

# }}}

# {{{ class Icon
class Icon(object):

    def __init__(self, state, args):
        self.state = state
        self.icon = None
        self._whisper_alert = False
        self._load_icon(args)

    def start(self):
        self._create_icon()
        if not self.state.check_irssi_plugin():
            self._ask_about_irssi_plugin()

    def _load_icon(self, args):
        if args.icon:
            self._icon_pixbuf = gtk.gdk.pixbuf_new_from_file(args.icon)
        else:
            self._icon_pixbuf = ICON_PIXBUF
        self._add_icon_emblems()

    def _add_icon_emblems(self):
        self._important_icon_pixbuf = IMPORTANT_EMBLEM_PIXBUF
        self._new_icon_pixbuf = DEFAULT_EMBLEM_PIXBUF

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
            if not self.state.check_socat():
                self._alert_about_socat()
            self.state.setup_irssi_plugin()
        else:
            sys.exit(1)

    def _alert_about_socat(self):
        msg = 'The irssi plugin requires the \'socat\' utility. Please ' \
              'install \'socat\' using your distribution\'s package manager.'
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        box = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, flags=flags,
                                type=gtk.MESSAGE_ERROR,
                                message_format=msg)
        box.run()
        box.destroy()
        sys.exit(2)

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

# {{{ IMPORTANT_EMBLEM_PIXBUF
IMPORTANT_EMBLEM_PIXBUF = gtk.gdk.pixbuf_new_from_data(
        zlib.decompress(base64.b64decode(
'eJztmQdUVOe2x88Mw1BFkCqIgDVeiS0Frz1qKKLRqCEqCgZ7V0SJgIAUC4pBIICKiMQSIGgAMWIsF2'
'uM0ViINSpSBwYYigICc/53fwfwYqKJ5b7Fem+9vdZeHM45c+a397fbd4bj/l/+r0nEBG74Olvu/bbm'
'eFNJdOV2xkzmZrc1x5vKuWXc9aPzuDA6FLU1y5vIDS+Vyiue4kv+9pxOW7O8idxcp1NVGNIOoZOlw9'
'ua5U3kWpDVvfpd3fDjSqOTbc3yJvJTUL9M5f7BkEX2gddYPYe25nldOREwLLguaTyUSfb4Oaj/b3RK'
'va2ZXkcO+dqOKkt2ATJm8Iq9YxuT3fssaWumF0mMu4P9hjkj/tSnUgImdc5PXlzLH18BZcYs3Ai3u+'
'81qathWzD+lUS4fzLs9Palysyo5bGhHi7GLecPBEzXvZfseVV5Zh1wajVfdXAm9nv8M7AtWV8mZxL8'
'gksvxOP20ejctBi/OezchvmOKteT/PY2XAgDzgXzOLkaN6In1rbX4PTZ9a9ntFeLmNrOtm3JmyQmYF'
'G/4l++VzQ+zELZ9SONp5MiftTSEOn+krzRt+7yLuBSJNkQyFenL0L0Qhtv9hmXYfq6p1YZPY6apt7m'
'/cHCTF/z94uHC1GSDVL+ad4l3P5XYmV2Zuy5+uzveFyLx4HAGXD/qDcmDbbKU+G4DvQxyZ1Nlrji0/'
'6yv6NY7zW/UkpqqSsSBeqJxb7/BRPEdy4dz+Urc8FX5AKKBzxfnI3G3PPg7x8DbiZh2yonHLSygkdH'
'Y57u/1LMcR1ztr6D0jAjRE9VdW5+jgrTDioqL5yZpCIRO/8RqccCdfU7mdbWTwaoqX33tvDDB3+g9S'
'D750K+thx8DeljGfjyB+Bl14Cc0+DvpGLb6mk4OmAAFF5r4G1sXKOjoRJ5K+QfaNjRCfvd1OLIng5q'
'lDbDNDRYv57R+vmiJn9b0T0bBqqrJx14h+xetAiHBwwopwtfvC1/aLC/VWHOHTka6sA31EJZqwBfVQ'
'BlyU3weeeBexnY5umMI/3740lmJsq++gqxnc2f+k8yRVl4J6QuUGPM810NDZ8c79oVdLy4mZs5nPnb'
'faREcivV2lqRM2MGSubNQ6mbGz9EIqmmaz1ehzXBb8rUWF+X5+aBlH1xI8pkj6r5hqdQkvJ1leArCw'
'D5LeK/ANzNQJjndIH/cXo6qjMy8Dg6GindrOBn3x7hn0uvDRSL9+dNmYLi2bPRVyxOpMe+Q7qhp1i8'
'b0uXLiieNQsly5ejaO5cyObMQXKPHsxOT7LP+IWgL5H4tU7zs1MCa/eFLHVtOfd16PolIcH+jSczM9'
'BQU4GnlTI0lFL8FN8An3uW+NMRRvGT0a8fqlNSUEVa+d13UERF4Xg/a0yxkMgujBvHV2zfjsoNG+Cj'
'qSkz5bjwnWZm1XdcXFDq4QHZsmUoWrAAhW5uyKNzDtraJ+irXV6HnYmpnkT799QA5Bz/Wrl/66rJ7F'
'x4sHfkAj09hI0fC4/xjpjnaAevxbNw7/z3uPnjbtw9GsFvdf8Mhxn/t9+iMjERlfv2oeKbb1BJ65A9'
'bBjKtmxB+bZtKA8JwTlap2xHRyjWrUPxqlUoXrECRRTvzPdFtA7nxoxRGohE+16XvUUuJ3hcV17dg7'
'ysOKTHBq49GLs5Y/n0yUjs3h1FPj64vXgxLo7/BHvNTeHX0QifWJrCf44DUvv2RVVCgsCt2L0bithY'
'lJPPyyMiUBYWhjJil69fj1J/f8jXrkWJpydk7u6QLVmCovnzBfYKWovlWlqVhDHwTflPR82Lrr8YCf'
'7GPlT/mtT45OaRpycTI7HEeQLShwxB1Z49Qow8Tk4W4rycGC58+CGujhyJil27BG7Fjh0op/gRlPGT'
'/+XBwZAHBEBOPihZs6aJvTluiigviih2Lrz/Pot7f+414761HAudtqrmVBBwOQbI3gv+Vgr4u4fxa1'
'okFk9xwI533xXioiI+HgrSCvJ1RVwcFDExKGfKbIqMFHxe+PnnKKRYKaC/ZZs3o6SZvXjlyiZ2FjeU'
'r4UU80yXdux4kftDfX1dOREyYUVN5irg/AbwlyKAX3cC1xNoPfbi1C5vftHkEdhPMVwRHi74WcF4W/'
'maxTnzd2lQEI527oz9Jib41dhYOPcsZohdtnBhU8yT3wumT8eNKVN4K6pHb8PO5GyI7fb6jLlsrgTO'
'+JMdG4GLW4Gfw5jyZ7Yvwvyx7+MrqnEKiukyskOIb6r7AjedK6U6U+rri+8tLLCT+K+YmwvnnvM71f'
'kWdvnSpYg2MSmlr3/vVTnjnbkOxxaJrqXOk6xZP0H67D3ClZBB55WpnwNH3MAfWwKc8OBx6ksgy4fn'
's7xxeMPkn2KWj85Z6GiNuF69UB4YiNKNG5uYmbIcpb9yipNviT/MyAhXqMbL/fwgI07m80Jizp80CX'
'ljxwpa7OTUMEgiKaevDyDtStrl7/h3OHHat7y504rNKrjuo3Zpj6uU9ULubmifeiSPBg6NB9LIjgwX'
'vuZ7VzRkzMbTNDfscR+a4DzCcp3HhJ6Ya0v+ZWw+Pryc7JBTzAjK8pT4E4h/vq4u9lP8FLm6In/iRO'
'SNH4+8ceOQN2YMcu3tkWtnh0f29vwNypO0Xr0Uy7S1y2kzuotQ2J5u6sv4Nal/X1rJbXv6FYeGCDEK'
'Nkqrsjx09lRGdwX29QcODAKSRqIx2R67Fr57PitwUF3U3D7opat200Zd/VtPS0v89MEHKKOaJ/C2Up'
'ancsrLUZqaMJVIEG9o2ORzyuP8zz5rsmPCBMGOXAcH5NraInfUKOTTsZzuy6HjJLLdWio99FdrkD6L'
'c6rYxNUiguMRKYIyWgp+hy6PuE5AfHfgm774PbQ3uhupHXTT1VamDuiFSzQHPKJaXUq5KNRCVssp1u'
'VU19kxi+sCqiVFxGdH/J2JP41iqHDmTBRMm4aCqVOb7Jg8GfmffvqcDY+IW0Yz0C8DB2KWicnxdjRD'
'/xW/x3Cu40NfroQPJ/5wDviaNEoF/HZ1YIcOsMsYWR4GCNDXK7k8fEjd78TA6rWcfM56Z8nq1UI9LP'
'H2FvKywNkZBfT9hRQrxcRqr6Mj8P9As3VLnWT5KtxHfmhtQz7Zy+a3fT17KgxFojjCG9ZFVfVv30+e'
'XcL9WL+VuLeRRjRrJLNFBMSo4pafauPQbqJRFjrc7lm9VbGoq4E8kWbcHIrbMlYPiVvgIibGXUhrw1'
'hLqLY40NzB+I+9915TvaFrbMYpJM5nNlA8lVBPP9WnD2y1tf9FwHMJy/LvuFsk5jNuXEmQGMowDjzT'
'bRzPs7Vo1vu+XL3Xx1zPNbZcu+truFOLh3GF9LGFZhyXlGpiUlNM68F8yuJD6KOsplN9lFN9d6Xa+U'
'9VVZz++GMUEWNLr21tQyHpXerr9mpqKfRc91flbi2XV0gLGkIlUG4Vo5HWomw91ygL5PCUju94c0+9'
'RnPd2X0ZczjXH+ZyNXQ4fLSWVto9WvPn2GmOkRE7m2nYuuQR7yNmD81orHYKs04rG1isCTlB63CLbH'
'TS1mY2zBM17UFfWdJmStcogqSo36LK121Rxdkl4h8C7Dhbyu/MgzO5h8uGcCbsvgU2nPqcD7lkA46L'
'+8XGBkUsbli8s5ih+BDYGSf12GLKjTLScsoTOcVZcfOc/JwNLKfZ59k6UF4/ohweq6PzhL5qvUrTfv'
'OVZOdEVYu7nppP6japo26TFL+tVpWHjJFYNV9WbX0v1d29ybRXlFGst8Q8i/ciihcZxQhjZ3ldSMdu'
'Zmawo9q/g3pEOfWvZzY0919m932aG87R7Mo0i3LgB9qjDW/aZ74y/6qhEum5he0OVAbpoXajDq8I0k'
'baF+rJre+h/amE/sz0MTa+lO/kJKy5wE9xIOQm8z3toYS65OWFAvLxCHV1IX/XUx1SUF8r+fJLFLP5'
'h/Vhtl+hNbhNz7JSUdlDz/bimnrWUtIZL9vnv0ziJrVzzFljVPMk2JCv2aCPXJ/22OwgafmNiD1rpo'
'tUms3ildUM9pf1pMIvvhBYStlsQ3HOGFn/Yj62F4lAiYMwskNBM4Ywe5J9Lfxs3WRkf2yXLrX0/Lf+'
'PerITP3DJb6mqA405auCTHB1uV6Z5xANa7qkbyWRpF+kHGP1ms0urH4UE/tDitvzNBPsMTAofUQsjJ'
'/tT0pp3q+l2bSB5tJqmqdLWH9r7hlCjrD5k/UEygHWiwerqLB9seXb8I/rqm6QNbfjbflaS1Sts+Dl'
'vp2R4qx/llbSJ8XSsi6f+kwR+b5y8WL+Ms0OwdSXBtMsQf0m9V2JJOE+61uUq6yfyWl/qKDjEzRrsz'
'5dSvF/dqANMqkXsLVqiR+hdlEdONy/f4WUas/brsGmUXo9zszu9EDu3R0K3+5YMVgPW8w6NsjJ19fI'
'74k9esg/lUqr6FYf0mVc0zsQrrdEcojtx1mOMv58qqUbzUyw8D0jXJ34KUppTVJ792b7q4B1Ghp3sm'
'mGeNaTKRYfkF+GaWqe4t5g3/5HWTFQ1/rkrM6/PfToofT8RwfsJT8v6myQYy4SpXNNcdqTe36PJ3mH'
'+G+xmKL8lLu58Z5GBvzCD4wQP8HqsYumRn2VhwefQH272eYZ3VVU0mKtrGpLnJ35IpZHZE8i1Sm65i'
'l+i/1ji1hocboJE019Vg0yKPIcaoTdE82R5GQeNdxc8qLfWiRdxeJDv1H83KO6NEuvvdK1r371ptFm'
'Uf0N1UbR9ZV7u3WrDe/WjfGx+kKIwrtq96ESSdWJkSOVuZRXFa6u/GQ1Nba2Nm/L3yLLbfQM/IYbOu'
'wY1yl+/ySL0tCPO2a+iJ/qZNpPFOuOWpr15jqqGTamGr25/9Rw/T5qamluVEfZI1s+1Px+yqY99ZQl'
'+voXbo8ejXN2dkq9t3h/8ndioSsy4/78u7XIWEVl9kcaGpvpeIH4z/2f3c/i2p0ORr7k0a7mYvGtbw'
'wNK+21tLLY//9d8v9ZETe/x1UVifzMJBI2B7107/W/Sf4Nsx5Zpg=='
    )), gtk.gdk.COLORSPACE_RGB, True, 8, 48, 48, 192)
# }}}

# {{{ DEFAULT_EMBLEM_PIXBUF
DEFAULT_EMBLEM_PIXBUF = gtk.gdk.pixbuf_new_from_data(
        zlib.decompress(base64.b64decode(
'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'
'HMf52ee9rUK8bK3wGZ2W14'
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
    parser.add_argument('--clear', action='store_true', dest='clear',
                        help='Signal a clear event to a running daemon.')
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

def main():
    args = _parse_args()

    if args.clear:
        Irssi(None, args).send_clear_message()
        sys.exit(0)

    state = State(args)
    if not args.foreground:
        _daemonize()

    state.main()

if __name__ == '__main__':
    main()

# vim:et:fdm=marker:sts=4:sw=4:ts=4
