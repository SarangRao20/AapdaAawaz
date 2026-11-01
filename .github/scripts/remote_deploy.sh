#!/usr/bin/env bash
# Remote deployment for the Aapda Awaaz API (runs on the VM, not in CI).
#
# Called over SSH by .github/workflows/ci-cd.yml:
#   ssh ... "bash -s -- /home/sarang/aapda/.deploy/incoming/backend.tar.gz <sha>" \
#       < .github/scripts/remote_deploy.sh
#
# Steps: back up the current code -> sync the new code -> install changed
# dependencies -> restart systemd -> wait for /api/health. Any failure restores
# the previous code and restarts, so a bad commit never leaves the API down.
set -euo pipefail

ARTIFACT="${1:?usage: remote_deploy.sh <code.tar.gz> <commit-sha>}"
SHA="${2:?usage: remote_deploy.sh <code.tar.gz> <commit-sha>}"

APP_ROOT="$HOME/aapda"
APP_DIR="$APP_ROOT/backend"
DEPLOY_DIR="$APP_ROOT/.deploy"
WORK_DIR="$DEPLOY_DIR/work"
BACKUP_DIR="$DEPLOY_DIR/backups"
VENV_PIP="$APP_DIR/venv/bin/pip"
SERVICE="aapda-api"
HEALTH_URL="http://127.0.0.1:8000/api/health"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
KEEP_BACKUPS=5

RSYNC_EXCLUDES=(
  --exclude=venv/
  --exclude=var/
  --exclude=.env
  --exclude=__pycache__/
  --exclude=.pytest_cache/
)

log() { printf '[deploy] %s\n' "$*"; }
die() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

[ -f "$ARTIFACT" ] || die "artifact not found: $ARTIFACT"
mkdir -p "$DEPLOY_DIR" "$WORK_DIR" "$BACKUP_DIR"

PREV_SHA="$(cat "$DEPLOY_DIR/DEPLOYED_SHA" 2>/dev/null || echo unknown)"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_DIR/backend-$STAMP-${PREV_SHA:0:7}.tar.gz"
OLD_REQ_HASH="$(sha256sum "$APP_DIR/requirements.txt" 2>/dev/null | cut -d' ' -f1 || true)"

log "commit      : $SHA"
log "previous    : $PREV_SHA"
log "artifact    : $ARTIFACT"

# 1. Back up the code that is currently live (secrets, venv and data stay put).
log "backing up current code -> $BACKUP"
tar -czf "$BACKUP" -C "$APP_ROOT" \
  --exclude='backend/venv' \
  --exclude='backend/var' \
  --exclude='backend/.env' \
  --exclude='backend/__pycache__' \
  --exclude='backend/.pytest_cache' \
  --exclude='*/__pycache__' \
  backend

# 1b. Snapshot the SQLite database with sqlite3's backup API (safe while the
#     service is running). A rollback restores code, not data, so this is the
#     copy to fall back to if a migration misbehaves.
DB_PATH="$APP_DIR/var/aapda.db"
DB_BACKUP="$BACKUP_DIR/aapda-db-$STAMP.db"
if [ -f "$DB_PATH" ]; then
  log "snapshotting database -> $DB_BACKUP"
  "$APP_DIR/venv/bin/python" - "$DB_PATH" "$DB_BACKUP" <<'PY'
import sqlite3, sys

src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src, timeout=30) as source, sqlite3.connect(dst) as target:
    source.backup(target)
PY
else
  log "no database at $DB_PATH yet - skipping snapshot"
fi

health_ok() { curl -fsS -m 10 "$HEALTH_URL" 2>/dev/null | grep -q '"status":"ok"'; }

wait_for_health() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    health_ok && return 0
    sleep 2
  done
  return 1
}

