# Execution Guardrails

## Resource Constraints

| Item | Limit | Reason |
|---|---|---|
| `max_parallel_teammates` | 3 | Matches the widest fan-out (3 health scanners, or 3 build owners) |
| `total_wall_clock_budget` | 60 min (build), 30 min (feature / maintain) | Use `timeout_seconds=3600` for cron team jobs |
| `total_token_budget` | Unbounded by default; set `swarmflow_budget` (e.g. 2,000,000) to cap it | Full builds are token-heavy; a team budget fails the run cleanly when it is hit |
| `max_lanes` | 12 | Keeps lanes reviewable and owner prompts within context |
| `max_fix_rounds` | default 2, hard cap 3 | Bounded verify → fix loop; prevents endless churn |
| `max_tickets` | default 5, hard cap 8 per sweep | Small maintenance batches stay reviewable; the rest go to the backlog |
| `max_defects_per_round` | 20 (blockers first) | Overflow is deferred and logged, never silently dropped |
| `prd_revision_rounds` | 1 | A second rejection halts the run |

## Behavioral Constraints

- **The Leader orchestrates only.** The Leader dispatches roles and assembles the report. The Leader does NOT write the PRD, design or code, and does NOT review.
- **Lane fences.** Each engineer edits only the paths in its own lanes. The API contract is read-only for engineers; a needed change is reported in `notes` and handled by the architect in the next run.
- **Pipeline integrity.** A stage never rewrites an upstream artifact, with one exception: the PM revises the PRD in response to client feedback.
- **Verification isolation.** QA and security review in parallel. Neither reads the other's report before submitting. Reviewers never patch code.
- **Contradiction handling.** When QA and security disagree on severity, both opinions are quoted verbatim in the report, and the stricter one gates the release. The Leader never mediates.
- **Git safety.** All work happens on the run branch, with one commit per lane or fix. No force-push, no history rewrite, no secrets or `.env` files committed.
- **Ship gate.** Shipping requires `client` approval, or `auto_approve` plus zero unresolved blockers. Unattended runs may open PRs or merge to non-production targets. A production deploy requires an explicit, pre-configured target documented in the playbook.
- **Self-improvement is proposed, not imposed.** The retro may rewrite the project playbook freely. Changes to this skill (`skill_improvements`) need user consent and are applied through `swarmskill-creator` MODIFY.

## Failure Handling

**(a) Teammate failure**

| Failure | Handling |
|---|---|
| PRD without acceptance criteria | One automatic retry with a corrective note, then continue |
| Client gives no answer or rejects twice | `halted_by_client`; no code is written; the retro still runs |
| A health scanner returns nothing | Warning; triage runs on the remaining scans |
| Architect returns no lanes | Default lanes (backend/, frontend/, infra/ + .github/), with a warning |
| A build owner returns nothing | Recorded as `blocked`; verification surfaces the gap |
| Both reviewers fail | Synthetic blocker `REVIEW-MISSING`; release is `not_ready` |
| Release packaging fails | `not_ready`; status `needs_attention` |
| Ship step fails | Status `ready_awaiting_ship`; the report includes the failure |
| Retro fails | Report status is kept; the playbook is unchanged; warning |
| Team token budget exhausted | The run fails as a whole (SwarmFlow semantics); rerun with a larger budget or a smaller scope |

Missing outputs always appear in the report's `warnings`. They are never silently omitted.

**(b) Input overscale and degraded modes**

- More than 12 lanes: the first 12 are built and the rest deferred to `.devco/BACKLOG.md` by the next maintain sweep.
- More than 20 defects in a round: the top 20 (blockers first) are routed and the rest deferred.
- More than `max_tickets` triaged tickets: the top N are worked and the rest stay in the backlog.
- A very large existing repo (feature mode): the architect limits lanes to the directories the feature touches.
- No `request` in build/feature mode: falls back to `maintain`.
- If a runtime has no SwarmFlow, the Leader follows [workflow.md](workflow.md) manually, dispatching team members with the inline personas.
