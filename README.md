# Claude Code Camp
This is the official repo for the Claude Code Camp operated by [ExamPro](https://www.exampro.co)

## Technical Journal

Bootcamp learning log under [`docs/technical_journal/`](docs/technical_journal/), one weekly summary (Technical Goal / Uncertainty / Hypotheses / Observations / Conclusions / Key Takeaway) backed by a detailed log per day.

- [Week 0 summary](docs/technical_journal/week0.md) — architecture comparison and key takeaway for the week.
  - [20-07-2026](docs/technical_journal/20-07-2026.md) — Repository setup, environment setup, Architecture 1 (Plain Agent File).
  - [21-07-2026](docs/technical_journal/21-07-2026.md) — Architecture 2 (Agent Skills), memory/goal tracking, the dungeon-trap and town-guard incidents, Architecture 3a (subagent port).
  - [22-07-2026](docs/technical_journal/22-07-2026.md) — Architecture 3b (programmatic `AgentDefinition`), Architecture 4 (n8n, blocked on API credits).
- [Week 1 summary](docs/technical_journal/week1.md) — plan: build the Baseline Agent (no SDK) in Ruby, then port.
  - [24-07-2026](docs/technical_journal/24-07-2026.md) — Step 0 (Configuration): missing `dotenv` gem, `settings.yaml` filename/location fix.
  - [27-07-2026](docs/technical_journal/27-07-2026.md) — Step 1 (Struct Skeleton): Ruby → Python port of the `Tool`/`Message`/`Context` data containers.
  - [28-07-2026](docs/technical_journal/28-07-2026.md) — Step 2 (The Tool Registry): Ruby → Python port of `Registry`/`UnknownToolError`, block → decorator, stale Ruby README output.
  - [31-07-2026](docs/technical_journal/31-07-2026.md) — Steps 3–5 (Prompt Builder, API Client, Agent Loop): five backends, the stdout gate breaking on live API calls, two upstream Ruby bugs, and a port skill abandoned as too costly.
  - [01-08-2026](docs/technical_journal/01-08-2026.md) — Running `log_viz` (the session JSONL read as traces rather than logs), Steps 6–8 (The Logger, The Run DSL, The REPL Loop): the JSONL becomes the verification artifact, `instance_eval` has no Python equivalent, step 07 turns out to be branched from before step 06, step 08's real subject is persisting the assistant reply — and three counted-`..` path bugs in one day, ending with `BOUKENSHA_DIR` moving out of every example into the launchers. Then Step 9 (Global Executable): the installed gem is a fourth entry path the launcher fix cannot reach, `~/.boukensharc` gains a second key, and why Python needs no step 9 — plus what to keep when extracting both agents after the bootcamp.
  - [02-08-2026](docs/technical_journal/02-08-2026.md) — Running the steps rather than porting them: a launcher renamed on a misread of the step-vs-folder numbering, `bundle check || bundle install` added to all 12 launchers, `mud_manager` built but never installed (and bundler blaming its author), and the confusion worth recording — `boukensha` and `bin/ruby/<step>` are not two doors into the same room.
