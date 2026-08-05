import json
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from . import runtime
from . import usage as usage_mod


class Logger:
    """Writes one JSON object per line to .boukensha/sessions/<session-id>.jsonl.

    Every event carries a `phase`, and the writer appends `session_id` and `at`
    to all of them. Nothing is ever read back here — log_viz is the reader."""

    DEFAULT_SESSION_DIR = "sessions"

    def __init__(self, *, session_id=None, dir=None, log=None, snapshot=None):
        self.session_id = session_id or self._generate_session_id()
        # `log` short-circuits `dir`, which short-circuits _default_dir() — and
        # _default_dir() builds a Config, so it must not run when a path was
        # given explicitly.
        self.path = (
            Path(log)
            if log
            else Path(dir or self._default_dir()) / f"{self.session_id}.jsonl"
        )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._log_io = open(self.path, "a", encoding="utf-8")
        # Ruby creates this lazily inside subscribe(), because an unset ivar
        # reads as nil there. Python has no such excuse.
        self._subscribers = []
        # Running totals for session_end. Accumulated here rather than re-summed
        # by every reader, for the same reason response events carry their own
        # cost: the file should be readable without replaying the run.
        self._started_at = time.monotonic()
        self._turns = 0
        self._total_tokens = 0
        self._total_cost_usd = 0.0
        self._closed = False
        self._write_log({"phase": "session_start", **(snapshot or {})})

    # Unused in this step — nothing calls it yet. log_viz's parser already
    # handles a "turn" phase, so the reader side is waiting for it.
    def turn(self, *, n):
        self._turns = max(self._turns, int(n))
        self._write_log({"phase": "turn", "n": n})

    def iteration(self, *, n, max):
        self._write_log({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, *, kind, n, max):
        self._write_log({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def turn_end(self, *, reason, iterations, tokens=None):
        self._write_log(
            {
                "phase": "turn_end",
                "reason": reason,
                "iterations": iterations,
                "tokens": tokens,
            }
        )

    # `messages` is included only when the last one is from the user.
    #
    # This event used to serialize the entire history on every iteration, which
    # grows quadratically in turn length: 191 KB of one 224 KB session file was
    # this one phase repeating itself. The only consumer is log_viz, which reads
    # `messages[-1]` and only when it is the user message that opened the turn
    # (log_viz/lib/log_viz/session.rb:77-86), so nothing downstream loses
    # anything. The rest of the conversation is still fully reconstructible from
    # the response and tool_result events.
    #
    # message_count stays on every event, so the history's *size* is still
    # visible even when its contents are not.
    # Built in two halves so `messages` keeps its original position between
    # message_count and tool_count when it is present — key order is part of
    # this file's output, per _write_log below.
    def prompt(self, *, messages, tools, context_window=None):
        event = {"phase": "prompt", "message_count": len(messages)}
        if messages and getattr(messages[-1], "role", None) == "user":
            event["messages"] = [self._serialize_message(m) for m in messages]
        event.update(
            {
                "tool_count": len(tools),
                "tools": list(tools.keys()),
                "context_window": context_window,
            }
        )

        self._write_log(event)

    def compaction(self, *, before, dropped, context_window):
        self._write_log(
            {
                "phase": "compaction",
                "before": before,
                "dropped": dropped,
                "context_window": context_window,
            }
        )

    def reasoning(self, *, text, redacted=False):
        self._write_log(
            {"phase": "reasoning", "text": str(text), "redacted": redacted}
        )

    def plan(self, *, text):
        self._write_log({"phase": "plan", "text": str(text).strip()})

    def tool_call(self, *, name, args):
        self._write_log({"phase": "tool_call", "name": name, "args": args})

    def tool_result(self, *, name, result, ok=True, error=None):
        self._write_log(
            {
                "phase": "tool_result",
                "name": name,
                "result": str(result),
                "ok": ok,
                "error": error,
            }
        )

    def response(self, *, text, usage=None, stop_reason=None, task=None, backend=None):
        event = {
            "phase": "response",
            "text": str(text).strip(),
            "usage": usage,
            "stop_reason": stop_reason,
        }
        metadata = self._execution_metadata(task=task, backend=backend, usage=usage)
        event.update(metadata)
        # Accumulate here rather than in _write_log: this is the only phase that
        # carries usage, and reading it off the built event means the totals can
        # never disagree with the lines they came from.
        self._total_tokens += (metadata.get("input_tokens") or 0) + (
            metadata.get("output_tokens") or 0
        )
        self._total_cost_usd += metadata.get("cost_usd") or 0.0
        self._write_log(event)

    def raw(self, *, data):
        if not runtime.is_debug():
            return

        self._write_log({"phase": "raw", "data": data})

    # Also unused in this step. A live consumer of the event stream (the TUI is
    # the obvious one) can watch events without re-reading the file.
    def subscribe(self, callback):
        self._subscribers.append(callback)

    # reason: "completed" | "interrupted" | "error".
    #
    # Before this existed, close() shut the file and wrote nothing, so a clean
    # exit, a Ctrl-C and a crash inside the agent loop were byte-identical on
    # disk — 0 of 62 archived sessions record how they ended. That matters here
    # beyond tidiness: "the session just stops" is also the shape a blocked
    # player journey has, and the two have to be distinguishable.
    #
    # Idempotent, because the run and repl paths both close in a finally block
    # and a future caller may well close twice.
    def close(self, reason="completed"):
        if self._closed:
            return

        self._closed = True
        if self._log_io and not self._log_io.closed:
            self._write_log(
                {
                    "phase": "session_end",
                    "reason": reason,
                    "turns": self._turns,
                    "total_tokens": self._total_tokens,
                    # None rather than 0.0 when nothing was priced: an unpriced
                    # session and a free one are different claims.
                    "total_cost_usd": (
                        round(self._total_cost_usd, 6)
                        if self._total_cost_usd
                        else None
                    ),
                    "duration_s": round(time.monotonic() - self._started_at, 3),
                }
            )
            self._log_io.close()

    # ---------- private ---------------------------------------------------

    def _default_dir(self):
        return Path(runtime.config().dir) / self.DEFAULT_SESSION_DIR

    # session_id and at are appended last, so they are the final two keys of
    # every line — key order is part of the output, since the .jsonl is the
    # artifact this step is judged on.
    #
    # timespec="seconds": Ruby's Time#iso8601 emits no fractional seconds, and
    # Python's isoformat() defaults to microseconds.
    #
    # separators + ensure_ascii=False: Ruby's JSON.generate is compact and emits
    # raw UTF-8. The default json.dumps would write ", " / ": " and escape the
    # em dash in the "(tool use — N calls)" text as —.
    def _write_log(self, event):
        event = {
            **event,
            "session_id": self.session_id,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self._log_io.write(
            json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
        )
        self._log_io.flush()
        # After the write and flush: a subscriber must not be able to stop the
        # line landing on disk.
        for subscriber in self._subscribers:
            subscriber(event)

    def _generate_session_id(self):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{secrets.token_hex(4)}"

    def _serialize_message(self, msg):
        return {"role": msg.role, "content": msg.content}

    # Note the asymmetry with the event builders above: only this block drops
    # its None values. tool_result deliberately keeps "error": null and
    # turn_end keeps "tokens": null.
    def _execution_metadata(self, *, task, backend, usage):
        if task is None and backend is None and usage is None:
            return {}

        tokens = self._usage_tokens(usage)
        metadata = {
            "task": self._task_name(task),
            "provider": self._provider_name(backend),
            "model": backend.model if backend else None,
            "usage_unit": getattr(backend, "usage_unit", None),
            "usage_level": getattr(backend, "usage_level", None),
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": self._estimate_cost(backend, tokens),
        }
        return {k: v for k, v in metadata.items() if v is not None}

    # task_name is a classmethod, so it must be *called*. Ruby's
    # `task.task_name` reads as an attribute but is already a method call;
    # transcribed literally, Python would hand json.dumps a bound method.
    def _task_name(self, task):
        if task is None:
            return None
        if hasattr(task, "task_name"):
            return task.task_name()

        return str(task)

    # Anthropic -> anthropic, OpenAI -> open_ai, OllamaCloud -> ollama_cloud.
    # Ruby splits "::" off the class name first; Python's __name__ has no
    # namespace to strip.
    def _provider_name(self, backend):
        if backend is None:
            return None

        return re.sub(
            r"([a-z\d])([A-Z])", r"\1_\2", type(backend).__name__
        ).lower()

    # The key-alias table moved to usage.py in step 12: Agent needs the same
    # integers for its turn budget and the TUI for its live counters, and three
    # copies of one provider quirk is how they drift apart.
    def _usage_tokens(self, usage):
        return usage_mod.tokens(usage)

    # `is None`, not truthiness: a genuine 0-token count is truthy in Ruby and
    # falsy in Python, and would silently report "no cost known".
    def _estimate_cost(self, backend, tokens):
        if backend is None or not hasattr(backend, "estimate_cost"):
            return None
        if tokens["input"] is None or tokens["output"] is None:
            return None

        return backend.estimate_cost(
            input_tokens=tokens["input"], output_tokens=tokens["output"]
        )
