import requests
import sys
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url_login = 'https://127.0.0.1:5001/api/login'
url_page = 'https://127.0.0.1:5001/login'

print("[Security Test] 1. Inspecting HTTP Response Headers...")
try:
    r_headers = requests.get(url_page, allow_redirects=False, verify=False)
    print("  > Status Code:", r_headers.status_code)
    
    headers = r_headers.headers
    csp = headers.get('Content-Security-Policy')
    x_frame = headers.get('X-Frame-Options')
    x_content = headers.get('X-Content-Type-Options')
    x_xss = headers.get('X-XSS-Protection')
    
    print("  > Content-Security-Policy:", csp)
    print("  > X-Frame-Options:", x_frame)
    print("  > X-Content-Type-Options:", x_content)
    print("  > X-XSS-Protection:", x_xss)
    
    # Check for correct settings
    assert csp is not None, "CSP header missing!"
    assert "https://cdn.tailwindcss.com" in csp, "CSP tailwind script source missing!"
    assert x_frame == 'DENY', "Clickjacking protection (X-Frame-Options) incorrect!"
    assert x_content == 'nosniff', "Mime sniff warning header missing!"
    assert x_xss == '1; mode=block', "X-XSS-Protection header incorrect!"
    print("[Security Test] ✅ PASS: Security headers injected correctly.")
    
except Exception as e:
    print("[Security Test ERROR] Headers check failed:", e)
    sys.exit(1)

print("\n[Security Test] 2. Testing Session Cookie Security Flags...")
try:
    cookies = r_headers.cookies
    # Find session cookie
    session_cookie = None
    for cookie in cookies:
        if cookie.name == 'session':
            session_cookie = cookie
            break
            
    if session_cookie:
        print("  > Session cookie found.")
        print("  > HttpOnly:", session_cookie.has_nonstandard_attr('HttpOnly') or session_cookie.secure)
        print("  > Secure:", session_cookie.secure)
        # Note: python requests may not parse all nonstandard attributes like SameSite easily, but we will print
    else:
        print("  > Session cookie not set on anonymous GET (normal behavior).")
except Exception as e:
    print("[Security Test ERROR] Session cookie check failed:", e)

print("\n[Security Test] 3. Testing Rate Limiter (Brute-Force Protection)...")
print("Executing 5 rapid failed login attempts...")
session = requests.Session()
for i in range(1, 6):
    r = session.post(url_login, data={'username': f'attacker_{i}', 'password': 'wrong_password'}, verify=False)
    print(f"  > Attempt {i}: Status={r.status_code} {r.text.strip()}")

print("Executing 6th login attempt (should trigger rate limit)...")
r_lim = session.post(url_login, data={'username': 'attacker_6', 'password': 'wrong_password'}, verify=False)
print(f"  > Attempt 6: Status={r_lim.status_code} {r_lim.text.strip()}")

if r_lim.status_code == 429:
    print("[Security Test] ✅ PASS: Rate limiter successfully blocked the 6th brute-force attempt.")
else:
    print("[Security Test] ❌ FAIL: Rate limiter did not block the 6th attempt! Status =", r_lim.status_code)
    sys.exit(1)
