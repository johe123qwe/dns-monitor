import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# === Cloudflare 配置 ===
API_TOKEN = os.getenv('CF_API_TOKEN')
ZONE_ID = os.getenv('CF_ZONE_ID')
RECORD_NAME = os.getenv('CF_RECORD_NAME')

# === Signal 配置 ===
SIGNAL_ENABLED = os.getenv('SIGNAL_ENABLED', 'false').lower() == 'true'
SIGNAL_API_URL = os.getenv('SIGNAL_API_URL', 'http://localhost:8080')
SIGNAL_SERVER_NUM = os.getenv('SIGNAL_SERVER_NUM', '+49xxxxxxxxxx')
SIGNAL_USERNAME = os.getenv('SIGNAL_USERNAME', 'admin')
SIGNAL_PASSWORD = os.getenv('SIGNAL_PASSWORD', 'password')
SIGNAL_CHAT_ID = os.getenv('SIGNAL_CHAT_ID')

# === 健康检查配置 ===
A_SERVER_IP = os.getenv('A_SERVER_IP')
B_SERVER_IP = os.getenv('B_SERVER_IP')
HEALTH_CHECK_PATH = os.getenv('HEALTH_CHECK_PATH', '/health')
HEALTH_PORT = int(os.getenv('HEALTH_PORT', 80))
TTL = int(os.getenv('TTL', 120))
PROXIED = os.getenv('PROXIED', 'true').lower() == 'true'

STATE_FILE = './state.json'
LOG_DIR = './logs'

# === 初始化日志记录 ===
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_file = os.path.join(LOG_DIR, datetime.now().strftime('%Y-%m-%d') + '.log')

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

# === 状态文件加载与保存 ===
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# === 健康检查函数 ===
def is_alive(ip):
    try:
        url = f"http://{ip}:{HEALTH_PORT}{HEALTH_CHECK_PATH}"
        resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except:
        return False

def is_consistently_down(ip, retries=3, delay=10):
    for i in range(retries):
        if is_alive(ip):
            return False
        if i < retries - 1:
            time.sleep(delay)
    return True

# === Cloudflare DNS 操作 ===
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

def get_dns_records():
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records?type=A&name={RECORD_NAME}"
    resp = requests.get(url, headers=headers)
    result = resp.json()
    records = {}
    for rec in result['result']:
        records[rec['content']] = rec['id']
    return records

def add_dns_record(ip):
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records"
    data = {
        "type": "A",
        "name": RECORD_NAME,
        "content": ip,
        "ttl": TTL,
        "proxied": PROXIED
    }
    resp = requests.post(url, headers=headers, json=data)
    log(f"[+] 添加 A记录 {ip}: {resp.status_code} {resp.text}")

def delete_dns_record(record_id, ip):
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}"
    resp = requests.delete(url, headers=headers)
    log(f"[-] 删除 A记录 {ip}: {resp.status_code} {resp.text}")

def send_signal(message):
    ''' 发送数据 '''
    if not SIGNAL_ENABLED:
        return
    url = '{}/v2/send'.format(os.getenv('SIGNAL_API_URL'))
    headers = {
        'Content-Type': 'application/json'
    }
    auth = (SIGNAL_USERNAME, SIGNAL_PASSWORD)

    data = {
        'message': '{}'.format(message),
        'number': SIGNAL_SERVER_NUM,
        'recipients': [SIGNAL_CHAT_ID],
    }

    try:
        resp = requests.post(url, headers=headers, json=data, auth=auth, timeout=5)
        if not resp.ok:
            log(f"[!] 发送 Signal 失败: {resp.status_code} {resp.text}")
    except Exception as e:
        log(f"[!] Signal 异常: {e}")


# === 主逻辑 ===

records = get_dns_records()
current_ips = set(records.keys())

state = load_state()

def check_server(ip, label):
    prev_status = state.get(ip, 'unknown')

    if is_alive(ip):
        state[ip] = 'up'
        if prev_status != 'up':
            log(f"[INFO] {label} 恢复上线")
            if ip not in current_ips:
                add_dns_record(ip)
                send_signal(f"{label} 服务器恢复上线，已添加 DNS 记录")
            else:
                log(f"[OK] {label} 已存在于 DNS 记录中，无需重复添加")
        else:
            log(f"[OK] {label} 正常运行，无变化")
    else:
        if is_consistently_down(ip):
            state[ip] = 'down'
            if prev_status != 'down':
                log(f"[WARN] {label} 连续健康检查失败，认定宕机")
                if ip in current_ips:
                    delete_dns_record(records[ip], ip)
                    send_signal(f"TeamsAPI {label} 服务器宕机，已删除 DNS 记录")
            else:
                log(f"[INFO] {label} 持续宕机，无需重复处理")
        else:
            log(f"[INFO] {label} 单次失败但未达阈值，跳过")

if __name__ == "__main__":
    # # === 执行检查 ===
    check_server(A_SERVER_IP, A_SERVER_IP)
    check_server(B_SERVER_IP, B_SERVER_IP)

    # # === 保存状态 ===
    save_state(state)