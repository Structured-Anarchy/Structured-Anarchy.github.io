from __future__ import annotations

from pathlib import Path
import json
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .content import ContentError, SiteData, Writing
from .vault import copy_encrypted


def build_site(data: SiteData, root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    _assert_safe_output(root, output)
    if output.exists():
        if not output.is_dir():
            raise ContentError(f"Output path is not a directory: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    copy_static_assets(root, output)
    try:
        private_available = copy_encrypted(root, output)
    except (ValueError, OSError) as exc:
        raise ContentError(f"invalid encrypted archive: {exc}") from exc
    copy_writing_assets(root, output, data.discussions)

    env = Environment(
        loader=FileSystemLoader(root / "site" / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["date_long"] = lambda value: value.strftime("%B %-d, %Y")
    env.globals["site"] = data.config
    env.globals["private_available"] = private_available
    env.globals["discussion_notes"] = data.discussions

    render_page(env, output / "index.html", "landing.html", active="home")
    render_page(env, output / "structural-map" / "index.html", "structural_map.html", active="structural-map")
    render_page(env, output / "symbols-and-meaning" / "index.html", "symbols.html", active="symbols")
    render_writing_section(env, output, "discussions", "Discussions", data.discussions)
    render_page(env, output / "404.html", "404.html", active="")
    write_manifest(output, data)


def _assert_safe_output(root: Path, output: Path) -> None:
    dist = root / "dist"
    if output == root:
        raise ContentError("Refusing to use repository root as build output")
    if root in output.parents or output == root:
        if output != dist and dist not in output.parents:
            raise ContentError(
                "Refusing to delete a source-tree output path outside dist/: "
                f"{output.relative_to(root)}"
            )


def copy_static_assets(root: Path, output: Path) -> None:
    site_assets = root / "site" / "assets"
    if site_assets.exists():
        shutil.copytree(site_assets, output / "assets", dirs_exist_ok=True)
    for legacy_dir in [root / "assets" / "img", root / "assets" / "pdf"]:
        if legacy_dir.exists():
            shutil.copytree(legacy_dir, output / "assets" / legacy_dir.name, dirs_exist_ok=True)


def copy_writing_assets(root: Path, output: Path, writings: list[Writing]) -> None:
    for writing in writings:
        target = output / "assets" / "content" / writing.section / writing.slug
        excluded = {
            writing.markdown_path.resolve(),
            writing.metadata_path.resolve(),
        }
        for path in writing.markdown_path.parent.rglob("*"):
            if not path.is_file() or path.resolve() in excluded:
                continue
            relative = path.relative_to(writing.markdown_path.parent)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def render_page(env: Environment, path: Path, template: str, **context) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = env.get_template(template).render(**context)
    path.write_text(html, encoding="utf-8")


def render_writing_section(
    env: Environment, output: Path, section: str, title: str, items: list[Writing]
) -> None:
    render_page(
        env,
        output / section / "index.html",
        "writing_index.html",
        active=section,
        section=section,
        title=title,
        items=items,
    )
    for item in items:
        render_page(
            env,
            output / section / item.slug / "index.html",
            "writing_detail.html",
            active=section,
            section=section,
            title=title,
            item=item,
        )


def write_manifest(output: Path, data: SiteData) -> None:
    manifest = {
        "discussions": [item.slug for item in data.discussions],
    }
    (output / "site-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
