# Content guide

The repository starts with empty member and discussion collections. Add content using the structures below; the build validates names, required fields, dates, and matching files.

## Members

Each member needs a profile image and TOML file with the same lowercase, URL-safe slug:

```text
members/<slug>.<jpg|jpeg|png|webp|gif>
members/<slug>.toml
```

Example metadata:

```toml
name = "Member name"
last_name = "Name"
join_date = "2026-09-06"
affiliations = ["Community or organisation"]
interests = ["Ethics", "Political philosophy"]
bio = "A short member biography."
```

`last_name` is optional. Members sort by join date, then last name.

## Discussions

Each discussion has matching Markdown and TOML files in its own directory. Images and other local assets can live alongside them.

```text
discussions/<slug>/<slug>.md
discussions/<slug>/<slug>.toml
```

Example metadata:

```toml
title = "A question worth discussing"
date_published = "2026-09-06"
```

The optional `comment_id` field can preserve an existing giscus thread. Discussions sort newest-first.

## Comments

Discussion pages are ready for giscus comments and reactions. Enable GitHub Discussions and the giscus app for the repository, then fill in `repo_id` and `category_id` in `site_config.toml`. Until then, regular builds show a placeholder; `scripts/build_site.py --production` deliberately fails if the configuration is incomplete.
