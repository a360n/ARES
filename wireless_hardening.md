# ARES Technical Advisory — Wireless Hardening & Frame Injection Defense

**Document ID**: ARES-SEC-ADV-002  
**Classification**: CONFIDENTIAL // TACTICAL INFRASTRUCTURE  
**Target Hardware**: Alfa AWUS036ACM / AWUS036ACH Wi-Fi Adapters (Orange Pi Zero 3 / Central PC)

---

## 🚨 Executive Threat Context

Standard WPA2-Personal (PSK) wireless infrastructure is highly vulnerable to physical-proximity cyber attacks:
1. **De-authentication Packet Injection**: Attackers can spoof the MAC address of an Access Point (AP) or a client (UAV/UGV) and transmit raw, unencrypted 802.11 management frames (Deauth/Disassoc) to drop the connection instantly. This terminates telemetry streams, interrupts visual feeds, and forces target drones to invoke automated panic returns.
2. **Offline Key Recovery**: WPA2-Personal handshakes can be captured off-the-air and brute-forced offline to extract passwords, allowing eavesdropping and MitM packet sniffing.

To achieve industrial production-standard safety, ARES must mandate **WPA3-Enterprise (Suite-B/192-bit)** coupled with mandatory **802.11w Protected Management Frames (PMF)**.

---

## 🛡️ Mandatory Security Posture

### 1. WPA3-Enterprise Suite-B (192-bit) Configuration
WPA3-Enterprise completely eliminates offline dictionary attacks by utilizing GCMP-256 (Galois Counter Mode Protocol) ciphers and ECDHE (Elliptic Curve Diffie-Hellman Ephemeral) for real-time key exchange, ensuring forward secrecy.

### 2. 802.11w Protected Management Frames (PMF)
Protected Management Frames apply cryptographic validation (via BIP - Broadcast Integrity Protocol) to unicast and multicast management frames (Deauthentication, Disassociation, and Beacon frames). Any spoofed unauthenticated management frame transmitted by an attacker is immediately discarded by the network interface card, rendering deauth attacks ineffective.

---

## 🛠️ Implementation Steps

### A. Orange Pi Node Setup (`wpa_supplicant.conf`)

Configure `/etc/wpa_supplicant/wpa_supplicant.conf` on the UAV and UGV nodes to enforce WPA3-Enterprise and mandatory PMF:

```ini
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="ARES_TACTICAL_SECURE"
    key_mgmt=WPA-EAP-SUITE-B-192
    ieee80211w=2  # Enforce Mandatory Protected Management Frames (0=disabled, 1=optional, 2=required)
    
    # EAP Configuration using TLS certificates
    eap=TLS
    identity="ares-node-01@ares.local"
    
    # Client certificates for node authentication
    ca_cert="/etc/ares/certs/ca.pem"
    client_cert="/etc/ares/certs/node_01.crt"
    private_key="/etc/ares/certs/node_01.key"
    private_key_passwd="secure_node_passphrase"
    
    # Restrict ciphers to 192-bit GCMP
    pairwise=GCMP-256
    group=GCMP-256
}
```

> [!IMPORTANT]
> `ieee80211w=2` is the critical setting that enforces PMF. If the Access Point does not support PMF, the client will refuse to connect, preventing any negotiated downgrade attacks.

---

### B. Access Point Setup (`hostapd.conf`)

If configuring the Central Control PC as a secure soft AP utilizing the Alfa Wi-Fi adapter, set the following parameters inside `/etc/hostapd/hostapd.conf`:

```ini
interface=wlan0
driver=nl80211
ssid=ARES_TACTICAL_SECURE
hw_mode=a
channel=36
ieee80211n=1
ieee80211ac=1

# Wireless Security Configuration
wpa=2
wpa_key_mgmt=WPA-EAP-SUITE-B-192
wpa_pairwise=GCMP-256
rsn_pairwise=GCMP-256

# RADIUS Server Configuration for EAP-TLS
auth_algs=1
ieee8021x=1
own_ip_addr=192.168.10.100
auth_server_addr=127.0.0.1
auth_server_port=1812
auth_server_shared_secret=radius_shared_secret_phrase

# Enforce Management Frame Protection (802.11w)
ieee80211w=2  # Enforce mandatory PMF
association_timeout=20
# SHA256 BIP (Broadcast Integrity Protocol) cipher
group_mgmt_cipher=BIP-GMAC-256
```

---

## 🔍 Validation & Verification Procedures

To verify that PMF is actively negotiated and protecting ARES streams:

1. **Verify Connection State on Node**:
   Run `wpa_cli status` on the UGV/UAV Orange Pi node:
   ```bash
   wpa_cli status
   ```
   Check the output flags. It must contain:
   ```txt
   key_mgmt=WPA-EAP-SUITE-B-192
   pairwise_cipher=GCMP-256
   group_cipher=GCMP-256
   pmf=1 (negotiated / required)
   ```

2. **Air-Monitor Validation via Wireshark**:
   - Put a separate wireless card into monitor mode: `airmon-ng start wlan1`
   - Capture management traffic: `tcpdump -i wlan1mon -y ieee802_11_radio -w capture.pcap`
   - Open in Wireshark and inspect Association Response frames.
   - Look under **Robust Security Network (RSN) Capabilities**:
     * `Management Frame Protection Required: True`
     * `Management Frame Protection Capable: True`

---

## 🔄 Secure Fallback: WPA2-AES with Rotating Mission Keys

If legacy mesh nodes or companion cards lack complete WPA3-Enterprise Suite-B capabilities, they MUST implement a hardened **WPA2-AES** profile with **rotating keys** combined with mandatory PMF:

### 1. Hardened WPA2-PSK Client Profile (`wpa_supplicant.conf`)
```ini
network={
    ssid="ARES_TACTICAL_FALLBACK"
    key_mgmt=WPA-PSK
    proto=RSN
    pairwise=CCMP
    group=CCMP
    ieee80211w=2  # Enforce mandatory PMF even on WPA2!
    psk="mission_key_generated_on_launch_12345"
}
```

### 2. Automated Key Rotation Script (Control Station soft AP)
To prevent key recovery via captured handshakes, the mission launch station rotates the PSK automatically immediately prior to every tactical takeoff/mission initiation:

```bash
#!/bin/bash
# ARES Tactical Wireless Key Rotator
# Generates a secure, 32-character random hex PSK and updates hostapd configurations.

set -e

CONFIG="/etc/hostapd/hostapd.conf"
NEW_KEY=$(openssl rand -hex 16)

echo "[*] Rotating wireless mission key..."
sed -i -E "s/^wpa_passphrase=.*/wpa_passphrase=${NEW_KEY}/" "${CONFIG}"

# Restart wireless interfaces to force new handshake exchanges
systemctl restart hostapd
echo "[✅ ROTATION SUCCESS] New Mission PSK generated and forced: ${NEW_KEY}"
```
Ensure this key is synchronized securely with target UGV/UAV companion computers over physical serial links or encrypted wired boundaries prior to field launches.
