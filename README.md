# Assignment: AI-Native Data Discovery with Agents

**Stage covered:** the first step of every AI/DS project: find the data, before any pipeline is built.
**Motto:** *Locate, catalog and assess the feasibility of the data sources for a business problem, before any pipeline is built.*

You are given a working multi-agent system that does data discovery. It searches an internal catalog and wiki in plain language, checks the client's register of external sources and public APIs, and then takes **links to any external dataset you supply**: a repository page, a portal record (Kaggle, Zenodo, data.gov, Hugging Face ...), a data package, a statistics API or a raw file. For each source it works out what the data is, reads a small sample, summarises schema, freshness, ownership and licence, flags data-quality and access red flags, and drafts a feasibility memo saying whether each source is of any use to the project.

It works, but not well enough. Some tools are missing, some rules are not written, and the agents make mistakes you will find in their traces. Your job is to close those gaps, run it on two business problems, judge what it produces, and turn what you learned into a skill file that works for **any** use case.

---

## Where things are in your bundle

```
<bundle>/
  Stack AI Rewire - DS - Data Discovery - Assignment Doc.docx    what to build and deliver
  Helper Guide.docx                                              setup, links, commands, hints, checklist
  Stack AI Rewire - DS - Data Discovery - Evaluation Rubric.xlsx fill in the learner cells before submitting
  starter-code/                                                  THIS folder: the system you work in (this README lives here)
  skills/data-discovery-agent/                                   SKILL.md (Steps 0-2b, you extend it) + README.md
```

Start with the Assignment Doc, then the Helper Guide. Copy the contents of `starter-code/` into your own cloned repo root and copy `skills/` alongside it (see section 5). Before Claude Code can find the skill, you must place it at `.claude/skills/data-discovery-agent/SKILL.md` in your repo. All paths below are relative to your repo root, i.e. the contents of `starter-code/`.

## 1. What you will be able to do
1. Run and steer a multi-agent pipeline (plan → scout → profile → assess → memo) and read its trace to find out why it did what it did.
2. Point an agent at **any** dataset link and get a defensible answer: what is behind it, what it covers, on what terms, and whether it fits the need.
3. Build agent tools that turn unfamiliar metadata (landing pages, schema.org JSON-LD, JSON-stat) into structured catalog records.
4. Encode feasibility judgement as deterministic rules plus agent judgement, and calibrate the verdicts.
5. Recognise the traps that sink projects at discovery time: migrated tables, unit changes, consent gaps, superseded copies, code systems that do not join, "last updated" dates that are not data dates, and licences that are not where you expect them.
6. Keep an agent inside guardrails (allowlist, byte caps, request budget, no personal data) and treat a refusal as a finding.
7. Write a reusable skill that gets a fresh Claude session to a comparable result on a new use case.

## 2. The system you are given

```
             use_cases/<ID>.json + brief.md           internal/<ID>_<client>/ (catalog + wiki)
                          │                            config/external_sources_register.json
                          ▼
  ┌──────────┐   ┌──────────┐  candidate gate   ┌───────────────────┐   ┌────────────────┐   ┌─────────────┐
  │ Planner  │──▶│  Scout   │──(YOU add dataset ▶│ Profiler × N      │──▶│ rules (Python) │──▶│ Risk        │
  │ plan per │   │ catalog, │   links: any URL) │ one per source,   │   │ + Risk         │   │ Assessor    │
  │ need +   │   │ wiki,    │                   │ inspects links,   │   │ judgement      │   │ verdicts,   │
  │ hints    │   │ register │                   │ samples data      │   │ flags          │   │ coverage    │
  └──────────┘   └──────────┘                   └───────────────────┘   └────────────────┘   └──────┬──────┘
                                                                                                    ▼
                                                     HUMAN REVIEW GATE  ◀──  Memo Writer: feasibility memo
```

