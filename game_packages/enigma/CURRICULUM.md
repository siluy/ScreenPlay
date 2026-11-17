# 15-task authored curriculum

Difficulty is an author estimate and remains pending human/model calibration. This project contains five easy, five medium and five hard tasks. All task goals are stated publicly; fixture data, predicates and witness reports remain evaluator-private.

| Task | Difficulty | Mechanisms | Why |
|---|---|---|---|
| enigma-oxyd-pair | easy | marble inertia, oxyd pairing | A single pair in a safe open arena isolates native marble control. |
| enigma-oxyd-memory | easy | marble inertia, oxyd pairing, color memory | Two colors introduce short-term memory in an otherwise safe open arena. |
| enigma-switch-gate | easy | switch, door, pairing | One visible switch controls the only passage; broad safe rooms allow recovery. |
| enigma-crate-passage | easy | pushable box, clearance, pairing | A box blocks the passage and can be pushed into a spacious landing area. |
| enigma-ice-crossing | easy | friction change, braking | One broad ice zone introduces momentum control without lethal borders. |
| enigma-winding-memory | medium | maze navigation, color memory, return travel | Alternating corridor entrances require remembering colors across long detours. |
| enigma-keyed-chamber | medium | inventory key, lock, door | Access depends on collecting an item and using its matching lock before pairing. |
| enigma-water-causeway | medium | water hazard, safe crossing, color memory | A finite-width bridge makes overshoot fatal while pairs require repeated crossings. |
| enigma-sequential-gates | medium | switch dependency, two doors, route planning | The second control is accessible only after the first gate is opened. |
| enigma-friction-slalom | medium | ice, sand, obstacle avoidance, memory | Changing traction and a central obstacle require braking and route correction in both directions. |
| enigma-key-switch-cascade | hard | inventory dependency, switch dependency, memory across chambers | An item unlocks a first region, which contains the second gate control; pairing spans all three regions. |
| enigma-crate-labyrinth | hard | multiple boxes, push clearance, maze, color memory | Two narrow openings need box displacement with enough clearance for returning to remembered stones. |
| enigma-icy-causeway | hard | low friction, water hazard, return crossings | Momentum persists on a three-cell ice bridge with lethal sides; each return crossing needs controlled approach. |
| enigma-gated-memory | hard | four-color memory, gated regions, navigation interference | Four pairs are interleaved across controlled chambers, increasing memory interference and revisitation cost. |
| enigma-keys-and-causeway | hard | two key codes, hazard crossing, ordered exploration, memory | Two distinct keys and locks span a water-divided middle chamber; wrong approaches cost recovery or life. |

## Object provenance and feasibility

Native examples: `tutorial_basic/a_tut05_2.xml` supplies `st_key`, `it_key`, `st_door` and code/target linking; `a_tut07_1.xml` supplies switch/door behavior; `a_tut03_2.xml` and `a_tut08_1.xml` supply pushable boxes; `m_tut09_2.xml` supplies ice and sand; `m_tut11_2.xml` supplies water. `enigma_oxydextra/oxe22_2.xml` demonstrates default switch-to-door messages. The authored Lua uses those original object classes without modifying friction, marble adhesion, force or collisions. Explicit Oxyd colors preserve native pairing and native level-finished scoring.

`topology-feasibility.json` parses all 15 XML files and records cell-space access after keys/switches and valid box displacements. All Oxyd stones have a reachable adjacent cell. The check is a necessary layout sanity check; it does not prove continuous-physics solvability or native message dispatch. Narrow water/ice routes intentionally demand braking. There are no authored low-level solution claims for the new levels.

## Desktop acceptance

All 15 current levels now have successful Episode/PyAutoGUI desktop trajectories and exact episode-local XML snapshots, independently checked against the current level files. Gates, keys, boxes, ice, water and the full combination goals have been exercised without changing the maps, physics or original task budgets. A deliberate water-death run confirms native resurrection cannot erase the terminal loss flag. See ../../artifacts/v1-singularity-enigma-desktop.json and ../../artifacts/v1-task-catalog.json.

These are fixture-author witnesses: private native positions informed author planning. They are not autonomous GUI-agent scores or shortest-path claims. The earlier topology report remains a separate, weaker evidence layer. Initial pointer recenter and Ignore Movement use the existing benchmark harness; no smoothing or physics assistance was added.

Independent static-reference replay checks also passed through `experiments.run_one(reference=True)` for `enigma-keys-and-causeway` (103 actions) and `singularity-undersea-research` (31 actions). These runs read the saved low-level sequence directly and did not use author feedback to select actions. Their `-replay` directories and explicit check results are in the desktop evidence JSON.
