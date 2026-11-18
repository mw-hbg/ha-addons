#!/usr/bin/env bash
# Start the built app image like the Supervisor would (without Home
# Assistant) and check the basics from inside the container.
set -euo pipefail
image="$1"
data=$(mktemp -d)
echo '{"log_level": "info"}' > "$data/options.json"

# ALLOW_ANY_UI_CLIENT: the page normally only answers Home Assistant's ingress
# proxy; here the checks run inside the container (127.0.0.1).
# A fake Home Assistant config folder with a file readable for everyone.
ha=$(mktemp -d)
echo "api_password: top-secret" > "$ha/secrets.yaml"
chmod 755 "$ha"; chmod 644 "$ha/secrets.yaml"
echo "homeassistant: {}" > "$ha/configuration.yaml"; chmod 644 "$ha/configuration.yaml"

# AppArmor: run the container with the app's own profile, like Home Assistant
# does. Required on CI (the GitHub runners have AppArmor), optional elsewhere.
here="$(cd "$(dirname "$0")/.." && pwd)"
security=()
if [ -d /sys/kernel/security/apparmor ] && command -v apparmor_parser >/dev/null; then
  sudo apparmor_parser -r -W "$here/apparmor.txt"
  security=(--security-opt apparmor=garmin_mcp)
  apparmor=1
elif [ -n "${CI:-}" ]; then
  echo "AppArmor is not available on this CI runner" >&2; exit 1
else
  echo "(AppArmor not available here – testing without the profile)"
  apparmor=0
fi
docker run -d --name app-smoke "${security[@]}" -e ALLOW_ANY_UI_CLIENT=1 -v "$data:/data" -v "$ha:/homeassistant" "$image" >/dev/null
trap 'docker logs app-smoke || true; docker rm -f app-smoke >/dev/null 2>&1 || true' EXIT

check() {
  docker exec app-smoke python3 -c "$1"
}

# Wait for the web UI
for _ in $(seq 1 30); do
  if check "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/status.json', timeout=2)" 2>/dev/null; then
    break
  fi
  sleep 2
done

echo "1. Web UI answers"
check "
import urllib.request
html = urllib.request.urlopen('http://127.0.0.1:8099/', timeout=5).read().decode()
assert 'Garmin Connect MCP' in html, 'page title missing'
assert 'type=\"password\"' in html, 'login form missing'
tools = urllib.request.urlopen('http://127.0.0.1:8099/tools', timeout=5).read().decode()
assert tools.count('class=\"tool\"') >= 100, 'tool list too short'
"

echo "1b. Page in German and English"
check "
import urllib.request
def page(lang, path='/'):
    req = urllib.request.Request('http://127.0.0.1:8099' + path, headers={'Accept-Language': lang})
    return urllib.request.urlopen(req, timeout=5).read().decode()
de, en = page('de-DE,de;q=0.9'), page('en-US')
assert 'lang=\"de\"' in de and 'Anmelden' in de, 'German page missing'
assert 'lang=\"en\"' in en and 'Log in' in en, 'English page missing'
assert 'Aktivitäten' in page('de', '/tools'), 'German tool list missing'
"

echo "2. Endpoint is protected by the secret path"
check "
import urllib.request, urllib.error
def code(url, method='GET'):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, method=method, data=b'{}' if method=='POST' else None), timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code
assert code('http://127.0.0.1:8100/') == 404
assert code('http://127.0.0.1:8100/mcp', 'POST') == 404
assert code('http://127.0.0.1:8100/wrong-secret/mcp', 'POST') == 404
secret = open('/data/secret_path').read().strip()
# not logged in -> a stand-in answers real MCP messages that tell the AI why
import json
def mcp(method, mid=1):
    req = urllib.request.Request(f'http://127.0.0.1:8100/{secret}/mcp', method='POST',
        data=json.dumps({'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': {}}).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())
init = mcp('initialize')
assert init['id'] == 1 and 'not logged in' in init['result']['instructions'], init
call = mcp('tools/call', 7)
assert call['id'] == 7 and call['result']['isError'] and 'log in' in call['result']['content'][0]['text'], call
# the stand-in is only reachable through nginx (it adds the key)
assert code('http://127.0.0.1:8099/mcp-unavailable/1', 'POST') == 403
"

echo "3. Secret path is never written to the log"
secret=$(docker exec app-smoke python3 -c "print(open('/data/secret_path').read().strip())")
if docker logs app-smoke 2>&1 | grep -q "$secret"; then
  echo "secret path found in log" >&2
  exit 1
fi

echo "3b. MCP server user cannot touch secrets or the app"
docker exec app-smoke python3 -c "
import sys; sys.path.insert(0, '/app')
import launcher as L
ident = L.mcp_identity()
assert ident and ident[0] != 0, 'unprivileged user missing'
L.prepare_mcp_dirs(ident)
"
docker exec -u garmin app-smoke python3 -c "
import os
open('/data/downloads/ok.txt', 'w').write('x'); os.remove('/data/downloads/ok.txt')
open('/data/garmin_tokens/ok.txt', 'w').write('x'); os.remove('/data/garmin_tokens/ok.txt')
try:
    os.listdir('/data')
    raise SystemExit('garmin user could list /data')
