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

    def __init__(self, handlers=None, human_answers=None, rejected_models=()):
        self.events: list[tuple] = []
        self.options: list[tuple[str, dict]] = []
        self.rejected_models = set(rejected_models)
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
            self.options.append((label, dict(options or {})))
            if options and options.get("model") in self.rejected_models:
                raise RuntimeError("model not in the model pool")
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


def test_model_routing_precedence_role_over_group_over_default(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {
            "request": "x", "auto_approve": True,
            "models": {"default": "base-model", "engineering": "coder-model",
                       "frontend": "ui-model", "Security": "sec-model"},
            "agent_types": {"backend": "codex"},
        },
    )
    plan = report["model_plan"]
    assert plan["product-manager"]["model"] == "base-model"
    assert plan["backend-engineer"] == {"model": "coder-model", "agent_type": "codex"}
    assert plan["frontend-engineer"]["model"] == "ui-model"
    assert plan["devops-sre"]["model"] == "coder-model"
    assert plan["security-reviewer"]["model"] == "sec-model"
    assert plan["qa-engineer"]["model"] == "base-model"
    sent = dict(rt.options)
    assert sent["frontend-engineer"] == {"model": "ui-model"}
    assert sent["backend-engineer"] == {"model": "coder-model", "agent_type": "codex"}
    assert sent["security-reviewer"] == {"model": "sec-model"}
    assert report["model_fallbacks"] == []


def test_no_routing_sends_no_options(monkeypatch):
    _report, rt = _run(monkeypatch, {"request": "x", "auto_approve": True})
    assert all(opts == {} for _label, opts in rt.options)


def test_rejected_model_falls_back_to_team_default(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "x", "auto_approve": True, "models": {"planning": "missing-model"}},
        rejected_models={"missing-model"},
    )
    assert report["status"] == "shipped"
    fallback_labels = {f["label"] for f in report["model_fallbacks"]}
    assert {"product-manager-prd", "architect-design", "tech-lead-retro"} <= fallback_labels
    retried = [opts for label, opts in rt.options if label == "architect-design"]
    assert retried == [{"model": "missing-model"}, {}]
    assert any("fell back" in w for w in report["warnings"])


def test_available_models_filters_unknown_names_and_keys(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "x", "auto_approve": True,
         "models": json.dumps({"default": "good", "review": "typo-model", "intern": "x"}),
         "available_models": "good, other"},
    )
    plan = report["model_plan"]
    assert plan["qa-engineer"]["model"] == ""
    assert plan["backend-engineer"]["model"] == "good"
    assert any("typo-model" in w for w in report["warnings"])
    assert any("intern" in w for w in report["warnings"])
    assert dict(rt.options)["qa-engineer"] == {}


def test_external_agent_falls_back_to_cli_default_model_then_team_default(monkeypatch):
    report, rt = _run(
        monkeypatch,
        {"request": "x", "auto_approve": True,
         "models": {"backend": "openai-only-model"}, "agent_types": {"backend": "claude"}},
        rejected_models={"openai-only-model"},
    )
    attempts = [opts for label, opts in rt.options if label == "backend-engineer"]
    assert attempts == [{"model": "openai-only-model", "agent_type": "claude"}, {"agent_type": "claude"}]
    assert report["status"] == "shipped"
    assert len([f for f in report["model_fallbacks"] if f["label"] == "backend-engineer"]) == 1


def test_runs_on_real_swarmflow_engine_with_model_pool():
    """End-to-end on openJiuwen's SwarmFlow engine (offline mock backend)."""
    runner = pytest.importorskip("openjiuwen.agent_teams.workflow.engine.runner")
    mock = pytest.importorskip("openjiuwen.agent_teams.workflow.engine.backends.mock")

    calls: list[tuple] = []

    class PoolBackend(mock.MockBackend):
        def model_pool_names(self):
            return ["deepseek-chat", "qwen3-coder"]

        async def run(self, prompt, opts, schema_json, *, call_key=None):
            calls.append((opts.get("label"), opts.get("model"), opts.get("agent_type")))
            return await super().run(prompt, opts, schema_json, call_key=call_key)

    review = {"result": "review", "verdict": "pass", "defects": []}
    fixtures = {
        "product-manager-prd": {"result": "prd", "verdict": "ready", "title": "Todo",
                                "user_stories": ["s"], "acceptance_criteria": ["c"]},
        "architect-design": {"result": "d", "verdict": "ready", "stack": "fastapi",
                             "lanes": [{"id": "L1", "owner": "backend-engineer", "paths": ["backend/"]}]},
        "backend-engineer": {"result": "built", "verdict": "done"},
        "qa-engineer": review,
        "security-reviewer": review,
        "devops-sre-release": {"result": "pkg", "verdict": "ready", "release_notes": "n"},
        "devops-sre-ship": {"result": "pr", "verdict": "done"},
        "tech-lead-retro": {"result": "retro", "verdict": "done"},
    }
    args = {"request": "todo app", "project_dir": "/srv/app", "auto_approve": True,
            "models": {"default": "deepseek-chat", "engineering": "qwen3-coder", "review": "not-in-pool"}}
    logs: list[str] = []
    report = asyncio.run(runner.run_workflow(
        str(WORKFLOW), args=args, backend=PoolBackend(fixtures=fixtures), log_sink=logs.append,
    ))

    assert report["status"] == "shipped"
    assert not [line for line in logs if "[lint]" in line]
    assert ("backend-engineer", "qwen3-coder", None) in calls
    assert ("architect-design", "deepseek-chat", None) in calls
    # "not-in-pool" is rejected by the engine and retried on the team default.
    assert ("qa-engineer", None, None) in calls
    assert {f["label"] for f in report["model_fallbacks"]} == {"qa-engineer", "security-reviewer"}
