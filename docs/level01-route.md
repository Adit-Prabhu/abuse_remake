# How the Level 1 route was found

`evidence/routes/level01.json` finishes Classic Level 1 from START in 1,414 ticks, about 94 s of
game time against a 9,000-tick limit. CI replays it (`tests/test_campaign_routes.py`).
`evidence/routes/solver/` holds the same kind of route from each checkpoint scenario's start:

| Situation | Ticks | Limit |
|---|---|---|
| `level01-cp1` | 1,440 | 2,700 |
| `level01-cp2` | 1,156 | 2,700 |
| `level01-cp3` | 337 | 2,700 |

These routes are evidence that each situation can be won under the ported rules. They come from
a privileged search over the engine's own state (`scripts/route_search.py`), so they are a
ceiling for what is possible, not a player.

## The level's puzzle

An unguided search wandered for hours. Level 1 is a chain of switches, a lift and teleporters,
and the A* distance the evaluator uses ignores all three. The way through, read from the level
file's objects and links:

1. From START, down to console 2: a lift, then the room whose floor is breakable.
2. Break the hidden floor, drop past the switch room at (720, 1080), go down the shaft into the
   long bottom corridor, and go along it to the lift at (2160, 1454).
3. **Ride the lift** up the shaft at x 2220 to the switch room, and throw the one-time switch at
   (1905, 705). Through two delay gates, it opens the trap door at (1680, 1469), far below.
4. Ride back down. Go through the trap door (and the breakable walls above and below it) to the
   lower chamber, then take the door teleporter at (2340, 1649) up to (1410, 914).
5. That room is a trap: two sensors wake nine spray-gun turrets. Stand on the teleporter at
   (1470, 1064), press down, and survive its animation to (1320, 659), by console 3.
6. From console 3, go right to the door teleporter at (2160, 569), up to (1710, 164), and right
   to the exit at (2715, 306). Press down there.

## The commands

These are run from the project folder. Each segment continues from the previous one with
`--prefix`, and `--via` gives the waypoints above. `--press 4` holds the action key for 4 ticks
at the switch. `--min-hp 1` lets the last segment cross the turret room: by default the search
drops any branch below 25 health.

```sh
R() { uv run python scripts/route_search.py --mode classic --level level01 --goal level02 "$@"; }
D=runs/level01-route
R --to 841,828 --budget 60000 --out $D/1-console2.json
R --prefix $D/1-console2.json --via "1050,1030;720,1080;510,1200;480,1400;1500,1430" \
   --to 2160,1440 --budget 150000 --out $D/2-lift.json
R --prefix $D/2-lift.json --via "2190,1100;2190,740" --to 1905,705 --press 4 --out $D/3-switch.json
R --prefix $D/3-switch.json --via "2190,740;2190,1100;2160,1440;1710,1430;1690,1560;2300,1640" \
   --to 1440,914 --budget 150000 --out $D/4-teleport.json
R --prefix $D/4-teleport.json --via "1470,1040;1320,659;1413,639;1965,569;2160,569;1935,314;2295,314" \
   --min-hp 1 --budget 150000 --out $D/5-exit.json
```

The situations' routes use the same segments. Each first segment adds `--start 81,111`
(`cp1`, starting from that console's own route to console 2) or `--start 841,828` (`cp2`). The
`cp3` route is one search: `--start 1413,639 --via "1965,569;2160,569;1935,314;2295,314"`.

The search is deterministic, so the chain reproduces the committed route input for input. The
first segment takes about 20 minutes; the others take seconds to minutes.

## What this says about the agents' task

The level is winnable, but not by heading right. A player has to find a lift, throw a switch it
cannot see from below, come back down, and cross a turret trap. The scripted baseline stalls in
the first section (`EVALUATION.md`). A model that only explores what it sees faces the same
puzzle, with no more help than the manual-level advice in its prompt.
