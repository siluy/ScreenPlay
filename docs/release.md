# Public source release

This checkout includes the benchmark, GUI/model harness, text adapters, native build drivers, human portal, tests and task-authoring utilities. It excludes the original Git history, paper drafts, raw evaluation outputs, participant data, local service credentials, provider-specific gateways and compiled/upstream caches.

The source package retains upstream source pins and notices. Native dependencies are fetched by the build commands. The public source tree has been checked independently of the development checkout; local validation results are delivered beside the archive, not as benchmark scores.

To prepare a subsequent source archive:

```sh
uv run python scripts/package_release.py --output dist/screenplay-bench
```

To publish this directory to a repository you control, initialize a new Git repository, review the staged file list and then push it. No historical `.git` directory is included. Set the desired remote and visibility yourself; this package has not been published.
