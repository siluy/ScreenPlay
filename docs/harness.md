# Harness and evaluation contract

## GUI

`gameworld run` executes a single task; `gameworld batch` runs a serial, resumable experiment plan. The agent configuration references environment-variable names, never embedded credentials. `src/gameworld/agents.py` owns provider requests and response parsing. `src/gameworld/experiments.py` records budgets, API attempts, results and usage. `src/gameworld/guarded.py` implements process limits. `src/gameworld/runner.py` owns observations and action receipts.

Each action is tied to the current observation and an action ID. Invalid actions consume decisions. `success` is boolean only for scored results; infrastructure interruptions may be unscored (`null`). Keep interruptions separate from scored failures. A resumed batch retains attempts and completed scores. Do not edit task definitions or protocol settings while resuming.

Use `gameworld replay RUN_DIRECTORY` to create a replay. Model responses and screenshots are local run artifacts and are excluded from this repository.

## Text

The interactive command `scripts/run_text.py` supports all six projects and outputs the same public observations and schemas used by the existing adapters. The default decisions follow the adapter: original 45 text tasks default to 100; the newer 45 use task-native limits. Set an explicit cap for a new protocol and record it; do not retroactively alter results.

```python
from pathlib import Path
from gameworld.agents import load_agent_config
from gameworld_text.agent import TextAgent
from gameworld_text.tatham import make_environment

# Build the relevant game first. Environment variables supply model credentials.
run = Path("runs/custom-text")
run.mkdir(parents=True, exist_ok=False)
(run / "private").mkdir()
agent = TextAgent(load_agent_config(Path("configs/agents/openai-compatible.json")))
env = make_environment("fifteen-01", max_decisions=100)
try:
    before = env.observe()
    while not before["ended"]:
        decision = agent.choose(before, run)
        after = env.step(decision.action)
        agent.remember(before, decision, after)
        before = after
finally:
    if hasattr(env, "close"):
        env.close()
```

This minimal integration example does not implement batch recovery or a process watchdog. Production experiments should add wall/process limits and preserve unscored API errors. Historical model-specific launch scripts, routing aliases and recovery automations are intentionally not distributed as general-purpose commands.

## Reproduction boundaries

The release contains task definitions and reference traces, not historical evaluation outputs or participant data. Reference traces are author feasibility evidence, not model scores. GUI reference runs require the expected viewport. Text interfaces alter both state representation and action vocabulary. Platform rendering and native library versions can affect reproducibility; retain build receipts, configuration, task IDs and stop reasons for every new run.
