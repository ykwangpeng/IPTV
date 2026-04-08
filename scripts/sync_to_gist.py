import os, requests
if os.path.exists('live_ok.txt'):
    with open('live_ok.txt','r',encoding='utf-8') as f: c = f.read()
    cnt = len([l for l in c.splitlines() if l.strip()])
    token = os.environ.get('GIST_TOKEN') or os.environ.get('GH_TOKEN', '')
    r = requests.patch('https://api.github.com/gists/dc272a4f2e95ffbd41e7e31d27ef3d76',
        headers={'Authorization': 'token ' + token, 'Content-Type': 'application/json'},
        json={'description': 'IPTV | {} sources'.format(cnt), 'files': {'IPTV.txt': {'content': c}}})
    print('Gist: {} sources'.format(cnt) if r.status_code == 200 else 'Failed: ' + str(r.status_code))
