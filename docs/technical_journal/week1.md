# Week 1

## Technical Goal

Instructor's stated goal (Week 1 Plan slide):

Build the **Baseline Agent** — a custom agent architecture that implements every part of an agent (config, registry, prompt building, API client, agent loop, logging, run DSL, REPL loop, global executable, standard tool library, TUI, context management — the `week1_baseline/ruby/00_config` through `12_context` steps) without using an Agent SDK.

Deliberately not using an Agent SDK so we can:
- Learn how all the parts work.
- Avoid an SDK's genericity/bias — SDKs tend to be tightly coupled to a specific provider or library, which may not suit our use case.

Gameplan:
- Get each step of the agent working in Ruby first.
- Port the working code to our language of choice (e.g. Python).
- Update the Agent Baseline Architecture Diagram after each step.

Once finished, this baseline agent becomes the "golden template" to reuse whenever building an agent going forward.

## Technical Uncertainty

- Whether hand-rolling REST calls to five separate LLM backends (Anthropic, OpenAI, Gemini, Ollama, Ollama Cloud) behind one normalized shape is worth the complexity it adds versus using an SDK — the plan deliberately avoids SDKs to avoid their genericity/bias, but that means absorbing every provider's own request/response schema by hand.
- Whether a config-driven `.boukensha/` directory (settings, secrets, prompts, session logs) will hold up structurally as more steps layer on top of `00_config`, or whether early schema choices will need reworking later.
- Whether the Ruby `MudManager` gem can be reused as-is from a Python port later in the week, given the plan is to build in Ruby first and port afterward.
- Whether avoiding third-party libraries (per the "standard library first" design constraint) is sustainable — `dotenv` was already an early exception.

## Technical Hypotheses

- Building every agent component from scratch (config, registry, prompt building, API client, loop, logging, DSL, REPL, global executable, tool library, TUI, context management) will surface exactly how each part works in a way that an Agent SDK would hide.
- A `~/.boukensha`-style external config directory, overridable via `BOUKENSHA_DIR`, is the right shape for something meant to be deployable on multiple servers.
- Getting each step working in Ruby first, then porting to Python, will make the porting step mostly mechanical since the underlying design won't change — a hypothesis Week 0 already partly refuted for a different kind of port (skill → subagent), worth watching for whether the same holds here.

## Technical Observations

Day-by-day detail is in [24-07-2026](24-07-2026.md), [27-07-2026](27-07-2026.md), [28-07-2026](28-07-2026.md) and [31-07-2026](31-07-2026.md). Summary so far:

- **Step 0 (Configuration)** — first run of `week1_baseline/bin/00_config` failed twice before working: once on a missing `dotenv` gem (`bundle install` fixed it), once on a config file that was both misnamed (`settings.yml` instead of the `settings.yaml` the code looks for) and misplaced (repo root instead of the directory `BOUKENSHA_DIR` actually resolves to). The underlying failure — `Config` silently returning `{}` when no settings file is found, rather than erroring — meant the real problem (file not found) surfaced several calls later as an opaque `NoMethodError` on `nil`, not as a config error.
- **Step 1 (Struct Skeleton)** — ported the three plain data containers (`Tool`, `Message`, `Context`) from Ruby to Python. Ruby `Struct`s became Python `@dataclass`es; `Context` stayed a plain class in both. The port was applied as the delta between step 0 and step 1 (the step-1 Python folder started as a copy of the step-0 one), which bore out the earlier hypothesis that porting is mostly mechanical when the design doesn't change. Verification is a literal `diff` of the Ruby and Python example output, which is empty — the byte-for-byte match required matching Ruby's `to_s` exactly (inclusive-range off-by-ones, an always-appended `...`, and Ruby symbol-form key rendering `[:direction]`).

