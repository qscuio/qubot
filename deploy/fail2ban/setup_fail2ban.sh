#!/bin/bash
# Fail2ban setup script for QuBot
# Run with: sudo bash setup_fail2ban.sh

set -e

echo "🔒 Setting up Fail2ban for QuBot..."

# Install fail2ban
echo "📦 Installing fail2ban..."
apt update
apt install -y fail2ban

# Create log directory
echo "📁 Creating log directory..."
mkdir -p /var/log/qubot
chown ubuntu:ubuntu /var/log/qubot

# Copy filter
echo "📝 Installing filter..."
cp qubot-scanner.conf /etc/fail2ban/filter.d/

# Copy jail config
echo "⚙️ Installing jail config..."
cp qubot.local /etc/fail2ban/jail.d/

# Enable and restart fail2ban
echo "🚀 Starting fail2ban..."
systemctl enable fail2ban
systemctl restart fail2ban

# Wait a moment and check status
sleep 2
echo ""
echo "✅ Fail2ban setup complete!"
echo ""
echo "📊 Status:"
fail2ban-client status
echo ""
echo "📋 QuBot jail status:"
fail2ban-client status qubot-scanner 2>/dev/null || echo "Jail will activate when log file is created"
echo ""
echo "💡 Tips:"
echo "  - View bans: sudo fail2ban-client status qubot-scanner"
echo "  - Unban IP:  sudo fail2ban-client set qubot-scanner unbanip <IP>"
echo "  - View log:  sudo tail -f /var/log/fail2ban.log"
