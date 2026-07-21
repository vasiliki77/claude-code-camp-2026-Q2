# TBAMUD / CircleMUD field guide

Verified against the running server at `localhost:4000` (TBAMUD 2025, DikuMUD
lineage). Read this when you need a command you don't know, or when something
in the game behaves unexpectedly.

## Contents

- [Reading the prompt](#reading-the-prompt)
- [Movement and navigation](#movement-and-navigation)
- [Looking around](#looking-around)
- [Combat](#combat)
- [Survival: health, hunger, thirst](#survival-health-hunger-thirst)
- [Items and equipment](#items-and-equipment)
- [Money and shops](#money-and-shops)
- [Character progression](#character-progression)
- [Communication](#communication)
- [Useful toggles](#useful-toggles)
- [Full command list](#full-command-list)

## Reading the prompt

```
22H 100M 83V (news) (motd) >
```

`H` hit points, `M` mana, `V` movement. Movement is spent per room and
regenerates while resting. `(news)`/`(motd)` just flag unread bulletins.

`mud.py` parses this into the `[hp | mana | moves]` footer on every call, so
you always see current vitals without asking. HP is the number that matters:
it is the difference between playing and respawning at the temple.

## Movement and navigation

Directions: `north` `south` `east` `west` `up` `down`, plus diagonals
`ne` `nw` `se` `sw`. Abbreviations (`n`, `s`, `e`, `w`, `u`, `d`) work.

`[ Exits: n e s w d ]` on the room description lists the ways out — this is
the single most important line for navigating, which is why the skill turns
`autoexits` on.

Other movement: `enter <thing>`, `leave`, `open`/`close`/`lock`/`unlock <dir>`,
`follow <person>`, `recall` back to the temple on some builds.

Dark rooms print `It is pitch black...` and hide everything, including mobs
and exits. You need a lit light source (`hold torch`) to see. Walking blind
into a dark room is a common way to get ambushed.

## Looking around

| Command | What it gives you |
|---|---|
| `look` | Full room description, exits, items, who is present |
| `look <thing>` / `examine <thing>` | Detail on an object, mob, or feature |
| `scan` | Mobs in *adjacent* rooms and their direction — scout before you walk |
| `exits` | Just the exit list |
| `where` | Locate players/mobs in the zone |
| `map` / `automap` | ASCII minimap, if the build supports it |
| `areas` | Zones and their level ranges |

`scan` is the safest habit in the game: it tells you what is one room away
before you are standing next to it.

## Combat

Combat is **round-based and asynchronous**. You start a fight, then the server
pushes a message every few seconds until someone dies or flees. This is the
one place where the difference between `send` and `read` matters most:
`send "kill X"` returns only the opening round, and the rest of the fight
arrives on its own and must be collected with `read`.

Always `consider <target>` first. The reply grades the matchup:

| Reply | Meaning |
|---|---|
| "You can kill it easily" / "Fairly easy" | Safe |
| "The perfect match!" | Even fight — real risk at low level |
| "You would need some luck" | Dangerous |
| "Are you mad!?" / "You ARE mad!" | Will kill you |

Commands: `kill <target>` (or `hit`), `flee` to escape (costs movement and can
fail — try again), `assist <player>`, `rescue <player>`, `bandage`.
Class skills: `kick`, `bash`, `backstab`, `whirlwind`, `cast '<spell>' <target>`.

`flee` early rather than late. A fled fight costs a little experience; a lost
one costs equipment and a corpse run. When HP drops under roughly a third,
disengage — the server will not warn you before the killing blow.

Mobs wander between rooms. `kill fido` failing with *"That player is not
here"* usually means it walked away, not that you mistyped — `look` or `scan`
to find where it went.

After a kill: `get all from corpse`, or let `autoloot`/`autogold` do it.

## Survival: health, hunger, thirst

`rest` then `stand` — resting regenerates HP, mana, and movement far faster
than standing. `sleep`/`wake` is faster still but leaves you defenceless.

Hunger and thirst tick up over time and print `You are hungry.` /
`You are thirsty.` Ignored long enough they stop regeneration and eventually
damage you. `eat <food>`, `drink <container>`, `drink <fountain>`.
Fountains are free — there is one on the Temple Square. Inns and shops sell
food cheaply.

## Items and equipment

`get <item>` / `get all` / `get all from <container>`, `drop`, `put <item> <container>`,
`give <item> <person>`, `inventory` (`i`), `equipment` (`eq`).

To use gear you must equip it: `wear <item>` for armour, `wield <weapon>` for
weapons, `hold <item>` for lights and wands. Carrying a sword does nothing —
an unwielded weapon is dead weight, and a fresh character with `Nothing.` in
`equipment` is fighting bare-handed.

`remove <item>` to take gear off. `junk`/`donate`/`sacrifice` to discard.

## Money and shops

Coins are gold. `gold` shows what you carry; `balance`, `deposit`, `withdraw`
at a bank (there is an ATM in the Temple of Midgaard).

In a shop: `list` to see stock, `buy <item>`, `sell <item>`, `value <item>`
for an appraisal before selling.

## Character progression

`score` is the character sheet: level, HP/mana/moves, armour class, alignment,
experience, gold, and how much experience remains to the next level.

`practice` at a guild spends practice sessions on skills and spells — this is
how skills improve. `levels` shows the experience table, `title` sets your
title, `save` writes the character to disk.

## Communication

Room: `say <msg>` (`'` is shorthand), `emote`. Private: `tell <player> <msg>`,
`reply`, `whisper`, `ask`.
Global: `gossip`, `shout`, `holler`, `auction`, `grats`.
Group: `group`, `gsay`/`gtell`, `follow`, `split` shared coins.

`who` lists who is online. On a quiet development port this is often just you.

## Useful toggles

`toggle` with no argument prints the whole preference table — current values
for every setting below. Read it before changing anything.

**These are toggles, not switches.** This server ignores a trailing `on`, so
`autoexits on` flips the current value rather than setting it. The values also
persist on the character between sessions, so a blind "enable" at each login
turns the setting off every other time. `mud.py setup` avoids the trap by
reading the table first and sending only the commands that are out of place.

- `autoexits` — always print the exit list (essential for navigation)
- `autoloot` — take items from corpses automatically
- `autogold` — take coins from corpses automatically
- `autosac` — sacrifice corpses automatically
- `autoassist` — join group members' fights
- `autosplit` — share coins with your group

Avoid `brief`: it suppresses room descriptions on movement, which removes the
context needed to decide where to go. It saves output at the cost of sight.

`toggle wimpy <hp>` makes the character flee automatically once HP drops below
the threshold — the single most useful safety setting for unattended play,
since it fires between tool calls when nothing is watching. `toggle wimpy 0`
turns it off; `toggle wimpy` reports the current value. Unlike the on/off
toggles this sets an absolute number, so re-sending it is harmless.

`display` and `prompt` customise the prompt — leave the `H/M/V` fields in
place, since `mud.py` parses them for the vitals footer. `pagelength` (default
22) controls how often output is paged.

## Full command list

Verified via `commands` on this server:

```
'  :  afk  alias  areas  assist  ask  astat  auction  autoassist  autodoor
autoexits  autogold  autokey  autoloot  automap  autosac  autosplit  backstab
balance  bandage  bash  brief  bug  buy  cast  check  clear  close  cls
commands  compact  consider  credits  deposit  diagnose  display  donate  down
drink  drop  east  eat  emote  enter  equipment  examine  exits  fill  flee
follow  gemote  get  give  gold  gossip  grab  grats  group  gsay  gtell
happyhour  help  hide  hindex  history  hit  hold  holler  house  identify
idea  immlist  info  inventory  junk  kick  kill  leave  levels  list  lock
look  mail  map  motd  news  ne  noauction  nogossip  nograts  norepeat
noshout  nosummon  notell  north  northeast  northwest  nw  offer  open  order
page  pick  policy  pour  practice  prefedit  prompt  put  qsay  quaff  quest
qui  quit  read  receive  recite  remove  rent  reply  report  rescue  rest
return  sacrifice  save  say  scan  score  se  sell  shout  sip  sit  sleep
sneak  socials  south  southeast  southwest  split  stand  steal  sw  take
taste  tell  time  title  toggle  track  typo  unfollow  unlock  up  use
value  version  visible  wake  weather  wear  west  where  whirlwind  whisper
who  whoami  whois  wield  withdraw  wizlist  write
```

`help <keyword>` documents any of them in game. Long help output is paged;
`mud.py` walks the pager automatically.
