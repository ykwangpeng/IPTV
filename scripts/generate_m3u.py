import os
if os.path.exists('live_ok.txt'):
    with open('live_ok.txt','r',encoding='utf-8') as f:
        lines=[l.strip() for l in f if ',' in l]
    with open('live_ok.m3u','w',encoding='utf-8') as f:
        f.write('#EXTM3U\n\n')
        for line in lines:
            parts=line.split(',',1)
            if len(parts)==2: f.write(f'#EXTINF:-1 tvg-name="{parts[0]}",{parts[0]}\n{parts[1]}\n')
    print('M3U done')