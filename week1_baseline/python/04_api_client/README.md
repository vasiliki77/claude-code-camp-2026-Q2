# 04 · The API Client (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/04_api_client`](../../ruby/04_api_client/README.md).
Same behaviour, same `.boukensha/` config directory — see that README for the
design spec (what `Client` is for, and what the raw response looks like per
provider). This file covers only what is Python-specific.

> ⚠️ The Ruby step-04 README has drifted. Its "New Files" table lists
> `backends/base.rb`, `tasks/base.rb`, `tasks/player.rb`, and `prompts/system.md`
> as new — all four arrived in step 03 — and its "Output eaxmple" block was
> captured on a different machine against a different model, from a code path
> that no longer exists. Read it for intent; take no file list or output from it.

This step is step 03 plus a `Client` and an `ApiError`. Step 03 built the
payload; this one finally sends it. One POST, one parsed response, no tool loop
yet — though with these two tools registered the model already replies with a
`tool_use` block, which is what step 05 exists to handle.

## Environment

There is **one shared virtualenv at the repo root** (`.venv/`), reused by every
Python step folder. Create it once from the repo root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/04_api_client/requirements.txt
```

Built and tested against Python 3.12. `requirements.txt` is unchanged from
steps 00–03 — the client uses only the standard library — so if you already
made the venv there is nothing to install.

Requires `ANTHROPIC_API_KEY` in `.boukensha/.env` (or the environment). **This
step makes a real, billable API call.**

## Run

```sh
./week1_baseline/bin/python/04_api_client
```

```
=== BOUKENSHA Step 4: API Client ===

Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Sending request to https://api.anthropic.com/v1/messages...

Raw response:
{
  "id": "msg_…",
  "type": "message",
  "role": "assistant",
  "model": "claude-haiku-4-5-20251001",
  "content": [
    { "type": "tool_use", "id": "toolu_…", "name": "list_directory", "input": { "path": "." } }
  ],
  "stop_reason": "tool_use",
  "usage": { "input_tokens": 693, "output_tokens": 53 }
}
```

## Verification — the stdout gate does not apply here

Steps 00–03 were verified with `diff <(ruby) <(python)`. **That cannot work from
this step onward.** The output now contains a live model response: the wording,
the token counts, and the `id` change on every run, so two perfectly correct
implementations would produce different bytes. It also costs money per run.

Four narrower checks replace it. All four pass for this port:

1. **Deterministic-prefix diff** — everything before the response is fixed:
   ```sh
   diff <(./week1_baseline/bin/ruby/04_api_client | head -6) \
        <(./week1_baseline/bin/python/04_api_client | head -6)
   ```
2. **Structural check** — both runs return the same top-level keys
   (`content`, `id`, `model`, `role`, `stop_details`, `stop_reason`,
   `stop_sequence`, `type`, `usage`). Compare key sets, not values. This is the
   real claim of the step: the payload was accepted and parsed.
3. **Error path, free** — a bogus key returns 401, which is deliberately *not*
   retryable, so it fails on the first attempt and costs nothing:
   ```sh
   ANTHROPIC_API_KEY=sk-ant-invalid ./week1_baseline/bin/python/04_api_client
   ```
   Both languages raise with the identical message
   `API request failed after 1 attempt (401): {…}` — note the singular
   "attempt" — differing only in the server-generated `request_id`.
4. **Retry logic, offline** — the live call never exercises backoff, so a
   throwaway `http.server` covers it: 503×2 then 200 succeeds on attempt 3 with
   sleeps of 0.5 and 1.0; 503 forever raises `ApiError` "after 4 attempts" with
   sleeps 0.5/1.0/2.0; a 404 fails immediately with no sleep; a refused
   connection exhausts all four attempts. Run from the scratchpad — this repo
   deliberately has no test framework, and the example is still the smoke test.

## Layout

```
boukensha/
  __init__.py        # public surface: + Client, ApiError
  config.py          # Config — dir resolution, .env + settings.yaml, PROMPTS_DIR
  client.py          # Client — POST, retry/backoff, ApiError                 (new)
  prompt_builder.py  # PromptBuilder — delegates serialization to a backend
  errors.py          # UnknownToolError, ApiError, UnsupportedModelError    (edited)
  backends/          # anthropic, gemini, ollama, ollama_cloud, openai + base
  context.py  message.py  tool.py  registry.py
  tasks/             # base.py, player.py — unchanged this step
