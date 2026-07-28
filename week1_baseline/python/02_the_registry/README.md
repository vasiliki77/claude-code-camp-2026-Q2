# 02 · The Tool Registry (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/02_the_registry`](../../ruby/02_the_registry/README.md).
Same behaviour, same `.boukensha/` config directory, same example output — see
that README for the full design spec (what the Registry is for and how dispatch
works). This file covers only what is Python-specific.

This step is step 01 plus a `Registry` and an `UnknownToolError`. Tools are no
longer built by hand and pushed onto the context — they are registered *through*
the registry, and called by name.

## Environment

There is **one shared virtualenv at the repo root** (`.venv/`), reused by every
Python step folder — you create it once, not per step. Create it from the repo
root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/02_the_registry/requirements.txt
```

Built and tested against Python 3.12. The `.venv/` directory is git-ignored.
This step's `requirements.txt` is identical to steps 00 and 01, so if you
already made the venv there is nothing to install.

## Run

```sh
./week1_baseline/bin/python/02_the_registry
```

The launcher invokes the repo-root venv's interpreter directly (no `activate`
needed) and prints:

```
=== BOUKENSHA Step 2: Tool Registry ===

Config:  #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Context: #<Context task=player turns=0 tools=2>
Tools:
  #<Tool name=move description=Move the player in a direction (north, so params=[:direction]>
  #<Tool name=shout description=Shout a message so everyone in the zone c params=[:message]>

Dispatching 'shout' with message='dragon spotted'...
Result: DRAGON SPOTTED

Dispatching 'move' with direction='north'...
Result: You move north into a torch-lit corridor.

UnknownToolError caught: No tool registered as 'flee'
```

This output is byte-for-byte identical to the Ruby version — verify with:

```sh
diff <(./week1_baseline/bin/ruby/02_the_registry) <(./week1_baseline/bin/python/02_the_registry)
```

## Layout

```
boukensha/
  __init__.py        # public surface: + Registry, UnknownToolError
  config.py          # Boukensha Config — dir resolution, .env + settings.yaml loading
  tool.py            # Tool  — name, description, parameters, block (a callable)
  message.py         # Message — role, content, tool_use_id
  context.py         # Context — task, system, messages, tools (+ register/add helpers)
  errors.py          # UnknownToolError                                    (new)
  registry.py        # Registry — registers tools, dispatches calls by name (new)
  tasks/
    base.py          # abstract stateless task (provider/model/prompt resolution)
    player.py        # concrete Player task (task_name = "player")
examples/
  example.py         # runnable smoke test (this step has no separate test suite)
requirements.txt     # python-dotenv, PyYAML (pinned)
```

`message.py` is untouched and unused by this step's example (`turns=0`) — as in
the Ruby version, it stays for the steps that follow.

## Differences from the Ruby version

- **A Ruby block becomes a Python decorator.** Ruby registers a tool by passing
  a block:

  ```ruby
  registry.tool("shout", description: "...", parameters: { message: { type: "string" } }) do |message:|
    message.upcase
  end
  ```

  Python has no block syntax, so `Registry.tool` returns a decorator and the
  decorated function *is* the block:

  ```python
  @registry.tool("shout", description="...", parameters={"message": {"type": "string"}})
  def shout(message):
      return message.upper()
  ```

  The decorator returns the function undecorated, so `shout(...)` remains
  callable directly. Registration still happens on the `Context` — the registry
  holds a reference to it, exactly as in Ruby.

- **Ruby's string-to-symbol dance has no Python equivalent.** The Ruby README
  flags `dispatch` converting string keys to symbols
  (`args.transform_keys(&:to_sym)`) as a real production gotcha: the API returns
  string-keyed JSON, but Ruby blocks take symbol keywords. Python keyword
  arguments *are* strings, so `dispatch` calls `tool.block(**args)` on the API's
  dict directly. There is nothing to translate — the problem simply does not
  exist here.

- **`UnknownToolError` subclasses `Exception`**, the analogue of Ruby's
  `StandardError` — not `BaseException`, which would slip past ordinary
  `except` handlers.

- **Parameter keys are strings, not symbols.** Ruby's
  `{ direction: { type: "string" } }` becomes
  `{"direction": {"type": "string"}}`. `Tool.__str__` re-adds the `:` prefix
  when rendering, so the printed `params=[:direction]` still matches Ruby.

- Carried over from earlier steps: `Tool`/`Message` are `@dataclass`es and
  `Context`/`Registry` are plain classes; `to_s` display is matched
  byte-for-byte (inclusive Ruby ranges `[0..40]` / `[0..60]` become the
  exclusive slices `[:41]` / `[:61]`, trailing `...` always appended); `PyYAML`
  is a deliberate third-party exception; a missing `settings.yaml` raises
  `FileNotFoundError` rather than silently returning `{}`.
