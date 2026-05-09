import os, subprocess, datetime, sys, json
from urllib.parse import urlparse, parse_qs, urlencode

# Ensure Git is in PATH for subprocess calls
_git_paths = r'C:\Program Files\Git\cmd;C:\Program Files\Git\bin'
if all(p not in os.environ.get('PATH','') for p in ['Git\\cmd','Git\\bin','git.exe']):
    os.environ['PATH'] = _git_paths + ';' + os.environ.get('PATH','')

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ========== 0. URL 清理（GitHub Push Protection 合规） ==========
SENSITIVE_PARAMS = {
    'userid','sign','auth_token','token','key','secret','password','passwd',
    'tk','auth','verify','access_token','refresh_token','expires_in','nonce',
    'authkey','encrypt','client_secret','migutoken','msisdn','txsecret','txtime',
    'signkey','api_key','apikey','private_key','pwd','authcode','sid','spid',
    'clientid','client_id','deviceid','device_id','session','sessionid',
    'signstr','sign_type','resign','authkey2','auth_token_v2',
    'sign_token','secure_token','access_key','accesskey','access_secret',
    'authsign','checksum','hash','md5','sha',
}

def clean_url(url):
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        clean_qs = {k: v for k, v in qs.items() if k.lower() not in SENSITIVE_PARAMS}
        return parsed._replace(query=urlencode(clean_qs, doseq=True)).geturl()
    except:
        return url

def sanitize_file(src, dst):
    with open(src, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    new_lines = []
    for line in lines:
        if ',#genre#' in line:
            new_lines.append(line)
        elif ',' in line:
            name, url = line.split(',', 1)
            new_lines.append('%s,%s' % (name, clean_url(url)))
        else:
            new_lines.append(line)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')
    return len([l for l in new_lines if l.strip() and ',#genre#' not in l])

GIT_EXE = r'C:\Program Files\Git\cmd\git.exe'

def get_token():
    """从环境变量或 git config 获取 GitHub Token"""
    token = os.environ.get('GIST_TOKEN', '')
    if token and token != 'YOUR_GIST_TOKEN_HERE':
        return token
    token = os.environ.get('GH_TOKEN', '')
    if token:
        return token
    r = subprocess.run([GIT_EXE, 'config', '--global', '--list'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    for line in r.stdout.splitlines():
        if line.startswith('user.ghp_') or line.startswith('GIST_TOKEN=') or (line.startswith('GITHUB_TOKEN=') and 'ghp_' in line):
            return line.split('=', 1)[1].strip()
    return ''

# ========== 1. GitHub Push ==========
print("=== GitHub Push ===")
try:
    if os.path.exists('live_ok.txt'):
        chan_count = sanitize_file('live_ok.txt', 'live_ok_git.txt')
        print("Sanitized: %d channels -> live_ok_git.txt" % chan_count)
    else:
        print("live_ok.txt not found, skip")
        chan_count = 0

    subprocess.run([GIT_EXE,'add','live_ok_git.txt','live_ok.m3u','.iptv_cache.json','.iptv_stats.json'],
        capture_output=True)
    r_diff = subprocess.run([GIT_EXE,'diff','--staged','--stat'],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r_diff.stdout.strip():
        print("Changes: " + r_diff.stdout.strip())
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        git_email = os.environ.get('GIT_EMAIL', 'github-actions[bot]@users.noreply.github.com')
        git_name = os.environ.get('GIT_NAME', 'github-actions[bot]')
        subprocess.run([GIT_EXE,'config','--local','user.email', git_email], check=False)
        subprocess.run([GIT_EXE,'config','--local','user.name', git_name], check=False)
        subprocess.run([GIT_EXE,'commit','-m','chore: auto-update ' + ts], check=False)
        print("Committed.")
        r_push = subprocess.run([GIT_EXE,'push','origin','master'],
            capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r_push.returncode == 0:
            print("Pushed to master.")
        else:
            print("Push error: " + (r_push.stderr.strip() or r_push.stdout.strip()))
    else:
        print("No changes, skip")
except Exception as e:
    print("GitHub error: " + str(e))

# ========== 2. Gist Sync ==========
print("\n=== Gist Sync ===")
if not os.path.exists('live_ok.txt'):
    print("live_ok.txt not found, skip")
else:
    with open('live_ok.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    lines = [l for l in content.splitlines() if l.strip() and ',#genre#' not in l]
    cnt = len(lines)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    token = get_token()
    if not token:
        print("No GIST_TOKEN found, skip")
    else:
        gist_id = os.environ.get('GIST_ID', '')
        import urllib.request
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)
        gist_files = {'IPTV.txt': {'content': content}}
        payload = json.dumps({
            'description': 'IPTV | %d channels | %s' % (cnt, ts),
            'files': gist_files
        }).encode()
        req = urllib.request.Request(
            'https://api.github.com/gists/' + gist_id,
            data=payload,
            headers={'Authorization': 'token ' + token,
                     'Accept': 'application/vnd.github.v3+json',
                     'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            print("Gist OK: %d channels" % cnt)
        except Exception as e:
            print("Gist error: " + str(e))
