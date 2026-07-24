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

Day-by-day detail is in [24-07-2026](24-07-2026.md). Summary so far:

- **Step 0 (Configuration)** — first run of `week1_baseline/bin/00_config` failed twice before working: once on a missing `dotenv` gem (`bundle install` fixed it), once on a config file that was both misnamed (`settings.yml` instead of the `settings.yaml` the code looks for) and misplaced (repo root instead of the directory `BOUKENSHA_DIR` actually resolves to). The underlying failure — `Config` silently returning `{}` when no settings file is found, rather than erroring — meant the real problem (file not found) surfaced several calls later as an opaque `NoMethodError` on `nil`, not as a config error.

## Technical Conclusions

_(To be filled in at the end of Week 1.)_

## Key Takeaway

_(To be filled in at the end of Week 1.)_