except PermissionError:
    pass
for path in ('/data/secret_path', '/app/launcher.py', '/data/new_file', '/etc/passwd'):
    try:
        open(path, 'a').close()
    except PermissionError:
        continue
    raise SystemExit(f'garmin user could write {path}')
try:
    open('/data/secret_path').read()
    raise SystemExit('garmin user could read the secret path')
except PermissionError:
    pass
import garmin_mcp  # the server itself still loads
"

echo "3b2. A second Garmin account: own user, no access to the first account's tokens"
second=$(docker exec app-smoke python3 -c "
import sys; sys.path.insert(0, '/app')
import launcher as L
svc = L.Services()
acc = svc.add_account()
ident = L.mcp_identity(acc.user)
assert ident and ident != L.mcp_identity(), 'second account has no user of its own'
L.prepare_mcp_dirs(ident, acc)
print(acc.user, acc.token_dir)
")
read -r user2 tokens2 <<< "$second"
echo "   $user2 -> $tokens2"
docker exec -u "$user2" app-smoke python3 -c "
import os, sys
open(sys.argv[1] + '/ok.txt', 'w').write('x'); os.remove(sys.argv[1] + '/ok.txt')
for path in ('/data/garmin_tokens', '/data/secret_path', '/data/accounts'):
    try:
        os.listdir(path) if os.path.isdir(path) else open(path).read()
    except PermissionError:
        continue
    raise SystemExit(f'second account could read {path}')
" "$tokens2"
docker exec -u garmin app-smoke python3 -c "
import os, sys
try:
    os.listdir(sys.argv[1])
    raise SystemExit('first account could read the tokens of the second')
except PermissionError:
    pass
" "$tokens2"

echo "3c. Landlock: the MCP server reaches only its own folders"
docker exec -u garmin -e GARMINTOKENS=/data/garmin_tokens -e HOME=/data/mcp_home -e GARMIN_FIT_DOWNLOAD_DIR=/data/downloads -w /data/downloads app-smoke python3 -c "
import sys; sys.path.insert(0, '/app')
import run_mcp
assert run_mcp.lock_down(), 'Landlock not active'
for path in ('/homeassistant/secrets.yaml', '/data/options.json'):
    try:
        open(path).read()
    except PermissionError:
        continue
    raise SystemExit(f'could read {path} despite Landlock')
try:
    open('/homeassistant/new.yaml', 'w')
    raise SystemExit('could write to the Home Assistant folder')
except PermissionError:
    pass
open('/data/downloads/x.fit', 'wb').write(b'x')
open('/data/garmin_tokens/probe', 'w').write('x')
open('/tmp/probe', 'w').write('x')
import garmin_mcp.activity_analysis, garmin_mcp.courses  # code still loads
from curl_cffi import requests  # HTTPS to Garmin still works (DNS, certificates)
try:
    r = requests.get('https://connect.garmin.com/', impersonate='chrome', timeout=20)
    print('   HTTPS to Garmin:', r.status_code)
except Exception as exc:
    text = str(exc).lower()
    if 'certificate' in text or 'permission' in text or 'denied' in text:
        raise
    print('   (network check skipped:', type(exc).__name__, ')')
"

if [ "$apparmor" = 1 ]; then
echo "3d. AppArmor: even root in the container only reaches the helper integration"
docker exec app-smoke python3 -c "
import os, time
assert 'garmin_mcp' in open('/proc/1/attr/current').read(), 'not confined by the profile'
for _ in range(30):  # the app copies the helper integration after its start
    if os.path.exists('/homeassistant/custom_components/garmin_mcp_webhook/manifest.json'):
        break
    time.sleep(1)
else:
    raise SystemExit('helper integration was not installed')
for action, path in (('r', '/homeassistant/secrets.yaml'), ('a', '/homeassistant/configuration.yaml'),
                     ('w', '/homeassistant/new_file.yaml'), ('w', '/homeassistant/www/x')):
    try:
        open(path, action).close()
    except (PermissionError, FileNotFoundError) as exc:
        if isinstance(exc, FileNotFoundError) and action == 'w' and 'www' in path:
            continue  # folder does not exist – would need mkdir, which is blocked too
        continue
    raise SystemExit(f'root could {action} {path} despite AppArmor')
try:
    os.mkdir('/homeassistant/www')
    raise SystemExit('root could create folders in the Home Assistant folder')
except PermissionError:
    pass
import subprocess
try:
    subprocess.run(['/bin/sh', '-c', 'true'], check=True)
    raise SystemExit('a shell could be started despite AppArmor')
except PermissionError:
    pass
"
test -f "$ha/custom_components/garmin_mcp_webhook/manifest.json"
grep -q "top-secret" "$ha/secrets.yaml"
fi

echo "4. Health check passes"
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' app-smoke)
  [ "$status" = "healthy" ] && break
  sleep 3
done
[ "$status" = "healthy" ] || { echo "health status: $status" >&2; exit 1; }

echo "Smoke test passed"
