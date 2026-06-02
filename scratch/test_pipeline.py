import requests
import time
import threading
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URLs
url_login = 'https://127.0.0.1:5001/api/login'
url_launch = 'https://127.0.0.1:5001/api/studio/launch'
url_stop = 'https://127.0.0.1:5001/api/simulation/stop'
url_stream = 'https://127.0.0.1:5001/api/telemetry/stream'

video_path = '/Users/alial-khazali/Documents/ARES/uploads/First_Simulator_Video.mov'

def stream_reader(session_name, sid):
    print(f"[{session_name}] Connecting to telemetry stream for sid: {sid}...")
    try:
        # Create a fresh requests session for streaming
        s = requests.Session()
        s.verify = False
        # Request stream with session ID parameter
        r_feed = s.get(f"{url_stream}?sid={sid}", stream=True, timeout=12, verify=False)
        chunk_count = 0
        for line in r_feed.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data:"):
                    chunk_count += 1
                    if chunk_count % 10 == 0:
                        print(f"[{session_name}] Received telemetry data payload chunk {chunk_count}: {decoded[:120]}...")
                    if chunk_count > 30:
                        print(f"[{session_name}] Completed streaming successfully.")
                        break
    except Exception as e:
        print(f"[{session_name} ERROR] stream listener failed:", e)

try:
    print("[Multi-Session Test] Starting concurrent session testing...")
    
    # 1. Start Session 1 (OPERATOR)
    s1 = requests.Session()
    s1.verify = False
    r_login1 = s1.post(url_login, data={'username': 'operator', 'password': 'operator123'})
    print("[Session 1] Operator login response:", r_login1.status_code, r_login1.json())
    
    # 2. Start Session 2 (ADMIN)
    s2 = requests.Session()
    s2.verify = False
    r_login2 = s2.post(url_login, data={'username': 'admin', 'password': 'admin123'})
    print("[Session 2] Admin login response:", r_login2.status_code, r_login2.json())

    # 3. Launch Simulation 1 under Session 1
    print("[Session 1] Launching Simulation 1...")
    with open(video_path, 'rb') as f:
        files = {'video': f}
        data = {'timeline': '[]'}
        r1 = s1.post(url_launch, files=files, data=data)
        print("[Session 1] Launch response:", r1.status_code, r1.json())
        time.sleep(0.5)
        session1_id = s1.get('https://127.0.0.1:5001/dashboard', verify=False).text.split('currentSessionId = "')[1].split('"')[0]
        print("[Session 1] Extracted Session ID:", session1_id)

    # 4. Launch Simulation 2 under Session 2 (sequential upload/launch should be instant and non-blocking!)
    print("[Session 2] Launching Simulation 2...")
    with open(video_path, 'rb') as f:
        files = {'video': f}
        data = {'timeline': '[]'}
        r2 = s2.post(url_launch, files=files, data=data)
        print("[Session 2] Launch response:", r2.status_code, r2.json())
        time.sleep(0.5)
        session2_id = s2.get('https://127.0.0.1:5001/dashboard', verify=False).text.split('currentSessionId = "')[1].split('"')[0]
        print("[Session 2] Extracted Session ID:", session2_id)

    # 5. Start parallel concurrent telemetry stream readers for both sessions
    t1 = threading.Thread(target=stream_reader, args=("Operator Reader", session1_id), daemon=True)
    t2 = threading.Thread(target=stream_reader, args=("Admin Reader", session2_id), daemon=True)
    
    t1.start()
    t2.start()

    print("[Multi-Session Test] Streaming active. Waiting for parallel payloads...")
    time.sleep(8)

    # 6. Stop simulation to clean up
    print("[Multi-Session Test] Stopping active simulations...")
    s1.post(url_stop)
    s2.post(url_stop)
    
    print("[Multi-Session Test] Session cleanups sent. Completed successfully.")

except Exception as e:
    print("[Multi-Session Test ERROR] Run failed:", e)
