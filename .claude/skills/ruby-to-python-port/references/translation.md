# Ruby → Python idiom catalogue

Every entry here comes from an idiom that actually appeared in this port. Append
new ones as you hit them — the catalogue is what makes step 12 cheaper than
step 04.

## Contents

- [Truthiness and nil](#truthiness-and-nil) — the trap that silently changes behaviour
- [Ranges and slicing](#ranges-and-slicing)
- [Symbols](#symbols)
- [Blocks](#blocks)
- [Methods, attributes, naming](#methods-attributes-naming)
- [Exceptions](#exceptions)
- [Keyword arguments and defaults](#keyword-arguments-and-defaults)
- [Collections and ordering](#collections-and-ordering)
- [Paths and files](#paths-and-files)
- [JSON](#json)
- [Module structure](#module-structure)

---

## Truthiness and nil

**The one that bites.** In Ruby only `nil` and `false` are falsy — `0`, `0.0`,
`""`, and `[]` are all truthy. In Python all of those are falsy. A literal
translation of a Ruby truth-check silently changes behaviour whenever the value
can legitimately be zero or empty.

| Ruby | Python | Note |
|---|---|---|
| `return nil unless in_cost && out_cost` | `if in_cost is None or out_cost is None: return None` | Step 03 `estimate_cost`. Local Ollama models cost `0.0` — truthy in Ruby, falsy in Python. A literal port reports "price unknown" for every free model |
| `x \|\| default` | `x if x is not None else default` | …when `0`/`""`/`[]` are valid values |
| `x \|\| default` | `x or default` | …when they are not. Both appear in this repo; pick per-case, don't apply one blindly |
| `value&.method` | `value.method() if value else None` | Safe navigation |
| `node[:key]` returning `nil` | `node.get("key")` | |
| `hash.fetch(:key)` | `hash["key"]` | Both raise on a missing key — that is the point of `fetch` |

Watch for the deliberate mix: Ruby step 03's `Backends::Base` uses `fetch` for
required metadata and `[]` for optional `usage_level`. Preserve the asymmetry
(`["…"]` vs `.get("…")`) — it encodes which keys are required.

## Ranges and slicing

Ruby's `..` ranges are **inclusive**; Python slices are exclusive. Off-by-one
here is invisible until the stdout diff fails.

| Ruby | Python |
|---|---|
| `str[0..40]` | `str[:41]` |
| `str[0..60]` | `str[:61]` |
| `str.slice(0, 60)` | `str[:60]` — `slice(start, length)` is already exclusive |

Also check whether a trailing `...` in a `to_s` is conditional or unconditional.
In this repo `Message#to_s` appends it unconditionally, even when the content is
shorter than the truncation point.

## Symbols

Python has no symbols. Most symbol machinery in the Ruby collapses to nothing —
resist the urge to reproduce it.

| Ruby | Python |
|---|---|
| `:user`, `:tool_result` | `"user"`, `"tool_result"` |
| `node[key.to_s] \|\| node[key.to_sym]` | `node.get(key)` — the dance exists only because YAML keys are strings and callers pass symbols |
| `args.transform_keys(&:to_sym)` before `block.call(**args)` | `block(**args)` — Python kwargs are already strings, so the translation step vanishes |
| `msg.role.to_s` | `msg.role` |
| `hash.keys.map(&:to_s)` | `list(hash)` |
| `case x when :a … when :b` | `if x == "a": … elif x == "b":` |
| `usage_unit: :tokens` | `"usage_unit": "tokens"` |

When a Ruby gymnastic disappears entirely, **say so in the Python README**.
Step 02's Ruby README calls `transform_keys(&:to_sym)` a production gotcha; a
reader comparing the two needs to be told the problem does not exist in Python
rather than left hunting for it.

## Blocks

| Ruby | Python |
|---|---|
| `registry.tool("move", …) do \|direction:\| … end` | `@registry.tool("move", …)` decorating `def move(direction): …` |
| `&block` parameter | The decorator's inner function takes the callable and returns it undecorated, so the name stays callable |
| `->(x) { … }` stored, not called | `lambda x: …` |

The decorator form is the settled choice for this repo. Have the decorator
return the function unchanged so `move(...)` still works directly.

## Methods, attributes, naming

| Ruby | Python |
|---|---|
| `attr_reader :dir` | plain public attribute `self.dir` |
| `def to_s` | `def __str__` |
| `def inspect = to_s` | `__repr__ = __str__` |
| `class << self; private` | `_`-prefixed methods |
| `@context` (no reader) | `self.context` — Python has no real privacy and later steps read it |
| `def validate_model!` | `def validate_model` — no `!` convention |
| `def prompt_override?` | `def prompt_override` — no `?` convention |
| `def self.foo(x)` | `@classmethod def foo(cls, x)` |
| Parenless call `b.context_window` | `@property`, so the call site keeps reading the same |

**Name collisions.** Ruby happily defines a class method and an instance method
with the same name (`Backends::Base.model_info(model)` and `#model_info`).
Python cannot. Keep the name on whichever one is part of the documented public
surface and rename the other — step 03 kept the classmethod `model_info(cls,
model)` and stored the instance's metadata as `self.info`.

## Exceptions

| Ruby | Python |
|---|---|
| `StandardError` | `Exception` — never `BaseException`, which slips past ordinary `except` |
| `raise ArgumentError, "msg"` | `raise ValueError("msg")` |
| `raise NotImplementedError` | same name, same meaning |
| `ENV.fetch("KEY")` | `os.environ["KEY"]` — both raise on missing |
| `begin … rescue Foo => e` | `try: … except Foo as e:` |

Error **message text** must match byte-for-byte when the example prints it —
step 02's `No tool registered as 'flee'` is part of the stdout gate, single
quotes included. When the message is never printed, match the shape but use
Python's natural form (`cls.__name__`, `{value!r}`) rather than faking a
`::`-qualified Ruby class name.

## Keyword arguments and defaults

| Ruby | Python |
|---|---|
| `def f(a:, b: nil)` | `def f(self, *, a, b=None)` — keyword-only |
| `def f(host: "x", model:)` | `def f(self, *, model, host="x")` — **reorder** |
| `def f(args = {})` | `def f(self, args=None)` then `args or {}` — never a mutable default |

Ruby allows a required keyword after a defaulted one; Python does not. Reorder
the signature. Because both are keyword-only, call sites do not change — note
the reorder in the README so it doesn't read as an accident.

## Collections and ordering

Insertion order is guaranteed in both languages, and in this repo it is
**output-visible**: tool registration order and payload key order both show up
in the printed JSON. Build dicts in the same order the Ruby builds its hashes.

| Ruby | Python |
|---|---|
| `hash.each_value { \|v\| … }` | `for v in d.values(): …` |
| `hash.values.map { \|x\| … }` | `[… for x in d.values()]` |
| `array.empty?` | `not array` |
| `hash.keys.sort.join(", ")` | `", ".join(sorted(d))` |
| `a + b` (arrays) | `a + b` (lists) |
| `hash.size` | `len(d)` |

## Paths and files

| Ruby | Python |
|---|---|
| `File.join(Dir.home, ".boukensha")` | `Path.home() / ".boukensha"` |
| `Pathname.new(raw).expand_path` | `Path(raw).expanduser().resolve()` — `expanduser()` is required, `expand_path` expands `~` |
| `File.expand_path("../../prompts", __dir__)` | `Path(__file__).resolve().parents[1] / "prompts"` — count the levels against the actual layout |
| `File.exist?(p) ? File.read(p).strip : nil` | `p.read_text().strip() if p.exists() else None` |
| `require_relative "../lib/boukensha"` | `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` before the import |
| `ENV["X"] \|\|= …` | `os.environ.setdefault("X", …)` |

The example's climb to the repo root is **4 levels** in both trees
(`examples/` → step → language → `week1_baseline/` → root), so `parents[4]`.
This has been miscounted once already; verify it rather than copying by eye.

## JSON

`json.dumps(payload, indent=2)` matches Ruby's `JSON.pretty_generate`
byte-for-byte — same indent, same `": "` separator, empty containers as `{}` /
`[]`, single-element arrays expanded across lines. Verified in step 03.

Pass `ensure_ascii=False`. Ruby emits non-ASCII raw; Python escapes it by
default. Nothing in the fixtures triggers it today, but a prompt edit would
break the gate in a way that looks unrelated to the edit.

Ruby symbol hash keys stringify on serialization, so `{ role: "user" }` and
`{"role": "user"}` produce identical JSON.

## Module structure

| Ruby | Python |
|---|---|
| `lib/boukensha.rb` requires | `boukensha/__init__.py` imports + `__all__` |
| `module Boukensha; module Backends` | the `boukensha/backends/` subpackage |
| `Boukensha::Backends::Anthropic` | `from boukensha import backends` → `backends.Anthropic` |

Export the subpackage rather than flattening: `Backends::Base` and
`Tasks::Base` collide on the name `Base` at the top level, and the namespaced
form mirrors the Ruby call site anyway.

Keep `__init__.py` import order matching the Ruby `require_relative` order —
free consistency, and it makes the two files diffable side by side.
