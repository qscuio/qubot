# Fail2ban Configuration for QuBot API
# =====================================
# 
# This guide helps you set up fail2ban to automatically block
# attackers who scan your API for vulnerabilities.

## Step 1: Install fail2ban

```bash
sudo apt update
sudo apt install -y fail2ban
```

## Step 2: Create custom filter for QuBot scanner detection

Create file: `/etc/fail2ban/filter.d/qubot-scanner.conf`

```ini
[Definition]
# Match scanner patterns in uvicorn/gunicorn logs
# Matches lines like: INFO: 35.93.174.253:5998 - "GET /niet951591809.html HTTP/1.1" 404 Not Found

failregex = ^INFO:\s+<HOST>:\d+ - "(?:GET|POST|PUT|DELETE|HEAD|OPTIONS) /(?:.*\.(?:php\d?|htr|asp|aspx|cfm|cgi|pl|jsp|jspx)|iisadmpwd|phpmyadmin|wp-admin|wp-login|\.env|\.git|administrator|shell|eval-stdin|niet)\S* HTTP/\d\.\d" (?:404|403|500)
            ^.*<HOST>.*Scanner detected.*$
            ^.*<HOST>.*Blocked request.*$

ignoreregex = 

# Date pattern for uvicorn logs (no date in default, using journal)
datepattern = 
```

## Step 3: Create jail configuration

Create file: `/etc/fail2ban/jail.d/qubot.conf`

```ini
[qubot-scanner]
enabled = true
port = http,https,8000
filter = qubot-scanner
# Point to your app's log file or use journal
logpath = /var/log/qubot/app.log
# Or if using systemd:
# backend = systemd
# journalmatch = _SYSTEMD_UNIT=qubot.service

# Ban settings
maxretry = 5          # Ban after 5 suspicious requests
findtime = 600        # Within 10 minutes
bantime = 3600        # Ban for 1 hour
action = iptables-multiport[name=qubot, port="http,https,8000", protocol=tcp]

# Increase ban time for repeat offenders
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 86400   # Max 24 hours
```

## Step 4: Configure logging in your app

Make sure your app logs to a file fail2ban can read. Add to your systemd service:

```ini
[Service]
StandardOutput=append:/var/log/qubot/app.log
StandardError=append:/var/log/qubot/app.log
```

Or create the log directory:

```bash
sudo mkdir -p /var/log/qubot
sudo chown $USER:$USER /var/log/qubot
```

## Step 5: Enable and start fail2ban

```bash
# Test the filter first
sudo fail2ban-regex /var/log/qubot/app.log /etc/fail2ban/filter.d/qubot-scanner.conf

# Restart fail2ban
sudo systemctl enable fail2ban
sudo systemctl restart fail2ban

# Check status
sudo fail2ban-client status qubot-scanner
```

## Step 6: Useful commands

```bash
# View banned IPs
sudo fail2ban-client status qubot-scanner

# Unban an IP
sudo fail2ban-client set qubot-scanner unbanip 1.2.3.4

# View fail2ban log
sudo tail -f /var/log/fail2ban.log

# Test filter against log
sudo fail2ban-regex /var/log/qubot/app.log /etc/fail2ban/filter.d/qubot-scanner.conf --print-all-matched
```

## Alternative: Use systemd journal (recommended)

If your app runs via systemd, use journal backend:

```ini
[qubot-scanner]
enabled = true
port = http,https,8000
filter = qubot-scanner
backend = systemd
journalmatch = SYSLOG_IDENTIFIER=uvicorn _SYSTEMD_UNIT=qubot.service
maxretry = 5
findtime = 600
bantime = 3600
action = iptables-multiport[name=qubot, port="http,https,8000", protocol=tcp]
```
