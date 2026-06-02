import requests
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url_base = 'https://127.0.0.1:5001'
url_login = f'{url_base}/api/login'
url_roles = f'{url_base}/api/admin/roles'
url_users = f'{url_base}/api/admin/users'
url_create_role = f'{url_base}/api/admin/roles/create'
url_create_user = f'{url_base}/api/admin/users/create'
url_modify_rank = f'{url_base}/api/admin/users/modify_rank'
url_clear = f'{url_base}/api/sessions/clear_all'

# --- 1. Log in as ADMIN ---
print("[Test IAM] 1. Logging in as ADMIN...")
session_admin = requests.Session()
session_admin.verify = False
r_login_admin = session_admin.post(url_login, data={'username': 'admin', 'password': 'admin123'})
print(f"[Test IAM] Admin login response: {r_login_admin.status_code} {r_login_admin.json()}")

# --- 2. Retrieve Roles List ---
print("\n[Test IAM] 2. Retrieving ARES roles list...")
r_roles = session_admin.get(url_roles)
print(f"[Test IAM] Roles status: {r_roles.status_code}")
roles_list = r_roles.json()
print(f"[Test IAM] Roles found: {[r['name'] for r in roles_list]}")

# Find standard operator role ID
operator_role = next(r for r in roles_list if r['name'] == 'operator')
operator_role_id = operator_role['id']
auditor_role = next(r for r in roles_list if r['name'] == 'auditor')
auditor_role_id = auditor_role['id']

# --- 3. Create Custom Role ---
print("\n[Test IAM] 3. Creating custom role 'custom_officer'...")
custom_role_payload = {
    "name": "custom_officer",
    "view_live_telemetry": True,
    "run_simulations": False,
    "export_reports": True,
    "delete_logs": False,
    "power_toggle_robot": False,
    "toggle_navigation_mode": True,
    "manual_robot_control": True
}
r_create_role = session_admin.post(url_create_role, json=custom_role_payload)
print(f"[Test IAM] Create role response: {r_create_role.status_code} {r_create_role.json()}")

# Fetch roles again to get the new role ID
roles_list = session_admin.get(url_roles).json()
custom_role = next(r for r in roles_list if r['name'] == 'custom_officer')
custom_role_id = custom_role['id']
print(f"[Test IAM] Custom role created successfully with ID: {custom_role_id}")

# --- 4. Spawn a New User assigned to the custom role ---
print("\n[Test IAM] 4. Spawning new user 'officer_jack' assigned to 'custom_officer'...")
user_payload = {
    "username": "officer_jack",
    "password": "jackpassword",
    "role_id": custom_role_id
}
r_create_user = session_admin.post(url_create_user, json=user_payload)
print(f"[Test IAM] Create user response: {r_create_user.status_code} {r_create_user.json()}")

# --- 5. Verify Non-Admin Access Blocking (SSH / IAM endpoints) ---
print("\n[Test IAM] 5. Creating a session as 'officer_jack' and testing IAM access block...")
session_jack = requests.Session()
session_jack.verify = False
r_login_jack = session_jack.post(url_login, data={'username': 'officer_jack', 'password': 'jackpassword'})
print(f"[Test IAM] Jack login response: {r_login_jack.status_code} {r_login_jack.json()}")

r_jack_roles = session_jack.get(url_roles)
print(f"[Test IAM] Jack retrieve roles response: {r_jack_roles.status_code} (Should be 403)")
if r_jack_roles.status_code == 403:
    print("[Test IAM] ✅ PASS: Non-admin strictly blocked from retrieving roles.")
else:
    print("[Test IAM] ❌ FAIL: Non-admin retrieved roles!")

r_jack_clear = session_jack.delete(url_clear)
print(f"[Test IAM] Jack wipe logs response: {r_jack_clear.status_code} (Should be 403)")
if r_jack_clear.status_code == 403:
    print("[Test IAM] ✅ PASS: Non-admin strictly blocked from deleting logs.")
else:
    print("[Test IAM] ❌ FAIL: Non-admin allowed to wipe logs!")

# --- 6. Root Administrator Invariant Guard Violations ---
print("\n[Test IAM] 6. Testing Invariant Guard Violations...")
# Attempting to assign new user to root admin role (id=1)
print("[Test IAM] Attempting to spawn user with root admin role (id=1)...")
root_user_payload = {
    "username": "fake_admin",
    "password": "fakepassword",
    "role_id": 1
}
r_root_user = session_admin.post(url_create_user, json=root_user_payload)
print(f"[Test IAM] Response: {r_root_user.status_code} {r_root_user.json()} (Should be 403 Forbidden)")
if r_root_user.status_code == 403:
    print("[Test IAM] ✅ PASS: Invariant Guard blocked assigning new user to root role.")
else:
    print("[Test IAM] ❌ FAIL: Assigned fake user to root admin!")

# Attempting to elevate existing user to root admin role (id=1)
print("[Test IAM] Attempting to elevate officer_jack to root admin role (id=1)...")
r_elevate = session_admin.put(url_modify_rank, json={"username": "officer_jack", "role_id": 1})
print(f"[Test IAM] Response: {r_elevate.status_code} {r_elevate.json()} (Should be 403 Forbidden)")
if r_elevate.status_code == 403:
    print("[Test IAM] ✅ PASS: Invariant Guard blocked elevating user to root role.")
else:
    print("[Test IAM] ❌ FAIL: Elevated user to root admin!")

# Attempting to downgrade admin from role_id=1
print("[Test IAM] Attempting to downgrade root admin...")
r_downgrade = session_admin.put(url_modify_rank, json={"username": "admin", "role_id": operator_role_id})
print(f"[Test IAM] Response: {r_downgrade.status_code} {r_downgrade.json()} (Should be 400 Bad Request)")
if r_downgrade.status_code == 400:
    print("[Test IAM] ✅ PASS: Invariant Guard blocked downgrading root administrator.")
else:
    print("[Test IAM] ❌ FAIL: Allowed downgrading root admin!")

# --- 7. Upgrading/Downgrading (Rank modification) ---
print("\n[Test IAM] 7. Testing Rank modification...")
print("[Test IAM] Downgrading officer_jack to auditor...")
r_modify = session_admin.put(url_modify_rank, json={"username": "officer_jack", "role_id": auditor_role_id})
print(f"[Test IAM] Response: {r_modify.status_code} {r_modify.json()}")
if r_modify.status_code == 200:
    print("[Test IAM] ✅ PASS: User role modified successfully.")
else:
    print("[Test IAM] ❌ FAIL: Rank modification blocked!")

# Verify user list
print("\n[Test IAM] 8. Checking updated user list...")
r_users = session_admin.get(url_users)
print(f"[Test IAM] Users status: {r_users.status_code}")
users_list = r_users.json()
for u in users_list:
    print(f"  > User: {u['username']} | Role: {u['role_name']}")

print("\n[Test IAM] System validation completed successfully.")
