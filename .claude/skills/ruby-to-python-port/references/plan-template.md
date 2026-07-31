# Plan document template

Write to `docs/plans/python_port/NN_name` — **no file extension**, matching the
existing plans. The sections below are the ones the four existing plans settled
into; each exists to answer a question the executing agent would otherwise have
to re-derive.

The plan is read later by an agent (or you, cold) with none of the context you
have right now. Everything it needs to avoid re-deriving the delta should be in
here. Concrete beats brief — plans in this repo run 250–450 lines and that has
been the right size.

---

## Skeleton

````markdown
# Port Plan — Step NN: <Step Name> (Ruby → Python)

<One paragraph: what is being ported and what the finished state prints.>

This is the <ordinal> of thirteen steps (`00_config` → `12_context`). Step NN is
substantively step NN-1 **plus <the delta in one phrase>**. <What does *not*
change.>

---

## Starting state (already done — do not redo)

<That python/NN_name already exists as a byte-for-byte copy of python/NN-1,
verified with `diff -rq … -x __pycache__`. That the repo-root .venv exists and
already has this step's deps. Which bin launchers exist and which do not.>

This plan is **not** "port step NN from scratch" — it is the exact set of edits
and additions that turn the copied folder into the real step NN.

---

## Decisions (carried over — settled, do not re-litigate)

<Bulleted list of every decision answered in an earlier plan that still binds:
shared repo-root .venv, snapshot-per-step, __str__ matched verbatim, dataclass
for value objects, decorator form for tools, FileNotFoundError divergence,
shared .boukensha/, no test framework, PyYAML exception. Carry the list forward
and add to it as the user settles new questions.>

---

## What Ruby changed between step NN-1 and step NN

Confirmed by diffing `ruby/NN-1_prev` against `ruby/NN_name`:

| Change | Ruby |
|---|---|
| **New** `lib/boukensha/x.rb` | <one line> |
| `lib/boukensha/y.rb` | <what changed> |
| `examples/example.rb` | <how it was rewritten> |

<Then: which files are byte-identical between the two Ruby steps, so the
executing agent knows not to touch their Python counterparts.>

> ⚠️ <Traps. Whitespace-only Ruby diffs that need no Python edit. Uncommitted
> Ruby working-tree changes and whether they apply. Anything reversed from an
> earlier step, like a deleted constant coming back.>

---

## Read before writing

| Ruby source (read this) | Purpose |
|---|---|
| … | … |

Supporting context (read for intent, do not port):

| File | Why |
|---|---|
| `ruby/NN_name/README.md` | <what it explains> |
| `week1_baseline/ruby/ITERATIONS.md` | <the relevant section> |

> ⚠️ <If the Ruby README's Expected Output block is stale, say so here and point
> at the Verification section instead.>

Live config consumed (do not modify): the repo-root `.boukensha/` — <which
settings this step actually reads>.

---

## The work — a checklist over the existing folder

### ➕ Add — <new modules>

<Per file: the Ruby source it comes from, then a two-column Ruby → Python table
for anything non-obvious. Inline the gotchas from references/translation.md that
actually apply, with the reason — the executing agent should not have to guess
why a guard is `is None` rather than a truth check.>

### ➕ Add — the launcher

`week1_baseline/bin/python/NN_name` — copy of the previous step's launcher with
both path segments changed; `chmod +x`.

### ✏️ Edit — <existing files>

<Exact edits. For __init__.py, the literal import block.>

### 🗑️ Delete

<Anything Ruby dropped this step. Omit the section if nothing.>

### ✅ Leave untouched (copied correctly from NN-1)

<List them explicitly. Saying what not to touch is as valuable as saying what
to change — it stops the executing agent from "tidying" a file that is already
correct.>

---

## Verification

Done when all pass:

1. `./week1_baseline/bin/ruby/NN_name` still runs unchanged.
2. `./week1_baseline/bin/python/NN_name` prints exactly:
   ```
   <the real captured stdout — from running the Ruby example, never from the
   Ruby README>
   ```
3. A literal diff of the two programs' stdout is **empty**:
   ```sh
   diff <(./week1_baseline/bin/ruby/NN_name) \
        <(./week1_baseline/bin/python/NN_name)
   ```
   This is the real gate. <Name what it catches for this step.>
4. The Python run exits `0`.
5. <Checks for anything the example does not exercise — a snippet that
   constructs the untouched code paths and asserts on them.>
6. <A grep that proves a specific Ruby-ism was not cargo-culted.>

---

## Open Questions

New to step NN; each lists a recommended default. (Everything under
**Decisions** is settled — do not resurface it.)

1. **<Question as a question?>** <The trade-off in two or three sentences.>
   *Recommend:* <the option, and why>.

2. …
````

---

## Notes on the sections

**Starting state** exists because the single most expensive mistake is treating
the port as from-scratch. It is a delta.

**Decisions** exists so the user is never asked the same thing twice. Every
question they answer graduates into this list in the next plan.

**Read before writing** is a reading list with a reason attached to each file,
split into "port this" and "read for intent". The second table stops the
executing agent from porting a README's prose into code.

**The work** is a checklist, not prose, so progress is countable. The ➕ / ✏️ /
🗑️ / ✅ markers let a reader see the shape of the change at a glance.

**Verification** must contain real captured output. Every plan's item 3 is the
stdout diff, because it subsumes most of the others.

**Open Questions** are the phase boundary. The user answers them inline as
sub-bullets under each question; those answers are binding and override the
recommendation. Questions with no real trade-off do not belong here — make the
call, state it in Decisions, and move on.