- Each agent is a tool-use loop over the Claude API (`discovery_agent/agent.py`) with its **own toolset** and a **submit tool** whose input is validated against a JSON schema and cross-checks. Invalid submissions go back to the model to fix.
- Tools (`discovery_agent/tools/`): internal catalog search (BM25), catalog entries with wiki backlinks, wiki pages, the external register, single-call public-API probes, **`inspect_dataset_link`** (works out any link: a UCI page, a GitHub file, a portal landing page via schema.org JSON-LD, a data package, JSON-stat, a JSON API, a raw file, an archive, a login wall), **`sample_data_file`** (profiles the first ≤2 MB of a data file: types, sentinels, ranges, value sets, with personal-looking values masked), a generic URL probe, and a JSON-stat summariser. The data-package summariser is an ungraded stub.
- Guardrails (`tools/http_client.py`): https only, domain allowlist (re-checked on redirects), per-response byte cap, per-run request budget, GET only, disk cache.
- Every LLM call, tool call and HTTP request is written to `outputs/<ID>/trace.jsonl`, and every agent's full conversation to `outputs/<ID>/transcripts/`.

## 3. The two use cases

| | UC1: Air quality and traffic | UC2: Ice-cream sales, weather and holidays |
|---|---|---|
| Client (fictional) | Valdena Civic Health Office, northern Italy | Valdena Gelato Shop, northern Italy |
| Question | Do traffic and weather explain poor-air days, and can the clinic warn patients in time? | Do hot days and public holidays raise ice-cream sales? |
| Windows | prototype 2004-03-10 to 2005-04-04 (public data), production 2024-01-01 to 2025-12-31 | history 2023-06-01 to 2025-05-31, recent 2025-06-01 to 2026-03-31 |
| Internal estate | 4 catalog entries, 3 wiki pages | 3 catalog entries, 2 wiki pages |
| Register (public APIs) | Open-Meteo (weather), Nager.Date (public holidays), a vendor feed with an expired agreement | Open-Meteo (weather), Nager.Date (public holidays) |
| Dataset links you supply (section 4) | 3 links: one public dataset, one statistics API, one distractor | none |

Read the briefs in `use_cases/` first. The `.json` files are the contract the rules check against.

The business problems, needs, grains, geographies and windows above are the inputs to this assignment. You are not asked to frame a new problem. A **reuse check** (section 9) then runs your finished skill on UC2 in a fresh session.

## 4. Dataset links (you supply these at the candidate gate)

The pipeline agents do not search the web. External datasets come from **you**, either from your own search or from the shortlist that Claude suggests in Step 2b (below). Every link is then checked by the pipeline like any other. After the Scout has searched the internal catalog and the register, the **candidate gate** shows which needs it could not meet and the Planner's hints on what to look for, then asks for dataset links. A link can be **any https URL**: a repository page, a portal record, a data package, an API call or a raw file. For each link you give the need ids it should fill and the windows it should cover. The agent then works out what the link holds and reports whether it is of any use.

### The links to use (UC1)
UC1 has three links. Check each one before you rely on it. UC2 has no dataset links: its weather and holiday data come from the register APIs.

| Use case | Link | Need ids | Windows | Link type the agent should detect |
|---|---|---|---|---|
| UC1 | `https://archive.ics.uci.edu/dataset/360/air+quality` | `N1` | `prototype` | UCI dataset page |
| UC1 | `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sdg_11_52?format=JSON&lang=EN&geo=IT` | `N6` | `prototype,production` | JSON-stat API (its host needs a G6 entry) |
| UC1 | `https://catalog.data.gov/dataset/open-air-chicago-hour-aggregations` | `N1` | `prototype` | Public landing page |

The same links, with needs and windows, are in `links/UC1_example_links.json`. Copy that file once, after the scout, to `outputs/UC1/links.json` (never copy over it). From then on, `outputs/UC1/links.json` is the **one** links file you use: you append each accepted Step 2b suggestion to it, and you pass only that file to `--links-file`. Every link in it needs a gate decision from you.
```bash
# The gate needs candidates.json (from the scout) and gate_decisions.json (your decisions), so run in this order:
python -m discovery_agent run --use-case UC1 --stop-after scout --no-input     # 1. plan + scout: writes outputs/UC1/candidates.json
cp links/UC1_example_links.json outputs/UC1/links.json                          # 2. copy once, after the scout: the one links file
# 3. write outputs/UC1/gate_decisions.json yourself: one accept or reject decision, with a reason, for every link in outputs/UC1/links.json (template: links/_TEMPLATE_gate_decisions.json)
python -m discovery_agent run --use-case UC1 --from-stage profile --links-file outputs/UC1/links.json --no-input   # 4. profile, assess, memo
python -m discovery_agent run --use-case UC2 --no-input     # no dataset links for UC2
```

