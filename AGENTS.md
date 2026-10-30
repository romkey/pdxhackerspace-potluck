# Instructions for AI assistants

Follow https://github.com/romkey/python-ai-rules/blob/main/RULES.md.
Follows python-ai-rules v0.0.0. When re-scanning, apply the entries in
its UPGRADING.md newer than that, then update this line.
With Claude Code, the `python-rules` plugin loads them for you.

Read docs/overview.md first. `main` is protected: work on a branch and
open a pull request; CI and Lint must pass before it can merge.

<!-- Project-specific notes go below. -->

- The page is `src/pdxhackerspace_potluck/templates/page.html` (one
  self-contained file: CSS and JS inline). Keep it that way.
- Schema changes are new numbered files in
  `src/pdxhackerspace_potluck/migrations/`, applied by
  `pdxhackerspace-potluck migrate`; never edit an applied one.
- Tests need PostgreSQL via `DATABASE_URL`; use the test compose file.
