---
name: fullstack-devco-swarm
description: |
  Self-reliant full-stack app development company as an agent team: PM, architect, backend, frontend, QA, security and DevOps/SRE build, extend and maintain an app.
  Use when the user wants a web app built end to end, a feature shipped across backend and frontend, or a codebase kept healthy through recurring maintenance sweeps.
  Do NOT use for a one-file script, a quick bug fix one engineer can do, or non-software work.
version: "0.1"
kind: swarm-skill
roles:
  - id: client
    kind: human_agent
    purpose: Human product owner; approves the PRD and the release, or gives feedback. Replaced by a strict clean-verification rule in auto_approve runs.
    skills: []
    tools: []
  - id: product-manager
    kind: ai_agent
    purpose: Turns requests and health findings into testable user stories, acceptance criteria and a prioritized backlog.
    skills: []
    tools: [git]
  - id: architect
    kind: ai_agent
    purpose: Tech lead; picks the stack, writes the API contract and data model, splits work into fenced lanes, runs the retro and curates the playbook.
    skills: [project-maintainer]
    tools: [git]
  - id: backend-engineer
    kind: ai_agent
    purpose: Implements APIs, persistence, migrations, auth and business logic exactly to the contract, with tests.
    skills: []
    tools: [git, python]
  - id: frontend-engineer
    kind: ai_agent
    purpose: Builds accessible, responsive UI against the API contract with all UI states and component tests.
    skills: []
    tools: [git, node]
  - id: qa-engineer
    kind: ai_agent
    purpose: Runs suites and the app, adds integration and e2e tests, files reproducible defects with severity and owner.
    skills: []
    tools: [git, python, node]
  - id: security-reviewer
    kind: ai_agent
    purpose: Independent adversarial review of authz, injection, secrets, dependencies and config; reports, never patches.
    skills: []
    tools: [git]
  - id: devops-sre
    kind: ai_agent
    purpose: Owns CI, containers, config, dependency hygiene, observability, health scans and approved releases.
    skills: []
    tools: [git, docker]
---

# Full-Stack DevCo Swarm

DevCo behaves like a small app development company. It is a mixed pattern. A specialization pipeline (PRD → design → build → verify → release) has parallel decomposition inside Build, where backend, frontend and DevOps each own fenced lanes, and an adversarial cross-check inside Verify, where QA and security review in isolation. A single agent playing all of these parts tends to skip contracts, edit the same files and pass its own work. DevCo is self-reliant because every run ends with a retrospective that rewrites the project's `.devco/PLAYBOOK.md`, and every role reads that playbook first. A recurring `maintain` run then lets the company look after the codebase without a human driving each step.

## Workflow

0. **Pre-flight: check dependencies.** Read [dependencies.yaml](dependencies.yaml) and verify each entry. Report anything missing: `required: true` means the run will likely fail; `required: false` means it still works, with less. **The user decides** whether to proceed. Also confirm `project_dir` (an absolute path) and the mode.
1. **Choose the mode and args.** Use `build` for a new app, `feature` for a change to an existing repo, or `maintain` for a health sweep. Args: `request`, `mode`, `project_dir`, `stack`, `auto_approve`, `max_fix_rounds`, `max_tickets`, `signals`, `models`, `agent_types`, `available_models`. See [workflow.md](workflow.md) § Args.
   - **Model routing:** if `<project_dir>/.devco/models.yaml` exists, pass its `models` and `agent_types` maps through unchanged. A model the user names in the request ("use Qwen for the engineers") overrides the file. Pass the names in the configured model list (`models.defaults[].model_name`) as `available_models` whenever you know them. If no routing is given, every role uses the team default model. To set routing up for a project, copy [templates/models.yaml](templates/models.yaml) to `.devco/models.yaml`.
2. **Intake.**
   - build/feature: `product-manager` writes `.devco/PRD.md`, and the `client` approves it or gives feedback. There is one revision round. A second rejection halts the run.
   - maintain: `devops-sre`, `qa-engineer` and `security-reviewer` scan health in parallel. Then `product-manager` triages the findings into ≤ `max_tickets` tickets. If there are zero tickets, the run reports `healthy` and goes straight to the retro.
