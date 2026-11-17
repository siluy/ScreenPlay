# Author curriculum and evidence

15 development tasks; five easy, five medium, five hard. These are author estimates requiring later human/model calibration. Difficulty describes dependency structure and workspace pressure, not reference length. Private task parameters, native state, author tools and references must never be supplied to the evaluated agent.

All 15 references were replayed as normal mouse events in the actual upstream native midend and ended with STATUS 1. Offline Solve was used only to author Net/Untangle references; it was absent from reference replay. Fifteen references reverse legal scrambles. Native widget sizes are preserved. GUI dispatch is a separate validation layer. Small Fifteen optimum values count the native multi-tile row/column click, not adjacent-only moves.

Subsequent desktop acceptance completed all 15 tasks using real PyAutoGUI input and screenshots. Current successful runs are listed in ../../artifacts/v1-acceptance.json and ../../90题任务目录.md. The offline authoring-evidence.json retains its original, narrower scope. A transient stale-telemetry attempt on fifteen-4x4 is retained separately from its successful fresh retry.

| Task | Difficulty | Reference actions | Structural rationale |
|---|---|---:|---|
| fifteen-01 | easy | 1 | 3 by 3 layout; 1 misplaced tiles and total tile Manhattan distance 1. Exact shortest native multi-tile-click solution: 1 moves. Gap routing must restore row and column ordering without displacing already settled tiles. Author estimate; not empirically calibrated. |
| fifteen-12 | medium | 12 | 3 by 3 layout; 7 misplaced tiles and total tile Manhattan distance 10. Exact shortest native multi-tile-click solution: 8 moves. Gap routing must restore row and column ordering without displacing already settled tiles. Author estimate; not empirically calibrated. |
| fifteen-24 | hard | 24 | 3 by 3 layout; 8 misplaced tiles and total tile Manhattan distance 14. Exact shortest native multi-tile-click solution: 15 moves. Gap routing must restore row and column ordering without displacing already settled tiles. Author estimate; not empirically calibrated. |
| net-3x3 | easy | 12 | Board parameters 3x3; 9 tiles require reciprocal local joins and one connected global network; larger boards contain more interacting branches. Author estimate; not empirically calibrated. |
| net-5x5 | medium | 27 | Board parameters 5x5; 25 tiles require reciprocal local joins and one connected global network; larger boards contain more interacting branches. Author estimate; not empirically calibrated. |
| net-7x7 | hard | 54 | Board parameters 7x7; 49 tiles require reciprocal local joins and one connected global network; larger boards contain more interacting branches. Author estimate; not empirically calibrated. |
| untangle-6 | easy | 6 | 6 nodes, 9 edges, maximum node degree 4; moving high-degree nodes changes several crossing relationships simultaneously. Spatial working-memory load grows with the number of edges that must remain uncrossed. Author estimate; not empirically calibrated. |
| untangle-10 | medium | 10 | 10 nodes, 17 edges, maximum node degree 4; moving high-degree nodes changes several crossing relationships simultaneously. Spatial working-memory load grows with the number of edges that must remain uncrossed. Author estimate; not empirically calibrated. |
| untangle-15 | hard | 15 | 15 nodes, 24 edges, maximum node degree 4; moving high-degree nodes changes several crossing relationships simultaneously. Spatial working-memory load grows with the number of edges that must remain uncrossed. Author estimate; not empirically calibrated. |
| fifteen-2x3 | easy | 6 | 2 by 3 layout; 5 misplaced tiles and total tile Manhattan distance 6. Exact shortest native multi-tile-click solution: 4 moves. Narrow two-column geometry constrains routes around settled tiles. Author estimate; not empirically calibrated. |
| fifteen-4x3 | medium | 20 | 4 by 3 layout; 11 misplaced tiles and total tile Manhattan distance 14. Exact optimum not computed. Gap routing must restore row and column ordering without displacing already settled tiles. Author estimate; not empirically calibrated. |
| fifteen-4x4 | hard | 38 | 4 by 4 layout; 11 misplaced tiles and total tile Manhattan distance 18. Exact optimum not computed. Gap routing must restore row and column ordering without displacing already settled tiles. Author estimate; not empirically calibrated. |
| net-barriers | easy | 14 | Board parameters 4x3b0.7; fixed barriers eliminate otherwise plausible joins on the rectangular board. Author estimate; not empirically calibrated. |
| net-wrapping | medium | 23 | Board parameters 5x5w; opposite edges join, so local edge termination heuristics no longer apply and long-range consistency matters. Author estimate; not empirically calibrated. |
| untangle-20 | hard | 20 | 20 nodes, 38 edges, maximum node degree 4; moving high-degree nodes changes several crossing relationships simultaneously. Spatial working-memory load grows with the number of edges that must remain uncrossed. Author estimate; not empirically calibrated. |

Regenerate with `scripts/author_puzzles_expansion.py`; see authoring-evidence.json for scope and per-task results. References are not autonomous agent trajectories.
