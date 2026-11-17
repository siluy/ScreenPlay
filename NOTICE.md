# License scope and upstream notices

The root MIT license applies to original ScreenPlay benchmark, harness, documentation and website contributions. It does **not** replace upstream licenses, remove existing notices, or relicense upstream-derived code or assets.

Native adapters under `game_packages/*/native/`, linked text drivers under `research/text-ablation/native/`, and any other upstream-derived portions retain the applicable upstream terms. Distribution of combined/derived programs must respect those terms. No full upstream checkout, compiled native binary or downloaded resource pack is bundled.

| Project | Upstream license information |
|---|---|
| Simon Tatham's Puzzles | Pinned repository `LICENCE` (MIT); see `game_packages/tatham/source.json` |
| OpenTTD | Pinned repository `COPYING.md` (GPL-2.0); OpenGFX has its own retained license |
| Endgame: Singularity | GPL-2.0-or-later; artwork varies; retained `UPSTREAM-*` files |
| PySolFC | GPL-3.0-or-later; cardsets have separate copyright notices |
| Enigma | GPL-2.0-or-later |
| Endless Sky | GPL-3.0-or-later; artwork has per-author licenses |

Exact upstream revisions and asset sources are in each `game_packages/<project>/source.json`. Existing notices accompanying individual files take precedence for those files. Dependencies installed through uv or the system package manager retain their own licenses.

## Paper

`paper/screenplay.pdf` is the author-visible manuscript including supplementary material. Its inclusion does not extend the software MIT license to the manuscript or third-party figures; those rights remain with their respective holders.
