#!/usr/bin/env python3
"""Fail-closed checks for the static GitHub Pages showcase."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.local_references: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "img":
            if not values.get("alt") and values.get("alt") != "":
                self.errors.append(f"image lacks alt text: {values.get('src', '<unknown>')}")
            if not values.get("src"):
                self.errors.append("image lacks src")
        for attribute in ("src", "href"):
            reference = values.get(attribute)
            if reference and self._is_local(reference):
                self.local_references.append(reference)

    @staticmethod
    def _is_local(reference: str) -> bool:
        if reference.startswith(("#", "mailto:", "tel:")):
            return False
        return not urlparse(reference).scheme and not reference.startswith("//")


def main() -> int:
    required = [DOCS / "index.html", DOCS / "styles.css", DOCS / "site.js", DOCS / ".nojekyll"]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing required site files: {', '.join(missing)}")

    parser = SiteParser()
    parser.feed((DOCS / "index.html").read_text(encoding="utf-8"))

    for reference in parser.local_references:
        clean_reference = reference.split("?", 1)[0].split("#", 1)[0]
        if clean_reference and not (DOCS / clean_reference).is_file():
            parser.errors.append(f"missing local reference: {reference}")

    images = list((DOCS / "assets").rglob("*.png")) + list((DOCS / "assets").rglob("*.svg"))
    if len(images) < 10:
        parser.errors.append(f"expected at least 10 showcase images, found {len(images)}")

    forbidden = ("/private/tmp/", "/Users/", "file://")
    for path in DOCS.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".svg"}:
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    parser.errors.append(f"private path leaked in {path.relative_to(ROOT)}: {marker}")

    if parser.errors:
        raise SystemExit("site validation failed:\n- " + "\n- ".join(parser.errors))

    print(f"site validation passed: {len(parser.local_references)} local references, {len(images)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
