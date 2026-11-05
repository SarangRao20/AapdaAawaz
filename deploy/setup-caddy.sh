#!/usr/bin/env bash
# One-time VM setup: HTTPS + dashboard + API on one origin. Run ON THE VM as the deploy user:
#   bash deploy/setup-caddy.sh aapdaawaaz.duckdns.org
# Needs: DNS for the domain already pointing at this VM, and inbound ports 80 and 443 open (Azure NSG too).
set -euo pipefail
SITE="${1:?usage: setup-caddy.sh <domain>}"
ROOT="$HOME/aapda/frontend-dist"

if ! command -v caddy >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
fi

mkdir -p "$ROOT"
[ -f "$ROOT/index.html" ] || echo '<p>Dashboard deploys on the next push to main.</p>' > "$ROOT/index.html"
chmod o+x "$HOME" "$HOME/aapda"          # let the caddy user read the built files

sed -e "s|__SITE__|$SITE|" -e "s|__ROOT__|$ROOT|" "$(dirname "$0")/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy

echo
echo "Now edit ~/aapda/backend/.env on the VM:"
echo "  COOKIE_SECURE=true"
echo "  CORS_ORIGINS=<existing values>,https://$SITE"
echo "then: sudo systemctl restart aapda-api"
