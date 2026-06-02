import requests
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url_base = 'https://127.0.0.1:5001'
url_login = f'{url_base}/api/login'
url_launch = f'{url_base}/api/studio/launch'
url_clear = f'{url_base}/api/sessions/clear_all'
url_studio = f'{url_base}/'

print("[Test] 1. Requesting root page without session...")
r = requests.get(url_studio, allow_redirects=False, verify=False)
print(f"[Test] Status code: {r.status_code} (Should be 302 redirecting to /login)")
if r.status_code == 302 or "login" in r.text.lower():
    print("[Test] ✅ PASS: Unauthorized access cleanly blocked and redirected.")
else:
    print("[Test] ❌ FAIL: Unauthorized access allowed.")

# --- Test Operator Account ---
print("\n[Test] 2. Logging in as OPERATOR...")
session_op = requests.Session()
session_op.verify = False
r_login_op = session_op.post(url_login, data={'username': 'operator', 'password': 'operator123'})
print(f"[Test] Operator login response: {r_login_op.status_code} {r_login_op.json()}")

print("[Test] 3. Attempting WIPE ALL LOGS as OPERATOR...")
r_clear_op = session_op.delete(url_clear)
print(f"[Test] Operator wipe response: {r_clear_op.status_code} (Should be 403 Forbidden)")
if r_clear_op.status_code == 403:
    print("[Test] ✅ PASS: Operator blocked from administrative action.")
else:
    print("[Test] ❌ FAIL: Operator was allowed to wipe logs!")

# --- Test Admin Account ---
print("\n[Test] 4. Logging in as ADMIN...")
session_admin = requests.Session()
session_admin.verify = False
r_login_admin = session_admin.post(url_login, data={'username': 'admin', 'password': 'admin123'})
print(f"[Test] Admin login response: {r_login_admin.status_code} {r_login_admin.json()}")

print("[Test] 5. Attempting WIPE ALL LOGS as ADMIN...")
r_clear_admin = session_admin.delete(url_clear)
print(f"[Test] Admin wipe response: {r_clear_admin.status_code} (Should be 200 SUCCESS)")
if r_clear_admin.status_code == 200:
    print("[Test] ✅ PASS: Admin successfully wiped database logs.")
else:
    print("[Test] ❌ FAIL: Admin was blocked from wiping logs!")

# --- Check Forensic Log Content ---
print("\n[Test] 6. Inspecting static/security_audit.log...")
audit_log_path = '/Users/alial-khazali/Documents/ARES/static/security_audit.log'
if os.path.exists(audit_log_path):
    print("[Test] ✅ PASS: static/security_audit.log created.")
    with open(audit_log_path, 'r') as f:
        lines = f.readlines()
        print(f"[Test] Log content (last 5 lines):")
        for line in lines[-5:]:
            print("  >", line.strip())
else:
    print("[Test] ❌ FAIL: static/security_audit.log not found!")
