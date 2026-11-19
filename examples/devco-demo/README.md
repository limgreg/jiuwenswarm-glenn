# DevCo tutorial: build "Shelfie" with the full-stack agent swarm

This walkthrough takes you from zero to a working app built by the
`fullstack-devco-swarm` team: a PM, an architect, backend and frontend engineers,
QA, a security reviewer and DevOps/SRE, with you as the client who signs off.

You will:

1. **Watch a free dry run** (no API key) to learn how a run flows.
2. **Set up** JiuwenSwarm, a model, and SwarmFlow.
3. **Build the demo app** "Shelfie", a small book-club tracker.
4. **Ship a feature** and **put the app on autopilot maintenance**.
5. **Give each role its own model**, optionally.

Files in this folder:

| File | What it is |
|---|---|
| `simulate.py` | Dry run on the real SwarmFlow engine with scripted agents. No model needed |
| `brief.md` | The Shelfie project brief, ready to paste into a Team session |
| `models.yaml` | Example per-role model routing |

---

## How the company works (2-minute mental model)

```
 you ──► Intake ──► Architecture ──► Build ──────────► Verify & Fix ──► Release ──► Retrospective
          PM writes   architect       backend ┐          QA  ┐  isolated   DevOps       tech lead
          the PRD,    picks stack,    frontend├ parallel  SEC ┘  reviews    packages,    updates
          you approve contract, lanes devops  ┘          blockers → owners  you approve  .devco/PLAYBOOK.md
```

- **Gates:** you are asked twice, at PRD approval and at release approval. Everything in between runs on its own.
- **Lanes:** the architect gives each engineer their own folders, so they can work in parallel without overwriting each other.
- **Fix loop:** QA and security review separately. Blocker and major defects go back to the owning engineer for up to 2 rounds (configurable). Nothing ships while blockers are open.
- **Memory:** every run ends with a retrospective that rewrites `<project>/.devco/PLAYBOOK.md`, and every role reads it first next time. This is how the team improves on *your* project.
- **Three modes:** `build` (new app), `feature` (change an existing repo) and `maintain` (health sweep, fix, ship).

---

## Step 1: Watch a dry run (no API key, ~1 second)

From the repository root, in the environment where jiuwenswarm is installed:

```bash
python examples/devco-demo/simulate.py                # whole build, gates auto-approved
python examples/devco-demo/simulate.py --interactive  # YOU answer the PRD and release gates
python examples/devco-demo/simulate.py --mode maintain
python examples/devco-demo/simulate.py --bad-model    # watch a misconfigured model fall back
```

This runs the skill's real `workflow.py` on openJiuwen's real SwarmFlow engine. Only the agents are scripted, so you see the true control flow. Abridged output:

```
== Intake ============================================================
   PM  product-manager-prd            model: deepseek-chat
   YOU PRD approval                   -> approved
== Architecture ======================================================
   ARC architect-design               model: deepseek-chat
== Build =============================================================
   ... Building 5 lanes across: backend-engineer, frontend-engineer, devops-sre
   BE  backend-engineer               model: qwen3-coder-plus
   FE  frontend-engineer              model: qwen3-coder-plus
   OPS devops-sre                     model: qwen3-coder-plus
== Verify & Fix ======================================================
   QA  qa-engineer                    model: deepseek-reasoner
   SEC security-reviewer              model: deepseek-reasoner
   ... Verification round 0: 2 blocking of 2 defects
   ... Fix round 1: dispatching backend-engineer
   BE  backend-engineer-fix           model: qwen3-coder-plus
   ... Verification round 1: 0 blocking of 0 defects
== Release ===========================================================
   YOU release approval               -> approved
   OPS devops-sre-ship                model: qwen3-coder-plus
== Retrospective =====================================================
   ARC tech-lead-retro                model: deepseek-chat
STATUS: shipped
Lesson -> playbook: Votes need a DB uniqueness constraint, not just an API check
```

Things to notice:
- QA caught a double-voting bug and security caught a missing owner check. Both went back to the backend engineer, and the re-check passed.
- Try `--interactive` and reject the PRD twice. The run stops before a single line of code is written (`halted_by_client`).

---

## Step 2: Set up JiuwenSwarm

1. **Install and start**
   ```bash
   pip install jiuwenswarm jiuwenswarm-tui
   jiuwenswarm-init      # first time only; installs fullstack-devco-swarm as a built-in skill
   jiuwenswarm-start     # web UI at http://localhost:5173
   jiuwenswarm-tui       # in a second terminal (recommended: it has the SwarmFlow monitor)
   ```
   Already installed before this skill existed? Restarting copies it in. You can also copy `jiuwenswarm/resources/agent/workspace/skills/fullstack-devco-swarm/` to `~/.jiuwenswarm/agent/workspace/skills/`.

2. **Add a model.** In the web UI open **More → Configuration**, enter `api_base`, `api_key`, `model` and `model_provider`, and click **Test**. Pick a model that is good at tool calling and code. Building a whole app is token-heavy, so start with a model you can afford to run for 30–60 minutes.

3. **Turn on SwarmFlow.** In the TUI:
   ```
   /swarmflow on
   /swarmflow         # should print: swarmflow: on · mode: team · budget: unbounded
   ```
   Optional spending cap: `/swarmflow on --budget 3000000` (tokens for the whole run).

