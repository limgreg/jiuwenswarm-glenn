"""Executable SwarmFlow workflow for fullstack-devco-swarm.

DevCo is a self-reliant full-stack app development "company" made of agents:
product manager, architect / tech lead, backend engineer, frontend engineer,
QA engineer, security reviewer, DevOps/SRE, plus a human client who approves
scope and releases.

One script drives three operating modes through the same six phases:

* ``build``    - greenfield app from a natural-language brief
* ``feature``  - add / change a feature in an existing repository
* ``maintain`` - self-maintenance sweep (health scan -> triage -> fix ->
                 verify -> release), designed to run unattended from cron

Every run ends with a Retrospective that writes lessons into the project's
``.devco/PLAYBOOK.md``; every role reads that playbook first, so the company
gets better at maintaining the project over time.

Args (dict or JSON string):
    request          str   brief / feature request / maintenance focus
    mode             str   build | feature | maintain   (default: build if
                           request is given, otherwise maintain)
    project_dir      str   absolute path of the repository to work in
    stack            str   optional stack preference, e.g.
                           "FastAPI + PostgreSQL + React/Vite + Docker"
    auto_approve     bool  skip human gates (unattended maintenance)
    max_fix_rounds   int   verify -> fix rounds, 0..3 (default 2)
    max_tickets      int   maintenance tickets per sweep, 1..8 (default 5)
    signals          str   optional extra input for maintain mode: CI logs,
                           error reports, issue list, user complaints
"""
import json
from string import Template

from swarmflow import agent, compact, human, log, parallel, phase

META = {
    "name": "fullstack-devco-swarm",
    "description": (
        "Autonomous full-stack app dev company: PM, architect, backend, frontend, "
        "QA, security and DevOps/SRE agents build, extend, and self-maintain an app."
    ),
    "whenToUse": (
        "Reuse when an app must be built end to end, a feature shipped across "
        "backend and frontend, or a codebase swept for health issues and fixed "
        "without a human driving each step."
    ),
    "phases": [
        {
            "title": "Intake",
            "detail": "build/feature: PM writes the PRD and the client approves; "
            "maintain: SRE, QA and security scan health in parallel, PM triages tickets",
        },
        {
            "title": "Architecture",
            "detail": "Architect fixes stack, API contract, data model and splits "
            "work into owned lanes (backend / frontend / devops)",
        },
        {
            "title": "Build",
            "detail": "Backend, frontend and DevOps engineers implement their lanes "
            "in parallel inside their own directories, with tests",
        },
        {
            "title": "Verify & Fix",
            "detail": "QA and security review in isolation; blocking defects are "
            "routed back to owners for bounded fix rounds",
        },
        {
            "title": "Release",
            "detail": "DevOps packages the release; the client approves deploy "
            "(auto-approved only when verification is clean)",
        },
        {
            "title": "Retrospective",
            "detail": "Tech lead records lessons in .devco/PLAYBOOK.md and proposes "
            "improvements to this swarm skill",
        },
    ],
}

# ---------------------------------------------------------------------------
# Limits (mirrored in bind.md)
# ---------------------------------------------------------------------------
MAX_LANES = 12
MAX_DEFECTS_PER_ROUND = 20
MAX_FIX_ROUNDS_CAP = 3
MAX_TICKETS_CAP = 8
LANE_OWNERS = ("backend-engineer", "frontend-engineer", "devops-sre")

# ---------------------------------------------------------------------------
# JSON Schemas for structured outputs (no "required"/"additionalProperties").
# ---------------------------------------------------------------------------
PRD_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "title": {"type": "string"},
        "user_stories": {"type": "array", "items": {"type": "string"}},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "non_goals": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
}

HEALTH_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string"},
                    "area": {"type": "string"},
                    "title": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
    },
}

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "tickets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "priority": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "acceptance": {"type": "string"},
                },
            },
        },
    },
}

DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "stack": {"type": "string"},
        "api_contract": {"type": "string"},
        "data_model": {"type": "string"},
        "lanes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "owner": {"type": "string"},
                    "title": {"type": "string"},
                    "scope": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

LANE_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "tests_added": {"type": "array", "items": {"type": "string"}},
        "test_command": {"type": "string"},
        "notes": {"type": "string"},
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "severity": {"type": "string"},
                    "owner": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "repro": {"type": "string"},
                },
            },
        },
    },
}

RELEASE_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "branch": {"type": "string"},
        "release_notes": {"type": "string"},
        "run_instructions": {"type": "string"},
        "deploy_steps": {"type": "string"},
    },
}

