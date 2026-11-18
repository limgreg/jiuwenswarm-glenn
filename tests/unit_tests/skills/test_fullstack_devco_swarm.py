"""Tests for the built-in ``fullstack-devco-swarm`` Swarm Skill.

The SwarmFlow runtime is replaced by an in-memory stub so the workflow's
control flow (modes, human gates, fix loop, degraded paths) can be exercised
without any model calls.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from jiuwenswarm.common.utils import DEFAULT_BUILTIN_SKILLS

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "jiuwenswarm" / "resources" / "agent" / "workspace" / "skills"
SKILL_DIR = SKILLS_ROOT / "fullstack-devco-swarm"
WORKFLOW = SKILL_DIR / "scripts" / "workflow.py"
VALIDATOR = SKILLS_ROOT / "swarmskill-creator" / "scripts" / "validate_swarmskill.py"


class _StubRuntime:
    """Minimal stand-in for the ``swarmflow`` facade."""

    def __init__(self, handlers=None, human_answers=None):
        self.events: list[tuple] = []
        self.handlers = handlers or {}
        self.human_answers = list(human_answers or [])

    def module(self) -> types.ModuleType:
        mod = types.ModuleType("swarmflow")
        mod.phase = lambda title: self.events.append(("phase", title))
        mod.log = lambda message: self.events.append(("log", message))
        mod.compact = lambda xs: [x for x in xs if x]

        async def parallel(thunks):
            results = []
            for thunk in thunks:
                try:
                    results.append(await thunk())
                except Exception:  # parallel never raises in SwarmFlow
                    results.append(None)
            return results

        async def human(prompt, *, schema=None, label=None, phase=None, options=None):
            self.events.append(("human", label, phase))
            return self.human_answers.pop(0) if self.human_answers else None

        async def agent(prompt, *, label=None, phase=None, schema=None, options=None):
            self.events.append(("agent", label, phase))
            assert "$" not in prompt.split("CONTEXT (JSON)")[0], "unsubstituted template var"
            handler = self.handlers.get(label)
            if handler is not None:
                return handler(prompt)
            return _default_reply(label, self)

        mod.parallel = parallel
        mod.human = human
        mod.agent = agent
        return mod

    def labels(self) -> list[str]:
        return [e[1] for e in self.events if e[0] in ("agent", "human")]


def _default_reply(label: str, rt: _StubRuntime):
    if label.startswith("product-manager-prd"):
        return {"result": "prd", "verdict": "ready", "title": "Todo",
                "user_stories": ["As a user I add todos"], "acceptance_criteria": ["todo persists"]}
    if label.endswith("-scan"):
        return {"result": "scan", "verdict": "issues",
                "findings": [{"severity": "major", "title": "outdated deps"}]}
    if label == "product-manager-triage":
        return {"result": "triage", "verdict": "ok", "tickets": [{"id": "T1", "title": "bump deps"}]}
    if label == "architect-design":
        return json.dumps({"result": "design", "verdict": "ready", "stack": "fastapi+react",
                           "lanes": [{"id": "L1", "owner": "backend", "paths": ["backend/"]},
                                     {"id": "L2", "owner": "Frontend dev", "paths": ["frontend/"]}]})
    if label in ("qa-engineer", "security-reviewer"):
        seen = sum(1 for e in rt.events if e[0] == "agent" and e[1] == label)
        if seen == 1:
            return {"result": "review", "verdict": "fail",
                    "defects": [{"id": "D1", "severity": "blocker", "owner": "frontend", "title": "crash"}]}
        return 'Report: {"result": "review", "verdict": "pass", "defects": []}'
    if label == "devops-sre-release":
        return {"result": "packaged", "verdict": "ready", "release_notes": "v1"}
    if label == "devops-sre-ship":
        return {"result": "PR opened", "verdict": "done"}
    if label == "tech-lead-retro":
        return {"result": "retro", "verdict": "done", "skill_improvements": ["x"],
                "next_maintenance_focus": ["deps"]}
    return {"result": "ok", "verdict": "done"}


def _run(monkeypatch, args, **runtime_kwargs):
    rt = _StubRuntime(**runtime_kwargs)
    monkeypatch.setitem(sys.modules, "swarmflow", rt.module())
    spec = importlib.util.spec_from_file_location("devco_workflow_under_test", WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = asyncio.run(module.run(args))
    json.dumps(report)  # result must be JSON-serializable
    return report, rt


def test_skill_is_default_builtin_and_present():
    assert "fullstack-devco-swarm" in DEFAULT_BUILTIN_SKILLS
    assert (SKILL_DIR / "SKILL.md").is_file()
    assert WORKFLOW.is_file()


def test_skill_passes_swarmskill_validator():
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(SKILL_DIR)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS]" in proc.stdout + proc.stderr


def test_build_mode_ships_after_fix_round(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "todo app", "project_dir": "/srv/app"},
        human_answers=[{"approved": True}, {"approved": True}],
    )
    assert report["status"] == "shipped"
    labels = rt.labels()
    assert labels.index("client-prd-approval") < labels.index("architect-design")
    assert "frontend-engineer-fix" in labels
    assert "backend-engineer-fix" not in labels
    assert labels[-1] == "tech-lead-retro"
    assert report["unresolved_blockers"] == []


def test_prd_rejected_twice_halts_before_code(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "todo app"},
        human_answers=[{"approved": False, "feedback": "add auth"},
                       {"approved": False, "feedback": "still no"}],
    )
    assert report["status"] == "halted_by_client"
    labels = rt.labels()
    assert "product-manager-prd-revision" in labels
    assert "architect-design" not in labels
    assert labels[-1] == "tech-lead-retro"


def test_maintain_mode_unattended_from_json_string(monkeypatch):
    report, rt = _run(monkeypatch, json.dumps({"mode": "maintain", "auto_approve": True}))
    assert report["mode"] == "maintain"
    assert report["status"] == "shipped"
    labels = rt.labels()
    assert {"devops-sre-scan", "qa-engineer-scan", "security-reviewer-scan"} <= set(labels)
    assert not any(e[0] == "human" for e in rt.events)


def test_maintain_mode_healthy_skips_build(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"mode": "maintain", "auto_approve": True},
        handlers={"product-manager-triage": lambda p: {"result": "ok", "verdict": "healthy", "tickets": []}},
    )
    assert report["status"] == "healthy"
    assert "architect-design" not in rt.labels()


def test_open_blockers_prevent_auto_ship(monkeypatch):
    report, rt = _run(monkeypatch, {"request": "x", "auto_approve": True, "max_fix_rounds": 0})
    assert report["status"] == "needs_attention"
    assert report["unresolved_blockers"]
    assert "devops-sre-ship" not in rt.labels()


def test_failed_agents_degrade_with_warnings(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "x", "auto_approve": True},
        handlers={"architect-design": lambda p: None,
                  "qa-engineer": lambda p: None,
                  "security-reviewer": lambda p: None},
    )
    assert report["status"] == "needs_attention"
    assert any("default lanes" in w for w in report["warnings"])
    assert report["unresolved_blockers"][0]["id"] == "REVIEW-MISSING"
    assert {"backend-engineer", "frontend-engineer", "devops-sre"} <= set(rt.labels())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("build", "build"), ("maintenance", "maintain"), ("", "build"), ("feature", "feature")],
)
def test_mode_normalization(monkeypatch, raw, expected):
    monkeypatch.setitem(sys.modules, "swarmflow", _StubRuntime().module())
    spec = importlib.util.spec_from_file_location("devco_workflow_modes", WORKFLOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.normalize_mode(raw, "some request") == expected
    assert module.normalize_mode("", "") == "maintain"
