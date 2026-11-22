#!/usr/bin/env bash
# First-boot init + safety settings, then start JiuwenSwarm in the foreground.
set -euo pipefail

CONFIG_DIR="${HOME}/.jiuwenswarm/config"
ENV_FILE="${CONFIG_DIR}/.env"

if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
    echo "[devco] first boot: initialising ~/.jiuwenswarm"
    jiuwenswarm-init
fi

# JiuwenSwarm loads this .env with override=True, so container env vars alone are
# not enough: pin the safety-critical settings in the file on every boot.
set_env() {
    local key="$1" value="$2"
    touch "${ENV_FILE}"
    if grep -q "^${key}=" "${ENV_FILE}"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
    else
        printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
    fi
}

# Everything listens on loopback only; the Tailscale sidecar is the single way in.
set_env FRONTEND_HOST 127.0.0.1
set_env WEB_HOST 127.0.0.1
set_env GATEWAY_HOST 127.0.0.1
set_env AGENT_SERVER_HOST 127.0.0.1
# Reject WebSocket connections from any other website (cross-site hijacking).
set_env JIUWENSWARM_ENABLE_ORIGIN_CHECK 1
set_env JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS "127.0.0.1,localhost${DEVCO_PUBLIC_HOST:+,${DEVCO_PUBLIC_HOST}}"

echo "[devco] web UI (via Tailscale): https://${DEVCO_PUBLIC_HOST:-<tailscale-name>}"
exec jiuwenswarm-start
