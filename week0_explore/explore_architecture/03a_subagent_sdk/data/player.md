# Player

Character state. The `- **Field**: value` lines under Vitals are rewritten in
place by `update_memory.py`, so keep their exact shape. Everything else is
free-form and edited by hand.

## Vitals

- **Level**: 1
- **HP**: 22 / 22
- **Mana**: 100 / 100
- **Moves**: 80 / 83
- **Experience**: 760 / 1240
- **Current Room**: The Temple Of Midgaard

`Experience` reads *earned / still needed for the next level* — not a fraction
of a total. 760 earned + 1240 needed = 2000 for level 2.

Last synced: 2026-07-21, from a live session.

## Character

- Name: `dummy` (password `helloworld`), age 17
- Rank: Dummy the Swordpupil
- Armor class 90/10, alignment 12, 22 gold coins
- 0 quest points, not on a quest

## Status flags to clear

- **Hungry** and **thirsty** as of last sync. Both silently cap HP and move
  regeneration even while resting, so clear them before any farming run.
- There is no fountain in the Temple itself — it is one room away on Temple
  Square. `drink fountain` inside the Temple returns "You can't find it!"

## Equipment

- A small sword was bought for 78g at the Weapon Shop on Main Street.
  Bare-fisted attacks missed constantly before it; the miss rate dropped
  measurably once armed.
- **Unverified:** whether it is currently wielded. Run `send equipment` at
  session start — a carried-but-unwielded weapon still leaves you punching.

## Goals

- [ ] **Primary:** reach level 7 and defeat the Massive Minotaur in the Newbie zone
- [ ] **Next up:** reach level 2 — 1240 exp to go at level-1 mob rates
- [x] Escape the dark sewer complex under the Guild of Swordsmen (path in [[world]])
- [x] Buy a weapon

## Playbook

1. `start`, then `setup --wimpy 8` (wimpy ≈ one third of max HP).
2. `send equipment` — confirm the sword is wielded.
3. Clear hunger/thirst at the Temple Square fountain.
4. `send look` before every fight, not just `consider`. `consider` grades the
   target only, and says nothing about guards standing by who will join in.
5. Farm the rooms listed in [[world]]; run `update_memory.py` after each level.
