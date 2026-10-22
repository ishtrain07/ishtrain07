#!/usr/bin/env bash
# One-command deploy of Heritage Plate on a fresh Ubuntu VM (e.g. a Nebius Compute CPU VM with a public IP).
#
#   curl -fsSL https://raw.githubusercontent.com/ishtrain07/ishtrain07/claude/stoic-wozniak-8ie5mb/heritage-plate/scripts/deploy_vm.sh | sudo bash
#
# Installs Docker, clones the app, asks for your keys (typed, never echoed), builds the
# image and serves it over HTTPS at https://<ip-with-dashes>.sslip.io via Caddy.
# Run it again any time to pull the latest code and redeploy; the URL stays the same.
set -euo pipefail

BRANCH="${BRANCH:-claude/stoic-wozniak-8ie5mb}"
REPO="${REPO:-https://github.com/ishtrain07/ishtrain07.git}"
DIR=/opt/heritage-plate
ENV_FILE="$DIR/hp.env"

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

if ! command -v docker >/dev/null; then
  echo "==> Installing Docker"
  apt-get update -qq && apt-get install -y -qq docker.io git curl >/dev/null
  systemctl enable --now docker
fi
command -v git >/dev/null || apt-get install -y -qq git >/dev/null

echo "==> Getting the code ($BRANCH)"
if [ -d "$DIR/src/.git" ]; then
  git -C "$DIR/src" fetch -q --depth 1 origin "$BRANCH" && git -C "$DIR/src" reset -q --hard FETCH_HEAD
else
  mkdir -p "$DIR" && git clone -q --depth 1 -b "$BRANCH" "$REPO" "$DIR/src"
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "==> Keys (input is hidden; stored only in $ENV_FILE on this VM)"
  key="${NEBIUS_API_KEY:-}"
  [ -n "$key" ] || read -rsp "Nebius Token Factory API key: " key </dev/tty; echo
  ls_key="${LANGSMITH_API_KEY:-}"
  [ -n "$ls_key" ] || read -rsp "LangSmith API key (Enter to skip tracing): " ls_key </dev/tty; echo
  umask 077
  {
    echo "NEBIUS_API_KEY=$key"
    if [ -n "$ls_key" ]; then
      echo "LANGSMITH_TRACING=true"
      echo "LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com"
      echo "LANGSMITH_PROJECT=heritage-plate"
      echo "LANGSMITH_API_KEY=$ls_key"
    fi
  } > "$ENV_FILE"
fi

echo "==> Building the app image"
docker build -q -t heritage-plate:latest "$DIR/src/heritage-plate" >/dev/null

IP="${PUBLIC_IP:-$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me)}"
HOST="${HOST:-$(echo "$IP" | tr . -).sslip.io}"

echo "==> Starting app + HTTPS at $HOST"
docker network inspect web >/dev/null 2>&1 || docker network create web >/dev/null
docker rm -f hp caddy >/dev/null 2>&1 || true
docker run -d --name hp --restart unless-stopped --network web --env-file "$ENV_FILE" heritage-plate:latest >/dev/null
docker run -d --name caddy --restart unless-stopped --network web -p 80:80 -p 443:443 \
  -v caddy_data:/data caddy:2 caddy reverse-proxy --from "$HOST" --to hp:8000 >/dev/null

echo -n "==> Waiting for HTTPS certificate"
for _ in $(seq 1 60); do
  if curl -fsS "https://$HOST/api/health" >/dev/null 2>&1; then
    echo; echo
    curl -fsS "https://$HOST/api/health" | grep -o '"mode":"[a-z]*"' || true
    echo "Live at: https://$HOST"
    exit 0
  fi
  echo -n "."; sleep 3
done
echo
echo "Not reachable yet. Check that ports 80 and 443 are open to the internet, then: docker logs caddy; docker logs hp"
exit 1
