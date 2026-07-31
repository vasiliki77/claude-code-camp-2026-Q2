# 03 · The Prompt Builder (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/03_prompt_builder`](../../ruby/03_prompt_builder/README.md).
Same behaviour, same `.boukensha/` config directory, same example output — see
that README for the full design spec (the per-provider format tables for system
prompts, tool results, tool definitions, and message roles, plus the model
metadata keys). This file covers only what is Python-specific.

This step is step 02 plus a serialization layer. Nothing calls an API yet — the
`PromptBuilder` delegates to a backend, and the backend turns the `Context` into
the exact payload one provider expects.

## Environment

There is **one shared virtualenv at the repo root** (`.venv/`), reused by every
Python step folder — you create it once, not per step. Create it from the repo
root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/03_prompt_builder/requirements.txt
```

Built and tested against Python 3.12. The `.venv/` directory is git-ignored.
This step's `requirements.txt` is identical to steps 00–02 — the new code needs
only the standard library's `json` — so if you already made the venv there is
nothing to install.

## Run

```sh
./week1_baseline/bin/python/03_prompt_builder
```

The launcher invokes the repo-root venv's interpreter directly (no `activate`
needed). With `.boukensha/settings.yaml` selecting `provider: anthropic` and
`model: claude-haiku-4-5`, it prints the header, the resolved provider/model,
and the Anthropic payload:

```
=== BOUKENSHA Step 3: Prompt Builder ===

Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
{
  "model": "claude-haiku-4-5",
  "system": "You are a MUD Journey Player Agent. ...",
  "max_tokens": 1024,
  "tools": [ { "name": "look", ... }, { "name": "move", ... } ],
  "messages": [ ... ]
}
```

The `system` value comes from `.boukensha/prompts/player/system.md` (the
`player` task sets `prompt_override.system: true`), not from this step's
packaged `prompts/system.md`.

This output is byte-for-byte identical to the Ruby version — verify with:

```sh
diff <(./week1_baseline/bin/ruby/03_prompt_builder) <(./week1_baseline/bin/python/03_prompt_builder)
```

`json.dumps(..., indent=2)` matches Ruby's `JSON.pretty_generate` exactly: same
indent, same `": "` separator, empty containers as `{}` / `[]`, single-element
arrays expanded across lines. `ensure_ascii=False` is passed so a non-ASCII
character in a prompt would be emitted raw, as Ruby does, rather than escaped.

## Layout

```
boukensha/
  __init__.py        # public surface: + PromptBuilder, UnsupportedModelError, backends
  config.py          # Boukensha Config — + PROMPTS_DIR (back after step 01)      (edited)
  tool.py            # Tool  — name, description, parameters, block (a callable)
  message.py         # Message — role, content, tool_use_id
  context.py         # Context — task, system, messages, tools
  errors.py          # UnknownToolError, UnsupportedModelError                    (edited)
  registry.py        # Registry — registers tools, dispatches calls by name
  prompt_builder.py  # PromptBuilder — delegates serialization to a backend       (new)
  backends/                                                                       (new)
    base.py          # model validation + model metadata (context window, pricing)
    anthropic.py     # https://api.anthropic.com/v1/messages
    gemini.py        # .../v1beta/models/{model}:generateContent
    ollama.py        # http://localhost:11434/api/chat
    ollama_cloud.py  # https://ollama.com/api/chat
    openai.py        # https://api.openai.com/v1/chat/completions
  tasks/
    base.py          # abstract stateless task (provider/model/prompt resolution)
    player.py        # concrete Player task (task_name = "player")
prompts/
  system.md          # packaged default system prompt (back after step 01)        (new)
examples/
  example.py         # runnable smoke test (this step has no separate test suite)
