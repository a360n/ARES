#!/bin/bash
# ARES DNS Spoofing Prevention Setup Script
# Maps static IP address records for ARES nodes inside /etc/hosts to bypass external DNS resolution.
# MUST BE RUN WITH ROOT PRIVILEGES (sudo)

set -e

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] ERROR: This script must be run with root privileges (sudo)."
  exit 1
fi

HOSTS_FILE="/etc/hosts"
BACKUP_FILE="/etc/hosts.bak"

echo "[*] Backing up active hosts mapping to ${BACKUP_FILE}..."
cp "${HOSTS_FILE}" "${BACKUP_FILE}"

# Static IP Address Allocations for ARES Tactical Network Grid
CONTROL_IP="192.168.10.100"
CONTROL_HOST="ares.control"

UAV_IP="192.168.10.101"
UAV_HOST="ares.uav"

UGV_IP="192.168.10.102"
UGV_HOST="ares.ugv"

echo "[*] Populating static node names for local lookup..."

# Helper function to append static record if not already present
add_host_entry() {
  local ip="$1"
  local hostname="$2"
  # Check if hostname or IP already exists in hosts file
  if grep -qE "${ip}|${hostname}" "${HOSTS_FILE}"; then
    echo "  > Record for ${hostname} (${ip}) already exists. Cleaning old entry..."
    # Remove existing conflicting lines matching hostname or IP
    sed -i.tmp -E "/${ip}|${hostname}/d" "${HOSTS_FILE}"
    rm -f "${HOSTS_FILE}.tmp"
  fi
  # Append entry cleanly
  echo -e "${ip}\t${hostname}" >> "${HOSTS_FILE}"
  echo "  > Successfully added: ${ip} -> ${hostname}"
}

add_host_entry "${CONTROL_IP}" "${CONTROL_HOST}"
add_host_entry "${UAV_IP}" "${UAV_HOST}"
add_host_entry "${UGV_IP}" "${UGV_HOST}"

echo "--------------------------------------------------------"
echo "[✅ ARES DNS AUDIT] /etc/hosts successfully populated."
echo "  > Local Resolution List:"
echo "    - control: ${CONTROL_IP} -> ${CONTROL_HOST}"
echo "    - uav:     ${UAV_IP} -> ${UAV_HOST}"
echo "    - ugv:     ${UGV_IP} -> ${UAV_HOST}"
echo "  > Ext DNS dependence removed. DNS Spoofing mitigated."
echo "--------------------------------------------------------"
