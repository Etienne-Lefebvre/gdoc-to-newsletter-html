"""STO Newsletter parser — Phase 1.

Reads a Google Doc using the bracket-tag convention and renders it
into an EmailOctopus-ready HTML file using the STO email template.

Usage:
    python parser.py --doc-id <DOC_ID> --credentials <PATH_TO_JSON> [--output newsletter.html]

The output file can be pasted into EmailOctopus's "Custom HTML" editor.
EmailOctopus's own merge tags (`{{UnsubscribeURL}}`, `{{SenderInfo}}`,
etc.) pass through untouched because Jinja is configured to use
`[[ var ]]` for its own variables.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from jinja2 import Environment, FileSystemLoader


SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


BLOCK_LAYOUT_DEFAULTS = {
    "META": "full",
    "SECTION": "full",
    "LEAD": "full",
    "HIGHLIGHT": "full",
    "SPOTLIGHT": "full",
    "EVENT": "half",
    "RECAP": "half",
    "NEWS": "full",
    "CITY-HALL": "full",
    "IMAGE-ONLY": "full",
}
KNOWN_BLOCKS = set(BLOCK_LAYOUT_DEFAULTS.keys())


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    link: Optional[str] = None


@dataclass
class BodyItem:
    type: str  # 'paragraph' | 'list_item'
    runs: list
    list_id: Optional[str] = None
    list_style: Optional[str] = None  # 'ordered' | 'unordered'


@dataclass
class Block:
    type: str
    fields: dict = field(default_factory=dict)
    buttons: list = field(default_factory=list)
    body: list = field(default_factory=list)
    layout: str = "full"
    body_html: str = ""


# ---------------------------------------------------------------------------
# Google Docs fetch
# ---------------------------------------------------------------------------


def fetch_doc(doc_id: str, credentials_path: str) -> dict:
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    service = build("docs", "v1", credentials=creds, cache_discovery=False)
    return service.documents().get(documentId=doc_id).execute()


# ---------------------------------------------------------------------------
# Doc walking helpers
# ---------------------------------------------------------------------------


def paragraph_text(paragraph: dict) -> str:
    """Concatenate all textRun content in a paragraph (without trailing newline)."""
    chunks = []
    for element in paragraph.get("elements", []):
        run = element.get("textRun")
        if run:
            chunks.append(run.get("content", ""))
    return "".join(chunks).rstrip("\n")


def paragraph_runs(paragraph: dict) -> list:
    """Extract formatted Run objects from a paragraph."""
    runs = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if not text_run:
            continue
        text = text_run.get("content", "").rstrip("\n")
        if not text:
            continue
        style = text_run.get("textStyle", {})
        link_url = None
        if "link" in style and style["link"].get("url"):
            link_url = style["link"]["url"]
        runs.append(
            Run(
                text=text,
                bold=bool(style.get("bold", False)),
                italic=bool(style.get("italic", False)),
                link=link_url,
            )
        )
    return runs


def list_style_for(doc: dict, list_id: str, nesting_level: int) -> str:
    """Decide ordered vs unordered for a Doc list."""
    lists = doc.get("lists", {})
    list_def = lists.get(list_id)
    if not list_def:
        return "unordered"
    levels = list_def.get("listProperties", {}).get("nestingLevels", [])
    if nesting_level >= len(levels):
        return "unordered"
    level = levels[nesting_level]
    glyph = level.get("glyphType", "")
    # Common ordered types in Docs API: DECIMAL, ZERO_DECIMAL, UPPER_ALPHA, etc.
    if glyph and glyph != "GLYPH_TYPE_UNSPECIFIED":
        return "ordered"
    return "unordered"


def iter_paragraphs(doc: dict):
    """Yield paragraph dicts from document body."""
    for item in doc.get("body", {}).get("content", []):
        para = item.get("paragraph")
        if para is not None:
            yield para


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------


OPEN_TAG_RE = re.compile(r"^\[([A-Z][A-Z-]*)\]$")
CLOSE_TAG_RE = re.compile(r"^\[/([A-Z][A-Z-]*)\]$")
FIELD_LINE_RE = re.compile(r"^([A-Za-z][\w \-]*?):\s*(.*)$")


def parse_blocks(doc: dict) -> list:
    blocks: list = []
    current: Optional[Block] = None
    state = "OUTSIDE"  # OUTSIDE | FIELDS | BODY

    for paragraph in iter_paragraphs(doc):
        text = paragraph_text(paragraph).strip()

        open_m = OPEN_TAG_RE.match(text)
        if open_m:
            block_type = open_m.group(1)
            if block_type not in KNOWN_BLOCKS:
                warn(f"Unknown block type [{block_type}] — ignoring its contents")
                current = None
                state = "OUTSIDE"
                continue
            current = Block(type=block_type)
            state = "FIELDS"
            continue

        close_m = CLOSE_TAG_RE.match(text)
        if close_m:
            if current is None:
                warn(f"Closing tag [/{close_m.group(1)}] with no open block — ignoring")
                continue
            if current.type != close_m.group(1):
                warn(
                    f"Mismatched closing tag [/{close_m.group(1)}] for open [{current.type}]"
                )
            blocks.append(current)
            current = None
            state = "OUTSIDE"
            continue

        if state == "OUTSIDE" or current is None:
            continue

        if state == "FIELDS":
            if text == "":
                state = "BODY"
                continue
            fm = FIELD_LINE_RE.match(text)
            if fm:
                key = fm.group(1).strip()
                value = fm.group(2).strip()
                if key.lower() == "button":
                    if "|" in value:
                        label, url = value.split("|", 1)
                        current.buttons.append(
                            {"label": label.strip(), "url": url.strip()}
                        )
                    else:
                        warn(f"Button field missing '|' separator: {value!r}")
                else:
                    current.fields[key] = value
                continue
            # Not a field — fall through into body
            state = "BODY"

        if state == "BODY":
            runs = paragraph_runs(paragraph)
            bullet = paragraph.get("bullet")
            if bullet:
                list_id = bullet.get("listId")
                nesting = bullet.get("nestingLevel", 0)
                style = list_style_for(doc, list_id, nesting) if list_id else "unordered"
                current.body.append(
                    BodyItem(
                        type="list_item",
                        runs=runs,
                        list_id=list_id,
                        list_style=style,
                    )
                )
            else:
                # Drop all blank paragraphs — the 16px bottom margin on each
                # rendered <p> already provides the visual spacing. Keeping
                # blanks would render as <p>&nbsp;</p> and double the gap.
                if not runs:
                    continue
                current.body.append(BodyItem(type="paragraph", runs=runs))

    if current is not None:
        warn(f"Block [{current.type}] was not closed before end of document")

    return blocks


# ---------------------------------------------------------------------------
# Markdown fallbacks (in case Doc has literal **bold** or [text](url))
# ---------------------------------------------------------------------------


MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def expand_markdown_in_runs(runs: list) -> list:
    """Expand `[text](url)` and `**bold**` in unstyled runs."""
    # Pass 1: links
    pass1 = []
    for r in runs:
        if r.link:
            pass1.append(r)
            continue
        out = []
        last = 0
        for m in MD_LINK_RE.finditer(r.text):
            if m.start() > last:
                out.append(Run(r.text[last : m.start()], r.bold, r.italic))
            out.append(Run(m.group(1), r.bold, r.italic, m.group(2)))
            last = m.end()
        if last < len(r.text):
            out.append(Run(r.text[last:], r.bold, r.italic))
        pass1.extend(out or [r])

    # Pass 2: bold
    pass2 = []
    for r in pass1:
        if r.bold:
            cleaned = MD_BOLD_RE.sub(r"\1", r.text)
            pass2.append(Run(cleaned, r.bold, r.italic, r.link))
            continue
        out = []
        last = 0
        for m in MD_BOLD_RE.finditer(r.text):
            if m.start() > last:
                out.append(Run(r.text[last : m.start()], False, r.italic, r.link))
            out.append(Run(m.group(1), True, r.italic, r.link))
            last = m.end()
        if last < len(r.text):
            out.append(Run(r.text[last:], False, r.italic, r.link))
        pass2.extend(out or [r])

    return pass2


def expand_markdown_in_blocks(blocks: list) -> None:
    for b in blocks:
        for item in b.body:
            item.runs = expand_markdown_in_runs(item.runs)


# ---------------------------------------------------------------------------
# Layout resolution
# ---------------------------------------------------------------------------


def resolve_layouts(blocks: list) -> None:
    """Set block.layout (half|full) using explicit Layout field or defaults,
    then promote orphan halves to full within each section."""
    for b in blocks:
        explicit = b.fields.pop("Layout", None)
        if explicit:
            layout = explicit.strip().lower()
            if layout not in ("half", "full"):
                warn(f"Invalid Layout={explicit!r} on [{b.type}] — using default")
                layout = BLOCK_LAYOUT_DEFAULTS.get(b.type, "full")
        else:
            layout = BLOCK_LAYOUT_DEFAULTS.get(b.type, "full")
        b.layout = layout

    # Sections delimit pairing groups
    group: list = []
    for b in blocks + [None]:  # sentinel to flush the final group
        if b is None or b.type == "SECTION":
            halves = [x for x in group if x.layout == "half"]
            if len(halves) % 2 == 1:
                for x in reversed(group):
                    if x.layout == "half":
                        x.layout = "full"
                        break
            group = []
            continue
        group.append(b)


# ---------------------------------------------------------------------------
# Body → HTML rendering (done in Python so the Jinja template stays simple)
# ---------------------------------------------------------------------------


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_attr(text: str) -> str:
    return escape_html(text).replace('"', "&quot;")


def runs_to_html(runs: list) -> str:
    parts = []
    for r in runs:
        t = escape_html(r.text)
        if r.link:
            t = (
                f'<a href="{escape_attr(r.link)}" target="_blank" '
                f'style="color:#623a00; text-decoration:underline;">{t}</a>'
            )
        if r.bold:
            t = f"<strong>{t}</strong>"
        if r.italic:
            t = f"<em>{t}</em>"
        parts.append(t)
    return "".join(parts)


def body_to_html(body: list) -> str:
    """Render the body of a block into HTML using the email template's
    paragraph/list patterns."""
    out = []
    i = 0
    n = len(body)
    while i < n:
        item = body[i]
        if item.type == "list_item":
            list_id = item.list_id
            style = item.list_style or "unordered"
            group = [item]
            j = i + 1
            while (
                j < n
                and body[j].type == "list_item"
                and body[j].list_id == list_id
            ):
                group.append(body[j])
                j += 1
            out.append(render_list(group, style))
            i = j
        else:
            out.append(render_paragraph(item))
            i += 1
    return "\n".join(out)


def render_paragraph(item: BodyItem) -> str:
    inner = runs_to_html(item.runs)
    if not inner.strip():
        return '<p style="margin:0 0 16px 0;">&nbsp;</p>'
    return f'<p style="margin:0 0 16px 0;">{inner}</p>'


def render_list(items: list, style: str) -> str:
    tag = "ol" if style == "ordered" else "ul"
    list_type = "decimal" if style == "ordered" else "disc"
    lis = "".join(f"<li>{runs_to_html(it.runs)}</li>" for it in items)
    return (
        f'<{tag} style="list-style-type:{list_type}; list-style-position:outside; '
        f'margin:0 0 16px 24px; padding:0;">{lis}</{tag}>'
    )


def prerender_block_bodies(blocks: list) -> None:
    for b in blocks:
        b.body_html = body_to_html(b.body)


# ---------------------------------------------------------------------------
# Row grouping for rendering
# ---------------------------------------------------------------------------


def build_rows(blocks: list) -> list:
    """Group blocks into rendering rows."""
    rows: list = []
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        if (
            b.layout == "half"
            and i + 1 < n
            and blocks[i + 1].layout == "half"
            and blocks[i + 1].type != "SECTION"
        ):
            rows.append({"kind": "pair", "left": b, "right": blocks[i + 1]})
            i += 2
        else:
            rows.append({"kind": "single", "block": b})
            i += 1
    return rows


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render(blocks: list, template_dir: Path, template_name: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        # Custom delimiters so EmailOctopus's own {{merge tags}} pass through
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)

    meta = next((b for b in blocks if b.type == "META"), None)
    meta_title = meta.fields.get("Title", "Strong Towns Ottawa Newsletter") if meta else "Newsletter"
    preheader = meta.fields.get("Preheader", "") if meta else ""

    content_blocks = [b for b in blocks if b.type != "META"]
    rows = build_rows(content_blocks)

    return template.render(
        meta_title=escape_html(meta_title),
        preheader=escape_html(preheader),
        rows=rows,
        escape=escape_html,
        escape_attr=escape_attr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="STO newsletter Doc → HTML parser")
    ap.add_argument("--doc-id", required=True, help="Google Doc ID (from the URL)")
    ap.add_argument(
        "--credentials",
        default=os.environ.get("STO_NEWSLETTER_CREDS"),
        help="Path to service account JSON key (or set STO_NEWSLETTER_CREDS env var)",
    )
    ap.add_argument("--output", default="newsletter.html", help="Output HTML file path")
    ap.add_argument(
        "--template-dir",
        default=str(Path(__file__).parent / "templates"),
        help="Directory containing newsletter.html.j2",
    )
    ap.add_argument(
        "--template-name", default="newsletter.html.j2", help="Template filename"
    )
    ap.add_argument(
        "--copy-to-clipboard",
        action="store_true",
        help="Copy the rendered HTML to the system clipboard after writing the file "
        "(Windows: pipes through clip.exe).",
    )
    ap.add_argument(
        "--open-preview",
        action="store_true",
        help="Open the rendered HTML in your default browser after writing.",
    )
    args = ap.parse_args()

    if not args.credentials:
        print(
            "ERROR: --credentials is required (or set STO_NEWSLETTER_CREDS env var)",
            file=sys.stderr,
        )
        return 2
    if not Path(args.credentials).exists():
        print(f"ERROR: credentials file not found: {args.credentials}", file=sys.stderr)
        return 2

    print(f"Fetching Google Doc {args.doc_id}...")
    try:
        doc = fetch_doc(args.doc_id, args.credentials)
    except HttpError as e:
        print(f"ERROR: Google Docs API call failed: {e}", file=sys.stderr)
        if e.resp.status == 403:
            print(
                "Hint: make sure the Doc is shared with the service account email "
                "(Viewer access is fine).",
                file=sys.stderr,
            )
        return 1
    print(f"  Title: {doc.get('title')!r}")

    print("Parsing blocks...")
    blocks = parse_blocks(doc)
    expand_markdown_in_blocks(blocks)
    resolve_layouts(blocks)
    prerender_block_bodies(blocks)

    print(f"Parsed {len(blocks)} blocks:")
    for b in blocks:
        title = b.fields.get("Title") or b.fields.get("Name") or "(no title/name)"
        n_btn = len(b.buttons)
        n_body = len(b.body)
        print(
            f"  [{b.type:<10}] layout={b.layout:<4} buttons={n_btn} body_items={n_body}  {title}"
        )

    print("Rendering...")
    html = render(blocks, Path(args.template_dir), args.template_name)

    out = Path(args.output)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html):,} chars)")

    if args.copy_to_clipboard:
        import subprocess
        try:
            subprocess.run(
                ["clip"], input=html, encoding="utf-8", check=True
            )
            print("Copied HTML to clipboard — paste straight into EmailOctopus.")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"WARNING: clipboard copy failed ({e})", file=sys.stderr)

    if args.open_preview:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())
        print(f"Opened {out} in browser.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
