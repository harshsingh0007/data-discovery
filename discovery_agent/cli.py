"""Command line: python -m discovery_agent <command> ...

  run                 run the agent pipeline (all stages, or a slice with --from-stage / --stop-after)
  tool                call one tool directly, without the LLM (for testing your tools)
  validate-use-case   check a use-case spec, brief and internal estate before running
  check               self-check a finished run (completeness, consistency, guardrails)
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_allowlist, load_settings, load_use_case
from .orchestrator import STAGES, Pipeline, RunOptions


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m discovery_agent", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the discovery pipeline")
    r.add_argument("--use-case", required=True, help="use-case id, e.g. UC1")
    r.add_argument("--from-stage", choices=STAGES, default="plan")
    r.add_argument("--stop-after", choices=STAGES, default="memo")
    r.add_argument("--link", action="append", default=[], metavar="URL",
                   help="a dataset link to assess (any https URL). Repeat for several; asked interactively if omitted")
    r.add_argument("--link-needs", action="append", default=[], metavar="N1,N2",
                   help="need ids for the matching --link (same order)")
    r.add_argument("--link-windows", action="append", default=[], metavar="W1,W2",
                   help="window ids for the matching --link (same order)")
    r.add_argument("--links-file", help='JSON list of {"url", "need_ids", "target_windows", "note"} (see links/_TEMPLATE_links.json)')
    r.add_argument("--only", help="profile only these source ids, comma-separated (debugging)")
    r.add_argument("--out", help="output folder (default outputs/<use case>)")
    r.add_argument("--no-input", action="store_true", help="never prompt (CI / scripted runs)")
    r.add_argument("--no-cache", action="store_true", help="ignore the HTTP cache and fetch live")

    t = sub.add_parser("tool", help="call one tool directly, without the LLM")
    t.add_argument("name")
    t.add_argument("args", nargs="?", default="{}", help="JSON object of tool arguments")
    t.add_argument("--use-case", required=True, help="use-case id whose catalog, register and use-case contract the tool sees, e.g. UC1")
    t.add_argument("--no-cache", action="store_true")

    v = sub.add_parser("validate-use-case", help="validate a use-case spec and its inputs")
    v.add_argument("use_case")

    c = sub.add_parser("check", help="self-check a finished run")
    c.add_argument("use_case")
    c.add_argument("--out")

    a = ap.parse_args(argv)
    from pathlib import Path

    if a.cmd == "run":
        if STAGES.index(a.from_stage) > STAGES.index(a.stop_after):
            ap.error("--from-stage comes after --stop-after")
        if not (len(a.link) == len(a.link_needs) == len(a.link_windows)):
            ap.error("give one --link-needs and one --link-windows per --link, in the same order")
        links = [{"url": u, "need_ids": _csv(n), "target_windows": _csv(w)} for u, n, w in zip(a.link, a.link_needs, a.link_windows)]
        if a.links_file:
            links += json.loads(Path(a.links_file).read_text(encoding="utf-8"))
        opts = RunOptions(use_case_id=a.use_case, out_dir=Path(a.out) if a.out else None, from_stage=a.from_stage,
                          stop_after=a.stop_after, links=links, interactive=not a.no_input,
                          use_cache=not a.no_cache, only_sources=_csv(a.only))
        Pipeline(opts).run()
        return 0

    if a.cmd == "tool":
        from .tools import REGISTRY, ToolContext, execute
        from .tools.http_client import HttpClient
        from .trace import Trace
        if a.name not in REGISTRY:
            print(f"Unknown tool. Available: {', '.join(sorted(REGISTRY))}", file=sys.stderr)
            return 2
        settings, trace = load_settings(), Trace(None)
        ctx = ToolContext(use_case=load_use_case(a.use_case), settings=settings,
                          http=HttpClient(settings, load_allowlist(), trace, use_cache=not a.no_cache), trace=trace, agent="cli")
        ok, payload = execute(a.name, json.loads(a.args), ctx)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if ok else 1

    if a.cmd == "validate-use-case":
        from .validation import validate_use_case
        errs = validate_use_case(a.use_case)
        print(f"{a.use_case}: {'OK' if not errs else f'{len(errs)} problem(s)'}")
        for e in errs:
            print(f"  - {e}")
        return 1 if errs else 0

    if a.cmd == "check":
        from .validation import check_run
        errs, stats = check_run(a.use_case, Path(a.out) if a.out else None)
        print(json.dumps({"use_case": a.use_case, "problems": errs, "trace_stats": stats}, indent=2))
        return 1 if errs else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