- **Step 2 (The Tool Registry)** — ported `Registry` and `UnknownToolError`, again as a delta over the previous step's Python folder, again verified by an empty `diff` of the two programs' output. This step is the first place the "porting is mostly mechanical" hypothesis bent: two constructs had no direct Python equivalent and needed a design decision rather than a translation. Ruby registers a tool by passing a block, which became a Python decorator (`Registry.tool` returns a decorator that registers the function and hands it back unchanged). And Ruby's `dispatch` must convert string keys to symbols before calling the block — a gotcha the Ruby README calls out as a real production concern — which **disappears entirely** in Python, where keyword arguments are already strings. The port is therefore not just a different spelling of the same code; one of the lessons the Ruby step exists to teach does not exist in the target language, and the Python README had to say so explicitly to avoid contradicting the Ruby one.
- **Documentation drifted from code, and only running it caught that.** The Ruby step-2 README's "Expected Output" block does not match what the Ruby program prints (it shows a `budget=8192` field that no longer exists and omits the `Config:` line). Since the port's whole verification strategy is diffing against Ruby's real stdout, the expected output had to be captured by running the Ruby example rather than read from its documentation.

- **Step 3 (Prompt Builder)** — ported `PromptBuilder`, `Backends::Base` and five backends. Stdout `diff` still empty, but the example exercises only Anthropic, so verification was extended: all five backends' payloads, headers, URLs and cost metadata dumped from both languages and diffed. The recurring theme of this step is that Ruby and Python disagree on truth. Ruby's `0.0` is truthy, Python's is falsy, so `estimate_cost`'s guard had to become `is None` or every free local model would report an unknown price.

- **Step 4 (API Client) — the byte-for-byte stdout gate stopped working.** The example now makes a live API call, so its output is non-deterministic and billable; two correct implementations produce different bytes. Verification had to be rebuilt around what *is* deterministic: a fixed-length prefix diff, a response key-set comparison, a free 401 exercising the error path, and an offline HTTP server covering retry/backoff. This is the first step where "diff the two programs" — the strategy every earlier step relied on — is simply unavailable, and it will stay unavailable for the rest of the week.

- **Step 5 (Agent Loop) — the delta was much larger than the new file suggested.** `agent.rb` is new, but all five backends changed too, and the loop only stays simple *because* they did: every provider now normalizes its response into one shape, so the agent never sees a raw provider payload. Two Ruby-vs-Python truthiness differences sat in the critical path, and one was dangerous — `wrap_up` disables tools by passing an empty list, which is falsy in Python, so the obvious port would have re-enabled every tool during the one call whose purpose is to stop the agent, silently defeating the iteration ceiling.

- **The cheap cross-language check keeps finding real bugs.** Feeding canned provider responses through both implementations and diffing the JSON caught a wire-format defect in step 5: Ruby's `#to_json` is compact, Python's `json.dumps` is not, and that string is OpenAI's `function.arguments`. The Anthropic-only example would never have surfaced it. Pattern confirmed over three steps: whatever the example does not exercise needs its own throwaway gate.

- **Two upstream Ruby bugs found and left unfixed.** `PromptBuilder#to_messages` is broken for three of five backends (arity mismatch) and survives unchanged to step 12. `PROMPTS_DIR` resolves outside the step folder to a directory that does not exist, in every step from 04 to 11, masked only because the player task overrides its prompt. Ruby is upstream and is not edited during a port; the first was mirrored, the second was fixed on the Python side by decision.

- **Skills were tried for the port workflow and abandoned as too costly and slow.** A `ruby-to-python-port` skill was written, then an A/B evaluation was attempted with two subagents on step 04. Each subagent starts cold and re-derives context the session already holds: the baseline burned 61,235 tokens and ~234 seconds and produced no plan at all, stopping to ask a clarifying question first. Both runs were abandoned with zero artifacts. The baseline also found the same non-obvious problems unaided, so the skill's marginal value was never demonstrated. Writing the plans directly in-session produced steps 04 and 05 for a fraction of the cost. Reusable instructions are not free when the reuse mechanism discards the context that made the work cheap.

## Technical Conclusions

_(To be filled in at the end of Week 1.)_

## Key Takeaway

_(To be filled in at the end of Week 1.)_
