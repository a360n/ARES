#!/bin/bash
# ARES Level 3 Network & Linux Infrastructure Hardening Script
# Targets Raspberry Pi companion computers, UAVs, UGVs, and Central Control PCs.
# Enforces strict UFW rules, subnet whitelisting, service deactivation, and DDoS rate-limiting.
# MUST BE RUN WITH ROOT PRIVILEGES (sudo)

set -e

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERROR: This script must be run with root privileges (sudo)."
  exit 1
fi

echo "[*] Initializing ARES Level 3 OS & Infrastructure Hardening Sweeps..."

# ----------------------------------------------------
# 1. Firewall Hardening via UFW (Uncomplicated Firewall)
# ----------------------------------------------------
echo "[*] Configuring UFW firewall rules..."

# Install UFW if not present (Raspberry Pi/Debian systems)
if ! command -v ufw >/dev/null 2>&1; then
  echo "  > UFW not found. Installing via apt..."
  apt-get update && apt-get install -y ufw
fi

# Reset UFW rules to default
ufw --force reset

# Set default policies to block all incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

# Whitelist Port 5001 (ARES Web UI/API over HTTPS) strictly from the ARES static IP subnet (192.168.10.0/24)
echo "[+] Whitelisting HTTPS Control Port 5001 from ARES Subnet (192.168.10.0/24) only..."
ufw allow proto tcp from 192.168.10.0/24 to any port 5001 comment 'ARES HTTPS Control Interface'

# Whitelist SSH Port 22 strictly from the ARES static IP subnet (192.168.10.0/24)
echo "[+] Whitelisting SSH Port 22 from ARES Subnet (192.168.10.0/24) only..."
ufw allow proto tcp from 192.168.10.0/24 to any port 22 comment 'ARES Secure SSH'

# Enable UFW
echo "[*] Enabling UFW firewall..."
ufw --force enable

# ----------------------------------------------------
# 2. Advanced DDoS Prevention via iptables
# ----------------------------------------------------
echo "[*] Injecting advanced iptables rate limiting rules for DDoS protection..."

# Drop invalid packets
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# Rate-limit TCP SYN flood attacks (Limit new TCP connections to 10/sec, burst of 15)
iptables -A INPUT -p tcp --syn -m limit --limit 10/s --limit-burst 15 -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP

# Rate-limit ICMP (ping) flood attacks (Limit ping to 3/sec, burst of 5)
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 3/s --limit-burst 5 -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -j DROP

# Limit concurrent TCP connections per IP to 25 (mitigates resource exhaustion)
iptables -A INPUT -p tcp --syn --dport 5001 -m connlimit --connlimit-above 25 -j REJECT --reject-with tcp-reset

# ----------------------------------------------------
# 3. Disable Non-Essential Services & Protocols
# ----------------------------------------------------
echo "[*] Auditing and disabling non-essential discovery/communications services..."

# Disable Avahi-daemon (mDNS / Bonjour)
if systemctl is-active --quiet avahi-daemon; then
  echo "  > Stopping and disabling Avahi Bonjour discovery daemon..."
  systemctl stop avahi-daemon || true
  systemctl disable avahi-daemon || true
fi

# Disable Bluetooth / Bluez RF links
if systemctl is-active --quiet bluetooth; then
  echo "  > Stopping and disabling Bluetooth service..."
  systemctl stop bluetooth || true
  systemctl disable bluetooth || true
fi

# Disable IPv6 stack globally (prevents address translation/spoofing exploits)
echo "[*] Disabling IPv6 globally in sysctl..."
sysctl -w net.ipv6.conf.all.disable_ipv6=1
sysctl -w net.ipv6.conf.default.disable_ipv6=1
sysctl -w net.ipv6.conf.lo.disable_ipv6=1
sysctl -p || true

# ----------------------------------------------------
# 4. Zero-Day Payload Persistence Defense
# ----------------------------------------------------
echo "[*] Configuring automated cron job to purge temporary folders (/tmp, /var/tmp) on boot..."

CRON_JOB="@reboot rm -rf /tmp/* /var/tmp/* >/dev/null 2>&1"
# Ensure duplicate cron jobs aren't created
(crontab -l 2>/dev/null | grep -Fv "/tmp/*" ; echo "${CRON_JOB}") | crontab -

echo "--------------------------------------------------------"
echo "[✅ ARES SECURITY STATUS] Level 3 OS & Infrastructure Hardened."
echo "  > UFW Firewall: Default DENY incoming active."
echo "  > Subnet Whitelist: Ports 5001 & 22 only accessible from 192.168.10.0/24."
echo "  > Services: Bluetooth, Avahi/Bonjour, and IPv6 deactivated."
echo "  > Persistence Mitigation: /tmp cleaning cron job installed."
echo "--------------------------------------------------------"
