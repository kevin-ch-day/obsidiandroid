# Agent instructions

The **canonical copy** of repository-wide guidance for contributors and automated agents is **[`docs/AGENTS.md`](docs/AGENTS.md)** (project shape, layout policy, testing, hygiene).

This file stays at the repo root because some tooling expects `AGENTS.md` here; treat **`docs/AGENTS.md`** as the single source of truth.

**Quick checks:** **`make ci-fast`** runs doc hygiene, import smoke, fast pytest,
and the strict ML scan. **`make ci`** adds canonical-closure validation; the
GitHub workflow runs integration lanes separately when relevant paths change.
