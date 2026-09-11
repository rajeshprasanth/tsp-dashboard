#!/usr/bin/env bash
# Install tsp-dashboard as a systemd service.
#
# Usage:  sudo ./scripts/install_service.sh
#
# What it does:
#   1. creates the dedicated system user `tspd`
#   2. copies the application to /opt/tsp-dashboard
#   3. creates a virtualenv and installs requirements
#   4. creates /data (tsp socket + job output) owned by tspd
#   5. writes /etc/tsp-dashboard.env from .env.example (edit passwords!)
#   6. installs the systemd units and starts the service
#
# Optional companion daemon (keeps a persistent task-spooler server):
#   sudo systemctl enable --now task-spooler.service
set -euo pipefail

PROG="tsp-dashboard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="/opt/$PROG"
ENV_FILE="/etc/$PROG.env"
RUN_USER="tspd"
UNIT_DIR="/etc/systemd/system"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m!!\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || die "please run as root: sudo $0"
}

create_user() {
  if ! id "$RUN_USER" &>/dev/null; then
    log "creating system user '$RUN_USER'"
    useradd --system --shell /usr/sbin/nologin "$RUN_USER"
  else
    log "user '$RUN_USER' already exists"
  fi
}

install_app() {
  log "installing application to $INSTALL_DIR"
  install -d -o "$RUN_USER" -g "$RUN_USER" "$INSTALL_DIR"
  tar --exclude='.venv' --exclude='.git' --exclude='**/__pycache__' \
      --exclude='users.json' --exclude='.env' \
      -C "$APP_DIR" -cf - . | tar -C "$INSTALL_DIR" -xf -
  chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

  if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
    log "creating virtualenv + installing requirements"
    python3 -m venv "$INSTALL_DIR/.venv"
    "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
  fi
}

create_data_dir() {
  log "creating /data (tsp socket + job output)"
  install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 /data
}

write_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "writing $ENV_FILE — EDIT IT NOW with real passwords"
    cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    chown "$RUN_USER:$RUN_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  else
    log "keeping existing $ENV_FILE"
  fi
}

install_units() {
  log "installing systemd units"
  install -m 0644 "$INSTALL_DIR/systemd/tsp-dashboard.service" "$UNIT_DIR/"
  if command -v ts >/dev/null 2>&1 || command -v tsp >/dev/null 2>&1; then
    install -m 0644 "$INSTALL_DIR/systemd/task-spooler.service" "$UNIT_DIR/"
  fi
  systemctl daemon-reload
}

main() {
  require_root
  create_user
  install_app
  create_data_dir
  write_env_file
  install_units

  log "enabling and starting $PROG"
  systemctl enable --now "$PROG.service"
  systemctl status --no-pager "$PROG.service" || true

  log "done — dashboard on http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):${TSPD_PORT:-8766}"
  log "next steps: sudo $EDITOR $ENV_FILE  then  sudo systemctl restart $PROG"
}

main "$@"