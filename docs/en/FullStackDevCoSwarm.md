# Full-Stack DevCo Swarm

`fullstack-devco-swarm` is a built-in [Swarm Skill](SwarmSkills.md) that makes a JiuwenSwarm team behave like a small, self-reliant app development company. It can:

- **build** a full-stack web app from a brief
- **ship a feature** across backend and frontend in an existing repository
- **maintain** a codebase on a schedule: scan its health, triage, fix, verify and release, without a human driving each step

It ships with an executable SwarmFlow script (`scripts/workflow.py`), so a run is deterministic, can be watched in `/swarmflows`, and is bounded by explicit limits.

## The company

| Role | Kind | Job |
|---|---|---|
| `client` | human | Approves the PRD and the release (skipped with `auto_approve`) |
| `product-manager` | AI | PRD with testable acceptance criteria; triages health findings into tickets; keeps `.devco/BACKLOG.md` |
| `architect` | AI | Stack, API contract, data model, and **lanes** with non-overlapping file paths; runs the retrospective and curates `.devco/PLAYBOOK.md` |
| `backend-engineer` | AI | APIs, persistence, migrations, auth, with tests |
| `frontend-engineer` | AI | Accessible UI with loading / empty / error / success states, with tests |
| `qa-engineer` | AI | Runs the suites and the app, adds e2e tests, files reproducible defects |
| `security-reviewer` | AI | Independent OWASP-style review; reports, never patches |
| `devops-sre` | AI | CI, containers, config, dependency hygiene, health scans, releases |

## Pipeline

```
Intake ─► Architecture ─► Build (backend ∥ frontend ∥ devops) ─► Verify & Fix (QA ∥ security, ≤3 rounds) ─► Release ─► Retrospective
```

- **build / feature**: the PM writes `.devco/PRD.md` and the client approves it (one revision round is allowed).
- **maintain**: SRE, QA and security scan in parallel, then the PM triages the findings into at most `max_tickets` tickets. If there are no tickets, the run reports `healthy`.
- Blocker and major defects go back to the owning engineer, up to `max_fix_rounds` times. Nothing ships while blockers are open.
- **Self-improvement**: every run ends with a retrospective that rewrites `<project>/.devco/PLAYBOOK.md`, and every role reads that playbook before starting. The retro also proposes `skill_improvements` to the skill itself. Apply them with `swarmskill-creator` in MODIFY mode once you agree.

## Usage

1. Enable SwarmFlow: `/swarmflow on` in the TUI, or set `modes.team.jiuwen_team.enable_swarmflow: true`. Optionally set a team token cap with `swarmflow_budget`.
2. In a Team session, ask for it in plain language:

   ```text
   Use fullstack-devco-swarm to build a recipe-sharing web app in /home/me/apps/recipes
   (FastAPI + PostgreSQL + React). Users sign up, post recipes with photos, and search by ingredient.
   ```

   The Leader runs `scripts/workflow.py` with args like:

   ```json
   {"mode": "build", "request": "...", "project_dir": "/home/me/apps/recipes",
    "stack": "FastAPI + PostgreSQL + React", "max_fix_rounds": 2}
   ```

3. Answer the two client gates in the TUI with `h`: PRD approval, then release approval.

### Args

| Arg | Default | Notes |
|---|---|---|
| `request` | — | Brief, feature request, or maintenance focus |
| `mode` | `build` if `request`, else `maintain` | `build` / `feature` / `maintain` |
| `project_dir` | `./devco-app` | Use an absolute path |
| `stack` | — | Greenfield stack preference |
| `branch` | `devco/<mode>` | All work is committed here; never force-pushed |
| `auto_approve` | `false` | Unattended: ships only if verification is clean |
| `max_fix_rounds` | `2` | 0–3 |
| `max_tickets` | `5` | 1–8 per maintenance sweep |
| `signals` | — | CI logs, error reports or issues for maintain mode |
| `models` | — | Model per role or group (see below) |
| `agent_types` | — | External CLI agent per role or group (`claude`, `codex`) |
| `available_models` | — | Pool names; routed names outside the list are dropped up front |

## Using different models per role

Any role can run on any model you have configured. Routing is per project, and a bad entry never breaks a run.

### 1. Put the models in the team model pool

List every model under `models.defaults` in `~/.jiuwenswarm/config/config.yaml`, or add them under **More → Configuration → Model List** in the web UI. Once two or more entries exist, JiuwenSwarm builds a **team model pool** keyed by `model_name`. The first entry, marked `is_default: true`, is the team default. Any OpenAI-compatible endpoint works, including local servers:

