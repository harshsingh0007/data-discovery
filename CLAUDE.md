# Project instructions for Claude Code

This repo is a multi-agent data-discovery system (Stack AI Rewire assignment). Read `README.md` first. The reusable skill is `skills/data-discovery-agent/SKILL.md` (copy it to `.claude/skills/data-discovery-agent/SKILL.md` as the README explains).

- Python 3.10+, stdlib plus `anthropic` and `jsonschema`. Do not add dependencies without asking.
- Run `python -m pytest tests/ -q` after every change. `tests/test_learner_gaps.py` is the learner's acceptance suite. Do not edit or weaken those tests to make them pass.
- Never loosen the byte caps or the request budget in `config/settings.json` to make a run pass. Refusals are findings. Add hosts to `config/allowlist.json` only when the learner asks (gap G6): exact hosts, never a parent domain, each justified in `outputs/artifacts/decisions.md`.
- Never hand-edit files under `outputs/<ID>/` (candidates, records, results). Fix the agent (prompt, tool, rule, validator) and re-run from the right stage.
- Never print, log or commit `ANTHROPIC_AUTH_TOKEN`.
- Metadata only: do not download datasets or copy personal data into outputs.
- When the learner asks you to implement a gap (G1–G7), explain the design and the edge cases, and let them review the diff. They must be able to defend it.
- Suggested sources are claims to check, not verified sources. Never fill a suggestion's coverage or reason from memory, and never decide accept or reject for the learner.
- Stop and wait for the learner at each STOP in `SKILL.md`: the needs table, the dataset-link question, each suggestion's decision, and any refused host.
