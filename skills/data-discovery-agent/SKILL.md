---
name: data-discovery-agent
description: >
  Reusable skill for Stack AI Rewire, Assignment: AI-Native Data Discovery. Runs all stages
  of AI/DS data discovery: locate, catalog and assess the feasibility of internal and
  external data sources for a business problem, before any pipeline is built. Works for
  any use case written to the use-case contract (use_cases/<ID>_*.json + brief + internal
  estate). Steps 0–2b set up tooling, frame the use case, run planning and scouting, and
  suggest external sources. Steps 3–5 cover profiling, risk assessment, the memo, and
  sign-off. Learner gaps G1–G7 are implemented between Steps 2b and 3.
---

# AI-Native Data Discovery: Assignment Runner (Steps 0–5)

You are Claude, running the first steps of **Stack AI Rewire, Assignment: AI-Native Data
Discovery** in Claude Code, against the learner's copy of this repo. The repo
contains a multi-agent discovery system (`discovery_agent/`): Planner → Scout (internal catalog,
wiki, external register) → **candidate gate, where the human adds dataset links (any URL)** →
Profiler (one per source) → deterministic rules → Risk Assessor → Memo Writer, then a human review gate.

This skill gets a use case ready, checks the tooling, runs **plan + scout**, and suggests external
sources for the needs that remain unmet (Step 2b). Profiling, red-flag assessment, the feasibility
memo and the learner gaps are done in a normal Claude Code session, guided by `README.md`.

The skill is **use-case agnostic**. UC1 (air quality and traffic) and UC2 (ice-cream sales, weather and holidays) ship with
the repo, but any business problem written to the contract below runs the same way.

## Required input
- `use_cases/<ID>_<slug>.json`: the machine-readable use case (windows, needs, grains, geography).
  Contract: `use_cases/_TEMPLATE_use_case.json`.
- `use_cases/<ID>_<slug>.md`: the business brief: problem, decisions supported, scope, out of scope.
- `internal/<ID>_<client>/catalog_export.json` + `internal/<ID>_<client>/wiki/*.md`: the client's
  internal catalog export and documentation (metadata only, never data values).
- `config/external_sources_register.json`: the external sources the client has agreements for or
  has approved, tagged with the use case id.
- **Dataset links** (any https URL): supplied by the human at the candidate gate, from their own
  search or accepted from the Step 2b suggestions. For UC1 and UC2, README.md section 4 lists links
  whose expected assessment is known.
