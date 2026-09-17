#!/bin/sh
set -eu

/usr/sbin/sshd -t
/usr/sbin/sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin|maxauthtries|x11forwarding|allowtcpforwarding) '
fail2ban-client status sshd
systemctl is-active --quiet fail2ban
echo "HOST_SECURITY_OK"
