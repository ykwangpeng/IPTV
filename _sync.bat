cd C:\tools\IPTV
git add -A
git commit -m "fix: fix encoding issues in output files"
git push
python scripts/sync_to_gist.py
