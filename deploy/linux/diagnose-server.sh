#!/usr/bin/env bash

set -u

SERVICE_NAME="biedribas-finansists"
BACKEND_URL="http://127.0.0.1:8011"
PUBLIC_URL="http://127.0.0.1"

echo "== Service =="
systemctl is-active "$SERVICE_NAME" || true
systemctl status "$SERVICE_NAME" --no-pager -l | sed -n '1,18p' || true

echo
echo "== Backend =="
curl -I --max-time 5 "$BACKEND_URL" || true

echo
echo "== Nginx =="
systemctl is-active nginx || true
curl -I --max-time 5 "$PUBLIC_URL" || true

echo
echo "== Sleep / idle hints =="
systemctl status sleep.target suspend.target hibernate.target --no-pager -l | sed -n '1,18p' || true
loginctl show-session "$(loginctl | awk 'NR==2 {print $1}')" -p IdleHint -p IdleSinceHint 2>/dev/null || true

echo
echo "== Recent logs =="
journalctl -u "$SERVICE_NAME" -n 40 --no-pager || true
echo
journalctl -u nginx -n 40 --no-pager || true
