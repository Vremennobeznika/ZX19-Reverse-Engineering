"""Use a public catalog's ordinary guest form, with its normal CSRF session."""
import http.cookiejar
import json
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = 'https://jlide.myddns.me'
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
with opener.open(base + '/ota', timeout=20) as r:
    html = r.read().decode('utf-8')
headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
           'Referer': base + '/ota', 'Origin': base, 'X-Requested-With': 'XMLHttpRequest'}
for cookie in jar:
    if cookie.name == 'XSRF-TOKEN':
        headers['X-XSRF-TOKEN'] = urllib.parse.unquote(cookie.value)
m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
if m:
    headers['X-CSRF-TOKEN'] = m.group(1)
# Exactly the production guest form's fields, with the target hardware string.
hardware = sys.argv[1] if len(sys.argv) > 1 else 'R19Z_V1.0'
if not re.fullmatch(r'[A-Za-z0-9_.-]+', hardware):
    raise ValueError('Invalid hardware identifier')
body = {'hardwareVersion': hardware, 'romVersion': 'M78_0', 'os': 2,
        'uid': 0, 'country': 'IT', 'mac': '00', 'appId': 1, 'dev': 2}
report = {'url': base + '/qcwx/app-update/last-ota', 'request': body,
          'note': 'Public guest form defaults; romVersion is a catalog placeholder, not the watch version.'}
req = urllib.request.Request(report['url'], data=json.dumps(body).encode(), headers=headers, method='POST')
try:
    with opener.open(req, timeout=25) as r:
        report.update(status=r.status, response=r.read(1000000).decode('utf-8', errors='replace'))
except urllib.error.HTTPError as e:
    report.update(status=e.code, response=e.read(2000).decode('utf-8', errors='replace'))
except Exception as e:
    report['error'] = repr(e)
(root / ('research/public-catalog-response-' + hardware + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
