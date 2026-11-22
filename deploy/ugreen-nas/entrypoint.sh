#!/usr/bin/env bash
# First-boot init + safety settings, then start JiuwenSwarm in the foreground.
set -euo pipefail

CONFIG_DIR="${HOME}/.jiuwenswarm/config"
ENV_FILE="${CONFIG_DIR}/.env"

if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
    echo "[devco] first boot: initialising ~/.jiuwenswarm"
    jiuwenswarm-init
fi

# Install / update the bundled DevCo skill (release image only; the source image
# ships it as a built-in skill). Existing installs are kept, because skill
# self-evolution may have improved them; set DEVCO_FORCE_SKILL_UPDATE=1 to
# replace (the old copy is kept as a backup).
BUNDLED_SKILL=/app/skills/fullstack-devco-swarm
USER_SKILL="${HOME}/.jiuwenswarm/agent/workspace/skills/fullstack-devco-swarm"
if [ -d "${BUNDLED_SKILL}" ]; then
    mkdir -p "$(dirname "${USER_SKILL}")"
    if [ ! -f "${USER_SKILL}/SKILL.md" ]; then
        cp -r "${BUNDLED_SKILL}" "${USER_SKILL}"
        echo "[devco] installed skill fullstack-devco-swarm"
    elif [ "${DEVCO_FORCE_SKILL_UPDATE:-0}" = "1" ]; then
        rm -rf "${USER_SKILL}.bak"
        mv "${USER_SKILL}" "${USER_SKILL}.bak"
        cp -r "${BUNDLED_SKILL}" "${USER_SKILL}"
        echo "[devco] updated skill fullstack-devco-swarm (previous copy: ${USER_SKILL}.bak)"
    fi
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
