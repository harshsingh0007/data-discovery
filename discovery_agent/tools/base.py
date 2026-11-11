"""Tool registry. Each tool is a plain Python function with a JSON input schema.

Agents only see the subset of tools they are given in agents.py.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from ..trace import Trace
from .http_client import HttpClient, HttpRefused


class ToolError(Exception):
    """An expected failure the model should see and react to (bad id, not found, ...)."""


class NotImplementedTool(ToolError):
    """A learner TODO that has not been implemented yet."""


@dataclass
class ToolContext:
    use_case: dict
    settings: dict
    http: HttpClient
    trace: Trace
    agent: str = ""

    def for_agent(self, agent: str) -> "ToolContext":
        return replace(self, agent=agent)


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[ToolContext, dict], Any]

    def api_schema(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    """Decorator that registers a tool."""

    def wrap(fn: Callable[[ToolContext, dict], Any]):
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            input_schema={"type": "object", "properties": properties, "required": required or [],
                          "additionalProperties": False},
            fn=fn,
        )
        return fn

    return wrap


def execute(name: str, args: dict, ctx: ToolContext) -> tuple[bool, Any]:
    """Run a tool. Returns (ok, payload). Never raises for tool-level failures."""
    started = time.time()
    if name not in REGISTRY:
        ok, payload = False, {"error": "UNKNOWN_TOOL", "message": f"No tool named {name!r}"}
    else:
        try:
            ok, payload = True, REGISTRY[name].fn(ctx, args or {})
        except NotImplementedTool as exc:
            ok, payload = False, {"error": "NOT_IMPLEMENTED", "message": str(exc)}
        except HttpRefused as exc:
            ok, payload = False, {"error": exc.code, "message": str(exc)}
        except ToolError as exc:
            ok, payload = False, {"error": "TOOL_ERROR", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures to the model, keep the run alive
            ok, payload = False, {"error": type(exc).__name__, "message": str(exc)[:1000]}
    ctx.trace.event("tool_call", agent=ctx.agent, tool=name, args=args, ok=ok,
                    ms=int((time.time() - started) * 1000),
                    result_chars=len(json.dumps(payload, default=str)))
    return ok, payload
