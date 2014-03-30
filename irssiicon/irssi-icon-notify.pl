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
use IO::Socket::INET;

$VERSION = "<<irssi-icon version>>";

%IRSSI = (
    authors     => 'Ian Good',
    contact     => 'ian.good@rackspace.com',
    name        => 'irssi-icon-notify.pl',
    description => 'Sends message and whisper notifications to irssi-icon.py',
);

my $TCP_HOST = '127.0.0.1';
my $TCP_PORT = '21693';

sub write_and_close {
    my $args = shift;
    my ($input_tag, $sock, $data) = @$args;

    print $sock $data;
    close $sock;

    Irssi::input_remove($$input_tag);
}

sub send_data {
    my ($data) = @_;

    my $sock = IO::Socket::INET->new(
        PeerHost => $TCP_HOST,
        PeerPort => $TCP_PORT,
        Proto => 'tcp',
    ) or return;
    $sock->blocking(0);
    my $tag;
    my @args = (\$tag, $sock, $data);
    $tag = Irssi::input_add($sock->fileno, Irssi::INPUT_WRITE,
                            \&write_and_close, \@args);
}

sub print_text_notify {
    my ($dest, $text, $stripped) = @_;
    my $server = $dest->{server};

    return if (!$server || !($dest->{level} & MSGLEVEL_PUBLIC));
    my $sender = $stripped;
    $sender =~ s/^\<.([^\>]+)\>.+/$1/;
    $stripped =~ s/^\<.[^\>]+\>.//;

    my $line = "$VERSION:NEWMSG> $sender\r\n" . $dest->{target};

    send_data($line);
}

sub message_private_notify {
    my ($server, $msg, $nick, $address) = @_;

    return if (!$server);

    my $line = "$VERSION:NEWWHISPER> $nick\r\n" . $msg;

    send_data($line);
}

Irssi::signal_add('print text', 'print_text_notify');
Irssi::signal_add('message private', 'message_private_notify');

# vim:sw=4:ts=4:sts=4:et:
