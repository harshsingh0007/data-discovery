"""A small, explicit agent loop: model -> tool calls -> results -> ... -> submit tool.

Every agent ends by calling its own `submit_<x>` tool. The input is validated against a
JSON schema plus custom checks. On failure the errors go back to the model so it can
fix them. The loop is hand-written so you can see and change every step.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import jsonschema

from .llm import LLMError, say
from .tools import REGISTRY, ToolContext, execute

Validator = Callable[[dict], list[str]]


class AgentFailed(RuntimeError):
    pass


@dataclass
class AgentSpec:
    name: str
    system_prompt: str
    tool_names: list[str]
    submit_name: str
    submit_description: str
    submit_schema: dict
    max_turns: int
    validators: list[Validator] = field(default_factory=list)


def _to_jsonable(block: Any) -> Any:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if isinstance(block, dict):
        return block
    return getattr(block, "__dict__", str(block))


def _clip(payload: Any, limit: int) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[:limit] + f' …[truncated {len(text) - limit} chars; ask for something narrower]'
    return text


def run_agent(spec: AgentSpec, task: str, *, llm, ctx: ToolContext, settings: dict,
              transcript_path: Path | None = None, label: str | None = None) -> dict:
    label = label or spec.name
    ctx = ctx.for_agent(label)
    tools = [REGISTRY[n].api_schema() for n in spec.tool_names]
    tools.append({"name": spec.submit_name, "description": spec.submit_description, "input_schema": spec.submit_schema})
    messages: list[dict] = [{"role": "user", "content": task}]
    limit = settings["agents"]["tool_result_char_limit"]
    nudges = 0
    try:
        for turn in range(1, spec.max_turns + 1):
            if turn == spec.max_turns and isinstance(messages[-1]["content"], list):
                messages[-1]["content"].append({"type": "text", "text": (
                    f"This is your final turn. Call {spec.submit_name} now with your best answer, and put anything "
                    "you could not verify in the unknowns or open-questions fields.")})
            resp = llm.complete(agent=label, system=spec.system_prompt, messages=messages, tools=tools,
                                max_tokens=settings["agents"]["max_tokens"], turn=turn)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "refusal":
                raise AgentFailed(f"{label}: the model declined the request (stop_reason=refusal)")
            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                nudges += 1
                if nudges > 2:
                    raise AgentFailed(f"{label}: ended without calling {spec.submit_name}")
                hint = " Your last reply hit max_tokens; be more concise." if resp.stop_reason == "max_tokens" else ""
                messages.append({"role": "user", "content": f"You must finish by calling the {spec.submit_name} tool.{hint}"})
                continue
            results, submitted = [], None
            for tu in tool_uses:
                if tu.name == spec.submit_name:
                    errors = validate(tu.input, spec)
                    ctx.trace.event("submit", agent=label, ok=not errors, errors=errors[:10])
                    if errors:
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                        "content": "Submission rejected. Fix these and call it again:\n- " + "\n- ".join(errors[:25])})
                    else:
                        submitted = tu.input
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "accepted"})
                elif tu.name not in spec.tool_names:
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                    "content": f"Tool {tu.name!r} is not available to the {spec.name} agent."})
                else:
                    ok, payload = execute(tu.name, tu.input, ctx)
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": _clip(payload, limit),
                                    **({} if ok else {"is_error": True})})
            messages.append({"role": "user", "content": results})
            if submitted is not None:
                say(f"  [{label}] done in {turn} turn(s)")
                return submitted
        raise AgentFailed(f"{label}: no valid {spec.submit_name} after {spec.max_turns} turns")
    except LLMError as exc:
        raise AgentFailed(f"{label}: {exc}") from exc
    finally:
        if transcript_path is not None:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text(json.dumps(
                {"agent": label, "system": spec.system_prompt,
                 "messages": [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str)
                               else [_to_jsonable(b) for b in m["content"]]} for m in messages]},
                indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def validate(payload: dict, spec: AgentSpec) -> list[str]:
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in jsonschema.Draft202012Validator(spec.submit_schema).iter_errors(payload)]
    if errors:
        return errors
    for check in spec.validators:
        errors.extend(check(payload))
    return errors
