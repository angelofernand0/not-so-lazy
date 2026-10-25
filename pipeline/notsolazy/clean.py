"""Visible, ordered blocks with paragraph-level formatting and source provenance."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from lxml import html
from pydantic import BaseModel

CLEANER_VERSION = "clean-v2"
BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "li",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
        "section",
    }
)
TRANSLATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "\u00ad": ""}
)


class Block(BaseModel):
    text: str
    tag: str
    is_bold: bool = False
    is_italic: bool = False
    is_underlined: bool = False
    is_all_caps: bool = False
    is_list_item: bool = False
    leading_heading: str = ""
    font_size: float | None = None
    source_index: int = 0
    page: int = 0


@dataclass(frozen=True)
class Format:
    bold: bool = False
    italic: bool = False
    underlined: bool = False
    list_item: bool = False
    font_size: float | None = None


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(TRANSLATION).split())


def decode_html(payload: bytes) -> str:
    """Prefer UTF-8, with declared/Windows encodings for older SEC HTML."""
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = payload.decode("utf-16", errors="replace")
    else:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            declared = re.search(
                rb"(?:charset|encoding)\s*=\s*['\"]?([a-zA-Z0-9_-]+)", payload[:4096]
            )
            encoding = declared.group(1).decode("ascii") if declared else "cp1252"
            try:
                text = payload.decode(encoding, errors="replace")
            except LookupError:
                text = payload.decode("cp1252", errors="replace")
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", text)


def local_tag(node: Any) -> str:
    return str(node.tag).split("}")[-1].split(":")[-1].lower()


def css(style: str) -> dict[str, str]:
    return {
        key.strip().lower(): value.strip().lower().replace("!important", "").strip()
        for part in style.split(";")
        if ":" in part
        for key, value in [part.split(":", 1)]
    }


def clean_html(payload: bytes, *, removed_texts: set[str] | None = None) -> list[Block]:
    tree = html.fromstring(
        decode_html(payload), parser=html.HTMLParser(no_network=True, recover=True)
    )
    # Comments and processing instructions carry no visible text.
    for node in tree.xpath("//comment()|//processing-instruction()"):
        parent = node.getparent()
        if parent is not None:
            if node.tail:
                previous = node.getprevious()
                if previous is None:
                    parent.text = (parent.text or "") + node.tail
                else:
                    previous.tail = (previous.tail or "") + node.tail
            parent.remove(node)
    for node in list(tree.iter()):
        if node.getparent() is None and node is not tree:
            continue
        tag = local_tag(node)
        style = css(node.get("style") or "")
        if (
            tag in {"script", "style", "head", "header", "hidden"}
            or style.get("display") == "none"
            or style.get("visibility") == "hidden"
            or "hidden" in node.attrib
            or node.get("aria-hidden") == "true"
        ):
            if node is tree:
                return []
            node.drop_tree()
            continue
        if tag == "table":
            links = node.xpath(".//a[starts-with(@href, '#')]")
            # A navigation table, rather than a substantive narrative/data table.
            item_links = sum(
                bool(re.search(r"\bitem\s*\d", link.text_content(), re.I)) for link in links
            )
            if len(links) >= 5 and item_links >= 3 and len(node.text_content().split()) < 600:
                if node is tree:
                    return []
                node.drop_tree()

    blocks: list[Block] = []
    runs: list[tuple[str, Format]] = []
    page = 0
    current_tag = "div"

    def flush() -> None:
        nonlocal runs
        text = normalize_text("".join(value for value, _ in runs))
        if text:
            total = sum(len(normalize_text(value)) for value, _ in runs) or 1

            def feature(name: str) -> bool:
                return (
                    sum(len(normalize_text(value)) for value, fmt in runs if getattr(fmt, name))
                    / total
                    >= 0.8
                )

            prefix = ""
            for value, fmt in runs:
                if not normalize_text(value):
                    prefix += value
                    continue
                if not (fmt.bold or fmt.italic):
                    break
                prefix += value
            leading = normalize_text(prefix)
            # A common SEC layout leaves the heading's final period in the
            # following unstyled span. Keep that punctuation with the heading.
            if leading and text.startswith(leading + ". "):
                leading += "."
            if leading == text or not re.search(r"[.!?]$", leading):
                leading = ""
            letters = "".join(letter for letter in text if letter.isalpha())
            blocks.append(
                Block(
                    text=text,
                    leading_heading=leading,
                    tag=current_tag,
                    is_bold=feature("bold"),
                    is_italic=feature("italic"),
                    is_underlined=feature("underlined"),
                    is_all_caps=len(letters) >= 2 and letters.isupper(),
                    is_list_item=any(fmt.list_item for _, fmt in runs),
                    font_size=max(
                        (
                            fmt.font_size
                            for value, fmt in runs
                            if normalize_text(value) and fmt.font_size is not None
                        ),
                        default=None,
                    ),
                    source_index=len(blocks),
                    page=page,
                )
            )
        runs = []

    def visit(node: Any, inherited: Format) -> None:
        nonlocal page, current_tag
        tag = local_tag(node)
        style = css(node.get("style") or "")
        boundary = tag in BLOCK_TAGS
        previous_tag = current_tag
        if style.get("page-break-before") == "always" or style.get("break-before") == "page":
            flush()
            page += 1
        if boundary:
            flush()
            current_tag = tag
        weight = style.get("font-weight", "")
        bold = inherited.bold or tag in {"b", "strong"}
        if weight:
            bold = weight in {"bold", "bolder"} or (weight.isdigit() and int(weight) >= 600)
        italic = inherited.italic or tag in {"i", "em"}
        if "font-style" in style:
            italic = style["font-style"] in {"italic", "oblique"}
        underline = inherited.underlined or tag == "u"
        if "underline" in style.get("text-decoration", ""):
            underline = True
        if "underline" in style.get("text-decoration-line", ""):
            underline = True
        size = inherited.font_size
        size_match = re.fullmatch(r"([0-9.]+)(pt|px)", style.get("font-size", ""))
        if size_match:
            size = float(size_match[1]) * (0.75 if size_match[2] == "px" else 1)
        fmt = Format(bold, italic, underline, inherited.list_item or tag == "li", size)
        if node.text:
            runs.append((node.text, fmt))
        for child in node:
            if local_tag(child) in {"br", "hr"}:
                flush()
                if local_tag(child) == "hr":
                    page += 1
            else:
                visit(child, fmt)
            if child.tail:
                runs.append((child.tail, fmt))
        if boundary:
            flush()
            current_tag = previous_tag
        if style.get("page-break-after") == "always" or style.get("break-after") == "page":
            flush()
            page += 1

    visit(tree, Format())
    flush()

    def running_key(text: str) -> str:
        return re.sub(r"\d+", "#", text)

    groups: dict[str, list[Block]] = defaultdict(list)
    for block in blocks:
        if len(block.text) < 150:
            groups[running_key(block.text)].append(block)
    positions: dict[int, list[int]] = {}
    for i, block in enumerate(blocks):
        positions.setdefault(block.page, []).append(i)
    edges = {i for indices in positions.values() for i in [*indices[:3], *indices[-3:]]}
    removed: set[int] = set()
    for i, block in enumerate(blocks):
        text = block.text
        if re.fullmatch(r"(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?", text, re.I):
            removed.add(i)
        elif re.fullmatch(
            r"item\s+\d+[a-z]?(?:\s*,\s*\d+[a-z]?)+|parts\s+[ivx]+\s+and\s+[ivx]+", text, re.I
        ):
            removed.add(i)
        elif re.fullmatch(r"(?:back to )?table of contents", text, re.I):
            removed.add(i)
        elif len(groups.get(running_key(text), [])) >= 3 and (
            i in edges or re.search(r"\b(?:form\s+10-k|table of contents)\b", text, re.I)
        ):
            if (
                len(text.split()) >= 6
                and re.search(r"[.!?;]$", text)
                and not re.search(r"\bform\s+10-k\b", text, re.I)
            ):
                continue
            peers = groups[running_key(text)]
            sizes = [b.font_size for b in peers if b.font_size is not None]
            # Keep a prominent chapter title even when the same text is repeated
            # in tiny running footers (Intel and Honeywell).
            prominent = bool(sizes and block.font_size and block.font_size > min(sizes) * 1.2)
            if prominent:
                continue
            if re.fullmatch(r"item\s+\d+[a-z]?[.]?", text, re.I):
                if i in edges and (
                    i + 1 == len(blocks)
                    or len(blocks[i + 1].text) > 150
                    or re.match(r"^item\s+\d", blocks[i + 1].text, re.I)
                ):
                    removed.add(i)
                continue
            appearances = {b.page for b in peers}
            if (len(appearances) >= 3 and i in edges) or re.search(
                r"\b(?:form\s+10-k|table of contents)\b", text, re.I
            ):
                removed.add(i)
    if removed_texts is not None:
        removed_texts.update(blocks[i].text for i in removed)
    return [block for i, block in enumerate(blocks) if i not in removed]