RETRO_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "verdict": {"type": "string"},
        "lessons": {"type": "array", "items": {"type": "string"}},
        "playbook_updates": {"type": "array", "items": {"type": "string"}},
        "skill_improvements": {"type": "array", "items": {"type": "string"}},
        "next_maintenance_focus": {"type": "array", "items": {"type": "string"}},
    },
}

APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "feedback": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Inline personas (condensed from roles/*.md "Inline Persona for Teammate").
# ---------------------------------------------------------------------------
PERSONA_PM = (
    "You are the Product Manager. Motto: 'If it is not in the acceptance "
    "criteria, it does not exist.' You turn fuzzy asks into testable user "
    "stories and you prioritise ruthlessly. You never design architecture or "
    "write production code."
)
PERSONA_ARCHITECT = (
    "You are the Architect and Tech Lead. Motto: 'Every lane gets a contract "
    "and a fence.' You choose boring, proven technology, define the API "
    "contract and data model first, and split work so engineers never edit "
    "the same files. You respect an existing codebase's stack and conventions."
)
PERSONA_BACKEND = (
    "You are the Backend Engineer. Motto: 'The API contract is law; the "
    "database is sacred.' You implement endpoints, persistence, auth and "
    "business logic exactly to contract, with migrations and unit tests. You "
    "only edit files inside your lane's paths."
)
PERSONA_FRONTEND = (
    "You are the Frontend Engineer. Motto: 'Every state the user can reach "
    "has a screen: loading, empty, error, success.' You build accessible, "
    "responsive UI against the API contract with component tests. You only "
    "edit files inside your lane's paths and never change the backend."
)
PERSONA_DEVOPS = (
    "You are the DevOps / SRE engineer. Motto: 'If it is not automated and "
    "observable, it is not done.' You own CI, containers, environment config, "
    "dependency hygiene, health checks, logs and runbooks. You never commit "
    "secrets and never deploy without an explicit approval."
)
PERSONA_QA = (
    "You are the QA Engineer. Motto: 'I am trying to break this before a user "
    "does.' You actually run the test suites and the app, write missing "
    "integration / end-to-end tests, and file reproducible defects. You never "
    "fix production code yourself."
)
PERSONA_SECURITY = (
    "You are the Security Reviewer. Motto: 'Assume every input is hostile and "
    "every secret will leak.' You review the change against OWASP Top 10 / "
    "ASVS basics, auth and authorization, injection, secrets, dependency CVEs "
    "and unsafe defaults. You report; you never patch."
)

# ---------------------------------------------------------------------------
# Resilient helpers
# ---------------------------------------------------------------------------


def extract_json(text, fallback=None):
    """Extract the first JSON object from text (LLM output may have prose)."""
    fallback_value = {} if fallback is None else fallback
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return fallback_value
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else fallback_value
    except (json.JSONDecodeError, ValueError):
        pass
    depth = 0
    start = None
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    parsed = json.loads(text[start:i + 1])
                    return parsed if isinstance(parsed, dict) else fallback_value
                except (json.JSONDecodeError, ValueError):
                    start = None
    return fallback_value


def safe_get(obj, key, default=""):
    """Safely get a string field from an agent result."""
    if obj is None:
        return str(default)
    if isinstance(obj, dict):
        value = obj.get(key, default)
        return str(default) if value is None else str(value)
    return str(default)


def safe_list(obj, key):
    """Safely get a list field from an agent result."""
    if isinstance(obj, dict) and isinstance(obj.get(key), list):
        return obj.get(key)
    return []


def has_meaningful_result(obj):
    """Return True only when semantic success fields are non-empty."""
    return (
        safe_get(obj, "verdict", "unknown") not in ("unknown", "")
        and bool(safe_get(obj, "result", "").strip())
    )


def parse_args(args):
    """Normalize args to dict. Swarmflow may pass JSON string or dict."""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args) if args.strip() else {}
            return parsed if isinstance(parsed, dict) else {"request": args}
        except json.JSONDecodeError:
            return {"request": args}
    return {}


def as_bool(value, default=False):
    """Coerce loose truthy values ("true", 1, "yes") to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def clamp_int(value, default, low, high):
    """Parse an int and clamp it into [low, high]."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def normalize_mode(raw_mode, request):
    """Resolve the operating mode."""
    mode = str(raw_mode or "").strip().lower()
    if mode in ("build", "feature", "maintain"):
        return mode
    if mode in ("new", "greenfield", "create"):
        return "build"
    if mode in ("maintenance", "health", "sweep", "self-maintain"):
        return "maintain"
    return "build" if str(request or "").strip() else "maintain"


def normalize_owner(owner):
    """Map free-form owner names onto the three build lanes."""
    text = str(owner or "").strip().lower()
    if "front" in text or "ui" in text or "web" in text:
        return "frontend-engineer"
    if "devops" in text or "sre" in text or "infra" in text or "ci" in text:
        return "devops-sre"
    return "backend-engineer"


def is_blocking(defect):
    """Blocker / critical / major defects block release."""
    severity = safe_get(defect, "severity", "minor").strip().lower()
    return severity in ("blocker", "critical", "high", "major")


def group_by_owner(items):
    """Group lanes or defects by normalized owner."""
    grouped = {owner: [] for owner in LANE_OWNERS}
    for item in items:
        if isinstance(item, dict):
            grouped[normalize_owner(item.get("owner"))].append(item)
    return grouped


def collect_defects(reviews):
    """Merge QA + security defects, capped, blockers first."""
    defects = []
    for review in reviews:
        for defect in safe_list(review, "defects"):
            if isinstance(defect, dict) and safe_get(defect, "title").strip():
                defects.append(defect)
    defects.sort(key=lambda d: 0 if is_blocking(d) else 1)
    return defects[:MAX_DEFECTS_PER_ROUND], max(0, len(defects) - MAX_DEFECTS_PER_ROUND)


def approval_granted(answer):
    """Interpret a human approval answer (None = no answer = not approved)."""
    if answer is None:
        return False, "no answer from client"
    parsed = extract_json(answer, fallback={})
    if parsed:
        return as_bool(parsed.get("approved"), False), safe_get(parsed, "feedback")
    text = str(answer).strip().lower()
    approved = text.startswith(("y", "approve", "ok", "lgtm", "ship"))
    return approved, str(answer)


# ---------------------------------------------------------------------------
# Prompt builders (string.Template so literal braces are safe)
# ---------------------------------------------------------------------------

ROLE_PROMPT = Template(
    """ROLE: $role_title at DevCo, an autonomous full-stack app development company.
$persona

OPERATING MODE: $mode
PROJECT DIRECTORY (work only inside it): $project_dir

COMPANY RULES
1. Before anything else, read $project_dir/.devco/PLAYBOOK.md if it exists and
   follow every lesson in it. Also read existing artifacts in $project_dir/.devco/
   (PRD.md, DESIGN.md, BACKLOG.md, HEALTH.md, reports/) so you build on prior work.
2. Work on the git branch named in the context (create it from the default branch
   if missing). Commit your own changes with clear conventional-commit messages.
   Never force-push, never rewrite history, never commit secrets or .env files.
3. Stay inside your role. If something outside your role is broken, report it in
   your JSON instead of fixing it.
4. Prefer the project's existing stack, conventions, package manager and test
   runner. Run the relevant tests before reporting done and report the command.

YOUR TASK
$task

CONTEXT (JSON)
$context

Return ONLY a valid JSON object - no markdown fences, no prose around it.
Expected fields: $fields
"""
)


def build_prompt(role_title, persona, task, context, fields, run_ctx):
    """Build a role prompt that requests JSON output."""
    context_text = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    return ROLE_PROMPT.substitute(
        role_title=role_title,
        persona=persona,
        mode=run_ctx["mode"],
        project_dir=run_ctx["project_dir"],
        task=task,
        context=context_text,
        fields=fields,
    )


TASK_PRD = """Write the Product Requirements Document for the request in the context.
- Save it to .devco/PRD.md (create .devco/ if needed) and commit it.
- In "feature" mode, first read the existing code and docs so the PRD fits the product.
- If client feedback is present in the context, revise the PRD to address every point.
- 3-12 user stories ("As a [user], I want [goal], so that [benefit]").
- Every acceptance criterion must be objectively testable (QA will test them verbatim).
- Make reasonable assumptions instead of blocking; list them under open_questions."""

TASK_HEALTH_DEVOPS = """Run a health scan of the repository from the DevOps/SRE angle.
- Does it install and build from a clean checkout? Does CI config exist and pass locally?
- Outdated or deprecated dependencies, lockfile drift, known-vulnerable packages
  (use npm audit / pip-audit / equivalent if available).
- Missing health checks, logging, Dockerfile/compose problems, broken scripts.
- Write the findings to .devco/HEALTH.md (append a dated section) and commit.
Findings severity: blocker | major | minor."""

TASK_HEALTH_QA = """Run a health scan of the repository from the QA angle.
- Run every test suite you can find; record failures, flaky tests and slow tests.
- Identify untested critical paths (auth, payments, data writes) and coverage gaps.
- Smoke-test the app if it can be started locally.
Findings severity: blocker | major | minor. Do not fix anything."""

TASK_HEALTH_SECURITY = """Run a security health scan of the repository.
- Secrets committed to the repo, unsafe defaults, missing auth/authorization checks,
  injection risks, insecure CORS / cookies / headers, vulnerable dependencies.
Findings severity: blocker | major | minor. Do not patch anything."""

TASK_TRIAGE = """Triage the health findings (and any external signals) into a prioritized backlog.
- Merge duplicates, drop noise, rank by user impact x risk x effort.
- Emit at most max_tickets tickets for this sweep; each must have a testable acceptance line.
- Append the full backlog (including deferred items) to .devco/BACKLOG.md and commit.
- If nothing is worth fixing, return an empty tickets list and verdict "healthy"."""

TASK_DESIGN = """Produce the technical design and split the work into lanes.
- Respect the existing stack. For a greenfield app with no preference, default to a
  boring, proven stack (e.g. FastAPI or Express + PostgreSQL + React/TypeScript with
  Vite + Docker Compose) and justify it in one line.
- Write .devco/DESIGN.md (architecture, data model, error model, auth) and the API
  contract (.devco/api/openapi.yaml or equivalent), scaffold the directory layout,
  then commit.
- Lanes: each lane has id, owner (backend-engineer | frontend-engineer | devops-sre),
  title, scope and the exact paths that owner may edit. Paths of different owners must
  NOT overlap. In maintain mode, turn each ticket into one or more lanes.
- At most 12 lanes. Keep lanes vertical and independently testable."""

TASK_LANE = """Implement every lane assigned to you in the context.
- Edit only files inside your lanes' paths (shared contract files are read-only).
- Write or update automated tests for what you build and run them.
- Commit per lane. Report files_changed, tests_added and the test_command you ran.
- verdict: "done" when all your lanes pass their tests, "partial" or "blocked" otherwise
  (explain in notes)."""

TASK_FIX = """Fix every defect assigned to you in the context.
- Reproduce first, add a regression test, then fix. Stay inside your lane paths.
- Commit each fix referencing the defect id. Report what you changed.
- verdict: "done" if all assigned defects are fixed and tests pass, else "partial"."""

TASK_QA_REVIEW = """Verify the current state of the branch against the acceptance criteria.
- Run all test suites, start the app if possible, and exercise every acceptance criterion.
- Add missing integration / end-to-end tests under the tests directory (test code only).
- Save a report to .devco/reports/qa.md and commit it.
- Each defect: id, severity (blocker|major|minor), owner (backend-engineer |
  frontend-engineer | devops-sre), title, detail, repro steps.
- verdict: "pass" only if there are no blocker/major defects, otherwise "fail"."""

TASK_SECURITY_REVIEW = """Review the changes on the branch for security problems (work independently of QA).
- Check authn/authz on every endpoint, input validation, injection, XSS/CSRF, secrets,
  CORS, dependency CVEs, error messages leaking internals, unsafe infra defaults.
- Save a report to .devco/reports/security.md and commit it.
- Each defect: id, severity (blocker|major|minor), owner, title, detail, repro.
- verdict: "pass" only if there are no blocker/major defects, otherwise "fail"."""

TASK_RELEASE = """Prepare the release.
- Ensure CI config, Dockerfile / compose, .env.example and README run instructions exist
  and work. Bump the version / changelog if the project uses them.
- Write release notes from the PRD / tickets and the verification reports.
- Do NOT deploy and do NOT merge to the default branch in this step.
- verdict: "ready" only if unresolved_blockers in the context is empty, otherwise "not_ready"."""

TASK_SHIP = """The client approved the release. Merge or open a pull request for the branch
according to the project's conventions (prefer a pull request if a remote exists), and
run the deployment steps only if the project has an automated, non-production or
explicitly approved target. Report exactly what you did; never force-push."""

TASK_RETRO = """Run the blameless retrospective for this run as Tech Lead.
- What slowed the team down, which defects escaped to verification, which commands or
  conventions should every role know next time?
- Rewrite .devco/PLAYBOOK.md: keep it under ~150 lines, dedupe, keep the most useful
  lessons at the top, remove lessons that proved wrong. Commit it.
- playbook_updates: the lessons you added/changed. skill_improvements: concrete
  suggestions to improve the fullstack-devco-swarm skill itself.
- next_maintenance_focus: what the next maintenance sweep should look at first."""


PRD_REVIEW_PROMPT = Template(
    """$heading - $title

User stories
$stories

Acceptance criteria
$criteria

Open questions / assumptions
$questions

Approve this scope? Answer approved=true, or approved=false with concrete feedback
(one revision round is allowed; a second rejection stops the run before any code is written).
"""
)

RELEASE_REVIEW_PROMPT = Template(
    """DevCo release is ready on branch $branch and verification is clean.

Release notes
$notes

How to run
$run

Deploy steps
$deploy

Ship it (merge or open a PR, then run the deploy steps above)? Answer approved=true,
or approved=false with feedback.
"""
)


def bullets(items):
    """Render a list as markdown bullets for human-facing prompts."""
    lines = ["- " + str(item) for item in items if str(item).strip()]
    return "\n".join(lines) if lines else "- (none)"


# ---------------------------------------------------------------------------
# Workflow entrypoint
# ---------------------------------------------------------------------------


async def run(args):
    """Execute the DevCo workflow and return a JSON-serializable report."""
    args = parse_args(args)

    request = str(args.get("request") or args.get("task") or "").strip()
    mode = normalize_mode(args.get("mode"), request)
    project_dir = str(args.get("project_dir") or "").strip() or "./devco-app"
    auto_approve = as_bool(args.get("auto_approve"), False)
    max_fix_rounds = clamp_int(args.get("max_fix_rounds"), 2, 0, MAX_FIX_ROUNDS_CAP)
    max_tickets = clamp_int(args.get("max_tickets"), 5, 1, MAX_TICKETS_CAP)
    branch = str(args.get("branch") or "").strip() or ("devco/" + mode)
    run_ctx = {"mode": mode, "project_dir": project_dir}
    base_context = {
        "request": request,
        "stack_preference": str(args.get("stack") or ""),
        "branch": branch,
        "mode": mode,
    }
    report = {
        "mode": mode,
        "project_dir": project_dir,
        "branch": branch,
        "status": "running",
        "stages": {},
        "warnings": [],
    }
    halted = False
    requirements = {}
    tickets = []

    log("DevCo run: mode=" + mode + " project=" + project_dir + " branch=" + branch)
    if mode != "maintain" and not request:
        log("No request given for build/feature mode; falling back to maintain mode")
        mode = "maintain"
        run_ctx["mode"] = mode
        base_context["mode"] = mode
        report["mode"] = mode

    # ------------------------------------------------------------------ Intake
    phase("Intake")
    if mode == "maintain":
        log("Health scan: DevOps/SRE, QA and Security in parallel")
        scan_context = dict(base_context, signals=str(args.get("signals") or ""))
        raw_scans = await parallel(
            [
                lambda: agent(
                    build_prompt("DevOps / SRE", PERSONA_DEVOPS, TASK_HEALTH_DEVOPS,
                                 scan_context, "result, verdict, findings[]", run_ctx),
                    label="devops-sre-scan",
                    phase="Intake",
                    schema=HEALTH_SCHEMA,
                ),
                lambda: agent(
                    build_prompt("QA Engineer", PERSONA_QA, TASK_HEALTH_QA,
                                 scan_context, "result, verdict, findings[]", run_ctx),
                    label="qa-engineer-scan",
                    phase="Intake",
                    schema=HEALTH_SCHEMA,
                ),
                lambda: agent(
                    build_prompt("Security Reviewer", PERSONA_SECURITY, TASK_HEALTH_SECURITY,
                                 scan_context, "result, verdict, findings[]", run_ctx),
                    label="security-reviewer-scan",
                    phase="Intake",
                    schema=HEALTH_SCHEMA,
                ),
            ]
        )
        scans = compact([extract_json(r, fallback={}) for r in raw_scans])
        missing_scans = 3 - len([s for s in scans if has_meaningful_result(s)])
        if missing_scans:
            report["warnings"].append(str(missing_scans) + " health scanner(s) returned no usable result")
        triage_raw = await agent(
            build_prompt(
                "Product Manager", PERSONA_PM, TASK_TRIAGE,
                dict(scan_context, max_tickets=max_tickets, health_scans=scans),
                "result, verdict, tickets[] (id, priority, title, detail, acceptance)",
                run_ctx,
            ),
            label="product-manager-triage",
            phase="Intake",
            schema=TRIAGE_SCHEMA,
        )
        triage = extract_json(triage_raw, fallback={})
        tickets = [t for t in safe_list(triage, "tickets") if isinstance(t, dict)]
        if len(tickets) > max_tickets:
            log("Deferring " + str(len(tickets) - max_tickets) + " tickets to the next sweep")
            tickets = tickets[:max_tickets]
        requirements = {"tickets": tickets, "health_scans": scans}
        report["stages"]["intake"] = {"health_scans": scans, "triage": triage}
        if not tickets:
            log("Triage found nothing worth fixing; skipping build stages")
            report["status"] = "healthy"
            halted = True
    else:
        prd_context = dict(base_context)
        prd = extract_json(
            await agent(
                build_prompt("Product Manager", PERSONA_PM, TASK_PRD, prd_context,
                             "result, verdict, title, user_stories[], acceptance_criteria[], "
                             "non_goals[], open_questions[]", run_ctx),
                label="product-manager-prd",
                phase="Intake",
                schema=PRD_SCHEMA,
            ),
            fallback={},
        )
        if not safe_list(prd, "acceptance_criteria"):
            log("PRD came back without acceptance criteria; retrying once")
            prd = extract_json(
                await agent(
                    build_prompt("Product Manager", PERSONA_PM,
                                 TASK_PRD + "\nYour previous answer had no acceptance criteria. Fix that.",
                                 prd_context,
                                 "result, verdict, title, user_stories[], acceptance_criteria[], "
                                 "non_goals[], open_questions[]", run_ctx),
                    label="product-manager-prd-retry",
                    phase="Intake",
                    schema=PRD_SCHEMA,
                ),
                fallback={},
            )
        if auto_approve:
            log("auto_approve=true: PRD accepted without client review")
        else:
            answer = await human(
                PRD_REVIEW_PROMPT.substitute(
                    heading="DevCo PRD ready for review",
                    title=safe_get(prd, "title", "untitled"),
                    stories=bullets(safe_list(prd, "user_stories")),
                    criteria=bullets(safe_list(prd, "acceptance_criteria")),
                    questions=bullets(safe_list(prd, "open_questions")),
                ),
                schema=APPROVAL_SCHEMA,
                label="client-prd-approval",
                phase="Intake",
            )
            approved, feedback = approval_granted(answer)
            if not approved and feedback.strip() and feedback != "no answer from client":
                log("Client requested PRD changes; PM revises once")
                prd = extract_json(
                    await agent(
                        build_prompt("Product Manager", PERSONA_PM, TASK_PRD,
                                     dict(prd_context, previous_prd=prd, client_feedback=feedback),
                                     "result, verdict, title, user_stories[], acceptance_criteria[], "
                                     "non_goals[], open_questions[]", run_ctx),
                        label="product-manager-prd-revision",
                        phase="Intake",
                        schema=PRD_SCHEMA,
                    ),
                    fallback=prd,
                )
                answer = await human(
                    PRD_REVIEW_PROMPT.substitute(
                        heading="Revised DevCo PRD (final review)",
                        title=safe_get(prd, "title", "untitled"),
                        stories=bullets(safe_list(prd, "user_stories")),
                        criteria=bullets(safe_list(prd, "acceptance_criteria")),
                        questions=bullets(safe_list(prd, "open_questions")),
                    ),
                    schema=APPROVAL_SCHEMA,
                    label="client-prd-approval-revised",
                    phase="Intake",
                )
                approved, feedback = approval_granted(answer)
            if not approved:
                log("Client did not approve the PRD; halting before any code is written")
                report["status"] = "halted_by_client"
                report["client_feedback"] = feedback
                halted = True
        requirements = {"prd": prd}
        report["stages"]["intake"] = {"prd": prd}

    # ------------------------------------------------------------ Architecture
    phase("Architecture")
    lanes = []
    design = {}
    if not halted:
        design = extract_json(
            await agent(
                build_prompt("Architect / Tech Lead", PERSONA_ARCHITECT, TASK_DESIGN,
                             dict(base_context, requirements=requirements),
                             "result, verdict, stack, api_contract, data_model, "
                             "lanes[] (id, owner, title, scope, paths[])", run_ctx),
                label="architect-design",
                phase="Architecture",
                schema=DESIGN_SCHEMA,
            ),
            fallback={},
        )
        lanes = [lane for lane in safe_list(design, "lanes") if isinstance(lane, dict)]
        if not lanes:
            log("Architect returned no lanes; degrading to one full-stack lane per discipline")
            report["warnings"].append("architect produced no lanes; used default lanes")
            lanes = [
                {"id": "L-backend", "owner": "backend-engineer", "title": "Backend",
                 "scope": "All server-side work for the requirements", "paths": ["backend/"]},
                {"id": "L-frontend", "owner": "frontend-engineer", "title": "Frontend",
                 "scope": "All UI work for the requirements", "paths": ["frontend/"]},
                {"id": "L-devops", "owner": "devops-sre", "title": "Platform",
                 "scope": "CI, containers, env config", "paths": ["infra/", ".github/"]},
            ]
        if len(lanes) > MAX_LANES:
            log("Capping lanes at " + str(MAX_LANES) + "; " + str(len(lanes) - MAX_LANES) + " deferred")
            report["warnings"].append("lanes beyond cap deferred")
            lanes = lanes[:MAX_LANES]
        report["stages"]["architecture"] = design

    # ------------------------------------------------------------------- Build
    phase("Build")
    build_results = {}
    if not halted:
        by_owner = group_by_owner(lanes)
        shared = {
            "branch": branch,
            "stack": safe_get(design, "stack"),
            "api_contract": safe_get(design, "api_contract"),
            "data_model": safe_get(design, "data_model"),
            "requirements": requirements,
        }
        fields = "result, verdict, files_changed[], tests_added[], test_command, notes"
        owners = [owner for owner in LANE_OWNERS if by_owner[owner]]
        log("Building " + str(len(lanes)) + " lanes across: " + ", ".join(owners))
        raw_builds = await parallel([
            thunk for owner, thunk in [
                ("backend-engineer", lambda: agent(
                    build_prompt("Backend Engineer", PERSONA_BACKEND, TASK_LANE,
                                 dict(shared, lanes=by_owner["backend-engineer"]), fields, run_ctx),
                    label="backend-engineer",
                    phase="Build",
                    schema=LANE_RESULT_SCHEMA,
                )),
                ("frontend-engineer", lambda: agent(
                    build_prompt("Frontend Engineer", PERSONA_FRONTEND, TASK_LANE,
                                 dict(shared, lanes=by_owner["frontend-engineer"]), fields, run_ctx),
                    label="frontend-engineer",
                    phase="Build",
                    schema=LANE_RESULT_SCHEMA,
                )),
                ("devops-sre", lambda: agent(
                    build_prompt("DevOps / SRE", PERSONA_DEVOPS, TASK_LANE,
                                 dict(shared, lanes=by_owner["devops-sre"]), fields, run_ctx),
                    label="devops-sre",
                    phase="Build",
                    schema=LANE_RESULT_SCHEMA,
                )),
            ] if by_owner[owner]
        ])
        for owner, raw in zip(owners, raw_builds):
            parsed = extract_json(raw, fallback={})
            if not has_meaningful_result(parsed):
                report["warnings"].append(owner + " returned no usable build result")
                parsed = {"result": "no result", "verdict": "blocked"}
            build_results[owner] = parsed
        report["stages"]["build"] = build_results

    # ------------------------------------------------------------ Verify & Fix
    phase("Verify & Fix")
    open_defects = []
    fix_history = []
    if not halted:
        verify_context = {
            "branch": branch,
            "requirements": requirements,
            "design_summary": safe_get(design, "result"),
            "api_contract": safe_get(design, "api_contract"),
            "build_results": build_results,
        }
        review_fields = "result, verdict, defects[] (id, severity, owner, title, detail, repro)"
        # Stop condition: at most max_fix_rounds fix rounds (hard cap MAX_FIX_ROUNDS_CAP),
        # i.e. max_fix_rounds + 1 verification passes.
        for fix_round in range(max_fix_rounds + 1):
            raw_reviews = await parallel(
                [
                    lambda: agent(
                        build_prompt("QA Engineer", PERSONA_QA, TASK_QA_REVIEW,
                                     dict(verify_context, fix_round=fix_round), review_fields, run_ctx),
                        label="qa-engineer",
                        phase="Verify & Fix",
                        schema=REVIEW_SCHEMA,
                    ),
                    lambda: agent(
                        build_prompt("Security Reviewer", PERSONA_SECURITY, TASK_SECURITY_REVIEW,
                                     dict(verify_context, fix_round=fix_round), review_fields, run_ctx),
                        label="security-reviewer",
                        phase="Verify & Fix",
                        schema=REVIEW_SCHEMA,
                    ),
                ]
            )
            reviews = [extract_json(r, fallback={}) for r in raw_reviews]
            if not any(has_meaningful_result(r) for r in reviews):
                report["warnings"].append("both reviewers failed in round " + str(fix_round))
                open_defects = [{"id": "REVIEW-MISSING", "severity": "blocker",
                                 "owner": "devops-sre", "title": "Verification did not run",
                                 "detail": "QA and security produced no usable output."}]
                break
            defects, overflow = collect_defects(reviews)
            if overflow:
                log(str(overflow) + " additional low-priority defects deferred to backlog")
            open_defects = [d for d in defects if is_blocking(d)]
            fix_history.append({"round": fix_round, "reviews": reviews,
                                "blocking": len(open_defects), "total": len(defects)})
            log("Verification round " + str(fix_round) + ": " + str(len(open_defects))
                + " blocking of " + str(len(defects)) + " defects")
            if not open_defects or fix_round >= max_fix_rounds:
                break
            by_owner_defects = group_by_owner(open_defects)
            fix_fields = "result, verdict, files_changed[], tests_added[], test_command, notes"
            fix_owners = [owner for owner in LANE_OWNERS if by_owner_defects[owner]]
            log("Fix round " + str(fix_round + 1) + ": dispatching " + ", ".join(fix_owners))
            raw_fixes = await parallel([
                thunk for owner, thunk in [
                    ("backend-engineer", lambda: agent(
                        build_prompt("Backend Engineer", PERSONA_BACKEND, TASK_FIX,
                                     dict(verify_context, defects=by_owner_defects["backend-engineer"]),
                                     fix_fields, run_ctx),
                        label="backend-engineer-fix",
                        phase="Verify & Fix",
                        schema=LANE_RESULT_SCHEMA,
                    )),
                    ("frontend-engineer", lambda: agent(
                        build_prompt("Frontend Engineer", PERSONA_FRONTEND, TASK_FIX,
                                     dict(verify_context, defects=by_owner_defects["frontend-engineer"]),
                                     fix_fields, run_ctx),
                        label="frontend-engineer-fix",
                        phase="Verify & Fix",
                        schema=LANE_RESULT_SCHEMA,
                    )),
                    ("devops-sre", lambda: agent(
                        build_prompt("DevOps / SRE", PERSONA_DEVOPS, TASK_FIX,
                                     dict(verify_context, defects=by_owner_defects["devops-sre"]),
                                     fix_fields, run_ctx),
                        label="devops-sre-fix",
                        phase="Verify & Fix",
                        schema=LANE_RESULT_SCHEMA,
                    )),
                ] if by_owner_defects[owner]
            ])
            fixes = compact([extract_json(r, fallback={}) for r in raw_fixes])
            fix_history[-1]["fixes"] = fixes
        report["stages"]["verify_and_fix"] = fix_history
        report["unresolved_blockers"] = open_defects

    # ----------------------------------------------------------------- Release
    phase("Release")
    if not halted:
        release = extract_json(
            await agent(
                build_prompt("DevOps / SRE", PERSONA_DEVOPS, TASK_RELEASE,
                             {"branch": branch, "requirements": requirements,
                              "build_results": build_results,
                              "unresolved_blockers": open_defects},
                             "result, verdict, branch, release_notes, run_instructions, deploy_steps",
                             run_ctx),
                label="devops-sre-release",
                phase="Release",
                schema=RELEASE_SCHEMA,
            ),
            fallback={"result": "release packaging failed", "verdict": "not_ready"},
        )
        ready = safe_get(release, "verdict").strip().lower() == "ready" and not open_defects
        ship = False
        if not ready:
            log("Release not ready (blockers remain or packaging failed); not shipping")
        elif auto_approve:
            ship = True
            log("auto_approve=true and verification clean: shipping")
        else:
            answer = await human(
                RELEASE_REVIEW_PROMPT.substitute(
                    branch=branch,
                    notes=safe_get(release, "release_notes", "(none)"),
                    run=safe_get(release, "run_instructions", "(none)"),
                    deploy=safe_get(release, "deploy_steps", "(none)"),
                ),
                schema=APPROVAL_SCHEMA,
                label="client-release-approval",
                phase="Release",
            )
            ship, ship_feedback = approval_granted(answer)
            if not ship:
                report["client_feedback"] = ship_feedback
        shipped = None
        if ship:
            shipped = extract_json(
                await agent(
                    build_prompt("DevOps / SRE", PERSONA_DEVOPS, TASK_SHIP,
                                 {"branch": branch, "release": release},
                                 "result, verdict, branch, release_notes, run_instructions, deploy_steps",
                                 run_ctx),
                    label="devops-sre-ship",
                    phase="Release",
                    schema=RELEASE_SCHEMA,
                ),
                fallback={"result": "ship step failed", "verdict": "failed"},
            )
        report["stages"]["release"] = {"package": release, "shipped": shipped}
        if shipped and has_meaningful_result(shipped) and safe_get(shipped, "verdict") != "failed":
            report["status"] = "shipped"
        elif ready:
            report["status"] = "ready_awaiting_ship"
        else:
            report["status"] = "needs_attention"

    # ----------------------------------------------------------- Retrospective
    phase("Retrospective")
    retro = extract_json(
        await agent(
            build_prompt(
                "Architect / Tech Lead (retrospective)", PERSONA_ARCHITECT, TASK_RETRO,
                {"branch": branch, "status": report["status"], "warnings": report["warnings"],
                 "requirements": requirements, "fix_history_summary": [
                     {"round": h.get("round"), "blocking": h.get("blocking"), "total": h.get("total")}
                     for h in fix_history
                 ], "unresolved_blockers": open_defects},
                "result, verdict, lessons[], playbook_updates[], skill_improvements[], "
                "next_maintenance_focus[]",
                run_ctx,
            ),
            label="tech-lead-retro",
            phase="Retrospective",
            schema=RETRO_SCHEMA,
        ),
        fallback={"result": "retro failed", "verdict": "unknown"},
    )
    report["stages"]["retrospective"] = retro
    report["skill_improvements"] = safe_list(retro, "skill_improvements")
    report["next_maintenance_focus"] = safe_list(retro, "next_maintenance_focus")
    if report["status"] == "running":
        report["status"] = "degraded"
    log("DevCo run finished with status " + report["status"])
    return report