3. **Architecture.** `architect` writes `.devco/DESIGN.md` and the API contract, and splits the work into ≤ 12 lanes. Each lane has one owner and paths that no other owner touches.
4. **Build.** `backend-engineer`, `frontend-engineer` and `devops-sre` implement their lanes in parallel on the run branch, with tests.
5. **Verify & Fix.** `qa-engineer` and `security-reviewer` review in isolation. Blocker and major defects go back to their owners, for up to `max_fix_rounds` rounds. Limits are in [bind.md](bind.md).
6. **Release.** `devops-sre` packages the release. The `client` approves shipping. With `auto_approve`, the release ships only if verification is clean. Shipping means merging or opening a PR, then running approved deploy steps.
7. **Retrospective.** `architect` (as tech lead) rewrites `.devco/PLAYBOOK.md` and returns `skill_improvements` and `next_maintenance_focus`. Show the `skill_improvements` to the user. If they agree, apply them with `swarmskill-creator` in MODIFY mode.
8. **Final: emit the DevCo Run Report.** It contains the status (`shipped` | `ready_awaiting_ship` | `needs_attention` | `healthy` | `halted_by_client` | `degraded`), the stage outputs, unresolved blockers (quoted verbatim), warnings and the retro. The Leader surfaces QA/security disagreements as they are and never mediates.

**Self-maintenance:** after the first successful build, offer to schedule a weekly sweep. For example: `/cron add name=devco-maintain cron_expr="0 3 * * 1" mode=team timeout_seconds=3600 description="Run the fullstack-devco-swarm skill in maintain mode on /abs/path/to/app with auto_approve=true"`.

## Roles

| id | Purpose | When dispatched | Input | Key dependencies | Role file |
|---|---|---|---|---|---|
| client | Approves scope and release | Intake + Release gates (skipped when `auto_approve`) | PRD summary, release notes | — | [roles/client.md](roles/client.md) |
| product-manager | PRD / triage / backlog | Intake, every run | request or health findings | git | [roles/product-manager.md](roles/product-manager.md) |
| architect | Design, lanes, retro, playbook | Architecture + Retrospective | PRD or tickets | project-maintainer, git | [roles/architect.md](roles/architect.md) |
| backend-engineer | Server lanes and fixes | Build (if it has lanes), Verify & Fix (if it has defects) | lanes/defects, contract | git, python | [roles/backend-engineer.md](roles/backend-engineer.md) |
| frontend-engineer | UI lanes and fixes | Build (if it has lanes), Verify & Fix (if it has defects) | lanes/defects, contract | git, node | [roles/frontend-engineer.md](roles/frontend-engineer.md) |
| qa-engineer | Functional verification | Intake scan (maintain), every Verify round | requirements, build results | git, python, node | [roles/qa-engineer.md](roles/qa-engineer.md) |
| security-reviewer | Adversarial security review | Intake scan (maintain), every Verify round, in parallel with QA | requirements, build results | git | [roles/security-reviewer.md](roles/security-reviewer.md) |
| devops-sre | Platform, health, release | Intake scan (maintain), Build, Release | lanes, blockers | git, docker | [roles/devops-sre.md](roles/devops-sre.md) |

> Before dispatching each teammate, read the matching role file and copy its `## Inline Persona for Teammate` section straight into the dispatch prompt.
> Most adopting agents do NOT auto-load role files for teammates. In SwarmFlow mode, `scripts/workflow.py` already inlines condensed personas.

## Files

| File | What it contains | When to read |
|---|---|---|
| [workflow.md](workflow.md) | Mermaid diagram, args, step-by-step protocol, quality gates, Final Report format | Before first dispatch — the complete playbook |
| [bind.md](bind.md) | Resource limits, behavioral constraints, failure handling and degraded modes | When hitting limits, handling failures, or needing degraded-mode rules |
| [roles/\*.md](roles/) | Per-role identity, success criteria, boundary, output schema, Inline Persona | Before dispatching each teammate — extract Inline Persona |
| [dependencies.yaml](dependencies.yaml) | External skills and tools required to run | **Startup** — verify deps, report missing items, user decides go/no-go |
| [scripts/workflow.py](scripts/workflow.py) | Executable SwarmFlow workflow (all three modes) | When running in SwarmFlow mode: `swarmflow(script_path=<this file>, args={...})` |
| [templates/PLAYBOOK.md](templates/PLAYBOOK.md) | Seed for `<project>/.devco/PLAYBOOK.md` | First run on a project — copy it in if no playbook exists |
| [templates/models.yaml](templates/models.yaml) | Per-role / per-group model and external-agent routing | When the user wants different models per role — copy to `<project>/.devco/models.yaml` |