The links will not be fully understood until you have done G1 (licences), G3 (JSON-stat) and G6 (the allowlist). Without G1, the profiler may still read a licence from the page itself, so do not expect every link to show `LIC-UNKNOWN`. The Eurostat host (`ec.europa.eu`) is refused until it has a G6 entry with a justification. Read the publisher page first, then re-run the inspection after you add the host. The Chicago link is a **distractor, and you accept it on purpose** at the gate, with your own reason. The pipeline then records the refusal, because its host (`catalog.data.gov`) must never be added to the allowlist; that refusal is the finding. Do not retry the link more than twice. Before you rely on what the agent says about them, find out yourself what each one is, what it covers and what its terms are. The agent's job is to tell you; your job is to check it.

### Try your own links too
Add any other public dataset you think fills a gap: a Zenodo record, a statistics office API, a GitHub CSV, a data.gov entry. Inspect it first without the LLM:
```bash
python -m discovery_agent tool inspect_dataset_link '{"url": "<your link>"}' --use-case UC1
python -m discovery_agent tool sample_data_file '{"url": "<a data file it lists>"}' --use-case UC1
```
Your own links are not scored automatically. Review them in `review_UCx.md`, and add each host you need to the allowlist with a reason (G6).

### Suggest sources (Step 2b)
**Search script (generate it with Claude Code).** Claude Code's built-in WebSearch does not work with the gateway key, and no search script is provided. Ask Claude Code, in this repo, to generate `scripts/web_search.py` with this prompt:

> Create `scripts/web_search.py`. Use only the Python standard library (urllib, json, os) and add no dependencies. It takes one query argument. It sends a POST to `{ANTHROPIC_BASE_URL}/v1/chat/completions` (no `/v1` added to the base URL) with the header `Authorization: Bearer {ANTHROPIC_AUTH_TOKEN}` and a JSON body: `model` from `WEB_SEARCH_MODEL`, defaulting to `gemini-3.8-flash`; one user message containing the query; and `web_search_options: {}`. It prints the answer text, then the citation URLs from the response. If a variable is missing, exit with a message that names it. Never print the token or the full request.

