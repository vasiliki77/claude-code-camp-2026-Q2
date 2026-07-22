# Week 0

## Technical Goal

Explore multiple agent architectures — plain agent file, Agent Skills, a filesystem-discovered subagent, an SDK-constructed subagent, and n8n — to determine which fits a live, stateful agent workload: playing a text MUD (tbaMUD/CircleMUD at `localhost:4000`). The bootcamp's stated primary challenge for the underlying task: level up enough to defeat the Massive Minotaur in the Newbie zone.

Deviation from that primary challenge: the week's actual output centers on comparing the five architectures and hardening the shared connection tooling (`mud.py`) rather than completing a full playthrough to the Minotaur fight. Architecture 4 (n8n) did not get built at all this week — see Conclusions.

## Technical Uncertainty

- Whether a spawned subagent's execution is visible enough to catch it going wrong — what it's actually doing turn to turn, and what it's costing in tokens — or whether problems only surface after the fact, e.g. from a wedged terminal.
- Whether a general coding-harness agentic loop (Claude Code) is a good fit for driving a real-time, stateful text-game character, or whether it needs a custom loop instead.
- Whether an LLM — especially a small one (Haiku 4.5) — can manage a telnet MUD's login and text UI without deterministic scripting underneath it.
- Whether plain markdown files are sufficient as a persistent memory store for player/world state as complexity grows.
- Whether porting the same underlying script between invocation mechanisms (skill → filesystem-discovered subagent → SDK-constructed subagent) would carry over cleanly or break.
- Whether two characters/agents could run concurrently against the same MUD infrastructure without interfering with each other.
- Whether n8n's Python (Beta) code node could realistically host `mud.py`'s daemon-based session manager.

## Technical Hypotheses

- A plain agent file with no dedicated tooling would struggle with the login handshake and real-time combat, since those are deterministic/stateful flows better handled by code than re-derived by a model every turn.
- Giving the agent a dedicated skill/script (a "MUD SDK") would resolve the connection problem and allow reliable play.
- Porting the same script from a skill to a filesystem-discovered subagent, then to a programmatically-defined subagent, would be architecturally "free" since the underlying script doesn't change.
- Markdown memory files would be adequate for player/world state at this scale.
- Since n8n advertises a Python (Beta) code node, `mud.py` could likely be pasted in with minimal changes.

## Technical Observations

Full day-by-day detail, exact room ids, error strings, and xp numbers are in [20-07-2026](20-07-2026.md), [21-07-2026](21-07-2026.md), and [22-07-2026](22-07-2026.md). Summary:

- **Architecture 1 (plain agent file)** failed to log in reliably even after scaling the model up from Haiku 4.5 to Sonnet 4.6. It invented throwaway connection scripts instead of reusing a stable interface, and went hunting through unrelated files when its login attempts failed.
- **Architecture 2 (Agent Skill)** succeeded once the login flow was grounded against the real server rather than assumed — a `PRESS RETURN` gate between password and account menu would have desynced any fixed send-sequence. Combat turned out to be asynchronous, forcing two distinct primitives (`send`, which waits for the next prompt, and `read`, which drains unsolicited output). Server toggles (`autoexits`/`autoloot`/`autogold`) are flips, not switches, and persist across sessions — naively re-enabling them at every login silently disables them every other session.
  - Playing with the skill surfaced two failure modes in the *game*, not the tooling: a pitch-black dungeon with no light source that a `reset` (quit + reconnect) could not escape, since tbaMUD stores location server-side; and a passive town guard joining a fight uninvolved to it, dropping HP 22 → 3. Both were fixed by reading the world's generated JSON data (`wld`/`zon`/`mob`) as ground truth instead of guessing from live `look`/`scan` text.
