"""
ARES Zero-Config SSL/TLS Certificate Provisioner
"""

import os
import sys
import json
import subprocess
from ares_app.config import CERT_DIR
from ares_app.utils.network import get_current_local_ip


def setup_ssl_context():
    """Ensures mkcert local CA trust and provisions SSL/TLS certificates."""
    cert_path = os.path.join(CERT_DIR, 'ares.pem')
    key_path = os.path.join(CERT_DIR, 'ares.key')
    ips_json_path = os.path.join(CERT_DIR, 'ares.ips.json')

    print("[SSL] Synchronizing Certificate Authority trust context...")
    try:
        subprocess.run(['mkcert', '-install'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[SSL] Local CA synchronized with system trust store [OK]")
    except Exception as install_err:
        print(f"[SSL WARNING] mkcert -install failed: {install_err}")

    local_ip = get_current_local_ip()
    required_hosts = ["localhost", "127.0.0.1", "::1", "ares.control"]
    if local_ip and local_ip not in required_hosts:
        required_hosts.append(local_ip)
    required_hosts = sorted(list(set(required_hosts)))

    regenerate_cert = False
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        regenerate_cert = True
    else:
        if os.path.exists(ips_json_path):
            try:
                with open(ips_json_path, 'r') as f:
                    existing_ips = json.load(f)
                if sorted(existing_ips) != required_hosts:
                    regenerate_cert = True
            except Exception:
                regenerate_cert = True
        else:
            regenerate_cert = True

    if regenerate_cert:
        print(f"[SSL] Generating trusted certificates for: {', '.join(required_hosts)}")
        try:
            subprocess.run([
                'mkcert', '-cert-file', cert_path, '-key-file', key_path
            ] + required_hosts, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            with open(ips_json_path, 'w') as f:
                json.dump(required_hosts, f)

            print("[SSL] SSL/TLS trusted certificates successfully provisioned [SUCCESS]")
        except Exception as e:
            print(f"[SSL FATAL] mkcert failed: {e}")
            sys.exit("[Server Init FATAL] SSL context must be enabled.")

    return (cert_path, key_path)