prompts/
  system.md          # new persona text                                    (edited)
examples/
  example.py         # runnable smoke test — read_file + list_directory tools
requirements.txt     # python-dotenv, PyYAML (pinned) — unchanged
```

## Differences from the Ruby version

- **`urllib.request`, not `requests`.** The Ruby README is explicit that using
  `net/http` rather than a gem is the point: the HTTP call should be visible,
  not hidden behind a library. `requests` would be about a third of the code and
  would be the first runtime dependency added since step 00, so the stdlib call
  stands. `requirements.txt` is untouched.

- **`urllib.error.HTTPError` must be caught before `URLError`.** This is the one
  structural trap in the step. Ruby's `Net::HTTP#request` *returns* a response
  object whatever the status, so Ruby inspects `response.code` afterwards.
  `urlopen` instead **raises** `HTTPError` on any non-2xx — and `HTTPError`
  subclasses `URLError`, which is in the transient-error tuple. Reversed, every
  500 would be swallowed as a transient connection failure, the status-code
  retry list would never run, and the bug would look like a flaky network.

- **The SSL setup evaporates.** Ruby sets `OpenSSL::SSL::VERIFY_PEER` and
  carries a commented-out `ca_file` line about macOS vs Linux/WSL2 certificate
  paths; the Ruby README devotes a section to it. `urlopen` verifies against the
  system trust store by default, so there is nothing to configure. Same shape as
  step 02's `transform_keys`: the problem does not exist here, and inventing an
  `ssl.SSLContext` to have something to point at would be cargo cult.

- **An explicit `timeout=60`, which Ruby does not write.** Ruby inherits
  `Net::HTTP`'s 60-second open/read defaults. Python's `urlopen` with no
  `timeout` uses the global socket default — normally "block forever" — so a
  hung connection would hang the example instead of retrying, and the transient
  path would never fire. Matching Ruby's *behaviour* here required writing a
  line Ruby did not need.

- **Exception class names cannot match.** Ruby's transient-exhaustion message
  interpolates `e.class` and prints `Errno::ECONNREFUSED`; Python's
  `type(e).__name__` prints `URLError`, because urllib wraps the underlying
  `OSError`. The message shape is identical; the class name is not, and cannot
  be without faking it.

- **`PROMPTS_DIR` stays correct here — a deliberate divergence.** Ruby step 04
  changed it to `File.expand_path("../../../prompts", __dir__)`, which resolves
  to `week1_baseline/ruby/prompts` — one level *above* the step folder, at a
  path that does not exist — while the `prompts/system.md` it is meant to find
  sits inside the step. Every Ruby step from 04 through 11 carries the same
  form. It is invisible today only because `prompt_override.system: true` routes
  the player task to `.boukensha/prompts/player/system.md`, so the packaged
  default is never read; it would break the moment anyone set that flag to
  `false`. Python keeps `parents[1] / "prompts"`, which resolves to the real
  directory. This is one of the few places the port knowingly does not mirror
  Ruby — worth raising upstream rather than propagating eight more times.

- **`tasks/base.py` needed no change this step.** Ruby fixed an error message
  that said `settings.yml` and added a Hash guard to `fetch`. Python has said
  `settings.yaml` since step 00 and its `_fetch` already guarded with
  `isinstance(settings, dict)` — Ruby caught up to Python, not the other way
  round.

- **`backends/__init__.py` keeps importing `Base`.** Ruby's `boukensha.rb`
  dropped its `backends/base` require this step, which is a no-op there because
  each backend file requires `base` itself. Removing the Python import to
  "match" would break `backends.Base` for anyone subclassing it, for no gain.

- Carried over from earlier steps: `Tool`/`Message` are `@dataclass`es while
  everything with behaviour is a plain class; tools are registered with the
  `@registry.tool(...)` decorator; backends are reached as `backends.Anthropic`;
  `PyYAML` is a deliberate third-party exception; a missing `settings.yaml`
  raises `FileNotFoundError`.
