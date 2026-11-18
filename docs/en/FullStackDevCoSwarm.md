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
