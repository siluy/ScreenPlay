# 15-task authored curriculum

Difficulty is an author estimate and remains pending human/model calibration. Each level contains five easy, five medium and five hard tasks. All task goals are stated publicly; fixture data, predicates and witness reports remain evaluator-private.

| Task | Difficulty | Mechanisms | Why |
|---|---|---|---|
| singularity-intrusion | easy | research allocation, simulation speed | A single research target from a minimal initial base. |
| singularity-research-chain | medium | research dependency, capacity expansion, bounded clock | Capacity must grow before the second research finishes within a tighter update budget. |
| singularity-server-foothold | easy | base purchase, capacity expansion | One immediate affordable expansion; no research prerequisite. |
| singularity-distributed-access | easy | world map, geographic diversification | Requires recognizing location membership and selecting a new location. |
| singularity-income-reserve | easy | CPU allocation, jobs, cash flow | A short income allocation exercise with upkeep and a modest reserve target. |
| singularity-storage-fitout | easy | equipment, construction labor | Separates a completed empty building from completed usable equipment. |
| singularity-datacenter-estate | medium | construction pipeline, upkeep, regional expansion | Multiple day-long projects and regional placement must all remain viable. |
| singularity-covert-hygiene | medium | prerequisite graph, research allocation, detection management | A branching prerequisite graph includes Personal Identification, which is not initially researched. |
| singularity-powered-storage | medium | batch equipment, reactor, reserve management | Coordinates equipment slots and construction while maintaining a cash floor. |
| singularity-parallel-production | medium | technology unlock, equipment availability, build versus research | Research unlocks hardware for a new building; CPU time and construction must be sequenced. |
| singularity-industrial-transition | hard | branch convergence, capital planning, multi-day construction | Several research branches converge on an expensive facility; spending and time exposure interact. |
| singularity-undersea-research | hard | location safety, danger-tier research, infrastructure dependency | Danger-1 research requires powered ocean infrastructure; ordinary urban CPUs alone cannot complete it. |
| singularity-balanced-expansion | hard | income versus research, limited capital, regional construction | Starting capital cannot cover the full goal and reserve, requiring deliberate income/research reallocation. |
| singularity-regional-resilience | hard | distributed operations, per-base equipment, upkeep exposure | Several locations and separate equipment inventories must satisfy simultaneous conditions. |
| singularity-hardware-frontier | hard | hardware replacement, construction downtime, active capacity, reserve constraint | Hardware replacement competes with research and labor; ownership alone is insufficient without active capacity. |

## Native feasibility evidence

`native-feasibility.json` records 15 successful offline trajectories through original `Player.give_time`, `Buyable.work_on`, research allocation, Base and Item constructors. Only the initial fixture uses `finish(is_player=False)`. The witness thereafter pays original cash/CPU/labor costs, applies maintenance, and retains discovery and loss rules. All 15 starts fail the goal; all 15 traces reach the simultaneous goal within the update budget, with an asserted reserve of six updates for every allowed UI decision. This is not a screenshot/PyAutoGUI trajectory and does not validate UI decision budgets. The display stub suppresses only UI presentation while simulating. A 14,400-second native tick corresponds to 432,000x speed at 30 FPS; dialog and input overhead are excluded.

Expansion witnesses buy additional native Datacenters before large research investments. The undersea witness installs eight Mainframes although the public minimum is two; this is a legal player strategy, not fixture assistance. Cash, regional spread, base types and each required equipment slot are checked on actual surviving completed objects. Available CPU uses the native active-capacity calculation. Diesel Generators reduce discoverability; they are not an invented power prerequisite.

## Desktop verification

All 15 current tasks now have successful native desktop witnesses, with unchanged original decision/update budgets. See `../../artifacts/v1-singularity-enigma-current-witnesses.json` for the exact successful run per task and `../../artifacts/v1-singularity-enigma-desktop.json` for successful attempts, retained exploratory attempts and the explicit native-death negative check. Enigma witnesses retain an XML snapshot equal to the current canonical level. Every executed input passed through Episode/PyAutoGUI and generated actual PNG/action/state records.

These are fixture-author feasibility witnesses, not autonomous-model scores. Author planning used private native telemetry; the saved references contain only low-level actions. The offline feasibility reports above remain scoped to their own checks and do not retroactively claim GUI execution. Difficulty remains an author estimate pending calibration.

Independent static-reference replay checks also passed through `experiments.run_one(reference=True)` for `enigma-keys-and-causeway` (103 actions) and `singularity-undersea-research` (31 actions). These runs read the saved low-level sequence directly and did not use author feedback to select actions. Their `-replay` directories and explicit check results are in the desktop evidence JSON.
