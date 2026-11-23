# ObsidianDroid

[![CI](https://github.com/kevin-ch-day/obsidiandroid/actions/workflows/ci.yml/badge.svg)](https://github.com/kevin-ch-day/obsidiandroid/actions/workflows/ci.yml)

ObsidianDroid is a research framework for Android malware family and type
classification. It combines retained antivirus verdicts and permission evidence
with reproducible cohort selection, model evaluation, and reporting.

## Features

- Run profile-driven experiments with vendor-derived, permission, or fused features.
- Browse catalog records and coverage from the read-only explorer.
- Inspect frozen evidence with the offline research tools, including permission
  trends and ATT&CK Mobile relationships.
- Assess an exact artifact SHA using a frozen evidence snapshot and review its
  stored assessment history.

## Installation

On Fedora with Python 3.11 or later:

```bash
git clone https://github.com/kevin-ch-day/obsidiandroid.git
cd obsidiandroid
./setup.sh
```

For the installed console commands and imports outside the checkout, activate
`.venv` and run `make install-editable`.

## Usage

Launch the interactive menu with `./run.sh`. Use **Explore Android data** to
browse the catalog or **Run malware classification** to select and check a
profile. Run `.venv/bin/python main.py --help` for direct entry-point options.
After editable installation, `obsidiandroid` opens the same menu. Both launchers
accept `analysis` and `pi-v2`. Run `./run.sh analysis --help` or
`./run.sh pi-v2 --help` to list the supported commands.

| Task | Guide |
| --- | --- |
| Configure sources, choose a profile, or inspect run output | [User guide](docs/user_guide.md) |
| Browse a retained research packet | [Offline research](docs/integrated_research.md) |
| Interpret permission evidence and ATT&CK Mobile relationships | [Permission and ATT&CK guide](docs/PERMISSION_ATTACK_INTEGRATION.md) |
| Create or review a local exact-SHA assessment | [Operational assessment](docs/OPERATIONAL_ASSESSMENT_V1.md) |

For a completed run, open `run_evidence_index.md` under
`output/runs/<run_id>/` first.

## Configuration

Profiles live in `profiles/` and shared settings live in `config/`.
Database-backed actions require configured Erebus and Permission Intel sources.
Normal analysis reads upstream evidence and writes run artifacts to local files
by default. Core result persistence uses an explicit workflow. See the
[runtime source-connection policy](docs/runtime_source_connection_policy.md)
and [modeling reference](docs/modeling_reference.md).

## Repository layout

| Path | Contents |
| --- | --- |
| [`src/obsidiandroid/`](src/obsidiandroid/) | Python package for the CLI, pipeline, modeling, assessment, and reporting |
| [`config/`](config/) and [`profiles/`](profiles/) | Shared settings, benchmark definitions, and runnable profiles |
| [`database/`](database/) | Versioned SQL migrations, views, and operator assets |
| [`scripts/`](scripts/) and [`tests/`](tests/) | Developer tools, diagnostics, and test suites |
| [`artifacts/`](artifacts/) and [`research/`](research/) | Frozen baselines and external research inputs |
| [`governance/`](governance/) | Versioned taxonomy repair evidence and receipts |
| [`docs/`](docs/README.md) | User, architecture, contributor, and operations guides |

Run `make tree-root` for a one-level view that respects Git ignore rules. Run
`make tree-source` for the expanded source tree.

## Running tests

With the project virtual environment active, run `make ci-fast` for the quick
gate or `make ci` to include canonical closure. The
[developer guide](docs/developer_guide.md) lists the integration and full suites.

## Contributing

Start with the [contributor guide](docs/AGENTS.md) and
[governance policy](docs/GOVERNANCE.md). See the
[structure migration history](docs/STRUCTURE_MIGRATION_PLAN.md) for earlier
package moves and retired imports.

## Version

The package version is **2.4.0**. See the [release notes](docs/RELEASE_NOTES.md),
[verification checklist](docs/releases/2.4.0_CODE_COMPLETE_CHECKLIST.md), and
[offline graph index](docs/releases/2.4.0_OFFLINE_GRAPH_INDEX.md).

## License

MIT License (see [LICENSE](LICENSE)).
For academic and research use only. Commercial use requires written permission.
Handle malware data responsibly and comply with VirusTotal terms and all applicable laws.
