# ScreenPlay

A benchmark and evaluation harness for agents acting in native games through GUI and text interfaces.

**[Read the full paper (PDF, including supplementary material)](paper/screenplay.pdf)**

*Beyond Getting It Done: Decoupling What Agents Achieve from How They See and Act*  
Luyang Si, Dongsheng Ma, Zhicheng Li (Sichuan University), Zhixiong Han, Leyi Pan, Lijie Wen.

## What is included

- **90 tasks across six projects**, with 15 tasks per project: Simon Tatham's Puzzles (Fifteen, Net, Untangle), PySolFC FreeCell, Endless Sky, Endgame: Singularity, OpenTTD and Enigma.
- Native game builds pinned to upstream commits, task fixtures, bounded actions, native scoring and authored reference trajectories.
- GUI model evaluation with an OpenAI-compatible provider, resumable serial batches, usage records and HTML replays.
- Text environments and an OpenAI-compatible text agent; 90 tasks are exposed through the human portal. The three newer interfaces remain experimental.
- A browser-based human-study portal with invitation management, explicit breaks and authenticated exports.

This is a source release. macOS is the validated native GUI host; browser clients can use other operating systems. It does not include prebuilt games, model weights, API credentials, participant records or historical model outputs. Tasks are development instances and include reference actions, not a hidden evaluation split.

## Install and inspect

Python 3.12, uv, Git and Xcode Command Line Tools are required. Install native libraries as described in [development](docs/development.md).

```sh
uv sync --locked --extra native-games
uv run gameworld tasks
uv run gameworld build tatham
uv run gameworld doctor
```

Run from a cloned source checkout: the runtime locates task packages and native drivers relative to the checkout. A standalone wheel is not a complete benchmark distribution.

## GUI evaluation

Give the host terminal Screen Recording and Accessibility permissions and keep the desktop unlocked. GUI runs share the real desktop and must run serially.

```sh
cp .env.example .env
# Set GAMEWORLD_BASE_URL, GAMEWORLD_MODEL and GAMEWORLD_API_KEY locally.
uv run gameworld agent-info --config configs/agents/openai-compatible.json --env-file .env
uv run gameworld run fifteen-01 --agent-config configs/agents/openai-compatible.json --env-file .env --output runs/gui-example
uv run gameworld batch --config configs/experiments/gui-example.json --env-file .env --output runs/gui-batch
# Continue the identical batch without replaying completed scores:
uv run gameworld batch --config configs/experiments/gui-example.json --env-file .env --output runs/gui-batch --resume
```

## Text interfaces

```sh
uv run python scripts/run_text.py --task fifteen-01 --output runs/text-example
# Enter one JSON action per line, e.g. {"type":"finish"}; EOF closes the environment.
```

The initial response contains the current observation and action schemas. For your own agent loop, use `gameworld_text.tatham.make_environment`, `env.observe()`, `env.step(action)` and `env.close()`. The provider implementation is `gameworld_text.agent.TextAgent`; see [harness documentation](docs/harness.md). Text and GUI observations/actions differ: their score difference is not a pure perception intervention.

## Human studies

```sh
uv run screenplay-human serve --data runs/my-study --port 8790
```

Open http://127.0.0.1:8790. The server prints the path to the local admin credential. `/admin` creates invitations, including a preset for the newest 45 text tasks. Use `--validation` and a separate data directory for operator tests. See [participants](docs/participants.md), [data protocol](docs/human-data.md) and [deployment](docs/development.md).

[Browse all 90 tasks](docs/tasks.md).

## Structure

| Directory | Contents |
|---|---|
| `game_packages/` | Fixed task catalog, upstream source pins, native bridges and reference actions |
| `src/gameworld/` | GUI runtime, provider integration, process limits, evaluation and replays |
| `src/gameworld_text/` | Text environments and provider adapter |
| `src/screenplay_human/` | Human-study website and isolated workers |
| `research/text-ablation/native/` | Native text drivers required at runtime |
| `scripts/` | Build, validation and task-authoring tools |
| `configs/` | Credential-free runnable examples |

## Validation

```sh
uv run pytest -q
node --check src/screenplay_human/static/app.js
node --test tests/test_human_singularity_ui.cjs deploy/cloudflare/test-gateway.mjs
```

These source checks do not replace native gameplay validation. Building all games requires upstream downloads and local dependencies; full native acceptance is not run in CI. See [release scope](docs/release.md) and [contributing](CONTRIBUTING.md).

## Licensing

See [LICENSE](LICENSE) for original project contributions and [NOTICE.md](NOTICE.md) for scope and upstream licenses. Native games, artwork and code derived from those projects retain their respective licenses. No ownership of upstream material is claimed.
