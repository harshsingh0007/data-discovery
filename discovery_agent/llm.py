"""Thin wrapper over the Anthropic SDK, configured for the Tiger AI Gateway.

The SDK reads ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN from the environment, the
same variables Claude Code uses in WSL. The model comes from DISCOVERY_MODEL, then
ANTHROPIC_MODEL, then DEFAULT_MODEL.
"""

from __future__ import annotations

import os
import sys
import time

try:  # the SDK's HTTP client is httpx, or httpx2 in some environments; its errors come from that module
    import httpx2 as httpx
except ImportError:
    import httpx

from .trace import Trace

DEFAULT_MODEL = "claude-opus-5-5"
STREAM_ATTEMPTS = 4  # first try plus 3 retries when the gateway drops a stream
STREAM_BACKOFF_S = 2.0  # waits 2s, 4s, 8s between attempts
MALFORMED_TOOL_JSON = "Unable to parse tool parameter JSON"  # start of the SDK's ValueError for a garbled tool call


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, trace: Trace):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment problem
            raise SystemExit(
                "The 'anthropic' package is missing. Run: pip install -r requirements.txt"
            ) from exc
        self._anthropic = anthropic
        if not (
            os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("ANTHROPIC_API_KEY")
        ):
            raise SystemExit(
                "No gateway credentials found. Export ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN and ANTHROPIC_MODEL "
                "(see README.md, 'Setup'). Never paste the token into code or commits."
            )
        self.client = anthropic.Anthropic(max_retries=4, timeout=600)
        self.model = (
            os.environ.get("DISCOVERY_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or DEFAULT_MODEL
        )
        self.effort = os.environ.get(
            "DISCOVERY_EFFORT"
        )  # optional: low | medium | high | xhigh | max
        self.trace = trace

    def complete(
        self,
        *,
        agent: str,
        system: str,
        messages: list,
        tools: list[dict],
        max_tokens: int,
        turn: int,
    ):
        kwargs = dict(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages
        )
        if tools:
            kwargs["tools"] = tools
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        a = self._anthropic
        try:
            msg = self._stream_with_retry(kwargs, agent=agent, turn=turn)
        except a.AuthenticationError as exc:
            raise SystemExit(
                f"Gateway rejected the credentials (401). Check ANTHROPIC_AUTH_TOKEN. {exc}"
            ) from exc
        except a.PermissionDeniedError as exc:
            raise SystemExit(
                f"Gateway refused this model or request (403). Check ANTHROPIC_MODEL={self.model!r}. {exc}"
            ) from exc
        except a.NotFoundError as exc:
            raise SystemExit(
                f"Model or endpoint not found (404). Check ANTHROPIC_BASE_URL (no /v1 suffix) "
                f"and the model id. {exc}"
            ) from exc
        except a.BadRequestError as exc:
            raise LLMError(f"Bad request (400) from {agent}: {exc}") from exc
        except a.APIConnectionError as exc:
            raise LLMError(f"Could not reach the gateway: {exc}") from exc
        except a.APIStatusError as exc:
            raise LLMError(
                f"Gateway error {exc.status_code} from {agent}: {exc}"
            ) from exc
        usage = getattr(msg, "usage", None)
        self.trace.event(
            "llm_call",
            agent=agent,
            turn=turn,
            model=self.model,
            stop_reason=msg.stop_reason,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )
        return msg

    def _stream_with_retry(self, kwargs: dict, *, agent: str, turn: int):
        """Read one streamed reply, retrying when the gateway drops the stream partway.

        The SDK's max_retries only covers starting the request. A stream that dies mid-response
        surfaces as a raw httpx error, or as an IndexError from the SDK's event accumulator
        (a content-block event arrives without its start event). Both are transient, and the
        call is safe to repeat because `messages` is not changed until complete() returns.
        """
        transient = (
            httpx.TransportError,
            IndexError,
            ValueError,
        )  # TransportError covers RemoteProtocolError, ReadError, ReadTimeout
        for attempt in range(1, STREAM_ATTEMPTS + 1):
            try:
                with self.client.messages.stream(**kwargs) as stream:
                    return stream.get_final_message()
            except transient as exc:
                # The SDK raises a bare ValueError when the model's tool-call JSON arrives garbled or cut off.
                # Retry only that one: any other ValueError is a real bug and must not be swallowed.
                if isinstance(exc, ValueError) and not str(exc).startswith(
                    MALFORMED_TOOL_JSON
                ):
                    raise
                self.trace.event(
                    "llm_retry",
                    agent=agent,
                    turn=turn,
                    attempt=attempt,
                    error=type(exc).__name__,
                )
                if attempt == STREAM_ATTEMPTS:
                    raise LLMError(
                        f"Gateway stream failed {attempt} times ({type(exc).__name__}: {exc})"
                    ) from exc
                say(
                    f"  [{agent}] stream dropped ({type(exc).__name__}); retrying {attempt}/{STREAM_ATTEMPTS - 1}"
                )
                time.sleep(STREAM_BACKOFF_S * 2 ** (attempt - 1))


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
