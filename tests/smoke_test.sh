#!/usr/bin/env bash
# Start the built app image like the Supervisor would (without Home
# Assistant) and check the basics from inside the container.
set -euo pipefail
image="$1"
data=$(mktemp -d)
echo '{"log_level": "info"}' > "$data/options.json"

# ALLOW_ANY_UI_CLIENT: the page normally only answers Home Assistant's ingress
# proxy; here the checks run inside the container (127.0.0.1).
docker run -d --name app-smoke -e ALLOW_ANY_UI_CLIENT=1 -v "$data:/data" "$image" >/dev/null
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
# not logged in -> the app answers 503 with a hint instead of the server
assert code(f'http://127.0.0.1:8100/{secret}/mcp', 'POST') == 503
"

echo "3. Secret path is never written to the log"
secret=$(docker exec app-smoke cat /data/secret_path)
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

echo "4. Health check passes"
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' app-smoke)
  [ "$status" = "healthy" ] && break
  sleep 3
done
[ "$status" = "healthy" ] || { echo "health status: $status" >&2; exit 1; }

echo "Smoke test passed"