- **The learner's search script** `scripts/web_search.py` for Step 2b. It is not provided: the learner
  generates it with Claude Code (Assignment Task 3; the prompt is in README.md, section 4, "Suggest
  sources (Step 2b)"). Claude Code's built-in `WebSearch` does not work with the gateway key, so do not
  use it. If the script is missing, fails, or returns no citations, stop at Step 2b and tell the learner
  to generate or fix it. Do not write suggestions without search results.
- `config/allowlist.json`, `config/red_flags.json`, `config/settings.json`: provided. Do not loosen
  the allowlist or the caps to make a run pass.
- Gateway credentials in the environment: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_MODEL`. Never print, log or commit the token.

## Repo scaffold this skill produces
```
.
├── use_cases/<ID>_*.json, <ID>_*.md         <- provided, or written by you in Step 1 (new use case)
├── internal/<ID>_<client>/                  <- provided, or assembled in Step 1 (new use case)
├── outputs/<ID>/
│   ├── use_case_validation.txt              <- Step 1
│   ├── search_plan.json                     <- Step 2 (Planner)
│   ├── candidates.json                      <- Step 2 (Scout)
│   ├── trace.jsonl, transcripts/            <- Step 2 (evidence of every LLM/tool/HTTP call)
│   ├── run_summary.json                     <- Step 2 (tokens, tool calls, warnings)
│   ├── links.json                           <- Step 2 (copy of the prescribed links) and Step 2b (accepted suggestions appended): the ONE links file
└── outputs/artifacts/step0_checks.md        <- Step 0
```
Everything after `candidates.json` (records/, rule_flags.json, risk_assessment.json,
discovery_results.json, feasibility_memo.md) is produced later, outside this skill.

---

## Step 0: Set up and check the tooling (no LLM calls)
1. If no environment is active: `python3 -m venv .venv && source .venv/bin/activate`, then
   `pip install -r requirements.txt`.
2. Check that the gateway variables are **set**, without printing their values:
   `python -c "import os;print({k: bool(os.environ.get(k)) for k in ['ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_MODEL']})"`.
   If any is `False`, stop and tell the learner which one. Do not ask them to paste the token.
3. Run the offline tests: `python -m pytest tests/ -q`. `tests/test_tools_offline.py` and
   `tests/test_agent_loop.py` must pass. `tests/test_learner_gaps.py` is **expected to fail** until
   the learner implements G1, G3, G4, G5 and G6. Report which gap tests fail; do not implement them here.
4. Smoke-test the tools without the LLM:
   - `python -m discovery_agent tool search_internal_catalog '{"query": "<a need from the brief>"}' --use-case <ID>`
   - `python -m discovery_agent tool inspect_dataset_link '{"url": "https://archive.ics.uci.edu/dataset/360/air+quality"}' --use-case <ID>`
   - `python -m discovery_agent tool list_external_register '{}' --use-case <ID>`
   Each must return JSON, not a traceback. A `DOMAIN_NOT_ALLOWLISTED` result is the guardrail
   working, not a bug.
5. Write `outputs/artifacts/step0_checks.md`: test results (pass/fail counts per file), the tool
   smoke results (one line each), and the model id in use. Never write the token.

## Step 1: Frame the use case against the contract
**Existing use case** (UC1 or UC2, where `use_cases/<ID>_*.json`
and `internal/<ID>_*/` already exist): check that the files exist, then do item 4 and item 5 below.
Do not rewrite a contract that someone else wrote. If item 4 fails, report the error and ask the
learner before you change any input.

**New use case** (the learner gives you a business problem): write the inputs, do not invent data.
1. Copy `use_cases/_TEMPLATE_use_case.json` to `use_cases/<ID>_<slug>.json` and fill every field:
   - `windows`: one per analysis period, with ISO dates and a purpose. Do not use a single
     open-ended window to dodge coverage checks.
   - `needs`: one row per data need, in business words, with `priority` (must/should/could),
     `min_grain` (one of `minute, 15min, 30min, hourly, daily, weekly, monthly, quarterly, annual,
     event, static`) and the `windows` it applies to. Aim for 5–12 needs. Split compound needs.
   - `as_of`: the date the discovery is valid for. It drives staleness checks.
2. Write `use_cases/<ID>_<slug>.md` with the same sections as the UC1 brief: business problem,
   decisions supported, scope, needs table, where to look, out of scope.
3. Internal estate: if the learner has a real catalog export, convert it to the
   `catalog_export.json` entry shape used in `internal/UC1_valdena_health/` (null where the catalog
   holds nothing, never a guess), and put the documentation pages in `wiki/` with the same front
   matter (`page_id`, `title`, `owner`, `last_edited`). Add the client's approved external sources
   to `config/external_sources_register.json` with the new use-case id and their real
   `agreement_status`. If the learner has no internal estate, stop and ask. Do not fabricate one.
4. Validate: `python -m discovery_agent validate-use-case <ID> | tee outputs/<ID>/use_case_validation.txt`.
   Fix every error it reports in the inputs, not in the validator.
5. Show the learner the needs table (id, name, priority, min_grain, windows) and the windows.
   **Pause** (for a human learner in an interactive session; in a non-interactive run, write the table and stop). Wait for them to confirm or change it. The needs list decides what the agents
   search for and what the rules check, so a wrong need here gives wrong verdicts later.

## Step 2: Plan and scout, then stop at the candidate gate
1. Run: `python -m discovery_agent run --use-case <ID> --stop-after scout --no-input`.
   This runs the Planner (search plan per need, including hints on what external data to link) and
   the Scout (catalog, wiki and register search), and writes `search_plan.json`, `candidates.json`, `trace.jsonl` and `transcripts/`.
2. If the run fails, read the last events in `outputs/<ID>/trace.jsonl` and the failing agent's
   transcript before changing anything. Fix the cause (credentials, model id, a prompt, a tool
   bug) and re-run. Do not raise `max_turns` or the HTTP caps as a first response.
3. Review `candidates.json` against the needs, and give the learner a table:
   need id → candidate source ids → `unmet_needs`. Then name, from the trace:
   - needs with no candidate, or only one;
   - internal entries the Scout opened but did not read the wiki backlinks for;
   - internal searches that returned nothing and were not rephrased.
4. Show the learner the `unmet_needs` and the planner's `external_data_hints`. If a need is already met
   by internal or register sources, say so. Then ask: **do you already have dataset links that fill any
   of these needs?** For UC1, name the three prescribed links in README.md section 4; UC2 has none. Ask whether
   the learner will use them. Each link needs need ids and windows. If the learner uses them, copy
   `links/UC1_example_links.json` to `outputs/<ID>/links.json` once, only if that file does not exist yet (for UC2, start from `[]`). Never copy over it: it may already hold accepted suggestions. The Chicago
   link in README.md section 4 is one the learner accepts on purpose: its refusal is the finding. Claude
   does not make that decision for the learner. **STOP and wait for the reply.**
   Only then go to Step 2b.

## Step 2b: Suggest external sources (only for needs still unmet)
1. Only after the learner has answered Step 2, item 4. Check that `scripts/web_search.py` exists in the
   learner's repo. If it does not, **STOP**: ask the learner to generate it with Claude Code, using the
   prompt in README.md ("Suggest sources (Step 2b)"), and wait for it. Do not write the script yourself.
   Once it exists, search with it for up to **five** public datasets that could fill the unmet needs:
   `python scripts/web_search.py "<query>"`. Use the planner's `external_data_hints` as starting queries.
   Each result is a lead from a search model, not a verified source. Only a URL with a citation may be
   suggested, and each one still needs checking on its publisher's page.
2. For each suggestion, show the learner: publisher, exact URL (the dataset or record page, not a search
   page), need ids, coverage **as the page states it** (quote the page; write `"not stated"` if the page
   does not say), and what still needs checking (licence, population, access). Do not download data.
3. **STOP and wait.** For each suggestion the learner decides `accept`, `reject` or `revise` (with new
   need ids or windows), with a short reason. The learner may also add links they found. Never decide,
   and never write a reason, for the learner. Silence is not acceptance.
4. Record every decision and reason in `outputs/artifacts/decisions.md` under "Source suggestions". Append each
   accepted suggestion to `outputs/<ID>/links.json` (the same file as Step 2), in the shape of
   `links/_TEMPLATE_links.json`, with the learner's reason as `note`. Never overwrite the prescribed links.
   The **learner** writes `outputs/<ID>/gate_decisions.json` (`{"decisions": [{"url", "decision": "accept" or
   "reject", "reason"}]}`), one entry for every link in `links.json`, after inspecting each link themselves.
   If the learner asks you to write it, transcribe only the reasons they have dictated, word for word, and
   say so in `decisions.md`. Never write a reason the learner did not give. The pipeline refuses to profile
   a link without one.
5. For each accepted link, check its host is on `config/allowlist.json`:
   `python -m discovery_agent tool inspect_dataset_link '{"url": "<link>"}' --use-case <ID>`.
   If a host is refused, **STOP**: the learner decides whether to add it, with a G6 justification in
   `outputs/artifacts/decisions.md`. Do not add hosts yourself, and do not try an alternate URL. The Chicago host (`catalog.data.gov`) is refused by design: record that refusal as a finding. The Eurostat host waits for G6 in Task 6; re-run the inspection after it is added.

**Then stop.** Tell the learner the candidate list and accepted links are ready for review. Before profiling, the learner must implement gaps G1–G7 (see `README.md`). Once all gap tests pass (`python -m pytest tests/test_learner_gaps.py -q`), proceed to Step 3.

---

## Step 3: Profile and rule-check

After `outputs/<ID>/gate_decisions.json` exists with one entry per link and all gap tests pass:

1. Run: `python -m discovery_agent run --use-case <ID> --from-stage profile --links-file outputs/<ID>/links.json --no-input`.
   This runs one Profiler agent per source in parallel (up to 4). Each profiler reads the catalog record or the linked landing page, calls `inspect_dataset_link`, `fetch_licence_page`, `sample_data_file` and wiki tools, then writes `outputs/<ID>/records/<source_id>.json`.

2. For each record in `outputs/<ID>/records/`:
   - Check `tool_errors`. Any value above 0 means a tool call failed; read the transcript at `outputs/<ID>/transcripts/profiler__<source_id>.json` to find which tool and why. Fix the agent (prompt, tool, validator) and re-run with `--from-stage profile --stop-after profile --only <source_id> --links-file outputs/<ID>/links.json --no-input`. Never hand-edit the record.
   - Check `licence.found_in`: for dataset links it must be one of `"json-ld"`, `"html-link"`, `"html-text"`, or `null`. If it is null for a source that has a licence on its page, G1 extraction failed — fix and re-run.
   - Check `temporal.start`, `temporal.end`, `temporal.grain` against the wiki page or publisher's page. If the profiler read a probe date as a data date, the transcript will show it; fix the prompt and re-run.
   - Check `quality_notes` for any `NOT_IMPLEMENTED` string. This means a gap (G3 or G4) was not closed before profiling. Close the gap, re-run the failing profiler.

3. For refused dataset links (host not on `config/allowlist.json`): the profiler returns `access.reachable: false`. This is correct. Do not add the host to work around it; record the refusal under G6 in `outputs/artifacts/decisions.md`.

4. For JSON-stat API links (Eurostat-style): `sample_data_file` returns JSON-stat 2.0. `summarize_jsonstat` (G3) must parse `dataset["id"]`, `dataset["dimension"]` and `dataset["value"]` to extract dimension labels, year coverage, cell counts and missing cells. If G3 is not implemented when profiling runs, the profiler logs `NOT_IMPLEMENTED` and cannot decode dimensions; fix G3 and re-run that profiler.

5. Read `outputs/<ID>/rule_flags.json`: one entry per source with `flags` (list of `{code, evidence, raised_by}`) and `warnings` (rules that raised `NotImplementedError` because a G4 rule was not yet implemented). Every warning means a rule was skipped — close G4 and re-run `--from-stage assess` to apply the missing rules.

---

## Step 4: Assess and draft the memo

After all records have `tool_errors: 0` and no `NOT_IMPLEMENTED` in quality_notes, and no rule warnings in `rule_flags.json`:

1. Write verdict calibration rules in G5 first: edit `discovery_agent/prompts/risk_assessor.md`, section `## Verdict calibration`. Write ordered rules (stop at the first that matches) mapping red-flag codes and priorities to verdicts. Each rule names the flag code(s), the condition (e.g. need priority, whether other windows are served), and the resulting verdict. Run `python -m pytest tests/test_learner_gaps.py -k g5 -q` to verify the format.

2. Run: `python -m discovery_agent run --use-case <ID> --from-stage assess --no-input`.
   This runs the Risk Assessor (one pass over all records and rule flags) and the Memo Writer, writing `risk_assessment.json`, `discovery_results.json` and `feasibility_memo.md`.

3. Read `outputs/<ID>/risk_assessment.json`. For each source:
   - Every rule flag must be either kept in `flags` or moved to `dismissed_rule_flags` with a specific reason. A flag moved without a reason is a prompt failure; tighten G5 or the prompt and re-run from assess.
   - Judgement flags (agent-added, not rule-raised) must cite a quote or field from the record or the wiki.
   - The verdict must match the calibration rules you wrote. If it does not, add a tighter rule and re-run.

4. Read `outputs/<ID>/feasibility_memo.md`. Confirm it has all seven sections: executive summary, need coverage table, per-source assessments, red-flag register, conditions and owners, recommended next steps, open questions. If a section is missing or thin, fix the prompt and re-run from assess. Never add content by hand.

5. Write your review: `outputs/artifacts/review_<ID>.md`. For each source: state whether you agree with the verdict and name the flag or field you checked in the record or wiki. For open questions: answer what you can; defer the rest to named owners. At least one flag must be traced to a specific field in a record or a wiki page.

6. Write gate decisions: `outputs/<ID>/gate_decisions.json` (template: `links/_TEMPLATE_gate_decisions.json`). One entry per URL in `outputs/<ID>/links.json`. `decision` is `accept` or `reject`. `reason` is at least 20 characters in your own words, as you gave it at the gate. If you ask Claude to write this file, dictate the reasons word for word; Claude transcribes only what you say and notes it in `decisions.md`. If the use case has no external links (e.g. UC2), write `{"decisions": []}`.

---

## Step 5: Evaluate and hand off

1. Write your sign-off: `outputs/<ID>/signoff.json` (template: `outputs/artifacts/_TEMPLATE_signoff.json`):
   - `verdict`: `proceed`, `proceed_with_conditions`, or `stop`.
   - `conditions`: for `proceed_with_conditions`, at least one entry with `text`, `owner` and `due` (ISO date). Name who can resolve it and by when.
   - `agreements`: at least one entry with `source_id` (from `discovery_results.json`) and `reason`. Explain why you agree with the verdict for that source.
   - `overrides`: empty unless you overrule the agent verdict. Each override needs `source_id`, `agent_verdict`, `your_verdict` and `reason`.
   - `traced_conclusion`: `source_id` (from `discovery_results.json`), `record_field` (a dotted path that exists in that source's record, e.g. `temporal.start`), `could_change_if` (at least 20 characters). Check the field exists in the record before writing — `temporal.end` is null for open-ended sources and will fail the check; use `temporal.start` instead.

2. Run: `python -m discovery_agent check <ID>`. Fix every item it lists. It checks:
   - `gate_decisions.json` has one entry per link with a reason of at least 20 characters.
   - `signoff.json` is valid: verdict, conditions (if `proceed_with_conditions`), at least one agreement, and a `traced_conclusion` whose `record_field` exists in the named source's record.
   - Repeat until `problems: []`.

3. Check trace stats in `outputs/<ID>/run_summary.json`:
   - `tool_errors`: should be 0 after G3 and G7 fixes.
   - `http_refused`: count of host-not-allowlisted blocks. Each refused host must appear in `decisions.md` under G6, either added with justification or recorded as a deliberate refusal.
   - `llm_calls` and `input_tokens`: confirm the run stayed within the caps in `config/settings.json`. Do not raise the caps; if an agent looped, fix its prompt.

4. Document the G7 fix in `outputs/artifacts/decisions.md` under "G7: One agent failure, fixed at its cause":
   - **Symptom**: what the agent reported (e.g. `NOT_IMPLEMENTED`, wrong dates, missing dimension labels).
   - **Evidence**: transcript file and turn number where the failure appeared.
   - **Root cause**: which function, tool or prompt was wrong.
   - **Fix**: what you changed (file, function, what it now does).
   - **Re-run**: the exact `--from-stage ... --stop-after profile --only <source_id>` command.
   - **Before / after**: the `quality_notes` or field values before and after the fix.
   - **Decision this failure could affect**: which need or verdict depended on the broken output.

5. Confirm deliverables in `outputs/artifacts/`:
   - `step0_checks.md`: test results, smoke test results, model id.
   - `decisions.md`: Step 2b suggestion decisions, gate decisions (transcribed from learner), G6 allowlist changes with justifications, G7 before/after evidence.
   - `review_<ID>.md` for each use case: per-source verdict agreement, flags checked against records, open questions.
   - `outputs/<ID>/gate_decisions.json` and `outputs/<ID>/signoff.json` (in the use-case folder, not artifacts/).
   Run `python -m discovery_agent check <ID>` one final time to confirm `problems: []`.

---

## Reuse check findings (UC2, fresh session)

Gaps found when following this skill with only the skill file and README:

- **`scripts/web_search.py` is a missing input.** It is not provided in the repo. Step 2b.1 correctly stops and asks the learner to generate it using the prompt in README.md section 4. Record it as a missing input.
- **UC2 has no prescribed links.** The candidate gate produces no links file. Step 2b.4 appends accepted suggestions to `outputs/UC2/links.json` starting from `[]`. If no suggestion is accepted, `gate_decisions.json` is `{"decisions": []}` and Steps 3–4 profile only internal and register sources.
- **Steps 3–5 for UC2 follow the same commands as UC1**, substituting `UC2`. No use-case-specific changes are needed.

---

## Rules that hold in every step
- **Metadata first, then a capped sample, never the whole dataset.** Read schemas, descriptions,
  coverage and terms; `sample_data_file` may read the first part of a file. Do not download whole
  datasets or copy personal data into any output.
- **Provenance on every claim.** Every statement about a source names a tool call, URL, catalog
  field or wiki page.
- **Unknown stays unknown.** Never infer a licence, owner, refresh cadence or consent. Use null and
  list it under unknowns.
- **Guardrails are not obstacles.** A refused host, an expired vendor agreement or a restricted
  table is a finding to record, not something to work around.
- **The agents are the product.** When an output is wrong, fix the agent (prompt, tool, rule,
  validator) and re-run. Never hand-edit `candidates.json`, records or results to look right.
- **A suggestion is not a verified source.** Selecting it grants no host access and no permission to
  use the data. Keep the exact-host allowlist.

---

## Extending this file

Steps 3–5 above were written based on what the learner actually did for UC1 and UC2. If you use this skill with a new use case and find a step that cannot be followed as written, record what was missing and open a revision. The test: a fresh Claude session with only this file and the README can run Steps 0–5 for a new use case and get a comparable result.
