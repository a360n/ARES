# ARES Node Infrastructure — Static IP Addressing & local DNS Overrides

**Document ID**: ARES-SEC-ADV-003  
**Classification**: CONFIDENTIAL // INFRASTRUCTURE HARDENING  
**Target OS**: Ubuntu Server (Netplan) / Raspberry Pi OS (dhcpcd) / companion computers

---

## 🚨 Threat Analysis: DNS Spoofing & DHCP Hijacking

In standard tactical deployments, using dynamic address assignments (DHCP) and external DNS resolution poses critical vulnerabilities:
1. **DHCP Hijacking**: Attackers can flood the local air interfaces with DHCP DISCOVER packets (DHCP Starvation) or run a rogue DHCP server. Once an ARES node (UAV/UGV) requests an address, the rogue server responds with malicious IP addresses and sets its own gateway as the default gateway, enabling full Man-in-the-Middle (MitM) traffic capturing.
2. **DNS Cache Poisoning / Spoofing**: Adversaries can intercept or forge answers to standard UDP port 53 DNS requests, redirecting `ares.control` or `ares.uav` host lookups to a malicious server.

**Mitigation**: Mandate static IP configurations on all network interfaces and hardcode internal node lookups inside `/etc/hosts`. This removes DHCP dynamic handshakes and prevents external DNS queries completely.

---

## 🛠️ Static IP Addressing Templates

Deploy one of the following configurations depending on the OS running on your companion computers:

### A. Netplan Configuration Template (Modern Ubuntu/Debian)
Write the following content into `/etc/netplan/01-netcfg.yaml` (replace interface `wlan0` with your active Alfa Wi-Fi driver interface):

```yaml
network:
  version: 2
  renderer: networkd
  wifis:
    wlan0:
      dhcp4: no
      dhcp6: no
      addresses:
        # UAV Node: Use 192.168.10.101/24
        # UGV Node: Use 192.168.10.102/24
        # GCS Central Node: Use 192.168.10.100/24
        - 192.168.10.101/24
      access-points:
        "ARES_TACTICAL_SECURE":
          auth:
            key-mgmt: WPA-EAP-SUITE-B-192
      # Explicitly omit gateway4 and nameservers to completely block out-of-subnet routing and external DNS
```

Apply the network configuration using:
```bash
sudo chmod 600 /etc/netplan/01-netcfg.yaml
sudo netplan apply
```

---

### B. DHCPCD Configuration Template (Raspberry Pi OS / Legacy)
Append the following static IP profile to `/etc/dhcpcd.conf` (assuming `wlan0` interface):

```ini
interface wlan0
static ip_address=192.168.10.101/24
# Omit static routers and static domain_name_servers to restrict traffic to the static subnet
```

Restart the network service:
```bash
sudo systemctl restart dhcpcd
```

---

## 🛡️ local Node Resolution overrides (`/etc/hosts`)

To completely neutralize DNS Spoofing, write the following entries at the bottom of `/etc/hosts` on **both the UAV, UGV companion computers, and Central GCS PC**:

```txt
# ARES Tactical Subnet local Resolvers (Neutralizes DNS Spoofing)
192.168.10.100  ares.control
192.168.10.101  ares.uav
192.168.10.102  ares.ugv
```

### Verification
Confirm that resolving names bypasses the network layer entirely by pinging `ares.control`:
```bash
ping -c 3 ares.control
```
Ensure it resolves instantly to `192.168.10.100` even when the node is completely disconnected from external internet interfaces.
