"""Dry-run the fullstack-devco-swarm on the real SwarmFlow engine — no model, no API key.

Every agent answer is scripted for the "Shelfie" demo brief (see brief.md), so you
can watch the whole company work in about a second before spending any tokens:
phases, parallel lanes, model routing, the QA/security fix loop, the human gates,
and the final run report.

Nothing is written to disk and no code is generated: this shows the *process*.
For a real build, follow README.md.

Usage (from the repository root, with jiuwenswarm installed):

    python examples/devco-demo/simulate.py                 # auto-approve the gates
    python examples/devco-demo/simulate.py --interactive   # you play the client
    python examples/devco-demo/simulate.py --mode maintain # a maintenance sweep
    python examples/devco-demo/simulate.py --bad-model     # watch a model fallback
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = (
    REPO_ROOT / "jiuwenswarm" / "resources" / "agent" / "workspace" / "skills"
    / "fullstack-devco-swarm" / "scripts" / "workflow.py"
)

try:
    from openjiuwen.agent_teams.workflow.engine.backends.mock import MockBackend
    from openjiuwen.agent_teams.workflow.engine.runner import run_workflow
except ImportError as exc:  # pragma: no cover - environment guard
    sys.exit(
        "This demo needs openjiuwen's SwarmFlow engine (installed with jiuwenswarm).\n"
        f"Import failed: {exc}"
    )

# Team model pool for the simulation (what config.yaml models.defaults would give you).
POOL = ["deepseek-chat", "qwen3-coder-plus", "deepseek-reasoner"]

ROLE_ICONS = {
    "product-manager": "PM ",
    "architect": "ARC",
    "tech-lead": "ARC",
    "backend-engineer": "BE ",
    "frontend-engineer": "FE ",
    "devops-sre": "OPS",
    "qa-engineer": "QA ",
    "security-reviewer": "SEC",
    "client": "YOU",
}


def icon(label: str) -> str:
    for prefix, tag in ROLE_ICONS.items():
        if label.startswith(prefix):
            return tag
    return "   "


# ---------------------------------------------------------------------------
# Scripted answers for the Shelfie demo
# ---------------------------------------------------------------------------

PRD = {
    "result": "PRD for Shelfie written to .devco/PRD.md",
    "verdict": "ready",
    "title": "Shelfie - book-club tracker (v1)",
    "user_stories": [
        "As a reader, I want to sign up and log in, so that my clubs and progress are mine",
        "As a reader, I want to create a club and share a join code, so that friends can join",
        "As a member, I want to add books to the club shelf, so that we have candidates",
        "As a member, I want to vote once per round, so that the club picks fairly",
        "As the owner, I want to close a round, so that the winner becomes 'currently reading'",
        "As a member, I want to post my progress, so that the club sees who is where",
    ],
    "acceptance_criteria": [
        "Given a new email, when I sign up, then I am logged in and see an empty club list",
        "Given a valid join code, when I join, then the club appears in my list",
        "Given an open round, when I vote twice, then the second vote replaces the first",
        "Given I am not the owner, when I try to close a round or delete a book, then I get 403",
        "Given progress 0-100, when I save it, then every member sees it on the club page",
        "Given a fresh clone, when I run docker compose up, then the app is on localhost:8080",
    ],
    "non_goals": ["email delivery", "payments", "social login", "mobile apps"],
    "open_questions": ["assumption: join codes never expire in v1"],
}

DESIGN = {
    "result": "Design in .devco/DESIGN.md, contract in .devco/api/openapi.yaml, layout scaffolded",
    "verdict": "ready",
    "stack": "FastAPI + SQLModel/SQLite + React/TS (Vite) + Docker Compose (as requested)",
    "api_contract": ".devco/api/openapi.yaml - /auth/*, /clubs, /clubs/{id}/books, "
                    "/clubs/{id}/rounds, /clubs/{id}/progress",
    "data_model": "User, Club(owner_id, join_code), Membership, Book, Round, Vote(unique round+user), Progress",
    "lanes": [
        {"id": "L1", "owner": "backend-engineer", "title": "Auth + users",
         "scope": "signup/login, password hashing, JWT cookies", "paths": ["backend/app/auth/"]},
        {"id": "L2", "owner": "backend-engineer", "title": "Clubs, books, rounds, votes, progress",
         "scope": "all club endpoints + owner checks", "paths": ["backend/app/clubs/"]},
        {"id": "L3", "owner": "frontend-engineer", "title": "Auth screens + club list",
         "scope": "login/signup/join pages", "paths": ["frontend/src/auth/", "frontend/src/clubs/"]},
        {"id": "L4", "owner": "frontend-engineer", "title": "Club page",
         "scope": "shelf, voting, progress bars", "paths": ["frontend/src/club/"]},
        {"id": "L5", "owner": "devops-sre", "title": "Platform",
         "scope": "Dockerfiles, compose, CI, .env.example", "paths": ["infra/", ".github/", "docker-compose.yml"]},
    ],
}

BUILD = {
    "backend-engineer": {"result": "Auth and club APIs implemented to contract", "verdict": "done",
                         "files_changed": ["backend/app/auth/routes.py", "backend/app/clubs/routes.py"],
                         "tests_added": ["backend/tests/test_auth.py", "backend/tests/test_clubs.py"],
                         "test_command": "pytest -q backend"},
    "frontend-engineer": {"result": "Auth, club list and club page built with all 4 UI states",
                          "verdict": "done",
                          "files_changed": ["frontend/src/club/ClubPage.tsx", "frontend/src/auth/Login.tsx"],
                          "tests_added": ["frontend/src/club/ClubPage.test.tsx"],
                          "test_command": "npm --prefix frontend test"},
    "devops-sre": {"result": "Compose stack, CI workflow and .env.example added", "verdict": "done",
                   "files_changed": ["docker-compose.yml", ".github/workflows/ci.yml"],
                   "tests_added": [], "test_command": "docker compose up -d && curl localhost:8080/health"},
}

HEALTH = {
    "devops-sre-scan": {"result": "2 outdated deps, CI green", "verdict": "issues",
                        "findings": [{"severity": "major", "area": "deps", "title": "fastapi 2 minors behind",
                                      "evidence": "pip list --outdated"}]},
    "qa-engineer-scan": {"result": "1 flaky test", "verdict": "issues",
                         "findings": [{"severity": "major", "area": "tests",
                                       "title": "test_close_round flaky (timing)", "evidence": "3/20 runs fail"}]},
    "security-reviewer-scan": {"result": "no new issues", "verdict": "pass", "findings": []},
}

TRIAGE = {"result": "2 tickets this sweep, 0 deferred", "verdict": "ok", "tickets": [
    {"id": "T-1", "priority": "P1", "title": "Fix flaky test_close_round",
     "detail": "freeze time in test", "acceptance": "20/20 runs pass"},
    {"id": "T-2", "priority": "P2", "title": "Bump fastapi + starlette",
     "detail": "patch-level upgrade", "acceptance": "tests pass on new versions"},
]}


def make_reviewer(name: str):
    """First verification round finds real problems; the re-check passes."""
    first = {
        "qa-engineer": {"result": "5/6 criteria pass", "verdict": "fail", "defects": [{
            "id": "QA-1", "severity": "blocker", "owner": "backend-engineer",
            "title": "Second vote is stored as an extra vote instead of replacing the first",
            "detail": "Criterion 3 fails: vote counts go to 2 for one member",
            "repro": "POST /clubs/1/rounds/1/votes twice as the same user"}]},
        "security-reviewer": {"result": "authz gap found", "verdict": "fail", "defects": [{
            "id": "SEC-1", "severity": "major", "owner": "backend-engineer",
            "title": "DELETE /clubs/{id}/books/{book} has no owner check",
            "detail": "Any member can delete books (broken access control)",
            "repro": "log in as non-owner member, send DELETE"}]},
    }[name]
    clean = {"result": "all criteria pass, regression tests added", "verdict": "pass", "defects": []}
    calls = {"n": 0}

    def reply(*_args):
        calls["n"] += 1
        return first if calls["n"] == 1 else clean

    return reply


def gate(label: str, interactive: bool):
    def reply(prompt, *_args):
        if not interactive:
            print(f"   YOU {label:<30} -> approved (auto; use --interactive to decide yourself)")
            return {"approved": True, "feedback": ""}
        print("\n" + "=" * 72 + f"\n[{label}] the swarm is asking YOU (the client):\n")
        print(prompt.strip())
        answer = input("\nApprove? [y/N] (anything else = feedback): ").strip()
        print("=" * 72)
        if answer.lower() in ("y", "yes"):
            return {"approved": True, "feedback": ""}
        return {"approved": False, "feedback": answer or "rejected"}
    return reply


MAINTAIN_OVERRIDES = {
    "architect-design": {"result": "2 tickets mapped to 2 lanes", "verdict": "ready",
                         "stack": "unchanged", "api_contract": "unchanged", "data_model": "unchanged",
                         "lanes": [
                             {"id": "T-1", "owner": "backend-engineer", "title": "Fix flaky test_close_round",
                              "scope": "freeze time in the test", "paths": ["backend/tests/"]},
                             {"id": "T-2", "owner": "devops-sre", "title": "Bump fastapi + starlette",
                              "scope": "update lockfile, rebuild image", "paths": ["backend/pyproject.toml",
                                                                                   "backend/uv.lock"]},
                         ]},
    "backend-engineer": {"result": "test_close_round now uses a frozen clock; 20/20 runs pass",
                         "verdict": "done", "files_changed": ["backend/tests/test_rounds.py"],
                         "tests_added": [], "test_command": "pytest -q backend --count 20"},
    "devops-sre": {"result": "fastapi/starlette upgraded, image rebuilt, CI green", "verdict": "done",
                   "files_changed": ["backend/pyproject.toml", "backend/uv.lock"],
                   "tests_added": [], "test_command": "pytest -q backend"},
    "qa-engineer": {"result": "both tickets meet their acceptance lines", "verdict": "pass", "defects": []},
    "security-reviewer": {"result": "upgrade closes 2 advisories, nothing new", "verdict": "pass",
                          "defects": []},
    "devops-sre-release": {"result": "Maintenance release packaged", "verdict": "ready",
                           "branch": "devco/maintain",
                           "release_notes": "Fix flaky round test; patch-level framework upgrade.",
                           "run_instructions": "unchanged", "deploy_steps": "open a pull request"},
    "tech-lead-retro": {"result": "Playbook updated", "verdict": "done",
                        "lessons": ["Tests that touch time must use a frozen clock"],
                        "playbook_updates": ["Add 'freeze time in tests' to conventions"],
                        "skill_improvements": [], "next_maintenance_focus": ["coverage of the progress API"]},
}


def fixtures(interactive: bool, mode: str = "build") -> dict:
    base = _build_fixtures(interactive)
    if mode == "maintain":
        base.update(MAINTAIN_OVERRIDES)
    return base


def _build_fixtures(interactive: bool) -> dict:
    return {
        "product-manager-prd": PRD,
        "product-manager-prd-revision": dict(PRD, result="PRD revised per client feedback"),
        "client-prd-approval": gate("PRD approval", interactive),
        "client-prd-approval-revised": gate("revised PRD approval", interactive),
        "architect-design": DESIGN,
        **BUILD,
        **HEALTH,
        "product-manager-triage": TRIAGE,
        "qa-engineer": make_reviewer("qa-engineer"),
        "security-reviewer": make_reviewer("security-reviewer"),
        "backend-engineer-fix": {"result": "QA-1: unique (round, user) + upsert; SEC-1: owner check",
                                 "verdict": "done", "files_changed": ["backend/app/clubs/routes.py"],
                                 "tests_added": ["backend/tests/test_votes_replace.py",
                                                 "backend/tests/test_book_delete_authz.py"],
                                 "test_command": "pytest -q backend"},
        "devops-sre-release": {"result": "Release packaged", "verdict": "ready", "branch": "devco/build",
                               "release_notes": "Shelfie v1: accounts, clubs, shelf, voting, progress.",
                               "run_instructions": "cp .env.example .env && docker compose up -> localhost:8080",
                               "deploy_steps": "open a pull request devco/build -> main"},
        "client-release-approval": gate("release approval", interactive),
        "devops-sre-ship": {"result": "Pull request opened from devco/build", "verdict": "done"},
        "tech-lead-retro": {"result": "Playbook updated", "verdict": "done",
                            "lessons": ["Votes need a DB uniqueness constraint, not just an API check",
                                        "Every mutating club endpoint needs an owner/member check test"],
                            "playbook_updates": ["Add 'authz test per mutating endpoint' to backend DoD"],
                            "skill_improvements": ["Have the architect list authz rules per endpoint in DESIGN.md"],
                            "next_maintenance_focus": ["dependency upgrades", "flaky tests"]},
    }


class NarratingBackend(MockBackend):
    """Mock backend with a model pool that prints each call as it happens."""

    def model_pool_names(self):
        return POOL

    async def run(self, prompt, opts, schema_json, **kwargs):  # kwargs differ across engine versions
        label = opts.get("label", "?")
        target = opts.get("model") or "team default"
        if opts.get("agent_type"):
            target = opts["agent_type"] + " CLI / " + target
        print(f"   {icon(label)} {label:<30} model: {target}")
        return await super().run(prompt, opts, schema_json, **kwargs)


def show_log(line: str) -> None:
    """Engine diagnostics: only surface lint warnings about the workflow script."""
    if line.startswith("[lint]"):
        print(f"   !!! {line}")


def show_progress(event) -> None:
    """Render SwarmFlow progress events: phase headers and workflow log lines."""
    kind = getattr(event, "kind", "")
    if kind == "phase" and event.phase:
        print(f"\n== {event.phase} " + "=" * max(4, 66 - len(event.phase)))
    elif kind == "log" and event.message:
        print(f"   ... {event.message}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interactive", action="store_true", help="answer the client gates yourself")
    parser.add_argument("--mode", choices=["build", "maintain"], default="build")
    parser.add_argument("--bad-model", action="store_true",
                        help="route QA/security to a model that is not in the pool, to see the fallback")
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW), help="path to the skill's workflow.py")
    opts = parser.parse_args()

    args = {
        "mode": opts.mode,
        "request": "Build Shelfie, a small book-club tracker (see brief.md)" if opts.mode == "build" else "",
        "project_dir": "/home/you/shelfie",
        "stack": "FastAPI + SQLite + React/Vite + Docker Compose",
        "auto_approve": opts.mode == "maintain",
        "models": {"default": "deepseek-chat", "engineering": "qwen3-coder-plus",
                   "review": "not-a-real-model" if opts.bad_model else "deepseek-reasoner"},
    }
    print(f"\nDevCo simulation - mode={opts.mode} - workflow: {opts.workflow}\n")
    report = asyncio.run(run_workflow(
        opts.workflow, args=args, backend=NarratingBackend(fixtures=fixtures(opts.interactive, opts.mode)),
        log_sink=show_log, progress_sink=show_progress,
    ))

    print("\n" + "-" * 72)
    print(f"STATUS: {report['status']}")
    print("Model plan:")
    for role, entry in report.get("model_plan", {}).items():
        print(f"   {role:<18} {entry['agent_type'] + ' / ' if entry['agent_type'] else ''}"
              f"{entry['model'] or 'team default'}")
    if report.get("model_fallbacks"):
        print("Fallbacks:")
        for f in report["model_fallbacks"]:
            print(f"   {f['label']}: {f['error'][:90]}")
    for h in report.get("stages", {}).get("verify_and_fix", []):
        print(f"Verify round {h['round']}: {h['blocking']} blocking / {h['total']} defects")
    retro = report.get("stages", {}).get("retrospective", {})
    for lesson in retro.get("lessons", []):
        print(f"Lesson -> playbook: {lesson}")
    if report.get("warnings"):
        print("Warnings:", json.dumps(report["warnings"], ensure_ascii=False))
    print("-" * 72)


if __name__ == "__main__":
    main()
