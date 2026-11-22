# Run JiuwenSwarm + the DevCo swarm on a UGREEN NAS

This folder runs JiuwenSwarm on a UGREEN NAS (UGOS Pro, DXP series) with Docker. You can then use it from your iPhone in Safari, plus an optional Telegram bot.

```
 iPhone (Tailscale app on)                    UGREEN NAS
 ┌───────────────────────┐   tailnet only    ┌──────────────────────────────────────────┐
 │ Safari:               │ ────────────────► │ devco-tailscale   (HTTPS, port 443)      │
 │ https://devco.<tn>    │   encrypted       │   └─ shared network ─┐                   │
 │                       │                   │ devco-jiuwenswarm    ▼                   │
 │ Telegram app ─────────┼──► Telegram ◄─────┼── bot polls (outbound only)              │
 └───────────────────────┘                   │   web UI / gateway / agents on 127.0.0.1 │
                                             │   /projects  ← apps the swarm builds     │
                                             └──────────────────────────────────────────┘
```

**Why it's set up like this.** A security review found that JiuwenSwarm's gateway has no login yet. So:
- **No ports are opened on your home network.** The app listens on `127.0.0.1` inside the container.
- **The only way in is Tailscale.** It serves the web UI over HTTPS to devices signed in to *your* tailnet.
- **Other websites are blocked.** The entrypoint turns on the WebSocket Origin check on every boot.

Never forward a port to this on your router.

---

## What you need

- A UGREEN NAS on **UGOS Pro**, with the **Docker** app installed from the App Center. Plan for **4 GB+ free RAM** (8 GB is comfortable) and ~10 GB of disk.
- **SSH** turned on: UGOS **Control Panel → Terminal → SSH**. You only need it for setup.
- A free **Tailscale** account, with the Tailscale app installed on your iPhone and signed in to the same account.
- An API key for at least one model provider (DeepSeek, DashScope, OpenRouter, OpenAI-compatible, …).
- Optional: a Telegram account for the bot.

## 1. Prepare Tailscale (5 min, in a browser)