- **Architecture 3a (filesystem-discovered subagent)** ported the same skill with zero logic changes, and every break was a path or a missing bundled asset (`references/`, `data/`), never the underlying script. Running the port also surfaced pre-existing bugs in the memory-extraction regexes that had been silently producing wrong output (e.g. a location parser returning `"You are hungry."` as a room name) rather than failing loudly.
- **Architecture 3b (SDK-constructed `AgentDefinition`)** hit a harness-naming mismatch (the subagent tool is called `Agent`, not `Task`) that, combined with restricting the orchestrator's own tool list, caused subagent spawning to fail outright. A live concurrency bug then appeared when running two characters (`dummy`, `smarty`) as simultaneous subagents: `mud.py`'s state directory was keyed only by `host-port`, so both shared one daemon and one socket. A stuck subagent's own ad-hoc workaround script (written to handle character creation, which `mud.py` didn't yet support) looped infinitely against a rejected server prompt — that loop, not the daemon, is what wedged the session.
- **Architecture 4 (n8n)** did not get built. No Claude API key exists for this account, since creating one requires platform credits and there are none. Installed n8n and ran it on localhost, and watched the lecture covering this architecture, but nothing beyond that. Started investigating adapting `mud.py` into an n8n Python (Beta) code-node tool and found a likely structural blocker worth flagging even though it stopped short of being tested live: that node runs on Pyodide (Python compiled to WASM), which has no raw sockets, no `subprocess`, no real OS threads, and no state persisting between node executions — so `mud.py`'s daemon architecture could not run inside the node itself; it would need an HTTP-wrapper daemon running outside n8n instead.

## Technical Conclusions

Revisiting each hypothesis:

- **Confirmed:** the plain agent file was a poor fit for the login flow — it needed to be handled deterministically in code, not re-derived by a model each run.
- **Confirmed, with a caveat:** a dedicated skill/script did fix connection reliability, but that only moved the risk up a layer. The two real failures of the week (the unrecoverable dark room, the town-guard ambush) were both in *deciding what to do*, not in the connection tooling — `mud.py` handled movement, combat, and resting correctly throughout.
- **Refuted:** the ports across invocation mechanisms were not free. Every one broke — on relative paths, missing bundled assets, or a harness tool-name mismatch — even though the underlying script's logic was untouched in every case. Identity and discovery mechanics (skill vs. filesystem-subagent vs. SDK-subagent) are a real cost of porting, distinct from the code itself.
- **Partially refuted:** markdown memory was adequate at this scale, but the regex-based extraction from game transcripts silently produced confident wrong data until the port forced it to actually be exercised — "adequate" needs "and independently verified by running it," not just "compiles and writes a file."
- **Unresolved:** whether n8n's Python (Beta) node can host `mud.py` directly remains untested rather than disproven — the Pyodide sandbox constraints make it look unlikely, but this was blocked before any live attempt.
- **Confirmed as a real gap, not just a hunch:** the `smarty` subagent's ad-hoc `create_char.py` and its infinite retry loop against a rejected class prompt were invisible until they had already wedged the session — there was no way to see what the subagent was doing, or what it was spending in tokens, while it was still running. This matches a gap the instructor's own Architecture 2 notes had already flagged (`docs/explore_architectures.md`: "we need auditable visibility of the agent for reporting token/usage and to review the player journey") and this week supplied a concrete incident of it.

New uncertainty for later weeks: whether an HTTP-wrapped daemon is the right n8n integration shape once API credits are available; whether the agent's own strategic/goal-decomposition layer — not the connection tooling — needs dedicated design, per the Explorer-Mode/Risk-Mode sketch in `docs/explore_architectures.md`; and how to get real-time visibility into a running subagent's actions and token spend rather than discovering problems only after something has already wedged.

Next steps: get Claude API credits to unblock Architecture 4; if n8n integration proceeds, add an HTTP interface to `mud.py`'s daemon rather than relying on the Python (Beta) node running the daemon itself.

## Key Takeaway

Every architecture failure this week was in the surrounding scaffolding — paths, tool names, shared state keys, sandbox constraints — never in `mud.py`'s core connection logic, which is the strongest signal yet that the daemon design is sound and the real remaining risk sits one layer up, in the strategy that decides what the agent does with it.