```yaml
models:
  defaults:
    - model_client_config:            # team default
        model_name: deepseek-chat
        client_provider: DeepSeek
        api_base: https://api.deepseek.com
        api_key: ${DEEPSEEK_API_KEY}
      is_default: true
    - model_client_config:            # code model via DashScope
        model_name: qwen3-coder-plus
        client_provider: DashScope
        api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
        api_key: ${DASHSCOPE_API_KEY}
    - model_client_config:            # any vendor via OpenRouter
        model_name: anthropic/claude-sonnet-4
        client_provider: OpenRouter
        api_base: https://openrouter.ai/api/v1
        api_key: ${OPENROUTER_API_KEY}
    - model_client_config:            # local model (Ollama / vLLM / LM Studio)
        model_name: qwen2.5-coder:32b
        client_provider: OpenAI
        api_base: http://localhost:11434/v1
        api_key: local
```

### 2. Route roles to models

Copy `templates/models.yaml` from the skill to `<project>/.devco/models.yaml` and fill it in:

```yaml
models:
  default: deepseek-chat                  # every role not listed
  engineering: qwen3-coder-plus           # backend, frontend, devops
  review: anthropic/claude-sonnet-4       # qa + security: a different family catches more
  security: deepseek-reasoner             # role key beats group key
agent_types:                              # optional external coding-agent CLIs
  backend: codex
```

| Key | Covers |
|---|---|
| `default` | every role not matched below |
| `planning` | `product-manager`, `architect` |
| `engineering` | `backend-engineer`, `frontend-engineer`, `devops-sre` |
| `review` | `qa-engineer`, `security-reviewer` |
| role id or alias | `pm`, `architect`/`tech-lead`, `backend`, `frontend`, `devops`/`sre`, `qa`, `security` |

For each role, the model comes from its role key, then its group key, then `default`, and otherwise the team default model.

You can also route ad hoc in the request ("use qwen3-coder-plus for the engineers"), or pass the routing directly as workflow args: `{"models": {...}, "agent_types": {...}, "available_models": [...]}`.

### External coding agents

`agent_types` hands a role to an external CLI agent through openJiuwen's third-party worker support:

- `claude` runs Claude Code. Install with `pip install "jiuwenswarm[claude]"`. It needs an Anthropic-compatible pool model, or no model at all to use the CLI's own default.
- `codex` runs Codex. Install with `pip install "jiuwenswarm[codex]"`. It needs an OpenAI-compatible pool model, or no model at all.

### Fallbacks

Each agent call tries, in order:

1. the routed options, e.g. `{"model": "m", "agent_type": "codex"}`
2. the external CLI's own default model (only when both `agent_type` and `model` are set)
3. the team default model

An unknown model name, a missing CLI or an auth failure therefore costs one retry, not the run. The run report lists:

- `model_plan`: the resolved model and agent type for each role
- `model_fallbacks`: each fallback, with the error that triggered it
- `warnings`: unknown routing keys, and names outside `available_models`

## Keep it self-maintaining with cron

After the first build, schedule a weekly sweep:

```text
/cron add name=devco-maintain cron_expr="0 3 * * 1" mode=team timeout_seconds=3600 targets=tui description="Run the fullstack-devco-swarm skill in maintain mode on /home/me/apps/recipes with auto_approve=true"
```

Each sweep scans health, fixes the top tickets on the `devco/maintain` branch, opens a PR or merges per the project's conventions only if QA and security pass, and updates the playbook. Results are pushed to the target channel. See [Scheduled Tasks](ScheduledTasks.md).

## Project memory (`.devco/`)

| File | Owner |
|---|---|
| `PRD.md` | product-manager |
| `BACKLOG.md` | product-manager |
| `DESIGN.md`, `api/` | architect |
| `PLAYBOOK.md` | architect (retro), read by everyone |
| `HEALTH.md` | devops-sre |
| `reports/qa.md`, `reports/security.md` | qa-engineer, security-reviewer |

## Run statuses

`shipped` · `ready_awaiting_ship` · `needs_attention` (blockers remain or packaging failed) · `healthy` (maintain: nothing to fix) · `halted_by_client` · `degraded`

## Guardrails

Limits, isolation rules and failure handling are defined in the skill's `bind.md`:

- at most 3 parallel teammates, 12 lanes, 20 defects per round and 3 fix rounds
- engineers edit only their own lane paths
- QA and security never see each other's reports before submitting
- no secrets are committed and nothing is force-pushed
- production deploys happen only to an explicit, pre-approved target
