# Step 8 — Global Executable

Package BOUKENSHA as a gem so the `boukensha` command works from anywhere on your machine.

## What this step adds

- `boukensha.gemspec` — declares the gem: name, version, which files to include, and the `bin/boukensha` executable
- `bin/boukensha` — the shebang script that becomes the global command
- `lib/boukensha_loader.rb` — resolves *which step folder* to load from, then boots the REPL
- `lib/boukensha.rb` + `lib/boukensha/` — step 7's lib, bundled as the default

## Install

```bash
cd 09_global_executable
gem build boukensha.gemspec
gem install boukensha-0.9.0.gem
```

After that, `boukensha` is on your `$PATH` and works from any directory.

## Settings: BOUKENSHA_PATH and BOUKENSHA_DIR

The loader owns two settings. Each resolves the same way and independently of
the other: **env var → `~/.boukensharc` → built-in default.**

| Setting | What it selects | Default |
|---------|-----------------|---------|
| `BOUKENSHA_PATH` | which step folder's lib to run | the lib bundled in the gem |
| `BOUKENSHA_DIR` | config dir: `settings.yaml`, `.env`, `prompts/` | `~/.boukensha` |

`BOUKENSHA_PATH` must point to a step folder that contains `lib/boukensha.rb`;
the loader aborts if it doesn't. `BOUKENSHA_DIR` is not checked — a config dir
with no `settings.yaml` yet is a normal state, and `Boukensha::Config` treats it
as empty.

## ~/.boukensharc

Permanent defaults for both, as `KEY=value` lines:

```
# Which step folder's lib the `boukensha` command loads.
BOUKENSHA_PATH=~/Sites/boukensha/09_global_executable

# Config dir: settings.yaml, .env, prompts/
BOUKENSHA_DIR=~/Sites/boukensha/.boukensha
```

Blank lines and `#` comments are ignored. A line with no `=` is read as
`BOUKENSHA_PATH`, so the original one-line format still works:

```bash
echo ~/Sites/boukensha/08_the_repl_loop > ~/.boukensharc
```

An env var always beats the rc file, per setting — so you can override just the
config dir for one run and leave the step selection alone:

```bash
BOUKENSHA_DIR=~/projects/mybot/.boukensha boukensha
```

**The rc file is read by the *installed* gem's loader, not the step folder's.**
After editing `lib/boukensha_loader.rb`, rebuild and reinstall for the change to
take effect (see Install above).

## Running a specific step

```bash
# step 7 (interactive REPL)
BOUKENSHA_PATH=~/Sites/boukensha/07_the_repl_loop boukensha

# step 6 doesn't have a REPL — loader tells you how to run it
BOUKENSHA_PATH=~/Sites/boukensha/06_the_run_dsl boukensha
# => boukensha: the step at .../06_the_run_dsl does not support the interactive REPL
#    Run its examples directly, e.g.: ruby .../06_the_run_dsl/examples/*.rb
```

## Debug mode

Shows both resolved settings, so you can see which step and which config dir you
actually got:

```bash
BOUKENSHA_DEBUG=1 boukensha
# => [boukensha] loading from: /path/to/step
#    [boukensha] config dir:   /path/to/.boukensha
```

## The key idea

The gem is just a **wrapper and a default**. All the teaching material stays in the numbered step folders exactly as it was. The gem doesn't copy or symlink anything — it just knows where to look.
