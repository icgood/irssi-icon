##
## This script is a modification of notify.pl, found here:
##     http://irssi-libnotify.googlecode.com/svn/trunk/notify.pl
##
## It is installed in the global irssi scripts directory. You can add it to
## your autorun directory like so:
##
##     $ cd ~/.irssi/scripts/autorun
##     $ ln -s /usr/share/irssi/scripts/irssi-icon-notify.pl .
##

use strict;
use Irssi;
use vars qw($VERSION %IRSSI);
use IO::Socket::UNIX;

$VERSION = "0.0";

%IRSSI = (
    authors     => 'Ian Good',
    contact     => 'ian.good@rackspace.com',
    name        => 'irssi-icon-notify.pl',
    description => 'Sends message and whisper notifications to irssi-icon.py',
);

my $SOCKFILE = "/tmp/irssi-icon.socket";

sub write_and_close {
    my $args = shift;
    my ($sock, $data) = @$args;

    print $sock $data;
    close $sock;
}

sub send_data {
    my ($path, $data) = @_;

    my $sock = IO::Socket::UNIX->new($path);
    $sock->blocking(0);
    my @args = ($sock, $data);
    Irssi::input_add($sock->fileno, Irssi::INPUT_WRITE,
                     \&write_and_close, \@args);
}

sub print_text_notify {
    my ($dest, $text, $stripped) = @_;
    my $server = $dest->{server};

	return if (!$server || !($dest->{level} & MSGLEVEL_PUBLIC));
    my $sender = $stripped;
    $sender =~ s/^\<.([^\>]+)\>.+/$1/;
    $stripped =~ s/^\<.[^\>]+\>.//;

    my $line = "NEWMSG $sender " . $dest->{target};

    send_data($SOCKFILE, $line);
}

sub message_private_notify {
    my ($server, $msg, $nick, $address) = @_;

    return if (!$server);

    my $line = "NEWWHISPER $nick";

    send_data($SOCKFILE, $line);
}

Irssi::signal_add('print text', 'print_text_notify');
Irssi::signal_add('message private', 'message_private_notify');
