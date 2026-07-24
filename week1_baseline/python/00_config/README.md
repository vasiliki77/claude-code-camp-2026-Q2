# 00 · Configuration (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/00_config`](../../ruby/00_config/README.md). Same
behaviour, same `.boukensha/` config directory, same example output — see that
README for the full design spec (config-dir resolution order, directory
structure, config schema). This file covers only what is Python-specific.

## Environment

There is **one shared virtualenv at the repo root** (`.venv/`), reused by every
Python step folder — you create it once, not per step. Create it from the repo
root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/00_config/requirements.txt
```

Built and tested against Python 3.12. The `.venv/` directory is git-ignored;
each new step folder that adds dependencies just re-runs the `pip install`
above against its own `requirements.txt` (they are identical across the early
steps).

## Run

```sh
./week1_baseline/bin/python/00_config
```

The launcher invokes the repo-root venv's interpreter directly (no `activate`
needed) and prints:

```
=== Boukensha Step 0: Configuration ===

Config dir:     <repo>/.boukensha
Tasks:          player

-- player task --
Provider:       anthropic
Model:          claude-haiku-4-5
Prompt override?true
System prompt:  You are a MUD Journey Player Agent. You are playing the MUD ...

MUD host:       localhost:4000
MUD user:       dummy

API key set?    true

#<Boukensha::Config dir=<repo>/.boukensha tasks=player>
```

This output is byte-for-byte identical to the Ruby version — verify with:

```sh
diff <(./week1_baseline/bin/ruby/00_config) <(./week1_baseline/bin/python/00_config)
```

## Layout

```
boukensha/
  __init__.py        # public surface: Config, Base, Player
  config.py          # Boukensha Config — dir resolution, .env + settings.yaml loading
  tasks/
    base.py          # abstract stateless task (provider/model/prompt resolution)
    player.py        # concrete Player task (task_name = "player")
prompts/
  system.md          # default system prompt shipped with the library
examples/
  example.py         # runnable smoke test (this step has no separate test suite)
requirements.txt     # python-dotenv, PyYAML (pinned)
```

## Differences from the Ruby version

- **`PyYAML` is a third-party dependency.** YAML is in Ruby's standard library
  but not Python's. Keeping a shared `settings.yaml` between both
  implementations was judged more valuable than the "standard-library-first"
  rule, so `PyYAML` is taken as a deliberate exception.
- **Missing `settings.yaml` raises instead of returning `{}`.** The Ruby
  silently falls back to an empty hash when the file is absent, which is what
  made the config bug on 2026-07-24 surface later as an opaque `nil` crash.
  The Python raises `FileNotFoundError` naming the resolved config dir, so the
  real problem is reported where it happens.
- **No string/symbol key handling.** Ruby does `node[key.to_s] || node[key.to_sym]`
  because YAML keys are strings but callers pass symbols. Python has no symbols,
  so every such lookup collapses to a single `dict.get`.