Use a Gemini model that returns citations (`gemini-3.8-flash` or `gemini-3.5-flash-lite`; check your key's model list). Results are leads, not verified sources. DeepSeek answered from memory without citations in the pilot, so do not use it for search. Test the script with one query before Step 2b.

After the Scout, ask Claude (in your Claude Code session, using the skill) for up to **five** external sources for the needs that are still unmet. Claude runs your script for each search and shows only URLs that come with a citation. For each one, check the publisher's page yourself: the exact link, the coverage the page states, and what still needs checking (licence, population, access). Accept, reject or revise each suggestion, with a short reason, and record it under "Source suggestions" in `outputs/artifacts/decisions.md`. Accepted links go into the candidate gate like any other link.

A suggestion is not a verified source. It gives no host access (a host needs an exact entry in `config/allowlist.json`, gap G6) and no permission to use the data. Inspect at least one accepted extra source through the workflow. For UC1 and UC2 the prescribed links are scored automatically; your suggested source is judged by your review and decision log.

## 5. Setup (WSL)

```bash
# in your cloned repo, after copying the contents of starter-code/ and the skills/ folder into it:
mkdir -p .claude/skills/data-discovery-agent
cp skills/data-discovery-agent/SKILL.md .claude/skills/data-discovery-agent/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Tiger AI Gateway: the same values as Claude Code (values come by email; never commit them)
export ANTHROPIC_BASE_URL="https://api.ai-gateway.tigeranalytics.com"
export ANTHROPIC_AUTH_TOKEN="<your assignment key>"
export ANTHROPIC_MODEL="<your model id>"
# optional: export DISCOVERY_MODEL=... to use a different model for the agents only
# optional: export DISCOVERY_EFFORT=medium   (only if your model supports the effort parameter)

python -m pytest tests/ -q        # provided tests pass; tests/test_learner_gaps.py fails until you close the gaps
```

Then open Claude Code in this folder. The skill is in `.claude/skills/data-discovery-agent/SKILL.md` (copied from `skills/data-discovery-agent/SKILL.md` in the bundle; if it is not auto-discovered, paste its contents as your message). Invoke `/data-discovery-agent` and say, for example, *"Run Steps 0–2b for UC1."* Claude checks the tooling, validates the use case, runs plan and scout, suggests external sources for the unmet needs, and stops at the candidate gate, where you choose the links.

## 6. Running and iterating

```bash
python -m discovery_agent run --use-case UC1 --links-file outputs/UC1/links.json   # everything (the candidate gate prompts only in a real terminal)
python -m discovery_agent run --use-case UC1 --stop-after scout       # cheap: plan + scout only
python -m discovery_agent run --use-case UC1 --from-stage assess      # re-run rules + Risk Assessor + memo on saved records
python -m discovery_agent run --use-case UC1 --from-stage profile --stop-after profile --only link.uci_360   # re-profile one source
python -m discovery_agent tool inspect_dataset_link '{"url": "https://archive.ics.uci.edu/dataset/360/air+quality"}' --use-case UC1   # any tool, no LLM (--use-case is required)
python -m discovery_agent validate-use-case UC1                       # check a use-case spec and its inputs
python -m discovery_agent check UC1                                   # self-check a finished run
```

A `--from-stage` run needs the earlier stages' files in `outputs/<ID>/`, so run `--stop-after scout` first. Source ids are `link.` plus a slug of the link (for example `link.uci_360`); `candidates.json` lists every id after the scout stage. Outputs go to `outputs/<ID>/`: `search_plan.json`, `candidates.json`, `candidates_final.json`, `records/*.json`, `rule_flags.json`, `risk_assessment.json`, **`discovery_results.json`**, **`feasibility_memo.md`**, `trace.jsonl`, `transcripts/`, `run_summary.json`.

**Cost:** a full run makes roughly 30 model calls for each use case (about 3 per profiled source). `run_history.jsonl` keeps one line per stage run; `run_summary.json` holds only the last stage. Iterate stage by stage. HTTP responses are cached in `.cache/http/`, so re-runs are cheap and reproducible. Use `--no-cache` only when you need fresh data.

## 7. Your tasks: the gaps

| Gap | What | Where | Done when |
|---|---|---|---|
| **G1** | Find the licence of **any** dataset from its landing page: schema.org JSON-LD first, then licence links, then licence sentences. Normalise the name, and treat "Unknown" as no licence. Until then, every dataset link is `LIC-UNKNOWN` | `discovery_agent/tools/licence.py` → `extract_licence` | `pytest tests/test_learner_gaps.py -k g1` |
| **G3** | Summarise a JSON-stat dataset (UC1's Eurostat link) | `discovery_agent/tools/formats.py` → `jsonstat_summary` | `-k g3` |
| **G4** | Three deterministic rules: window coverage plus staleness, grain mismatch, and metadata-versus-documentation contradiction | `discovery_agent/risk_rules.py` | `-k g4` |
| **G5** | Write the verdict calibration rules the Risk Assessor follows | `discovery_agent/prompts/risk_assessor.md` (the G5 comment) | `-k g5`, plus verdicts you can defend |
| **G6** | Allowlist exactly the hosts your dataset links need (the link, the files it points to, its terms page), nothing broader | `config/allowlist.json` + `outputs/artifacts/decisions.md` | `-k g6`, plus a justification per host |
| **G2** | Not graded in this version: the data-package summary is a stub. | `discovery_agent/tools/formats.py` | not graded |
| **G7** | Find **one** agent mistake in a trace or transcript, fix it at the cause (prompt, tool description, validator or rule), re-run from that stage, and show before and after | anywhere in `discovery_agent/` | evidence in `outputs/artifacts/decisions.md` |

Hints for G7: does the Scout follow the wiki note about station VR-03 (it has stopped, but the catalog says active)? Does a profiler read the -200 values in the UCI data as real measurements? Does anyone notice that the traffic counts changed definition in 2024? Does the agent retry a refused host, or follow a login wall?

You will use Claude Code to do this work. That is the point. But you own the result: read every diff, and be ready to explain every rule and threshold.

### Explain briefly (in `decisions.md` and your memo reviews)
- **G1 and G3:** one edge case in each function (for example an unknown licence, or a JSON-stat response with a missing year), and how it changes the catalog record.
- **G4–G5:** one rule that makes a source feasible for one need or window but not another, using a UC1 or UC2 case, and the reason for each red flag you dismiss.
- **G7:** the project decision the failure could affect, and one related source or test you checked the fix against.
- **Memo review:** one conclusion traced from the source information to the verdict, and what could change it. Say where you agree with the agent, and why.

## 8. Ground rules
- **Metadata first, then a small sample, never the whole dataset.** `sample_data_file` reads at most a few MB to check structure and quality. Do not download datasets. No personal data in any output.
- **Do not weaken the guardrails** to make a run pass. A refused host, an expired agreement or a restricted table is a finding.
- **One exception to the config rule:** change only `latitude` and `longitude` in the `api.open_meteo_archive` `default_query` in `config/external_sources_register.json`, to the city you choose. Record the city and the reason in `outputs/artifacts/decisions.md`.
- **Fix the agent, not the output.** Never hand-edit `candidates.json`, records or results. Change a prompt, tool, rule or validator and re-run.
- **Provenance on every claim**, in records and in the memo.
- **Stop at the human review gate.** You are the human: review the memo and record your decision.
- **A suggestion is not a verified source.** Selecting it grants no host access and no permission to use the data.
- **Stopping is a valid outcome.** If a need stays unmet or a source is refused, record it rather than inventing a substitute.

## 9. Deliverables

| Item | Location |
|---|---|
| Gap implementations G1, G3, G4, G5, G6 (all of `tests/` passing) and the G7 fix | the files in section 7; the G7 fix is in `discovery_agent/` |
| Full runs for both use cases, with the dataset links from section 4 (plus any of your own) | `outputs/UC1/`, `outputs/UC2/` (keep the traces and transcripts) |
| Self-check output for both runs | `outputs/artifacts/check_UC1.json`, `check_UC2.json` (`python -m discovery_agent check UCx > ...`) |
| Your review of each memo: where you agree, where you overrule the agent and why, your verdict on each dataset link, your gate decision | `outputs/artifacts/review_UC1.md`, `review_UC2.md` |
| Gate decisions: `outputs/<ID>/gate_decisions.json`. Accept or reject every dataset link, with a reason of at least 20 characters in your own words. The pipeline refuses to profile a link without one | `outputs/<ID>/gate_decisions.json` |
| Sign-off: your gate decision, reviewer, conditions with owners, agreements or overrides, and one traced conclusion (a source, a record field and what could change it) | `outputs/<ID>/signoff.json`; `python -m discovery_agent check <ID>` checks it |
| Decisions log: source suggestions and your reasons, G1–G3 edge cases, the G4–G5 feasibility case, allowlist justification (G6), calibration rationale (G5), the G7 before/after | `outputs/artifacts/decisions.md` (template provided) |
| Extended skill file: Steps 3–5, working for any use case | `.claude/skills/data-discovery-agent/SKILL.md` (and the copy in `skills/data-discovery-agent/`) |
| Submission notes: reuse check, delivery reflection and ownership (section below) | this README, under "Submission notes" |
| Walkthrough (written, not a live session) | `outputs/artifacts/walkthrough.md` |

**Gate decisions file.** You write `outputs/<ID>/gate_decisions.json` yourself (template: `links/_TEMPLATE_gate_decisions.json`). It has one entry per dataset link in `outputs/<ID>/links.json`, the one links file. The `url` must match that file exactly. `decision` is `accept` or `reject`. `reason` is at least 20 characters, in your own words. Only accepted links are profiled.

**Pull request and pytest evidence.** Save the pytest output as `outputs/artifacts/pytest_before.txt` and `outputs/artifacts/pytest_after.txt`. Paste the pull request URL into the rubric (row "Pull request link"). The instructor reviews the pull request.

**Sign-off file.** Write `outputs/<ID>/signoff.json` (template: `outputs/artifacts/_TEMPLATE_signoff.json`) and `outputs/artifacts/review_<ID>.md`. `python -m discovery_agent check <ID>` checks them. It lists every missing item in one run.

**Checklist for the sign-off step (both use cases):**
- `outputs/<ID>/gate_decisions.json`: every dataset link accepted or rejected, with reasons (none for UC2).
- `outputs/<ID>/discovery_results.json`, `feasibility_memo.md` and the records: produced by a full run through assess.
- `outputs/artifacts/review_<ID>.md`: your memo review.
- `outputs/<ID>/signoff.json`: reviewer, verdict, conditions (if proceeding with conditions), at least one agreement or override, and one traced conclusion whose source and record field exist.
- `python -m discovery_agent check <ID>` with no problems listed.

Keep generated records and traces (`outputs/<ID>/`) as supporting evidence.

## 10. Evaluation (100)
| Part | Points |
|---|---|
| Automatic score of `discovery_results.json` against a hidden answer key (average of UC1 and UC2): discovery recall, verdict calibration, red-flag recall, the assessment of each section-4 dataset link, precision, overall verdict, minus guardrail penalties from the trace | 40 |
| G1, G3, G4: tests pass, the code is clear and not hard-coded to the fixtures, and the edge cases are explained | 11 |
| G5: calibration rules are specific, consistent and reflected in the verdicts, with one feasible-for-one-need case explained | 5 |
| G7: a real failure, fixed at its cause, with measured before/after and the project decision it could affect | 10 |
| Memo review: you caught what the agent got wrong or missed, traced a conclusion to a record field, and explained where you agree and why. The sign-off checks are automatic | 16 |
| Skill extension: concrete steps, reusable on a new use case, plus the reuse check and delivery reflection in the Submission notes | 10 |
| Decisions log, including G6 allowlist minimality, your gate decisions and the reasons for each source selection or rejection | 4 |
| Walkthrough (15 minutes with your instructor): you explain one rule, trace one claim to its record, and explain one rejected source and one memo conclusion, in your own words | 4 |

The self-check (`check`) tells you whether your outputs are complete and consistent. It does not tell you whether the verdicts are right. Judging that is the assignment.

## 11. Troubleshooting
- `No gateway credentials found`: export the three variables in the same shell (see section 5).
- `401` / `403` / `404` from the gateway: wrong token, a model id not enabled for your key, or a base URL with `/v1` appended (do not add it).
- `DOMAIN_NOT_ALLOWLISTED`: the guardrail is working; see G6.
- `NOT_IMPLEMENTED` in a transcript: a gap you have not closed yet.
- An agent fails with "no valid submit_<tool> after N turns": read its transcript in `outputs/<ID>/transcripts/`, because the validator's messages say what was wrong.
- A data file times out or is a zip: that is a real finding about the file. It does not make the source unreachable if its metadata was read.
- A link is a login wall (Kaggle downloads, some portals): record `ACC-RESTRICTED`. Never put credentials in the agent.
- `error: the following arguments are required: --use-case` on a `tool` command: add `--use-case UC1` (or the use case you are working on). The `tool` command no longer defaults to UC1.
- Step 2b: Claude Code's built-in `WebSearch` does not work with the gateway key. Use your own `scripts/web_search.py` (Step 2b). If the script is missing, fails or returns no citations, tell the instructor. Do not write a shortlist from memory; a suggestion needs a link you actually found.

## Submission notes
Your walkthrough is a written file, `outputs/artifacts/walkthrough.md`, not a live session. In your own words, citing your own files, explain one rule you wrote or accepted, one claim in `signoff.json` traced to its record field, one rejected source and why, and one memo conclusion. Answer from your own files.

Write these answers in this README, under this heading. Keep each answer short.

**Reuse check.** Open a fresh Claude Code session that has only your skill and this README. Run Steps 0–2b for UC2, and profile the links you accept in Step 2b (UC2 has no prescribed links). If none survives your check, record "none accepted" and stop. Answer:
- Which steps could not be followed as written, and what was missing?
- Which inputs would a data scientist replace for a new project (use-case contract, catalog export, wiki, register entries, permitted hosts, dataset links)?
- Which values did you find hard-coded for UC1 or UC2, and what did you change?

**Reuse check answers (Harsh, 2026-11-11):**
- Step 2b could not be followed as written because `scripts/web_search.py` was missing from the repo. The skill correctly stopped at Step 2b.1 and asked me to generate it. For UC2, no suggestion survived the check — none accepted, profiling covered only internal and register sources.
- A data scientist replacing this for a new project would need: the use-case JSON (`use_cases/<ID>_*.json`), the internal catalog (`internal/<ID>_*/catalog_export.json`), wiki pages, register entries in `config/external_sources_register.json`, any host additions to `config/allowlist.json`, and their own dataset links.
- The three prescribed links in `links/UC1_example_links.json` and the `ec.europa.eu` allowlist entry are UC1-specific. A new use case needs its own links file and its own justified allowlist additions via G6.

**Delivery reflection.** For one bounded activity (for example, reviewing one source shortlist):
- The steps you did yourself, and what the assistant did.
- What you still had to check yourself.
- Your review time (measured by you) and the model usage from `outputs/<ID>/run_history.jsonl` (one line per stage run). If you did not measure your review time, say so and make no time-saving claim.

**Delivery reflection (Harsh, 2026-11-11):** Activity: reviewing the UC1 source shortlist and Step 2b suggestions.
- I read each suggestion and gave the accept/reject decision with my own reason. I dictated the gate decision reasons word for word. I checked each memo verdict against `risk_assessment.json` and the wiki before agreeing, and I wrote the sign-off conditions and traced conclusion myself.
- The assistant ran the pipeline commands, showed me outputs, and transcribed my decisions into files. I still had to check that the licence flags and temporal fields in each record matched the source page and wiki — the assistant could not do that check for me.
- I did not measure my review time and make no time-saving claim. UC1 model usage from `run_history.jsonl`: 45 LLM calls total across plan/scout, profile (including one re-run after the G3 fix), and two assess/memo runs — 574,595 input tokens, 124,432 output tokens. UC2: 32 LLM calls, 332,787 input tokens, 54,001 output tokens.

**Ownership.** In a few sentences each:
- One source you selected or rejected, and why.
- One rule or agent correction you made, and what it changed.
- One change a new use case would need in the skill or the inputs.

**Ownership answers (Harsh, 2026-11-11):**
- I rejected EEA AirBase v8 because the UCI link already covers N1 for the prototype window. I accepted the Chicago `catalog.data.gov` link deliberately, knowing the host would be refused by the allowlist — the pipeline's guardrail refusal is the finding, not a bug. Its host must never be added.
- I implemented G3 (`jsonstat_summary` in `discovery_agent/tools/formats.py`) to fix the Eurostat profiler's `NOT_IMPLEMENTED` failure. After the fix, the Eurostat record correctly shows 36 cells covering 2005–2023, making it clear the production window (2024–2025) has no coverage — a verdict-changing finding for N6 that was previously unknown.
- A new use case needs a new `use_cases/<ID>_*.json` contract, a matching `internal/<ID>_*/catalog_export.json`, wiki pages, and register entries. The allowlist, the skill steps, and the gap implementations work without change for any use case written to the same contract.

*The companies, people and internal documents are fictional. The public datasets and APIs are real; their terms belong to their providers and must be read at the source.*
