#!/bin/bash
# Script to restore SSH config and add alternative ports
# Run this on the server via Hetzner Console

set -e

echo "=== Restoring SSH Configuration ==="

# Backup current config (even if empty)
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date +%Y%m%d_%H%M%S)

# Create a basic SSH config with alternative ports
sudo tee /etc/ssh/sshd_config > /dev/null << 'SSHCONFIG'
# SSH Server Configuration
# Generated on $(date)

# Port configuration - listen on multiple ports
Port 22
Port 2222
Port 443

# Protocol version
Protocol 2

# Host keys
HostKey /etc/ssh/ssh_host_rsa_key
HostKey /etc/ssh/ssh_host_ecdsa_key
HostKey /etc/ssh/ssh_host_ed25519_key

# Logging
SyslogFacility AUTH
LogLevel INFO

# Authentication
LoginGraceTime 120
PermitRootLogin yes
StrictModes yes
MaxAuthTries 6
MaxSessions 10

# Public key authentication
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# Password authentication (disable for security, enable if needed)
PasswordAuthentication yes
PermitEmptyPasswords no
ChallengeResponseAuthentication no

# X11 forwarding
X11Forwarding no

# Print motd
PrintMotd no
PrintLastLog yes

# TCP keepalive
TCPKeepAlive yes
ClientAliveInterval 60
ClientAliveCountMax 3

# Use DNS
UseDNS no

# Allow users
AllowUsers root

# Subsystem
Subsystem sftp /usr/lib/openssh/sftp-server
SSHCONFIG

echo "✅ SSH config restored"

# Test the configuration
echo "Testing SSH configuration..."
if sudo sshd -t; then
    echo "✅ SSH config is valid"
else
    echo "❌ SSH config has errors!"
    exit 1
fi

# Restart SSH service
echo "Restarting SSH service..."
sudo systemctl restart ssh

# Wait a moment
sleep 2

# Check SSH status
if sudo systemctl is-active --quiet ssh; then
    echo "✅ SSH service is running"
else
    echo "❌ SSH service failed to start!"
    sudo systemctl status ssh
    exit 1
fi

# Verify ports are listening
echo ""
echo "Checking listening ports..."
sudo netstat -tlnp | grep -E ':(22|2222|443)' || sudo ss -tlnp | grep -E ':(22|2222|443)'

echo ""
echo "✅ SSH configuration complete!"
echo ""
echo "Next steps:"
echo "1. Update Hetzner Firewall to allow ports 2222 and 443"
echo "2. Test connection: ssh -p 2222 root@77.42.45.93"
echo "3. Or: ssh -p 443 root@77.42.45.93"





