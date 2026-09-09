# Structured Anarchy

Source for the Structured Anarchy philosophy club website.

GitHub Actions builds the static site into `dist/` and deploys that generated
artifact to GitHub Pages. Generated `dist/` output is intentionally not tracked
on `main`.

Create the development environment and launch a local preview with:

```sh
conda env create -f environment.yml
scripts/local_launch.sh
```

The launcher defaults to `structured_anarchy_py`; set `CONDA_ENV` to use an
equivalent existing environment.

Member and discussion formats are documented in
[`docs/content-guide.md`](docs/content-guide.md).

The Structural Map, extraction skill, encrypted session archive, and automated
checks are documented in [`docs/structural-map.md`](docs/structural-map.md).
Readable session material stays under ignored `data/*`; only `encrypted/` is
published. Probability inference is deferred.
