---
name: ruby-to-python-port
description: Ports one step of the Boukensha Ruby baseline (week1_baseline/ruby/NN_*) into its Python counterpart (week1_baseline/python/NN_*) — first as a written plan under docs/plans/python_port/, then as the execution of that plan once the user has answered its Open Questions. Use this whenever the user mentions porting a step, carrying the latest Ruby changes over to Python, writing or executing a port plan, or names a step folder like 03_prompt_builder or 04_api_client. Also use it when they say something looser like "port the next step", "do the Python version of this", "execute the plan", or when they ask why the Ruby and Python outputs differ — the stdout-diff gate in here is the answer to that question.
---

# Ruby → Python port (Boukensha, week 1)

## The shape of the work

`week1_baseline/` holds thirteen self-contained snapshots of the same agent, in
two languages:

```
week1_baseline/
  ruby/{00_config … 12_context}/     lib/boukensha/…, examples/example.rb, prompts/
  python/{00_config … }/             boukensha/…,     examples/example.py, prompts/
  bin/ruby/NN_name                   launcher: bundle exec ruby examples/example.rb
  bin/python/NN_name                 launcher: <repo>/.venv/bin/python examples/example.py
docs/plans/python_port/NN_name       one plan per step, no file extension
```

Ruby is upstream and always finished first. Each step *N* starts life as a
byte-for-byte copy of step *N-1* and is edited in place — the duplication is
deliberate, because it makes `diff step-N step-N+1` the definition of what that
iteration added.

That gives the port its central move: **you are never porting a whole step.**
The Python folder for step *N* is already a copy of Python step *N-1*, so the
work is exactly the delta that Ruby added between *N-1* and *N*. Find that delta
mechanically, and the port stops being a translation exercise and becomes a
checklist.

Both languages read the same repo-root `.boukensha/` (settings, `.env`, prompt
overrides) and share one repo-root `.venv/`. Neither is per-step.

## Two phases, with the user in between

Phase 1 writes a plan. The user then annotates it — usually by typing answers
directly under the Open Questions as sub-bullets. Phase 2 executes it. They are
separate invocations: when the user says "write the plan", stop after phase 1;
when they say "execute plan @docs/plans/python_port/NN_name", read their
annotations first and go.

---

## Phase 1 — write the plan

### 1. Establish the delta

```sh
# What Ruby added this step — the authoritative change list
diff -ru week1_baseline/ruby/{NN-1}_prev week1_baseline/ruby/NN_name --exclude=Gemfile.lock

# Confirm the Python folder really is an untouched copy of the previous step
diff -rq week1_baseline/python/{NN-1}_prev week1_baseline/python/NN_name -x __pycache__
```

The second command should print nothing. If it prints differences, someone has
already started — say so and fold their work into the plan rather than writing a
plan that pretends the folder is pristine.

### 2. Read every Ruby file the diff touched

Read them in full, not in excerpt. A port that misses a default argument or a
key ordering fails the gate at the end, and it is much cheaper to read the file
than to debug the diff.

### 3. Run the Ruby example and capture its real output

```sh
./week1_baseline/bin/ruby/NN_name
```

**The Ruby READMEs' "Expected Output" blocks are unreliable** — step 02's shows
`budget=8192` and omits a whole line. The running program is the specification;
the README is a description of it that has drifted. Capture the real stdout and
paste that into the plan's Verification section.

### 4. Write the plan

Write to `docs/plans/python_port/NN_name` — no file extension, matching the
existing four. Follow `references/plan-template.md`, which has the section
skeleton and explains what each section is for. Consult
`references/translation.md` while filling in the translation tables — it is the
accumulated catalogue of Ruby idioms that have already bitten this port, with
the Python form that works.

### 5. Flag every judgment call as an Open Question, with a recommendation

The user answers these inline and their answers become binding for later steps.
Give each one a `*Recommend:*` line with the reasoning, so answering is a yes/no
rather than an essay. Questions already settled in an earlier plan belong under
**Decisions (carried over)** instead — re-asking them wastes the user's time and
invites the two ports to drift apart.

### 6. Stop

Do not start editing Python files. The Open Questions are open.

---

## Phase 2 — execute the plan

Read the plan *including the user's inline annotations* — they appear as
sub-bullets under the Open Questions and they override the recommendations.
Then work the checklist.

Do the whole checklist, including the README rewrite at the end. The Python
step README is the one place where the deliberate divergences from Ruby get
recorded; skipping it is how the two implementations quietly drift.

### The gate

```sh
diff <(./week1_baseline/bin/ruby/NN_name) <(./week1_baseline/bin/python/NN_name)
```

Empty output is the definition of done. This single command catches string
truncation off-by-ones, `__str__` formatting, dict/hash ordering, JSON
indentation, and tool registration order all at once — which is why the ports
match Ruby's `to_s` output verbatim even where a Pythonic form would read
better. Diffability is worth more than idiom here.

Also confirm the Python program exits `0`, and run whatever extra checks the
plan's Verification section lists.

### Cover what the example does not

The example exercises one path — one backend, one provider, one code branch.
Anything the plan added that the example never touches is unverified by the
gate. When that happens, write a throwaway script in the scratchpad that
exercises the untouched paths in both languages and diff those outputs too.

Step 03 shipped five backends and the example ran one; dumping all five
backends' payloads, headers, URLs, and cost metadata from both languages and
diffing the JSON took one extra round-trip and proved the other four. That is
the pattern: if it isn't in the gate, put it in a temporary gate of your own.

---

## House rules

**Never edit the Ruby side.** Ruby is upstream. If you find a bug there — a
stale README, an arity mismatch, a typo in a prompt — say so and let the user
decide. Silently fixing it makes every future step-to-step diff carry your
delta, which is exactly the property that makes this repo teachable.

**Mirror Ruby's bugs, then document them.** Step 03's `PromptBuilder#to_messages`
raises for three of five backends, and the same shape survives to step 12. The
Python port reproduces it and explains why in the README. A port that
"improves" as it goes stops being comparable, and comparability is the point.

**Simplify where Ruby was working around Ruby.** The opposite case. Ruby's
`node[key.to_s] || node[key.to_sym]` dance exists because YAML gives strings
and callers pass symbols; Python has no symbols, so it collapses to one lookup.
Likewise `args.transform_keys(&:to_sym)` before calling a block — Python kwargs
are already strings, so the whole step disappears. Do not port the workaround
and then invent a Python problem for it to solve. Note the disappearance in the
README so a reader comparing the two isn't left wondering.

**Do not port uncommitted Ruby fixes without checking.** Run `git diff` on the
Ruby step. Step 03's working tree had a `BOUKENSHA_DIR` depth fix that Python
never needed — the Python path arithmetic was already correct.

**Prefer the honest divergence to the fake match.** Where Python genuinely
cannot mirror Ruby — a required parameter after a defaulted one, two methods
sharing a name across class and instance — pick the form that works, keep the
call sites identical, and write down why in the README's "Differences from the
Ruby version" section.

## Reference files

- `references/plan-template.md` — the plan document skeleton, section by
  section, with what each section is for. Read this before writing a plan.
- `references/translation.md` — Ruby → Python idiom catalogue: the truthiness
  traps, range/slice off-by-ones, symbol handling, blocks-as-decorators,
  exception mapping, JSON parity. Read this while writing the plan's
  translation tables, and again while executing. **Append to it** whenever a
  step turns up a new idiom — that is what keeps step 12 cheaper than step 04.