4. **Safety: keep it local.** A security review of this codebase found that the gateway WebSocket has no authentication. For now:
   - Keep the default `127.0.0.1` binding. Do not set `WEB_HOST`, `GATEWAY_HOST` or `FRONTEND_HOST` to `0.0.0.0`.
   - In `~/.jiuwenswarm/config/.env`, set `JIUWENSWARM_ENABLE_ORIGIN_CHECK=1`, so other websites in your browser cannot talk to it.
   - Give the swarm an empty project folder, not your home directory.

---

## Step 3: Build Shelfie

1. Create an empty folder, e.g. `mkdir ~/shelfie`. *(Optional)* copy `models.yaml` to `~/shelfie/.devco/models.yaml` (see Step 6).
2. In the TUI, start a fresh team session with `/new`, then `/mode team` if you are not already in it.
3. Open `brief.md`, change `project_dir` to your folder's **absolute** path, and paste everything below the line.

What happens next:

| You see | What to do |
|---|---|
| Running banner `◐ 1 workflow running` | Nothing. Open `/swarmflows` to watch phases and agents live |
| A pending question (press **`h`**) with the PRD | Read the user stories and acceptance criteria. Reply `approved=true`, or `approved=false` with concrete feedback, e.g. *"add a dark mode toggle; drop progress percentages, use chapters"*. You get one revision round |
| Build and Verify phases | Nothing. In `/swarmflows` → phase → agent, press `p` for the prompt and `o` for the outcome |
| Second pending question: the release | It lists release notes and how to run. Approve to let DevOps open a PR or merge per your repo conventions |
| Final report | Status (`shipped`, `ready_awaiting_ship`, `needs_attention`, …), unresolved blockers, and the retrospective |

4. **Run what they built**
   ```bash
   cd ~/shelfie
   cat .devco/PRD.md .devco/DESIGN.md     # what was agreed and designed
   git log --oneline                      # one commit per lane / fix
   cp .env.example .env && docker compose up
   ```
   Then open the URL from the release notes. Read `.devco/reports/qa.md` and `.devco/reports/security.md` to see what was caught.

**Tips for good results**
- Be concrete in the brief: list the user-visible features, the stack, and what is out of scope.
- Smaller is better for a first run. Six user stories is about right.
- If the status is `needs_attention`, read the unresolved blockers, then rerun in `feature` mode with *"fix the open blockers in .devco/reports"*.

---

## Step 4: Ship a feature

Same session, or later:

```
Use fullstack-devco-swarm in feature mode on /ABSOLUTE/PATH/TO/shelfie:
add a "reading streak" badge that counts consecutive days a member updated progress.
```

Feature mode reads the existing code and playbook first, writes a PRD for the change only, and limits lanes to the folders the feature touches.

---

## Step 5: Put it on autopilot (self-maintenance)

Ask for a sweep any time:

```
Use fullstack-devco-swarm in maintain mode on /ABSOLUTE/PATH/TO/shelfie with auto_approve=true
```

Or schedule a weekly one (Monday 03:00):

```
/cron add name=shelfie-maintain cron_expr="0 3 * * 1" mode=team timeout_seconds=3600 targets=tui description="Use fullstack-devco-swarm in maintain mode on /ABSOLUTE/PATH/TO/shelfie with auto_approve=true"
```

Each sweep:
1. SRE, QA and security scan in parallel: dependencies, CVEs, failing or flaky tests, secrets.
2. The PM picks up to 5 tickets and logs the rest in `.devco/BACKLOG.md`.
3. The engineers fix them, and QA and security re-check.
4. The fixes ship **only if verification is clean**, on the `devco/maintain` branch.
5. The retro updates the playbook with what to look at next time.

Add `signals` to point it at something specific: `signals="CI is failing on test_votes; users report slow club page"`.

---

## Step 6 (optional): A different model per role

1. List every model you want under `models.defaults` in `~/.jiuwenswarm/config/config.yaml`, or in **More → Configuration → Model List**. With two or more entries they form the **team model pool**.
2. Copy `models.yaml` from this folder to `<project>/.devco/models.yaml` and use names from your pool:
   ```yaml
   models:
     default: deepseek-chat
     engineering: qwen3-coder-plus   # backend, frontend, devops
     review: deepseek-reasoner       # qa + security
   ```
   The keys are `default`, `planning` (PM + architect), `engineering`, `review`, or a single role (`pm`, `backend`, `frontend`, `devops`, `qa`, `security`, `tech-lead`). A role key beats its group key.
3. A wrong name never breaks the run. That call falls back to your default model, and the report lists it under `model_fallbacks`. Try `simulate.py --bad-model` to see this.

You can also say it in the request: *"…use qwen3-coder-plus for the engineers"*.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| The Leader answers in chat instead of starting a workflow | Run `/swarmflow on`, then `/new`, and name the skill explicitly ("Use fullstack-devco-swarm …") |
| No `h` prompt appears | Open `/swarmflows`; the node shows `waiting_for_human` |
| `halted_by_client` | You rejected the PRD twice or didn't answer. Start again with clearer requirements |
| `needs_attention` | Blockers remained after the fix rounds. Read `.devco/reports/*.md`, then run a `feature` run to fix them, or raise `max_fix_rounds` (max 3) |
| Run failed on budget | Raise `swarmflow_budget` or shrink the brief |
| The skill isn't found | Check that `~/.jiuwenswarm/agent/workspace/skills/fullstack-devco-swarm/SKILL.md` exists, then restart |

More detail: `docs/en/FullStackDevCoSwarm.md` (reference) and `docs/en/TUISwarmFlowGuide.md` (monitoring UI).
