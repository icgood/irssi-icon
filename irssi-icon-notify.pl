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
use HTML::Entities;

$SOCKFILE = "/tmp/irssi-icon.socket";
$VERSION = "0.01";

%IRSSI = (
    authors     => 'Ian Good',
    contact     => 'ian.good@rackspace.com',
    name        => 'irssi-icon-notify.pl',
    description => 'Sends message and whisper notifications to irssi-icon.py',
);

sub sanitize {
  my ($text) = @_;
  encode_entities($text);
  return $text;
}

sub print_text_notify {
    my ($dest, $text, $stripped) = @_;
    my $server = $dest->{server};

	return if (!$server || !($dest->{level} & MSGLEVEL_PUBLIC));
    my $sender = $stripped;
    $sender =~ s/^\<.([^\>]+)\>.+/\1/ ;
    $stripped =~ s/^\<.[^\>]+\>.// ;

    my $line = "NEWMSG $sender " . $dest->{target};

    my $cmd = "EXEC - socat EXEC:\"echo $line\" GOPEN:$SOCKFILE";
    $server->command($cmd);
}

sub message_private_notify {
    my ($server, $msg, $nick, $address) = @_;

    return if (!$server);

    my $line = "NEWWHISPER $nick";

    my $cmd = "EXEC - socat EXEC:\"echo $line\" GOPEN:$SOCKFILE";
    $server->command($cmd);
}

Irssi::signal_add('print text', 'print_text_notify');
Irssi::signal_add('message private', 'message_private_notify');
