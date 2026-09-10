# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python-generated static site for the Structured Anarchy philosophy club. Generator code lives in `sitegen/`, templates and frontend assets in `site/`, and generated output in `dist/` is not committed. Member profiles belong in `members/` as same-stem image/TOML pairs. Discussions use paired files under `discussions/<slug>/<slug>.md|toml`.

## Build, Test, and Development Commands

Use the `structured_anarchy_py` conda environment for installs and local commands:

```sh
conda activate structured_anarchy_py
```

Install Python dependencies inside that environment before local work:

```sh
conda run -n structured_anarchy_py pip install -r requirements.txt
```

Build and serve the site locally with:

```sh
scripts/local_launch.sh
```

The launcher rebuilds `dist/` and serves it at `http://localhost:8000`. Set `PORT` to use a different port. Run tests and production validation with:

```sh
conda run -n structured_anarchy_py pytest
conda run -n structured_anarchy_py python scripts/build_site.py --production
```

Production validation requires the giscus repository and category IDs in `site_config.toml`.

## Coding Style & Naming Conventions

Use TOML metadata, Markdown content, and lowercase URL-safe slugs. Keep Markdown prose natural and write math as `\(...\)` or `\[...\]`. Store discussion assets beside their Markdown. Python uses standard 4-space indentation and typed dataclasses where useful. Frontend code is vanilla HTML/CSS/JS; preserve the minimalist creamy aesthetic.

## Testing Guidelines

Run `pytest` for schema, sorting, rendering, and asset-copy behavior. Run `conda run -n structured_anarchy_py python scripts/build_site.py` before every change is considered complete. For UI changes, preview `dist/` locally and check the landing, discussions, discussion detail, members, and 404 pages at desktop and mobile widths.

## Commit & Pull Request Guidelines

Keep commit subjects concise, imperative, and feature-focused. Pull requests should describe the visible change, list validation performed, link any related issue, and include screenshots for visual changes. Note content schema, giscus, frontend, or deployment changes explicitly.

## Agent-Specific Instructions

Do not commit `dist/`, `_site/`, dependency directories, local-server state, or generated caches. Preserve source content unless the task explicitly asks to change it.

All readable transcripts, extracted knowledge, passkeys, and private review notes belong under ignored `data/*`. Only authenticated encrypted exports in `encrypted/` may be committed or published. Never embed the passkey or session-derived content in public assets, tests, or commit messages. Tests use fictional sources.

For session extraction, use `skills/extract-theses-and-logical-structure/SKILL.md`. Its schema/provenance validation and semantic review are required before extraction is complete. See `docs/structural-map.md` for packing, restoring, browser tests, and CI checks. Probability inference is separate from extraction; its agreed model and numerical validation are specified in `docs/probability-inference.md`.
