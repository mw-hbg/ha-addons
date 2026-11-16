#!/usr/bin/env bash
# Start the built add-on image like the Supervisor would (without Home
# Assistant) and check the basics from inside the container.
set -euo pipefail
image="$1"
data=$(mktemp -d)
echo '{"log_level": "info"}' > "$data/options.json"

docker run -d --name addon-smoke -v "$data:/data" "$image" >/dev/null
trap 'docker logs addon-smoke || true; docker rm -f addon-smoke >/dev/null 2>&1 || true' EXIT

check() {
  docker exec addon-smoke python3 -c "$1"
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
# not logged in -> the add-on answers 503 with a hint instead of the server
assert code(f'http://127.0.0.1:8100/{secret}/mcp', 'POST') == 503
"

echo "3. Secret path is never written to the log"
secret=$(docker exec addon-smoke cat /data/secret_path)
if docker logs addon-smoke 2>&1 | grep -q "$secret"; then
  echo "secret path found in log" >&2
  exit 1
fi

echo "4. Health check passes"
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' addon-smoke)
  [ "$status" = "healthy" ] && break
  sleep 3
done
[ "$status" = "healthy" ] || { echo "health status: $status" >&2; exit 1; }

echo "Smoke test passed"
