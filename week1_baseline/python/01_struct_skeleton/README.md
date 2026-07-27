# 01 · The Struct Skeleton (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/01_struct_skeleton`](../../ruby/01_struct_skeleton/README.md).
Same behaviour, same `.boukensha/` config directory, same example output — see
that README for the full design spec (the field-by-field description of `Tool`,
`Message`, and `Context`). This file covers only what is Python-specific.

This step is step 00 plus three plain data containers — the shapes the agent
passes around. No logic yet.

## Environment

There is **one shared virtualenv at the repo root** (`.venv/`), reused by every
Python step folder — you create it once, not per step. Create it from the repo
root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/01_struct_skeleton/requirements.txt
```

Built and tested against Python 3.12. The `.venv/` directory is git-ignored.
This step's `requirements.txt` is identical to step 00, so if you already made
the venv for 00 there is nothing to install.

## Run

```sh
./week1_baseline/bin/python/01_struct_skeleton
```

The launcher invokes the repo-root venv's interpreter directly (no `activate`
needed) and prints:

```
=== Boukensha Step 1: Struct Skeleton ===

Config:   #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Context:  #<Context task=player turns=2 tools=1>
Tool:     #<Tool name=move description=Move the player in a direction (north, so params=[:direction]>
Messages:
  #<Message role=user content=Explore north and tell me what you find....>
  #<Message role=assistant content=Sure, let me head north and take a look....>
```

This output is byte-for-byte identical to the Ruby version — verify with:

```sh
diff <(./week1_baseline/bin/ruby/01_struct_skeleton) <(./week1_baseline/bin/python/01_struct_skeleton)
```

## Layout

```
boukensha/
  __init__.py        # public surface: Config, Base, Player, Tool, Message, Context
  config.py          # Boukensha Config — dir resolution, .env + settings.yaml loading
  tool.py            # Tool  — name, description, parameters, block (a callable)
  message.py         # Message — role, content, tool_use_id
  context.py         # Context — task, system, messages, tools (+ register/add helpers)
  tasks/
    base.py          # abstract stateless task (provider/model/prompt resolution)
    player.py        # concrete Player task (task_name = "player")
examples/
  example.py         # runnable smoke test (this step has no separate test suite)
requirements.txt     # python-dotenv, PyYAML (pinned)
```

No packaged `prompts/` directory this step — as in the Ruby version, the
example resolves its system prompt through the user override in
`.boukensha/prompts/player/system.md`.

## Differences from the Ruby version

- **`Tool` and `Message` are `@dataclass`es.** Ruby uses `Struct.new(...)`; the
  Python dataclass is its direct analogue (positional fields, generated
  `__init__`), with a hand-written `__str__` for the display format. `Context`
  is a plain class in both, since it carries behaviour.
- **`to_s` display is matched byte-for-byte**, which pins two Python-specific
  choices so `diff` against Ruby stays empty:
  - Ruby's inclusive ranges `[0..40]` / `[0..60]` become the exclusive slices
    `[:41]` / `[:61]`, and the trailing `...` is always appended.
  - `Tool` renders its parameter keys as `[:direction]` (Ruby symbol form), not
    Python's `['direction']`.
- Carried over from step 00: `PyYAML` is a deliberate third-party exception;
  a missing `settings.yaml` raises `FileNotFoundError` rather than silently
  returning `{}`; and there is no string/symbol key dance (Python has no
  symbols).
