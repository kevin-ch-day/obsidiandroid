# Agent instructions

The **canonical copy** of repository-wide guidance for contributors and automated agents is **[`docs/AGENTS.md`](docs/AGENTS.md)** (project shape, layout policy, testing, hygiene).

This file stays at the repo root because some tooling expects `AGENTS.md` here; treat **`docs/AGENTS.md`** as the single source of truth.

**Quick checks:** **`make ci`** mirrors **GitHub Actions** (`.github/workflows/ci.yml`): doc hygiene, import smoke, fast pytest, strict ML scan.