1. In the [Tailscale admin console](https://login.tailscale.com/admin/dns), go to **DNS**:
   - Enable **MagicDNS**.
   - Under **HTTPS Certificates**, click **Enable HTTPS**.
   - Note your **Tailnet name** (looks like `tail1234.ts.net`).
2. Go to **Settings → Keys → Generate auth key**. Leave *Reusable* and *Ephemeral* **off** and turn *Pre-approved* **on**. Copy the key (`tskey-auth-…`).

## 2. Put the files on the NAS

SSH in from a computer on your home network (`ssh <your-ugos-user>@<nas-ip>`), then:

```bash
sudo mkdir -p /volume1/docker/devco/data /volume1/docker/devco/projects
sudo chown -R 1000:1000 /volume1/docker/devco/data /volume1/docker/devco/projects
cd /volume1/docker/devco
sudo git clone -b claude/sweet-mendel-6case1 https://github.com/limgreg/jiuwenswarm-glenn.git src
```

- **Different volume?** If your storage pool is `/volume2`, use that everywhere instead of `/volume1`.
- **No `git` on the NAS?** Download the branch as a ZIP from GitHub on your computer. Upload it with the UGOS **Files** app to `docker/devco/`, unzip it there, and rename the folder to `src`.
- **The `chown 1000:1000`:** the container runs as user ID 1000 and needs to write to these two folders.

## 3. Configure

```bash
cd /volume1/docker/devco/src/deploy/ugreen-nas
sudo cp .env.example .env
sudo nano .env        # fill in TS_AUTHKEY, TS_TAILNET; check the two folder paths
```

## 4. Start it

```bash
sudo docker compose up -d --build
```

- The **first build takes 10–25 minutes**: it installs Python and Node dependencies and builds the web UI.
- **Slow downloads (e.g. from mainland China)?** Add `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` by running `sudo docker compose build --build-arg PIP_INDEX_URL=… && sudo docker compose up -d`.
- **Watch it start:** `sudo docker compose logs -f`. Wait for the web UI line and `[devco] web UI (via Tailscale): https://devco.tail1234.ts.net`.
- Both containers also appear in the UGOS **Docker** app, where you can see logs, restart, and check CPU/RAM.

## 5. Open it on your iPhone

1. Turn on the Tailscale app.
2. In Safari, open `https://devco.<your-tailnet>.ts.net`. Tip: **Share → Add to Home Screen** makes it feel like an app.
3. Go to **More → Configuration**, add your model (`api_base`, `api_key`, `model`, `model_provider`), and click **Test**.
4. Turn on SwarmFlow (one time). Over SSH, either:
   - edit `/volume1/docker/devco/data/jiuwenswarm/config/config.yaml`, set `enable_swarmflow: true` under `modes.team.jiuwen_team`, then run `sudo docker compose restart jiuwenswarm`; or
   - run `sudo docker exec -it devco-jiuwenswarm jiuwenswarm-tui` and type `/swarmflow on`.

   Then start a **new chat** in the web UI.

You're ready. In a **Team** chat, paste the demo brief from `examples/devco-demo/brief.md`, with:

```
project_dir: /projects/shelfie
```

Inside the container, `/projects` is your NAS folder `/volume1/docker/devco/projects`. The finished app shows up there, and you can open it in the UGOS **Files** app.

## 6. Optional: Telegram bot

Use this for quick commands and status from anywhere ("run a maintain sweep on /projects/shelfie").

1. In Telegram, message **@BotFather** → `/newbot` → copy the **token**.
2. In the web UI, go to **Channels → Telegram**. Paste the token, enable it, and save.
3. **Lock it to you.** Find your numeric Telegram user ID (see *Get `user_id`* in `docs/en/InternationalChannels.md`) and put it in **`allow_from`**. Left empty, **anyone** who finds your bot can command the swarm, and so run commands on your NAS.

The bot polls Telegram over an outbound connection, so no ports need opening.

**What Telegram can't do (yet):**
- **The approval prompts** (PRD and release) only appear in the web UI or TUI. For runs started from Telegram, say `auto_approve=true`; the swarm then ships only when QA and security pass. For new builds, use the web UI so you can approve the PRD yourself.
- **Scheduled tasks can't report to Telegram.** Cron delivery supports web, tui, feishu, whatsapp, wecom, xiaoyi, wechat and dingtalk. Send the weekly sweep to the web UI instead:
  ```
  /cron add name=shelfie-maintain cron_expr="0 3 * * 1" mode=team timeout_seconds=3600 targets=web description="Use fullstack-devco-swarm in maintain mode on /projects/shelfie with auto_approve=true"
  ```

## 7. Optional: the TUI over SSH

The terminal UI has the live SwarmFlow monitor (`/swarmflows`). From an SSH session to the NAS, e.g. Termius or Blink on your iPhone while on home Wi-Fi:

```bash
sudo docker exec -it devco-jiuwenswarm jiuwenswarm-tui
```

## Day-to-day

| Task | Command (in `deploy/ugreen-nas`) |
|---|---|
| Stop / start | `sudo docker compose stop` / `sudo docker compose start` |
| Update to the latest code | `cd ../.. && sudo git pull && cd deploy/ugreen-nas && sudo docker compose up -d --build` |
| Logs | `sudo docker compose logs -f jiuwenswarm` |
| Back up | Copy `/volume1/docker/devco/data` (config, keys, sessions) and `projects/` (your apps), e.g. with UGOS backup / snapshots |
| Remove | `sudo docker compose down` (the data folders stay) |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `devco-tailscale` restarts, log mentions `/dev/net/tun` | In `docker-compose.yml`, set `TS_USERSPACE: "true"` and delete the `devices:` and `cap_add:` blocks. Serving the web UI still works |
| Safari: "can't connect" | Is the Tailscale app on and signed in to the same account? Is the machine `devco` online in the admin console? |
| Certificate warning | **Enable HTTPS** in the Tailscale DNS settings (step 1), then `sudo docker compose restart tailscale` |
| Page loads but chat never connects | `TS_TAILNET` / `TS_HOSTNAME` in `.env` must match the URL exactly. Check `sudo docker compose logs jiuwenswarm \| grep origin_not_allowed` |
| `Permission denied` under `/home/app/.jiuwenswarm` | Re-run the `chown -R 1000:1000` from step 2 |
| Build fails on `openjiuwen` (`gitcode.com`) | The NAS needs to reach gitcode.com during the build. Retry, or build on a network that can reach it |
| NAS slows down during big builds | Uncomment `mem_limit` / `cpus` in `docker-compose.yml` |

**Known limitation.** The swarm's DevOps role can't run `docker compose up` for the apps it builds, because the container deliberately has no access to the NAS's Docker. Build checks and tests still run. To try a finished app, run `sudo docker compose up` in its folder under `projects/` yourself.
