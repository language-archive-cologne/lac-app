from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class InlineCspHashes:
    script_hashes: tuple[str, ...] = ()
    style_hashes: tuple[str, ...] = ()
    has_script_attribute_hashes: bool = False
    has_style_attribute_hashes: bool = False


def build_csp_sha256(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("ascii")
    return f"'sha256-{encoded}'"


class _InlineCspHashParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._script_hashes: set[str] = set()
        self._style_hashes: set[str] = set()
        self._has_script_attribute_hashes = False
        self._has_style_attribute_hashes = False
        self._script_content: list[str] | None = None
        self._style_content: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_attrs = {name.lower(): value or "" for name, value in attrs}

        if tag.lower() == "script" and "src" not in normalized_attrs:
            self._script_content = []
        elif tag.lower() == "style":
            self._style_content = []

        for name, value in attrs:
            if not value:
                continue

            lowered_name = name.lower()
            if lowered_name.startswith("on"):
                self._script_hashes.add(build_csp_sha256(value))
                self._has_script_attribute_hashes = True
            elif lowered_name == "style":
                self._style_hashes.add(build_csp_sha256(value))
                self._has_style_attribute_hashes = True

    def handle_data(self, data: str) -> None:
        if self._script_content is not None:
            self._script_content.append(data)
        elif self._style_content is not None:
            self._style_content.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "script" and self._script_content is not None:
            script = "".join(self._script_content)
            if script.strip():
                self._script_hashes.add(build_csp_sha256(script))
            self._script_content = None
        elif lowered_tag == "style" and self._style_content is not None:
            style = "".join(self._style_content)
            if style.strip():
                self._style_hashes.add(build_csp_sha256(style))
            self._style_content = None

    def inline_hashes(self) -> InlineCspHashes:
        return InlineCspHashes(
            script_hashes=tuple(sorted(self._script_hashes)),
            style_hashes=tuple(sorted(self._style_hashes)),
            has_script_attribute_hashes=self._has_script_attribute_hashes,
            has_style_attribute_hashes=self._has_style_attribute_hashes,
        )


def collect_inline_csp_hashes(document: str) -> InlineCspHashes:
    parser = _InlineCspHashParser()
    parser.feed(document)
    parser.close()
    return parser.inline_hashes()