rollback() {
  log "ROLLBACK -> ${PREV_SHA:0:7}"
  sudo journalctl -u "$SERVICE" -n 80 --no-pager 2>/dev/null | tail -40 || true

  rm -rf "$WORK_DIR/old"
  mkdir -p "$WORK_DIR/old"
  if tar -xzf "$BACKUP" -C "$WORK_DIR/old" && [ -d "$WORK_DIR/old/backend" ]; then
    rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$WORK_DIR/old/backend/" "$APP_DIR/"
    log "previous code restored"
  else
    log "WARNING: could not read backup $BACKUP"
  fi

  local new_req_hash
  new_req_hash="$(sha256sum "$APP_DIR/requirements.txt" 2>/dev/null | cut -d' ' -f1 || true)"
  if [ -n "$OLD_REQ_HASH" ] && [ "$OLD_REQ_HASH" != "$new_req_hash" ]; then
    log "restoring previous dependencies"
    "$VENV_PIP" install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt" || \
      log "WARNING: dependency restore failed"
  fi

  sudo systemctl restart "$SERVICE" || true
  if wait_for_health; then
    log "rollback recovered - API is healthy on the previous commit"
  else
    log "CRITICAL: API still unhealthy after rollback"
  fi
  printf '[%s] FAILED %s (rolled back to %s, db snapshot %s)\n' \
    "$STAMP" "$SHA" "$PREV_SHA" "$DB_BACKUP" >> "$DEPLOY_DIR/deploy.log"
  exit 1
}

# 2. Stage the artifact and sanity-check it before touching the live tree.
log "staging new code"
rm -rf "$WORK_DIR/new"
mkdir -p "$WORK_DIR/new"
tar -xzf "$ARTIFACT" -C "$WORK_DIR/new"
[ -f "$WORK_DIR/new/app/main.py" ] || die "artifact is not the backend (app/main.py missing)"
[ -f "$WORK_DIR/new/requirements.txt" ] || die "artifact is missing requirements.txt"
NEW_REQ_HASH="$(sha256sum "$WORK_DIR/new/requirements.txt" | cut -d' ' -f1)"

# 3. Sync code into place. venv/, var/ and .env are never touched.
log "syncing code into $APP_DIR"
rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$WORK_DIR/new/" "$APP_DIR/"
rm -rf "$WORK_DIR/new"

# 4. Install dependencies only when requirements.txt actually changed.
INSTALLED_REQ_HASH="$(cat "$DEPLOY_DIR/requirements.sha256" 2>/dev/null || echo '')"
if [ "$NEW_REQ_HASH" != "$INSTALLED_REQ_HASH" ]; then
  log "requirements changed - installing"
  if ! "$VENV_PIP" install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt"; then
    log "pip install failed"
    rollback
  fi
else
  log "requirements unchanged - skipping pip install"
fi

# 5. Restart and prove the API is healthy, otherwise roll back.
log "restarting $SERVICE"
sudo systemctl restart "$SERVICE"
if ! wait_for_health; then
  log "health check failed after ${HEALTH_TIMEOUT}s"
  rollback
fi

printf '%s\n' "$SHA" > "$DEPLOY_DIR/DEPLOYED_SHA"
printf '%s\n' "$NEW_REQ_HASH" > "$DEPLOY_DIR/requirements.sha256"
printf '[%s] OK %s (db snapshot %s)\n' "$STAMP" "$SHA" "$DB_BACKUP" >> "$DEPLOY_DIR/deploy.log"

log "deployed $SHA"
log "database snapshot kept at $DB_BACKUP"
curl -fsS -m 10 "$HEALTH_URL" || true
printf '\n'

# 6. Keep the last few backups, drop the rest.
ls -1t "$BACKUP_DIR"/backend-*.tar.gz 2>/dev/null | tail -n "+$((KEEP_BACKUPS + 1))" | xargs -r rm -f
ls -1t "$BACKUP_DIR"/aapda-db-*.db 2>/dev/null | tail -n "+$((KEEP_BACKUPS + 1))" | xargs -r rm -f
rm -rf "$WORK_DIR"