requirements.txt     # python-dotenv, PyYAML (pinned)
```

`prompts/system.md` and `Config.PROMPTS_DIR` were both deleted in step 01 and
both return here, mirroring Ruby: the example now passes `default_prompts_dir=`
so there is a packaged fallback when a task does not override its prompt.

## Differences from the Ruby version

- **Message roles are strings.** `Context.add_message` has taken strings since
  step 01, so Ruby's `case msg.role when :tool_result` becomes
  `if msg.role == "tool_result"`, and every `msg.role.to_s` disappears.

- **Payload keys are string keys, not symbols.** Ruby builds
  `{ role: "user", input_schema: {...} }`; Python builds
  `{"role": "user", "input_schema": {...}}`. `JSON.pretty_generate` stringifies
  symbol keys anyway, so the emitted JSON is identical. Key **order** is
  load-bearing — Python dicts preserve insertion order, so each `to_payload`
  lists its keys in the same order as its Ruby counterpart.

- **`estimate_cost` guards with `is None`, not truthiness.** Ruby writes
  `return nil unless input_cost && output_cost`, which is safe there because
  **`0.0` is truthy in Ruby**. In Python `0.0` is falsy, so the literal
  translation would report "no price known" for every local Ollama model — all
  of which cost exactly `0.0`. The guard is therefore
  `if input_cost is None or output_cost is None`. Ollama Cloud models, whose
  prices are genuinely `None` (plan-based, not token-based), still return
  `None`.

- **`Ollama.__init__` swaps its parameters.** Ruby writes
  `initialize(host: "http://localhost:11434", model:)`; Python cannot follow a
  defaulted parameter with a required one, so it is
  `__init__(self, *, model, host="http://localhost:11434")`. Both are
  keyword-only, so call sites are unchanged.

- **Ruby's two `model_info` methods split in two.** Ruby has a class-level
  `self.model_info(model)` (table lookup) and an instance-level `model_info`
  (the cached hash for this backend's model). Python cannot hold both names, so
  the classmethod keeps the name and the instance stores its metadata as
  `self.info`. The documented instance surface — `context_window`,
  `input_token_cost_per_million`, `output_token_cost_per_million`,
  `usage_unit`, `usage_level`, `estimate_cost` — is unaffected, and is exposed
  as properties so it reads like Ruby's parenthesis-free calls.

- **Backends live in a subpackage, reached as `backends.Anthropic`.** Ruby
  namespaces them as `Boukensha::Backends::Anthropic`. A flat
  `from boukensha import Anthropic` would work, but `Backends::Base` and
  `Tasks::Base` would then collide on the name `Base`, so the example does
  `from boukensha import backends` and calls `backends.Anthropic(...)`.

- **`validate_model` drops Ruby's `!` suffix** (no such convention in Python)
  and raises `UnsupportedModelError`, which subclasses `Exception` — the
  analogue of Ruby's `StandardError`, not `BaseException`. The message names
  the plain class (`OpenAI does not support model 'gpt-4o'. Supported models:
  …`) rather than a faked `::`-qualified Ruby path.

- **`PromptBuilder.to_messages` is broken for three of five backends — on
  purpose.** It calls `self.backend.to_messages(self.context.messages)`, but
  `OpenAI`, `Ollama`, and `OllamaCloud` define `to_messages(system, messages)`,
  so that delegator raises a `TypeError` for them. This is faithful to the Ruby
  baseline, where the same mismatch survives unchanged through step 12.
  `to_api_payload` is the path the example and every later step use, and it
  passes `context.system` correctly.

- **`ArgumentError` maps to `ValueError`** in the example's provider switch,
  consistent with `tasks/base.py`.

- Carried over from earlier steps: `Tool`/`Message` are `@dataclass`es while
  `Context`, `Registry`, `PromptBuilder`, and the backends are plain classes;
  tools are registered with the `@registry.tool(...)` decorator (Python's
  stand-in for a Ruby block); `to_s` display is matched byte-for-byte; `PyYAML`
  is a deliberate third-party exception; a missing `settings.yaml` raises
  `FileNotFoundError` rather than silently returning `{}`.
