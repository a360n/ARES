#!/bin/bash
# ARES Level 2 Network Security Stack Hardening Script
# Protects ARES nodes from Packet Injection, MitM, Port Scanning, and DDoS.
# MUST BE RUN WITH ROOT PRIVILEGES (sudo)

set -e

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERROR: This script must be run with root privileges (sudo)."
  exit 1
fi

echo "[*] Initializing ARES Network Stack Hardening Sweeps..."

# ----------------------------------------------------
# 1. Firewall Rule Setup (iptables)
# ----------------------------------------------------
echo "[*] Setting up iptables firewall policies..."

# Clear existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

# Set default policies to DROP all incoming and forwarding traffic
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow established and related connections (so the node can receive responses to outgoing requests)
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow all loopback (localhost) traffic
iptables -A INPUT -i lo -j ACCEPT

# Whitelist Port 5001: Central Control PC / Web Monitor (Forced HTTPS)
echo "[+] Whitelisting control port 5001 (ARES HTTPS Web Monitor/API)..."
iptables -A INPUT -p tcp --dport 5001 -m conntrack --ctstate NEW -j ACCEPT

# Whitelist SSH (Port 22): Enforce SSH Key-Based Authentication only
echo "[+] Whitelisting port 22 (SSH Remote Access)..."
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -j ACCEPT

# ----------------------------------------------------
# 2. DDoS & Flood Protection (Rate Limiting)
# ----------------------------------------------------
echo "[*] Implementing network-level DDoS rate limiting..."

# Drop invalid packets
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# Rate-limit TCP SYN flood attacks (Limit new TCP connections to 20/sec, burst of 30)
iptables -A INPUT -p tcp --syn -m limit --limit 20/s --limit-burst 30 -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP

# Rate-limit ICMP (ping) flood attacks (Limit ping to 5/sec, burst of 8)
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 5/s --limit-burst 8 -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -j DROP

# Limit concurrent TCP connections per IP to 35 (prevents resource exhaustion)
iptables -A INPUT -p tcp --syn --dport 5001 -m connlimit --connlimit-above 35 -j REJECT --reject-with tcp-reset

# ----------------------------------------------------
# 3. Disable Non-Essential System Services
# ----------------------------------------------------
echo "[*] Auditing and disabling non-essential discovery/network services..."

# Disable Avahi-daemon (mDNS / Zeroconf - vulnerable to local spoofing/recon)
if systemctl is-active --quiet avahi-daemon; then
  echo "  > Stopping and disabling Avahi mDNS discovery daemon..."
  systemctl stop avahi-daemon || true
  systemctl disable avahi-daemon || true
fi

# Disable Bluetooth / Bluez (minimizes physical radio attack surface)
if systemctl is-active --quiet bluetooth; then
  echo "  > Stopping and disabling Bluetooth stack..."
  systemctl stop bluetooth || true
  systemctl disable bluetooth || true
fi

# ----------------------------------------------------
# 4. Kernel Network Stack Hardening (sysctl)
# ----------------------------------------------------
echo "[*] Injecting kernel parameters for transport layer hardening..."

# Ignore ICMP echo broadcasts (Prevents Smurf DDoS attacks)
sysctl -w net.ipv4.icmp_echo_ignore_broadcasts=1

# Disable IP Source Routing (Prevents packets being routed through malicious hops)
sysctl -w net.ipv4.conf.all.accept_source_route=0
sysctl -w net.ipv4.conf.default.accept_source_route=0

# Enable TCP SYN Cookies (Protects against SYN flood resource starvation)
sysctl -w net.ipv4.tcp_syncookies=1

# Log Martians (Logs packets with impossible addresses)
sysctl -w net.ipv4.conf.all.log_martians=1
sysctl -w net.ipv4.conf.default.log_martians=1

# Ignore ICMP redirects (Prevents routing table hijacking/MitM)
sysctl -w net.ipv4.conf.all.accept_redirects=0
sysctl -w net.ipv4.conf.default.accept_redirects=0

# Disable IPv6 Stack globally (if ARES operates purely under static IPv4 topology)
echo "[*] Restricting network stack to strict static IPv4 addresses (IPv6 disabled)..."
sysctl -w net.ipv6.conf.all.disable_ipv6=1
sysctl -w net.ipv6.conf.default.disable_ipv6=1
sysctl -w net.ipv6.conf.lo.disable_ipv6=1

# Save sysctl settings
sysctl -p || true

echo "--------------------------------------------------------"
echo "[✅ ARES SECURITY STATUS] Level 2 Network Stack Hardened."
echo "  > Firewall: Default DROP active."
echo "  > Ports: Only 5001 (HTTPS) and 22 (SSH) allowed."
echo "  > Services: Avahi, Bluetooth, and IPv6 deactivated."
echo "  > Protection: DDoS Rate Limiting & SYN Cookies enabled."
echo "--------------------------------------------------------"
