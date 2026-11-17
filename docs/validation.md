# Validation scope

Run the source checks in the README from this checkout. Python tests exercise protocol boundaries, result semantics, invitations, pause/resume and authenticated HTTP behavior. Node tests cover the gateway and Singularity slider labels. HTTP tests need permission to bind ephemeral loopback ports.

Native builds and gameplay require the dependencies listed in development.md. Use `scripts/verify_human_portal.py` only against an isolated `--validation` study. The checker refuses a production human study. Add `--all-new-text` to cover all 45 newly introduced text tasks.

This release does not bundle historical acceptance artifacts or scores. Passing source tests does not imply that every native game was rebuilt or replayed on the recipient's machine. Do not mix author test trajectories with formal human or model results.
