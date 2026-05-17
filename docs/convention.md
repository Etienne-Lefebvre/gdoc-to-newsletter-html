# The bracket-tag convention

This is the spec for how content is structured in the Google Doc so the parser can understand it.

## The basic shape

Every piece of content lives inside a **block** that starts with an opening tag like `[HIGHLIGHT]` and ends with a closing tag like `[/HIGHLIGHT]`. Inside the block, fields come first (one `Key: value` per line), then a blank line, then the free-form body.

```
[BLOCK_NAME]
Field1: value
Field2: value
Button: Label | https://example.com

Body text goes here. Paragraphs are separated by blank lines.
[/BLOCK_NAME]
```

**Anything outside of `[BLOCK]...[/BLOCK]` tags is invisible to the parser.** You can leave onboarding text, scratch notes between blocks, or commentary — none of it shows up in the newsletter.

## Block types

| Tag | Purpose | Notes |
|---|---|---|
| `[META]` | Title + preheader | Required. One per Doc. |
| `[SECTION]` | Navy banner divider | One `Name:` field. No body. |
| `[LEAD]` | Italic intro paragraph | Just a body, no fields. |
| `[HIGHLIGHT]` | Full-width story | Image + title + body + 0–3 buttons. |
| `[SPOTLIGHT]` | Community group feature | Same shape as HIGHLIGHT. |
| `[EVENT]` | Upcoming event | 50/50 text + image layout. Auto-pairs with the next EVENT. |
| `[RECAP]` | Event recap | 50/50 by default. Add `Layout: full` to break out as full-width. |
| `[NEWS]` | Bulleted news list | One body, written as a Google Docs bulleted list. |
| `[CITY-HALL]` | Meeting list | Same shape as NEWS, different visual treatment. |
| `[IMAGE-ONLY]` | Standalone image | One `Image:` field. No body. |

## Fields

Recognized fields (all optional unless noted):

| Field | Used by | Notes |
|---|---|---|
| `Title:` | META, HIGHLIGHT, SPOTLIGHT, EVENT, RECAP | Style as Heading 2 in the Doc for sidebar navigation. |
| `Name:` | SECTION | Style as Heading 1 in the Doc. |
| `Preheader:` | META | ~90 chars max; the inbox preview text. |
| `Image:` | HIGHLIGHT, SPOTLIGHT, EVENT, RECAP, IMAGE-ONLY | Hosted image URL. Upload to your image host first. |
| `Image Link:` | HIGHLIGHT, SPOTLIGHT | Makes the image clickable. |
| `Caption:` | HIGHLIGHT, SPOTLIGHT | Italic caption shown below the image. |
| `Date:` | EVENT | E.g. `May 14, 6:15 PM - 7:45 PM` |
| `Location:` | EVENT | E.g. `St. Peter's Lutheran Church, 400 Sparks St` |
| `Button:` | HIGHLIGHT, SPOTLIGHT, EVENT | Format: `Label | URL`. Add up to 3 lines. |
| `Layout:` | Any | Force `half` or `full` (overrides default). |

## Layout rules

Each block has a default layout. Override per-block with `Layout: half` or `Layout: full`.

| Block | Default |
|---|---|
| HIGHLIGHT, SPOTLIGHT, LEAD, NEWS, CITY-HALL, IMAGE-ONLY | `full` |
| EVENT, RECAP | `half` |

**Auto-pairing:** consecutive `half` blocks within a section pair up into 2-column rows automatically. If a section ends with an unpaired `half` block (odd number), the orphan auto-promotes to `full` so it doesn't render in a lonely 50% column.

**Buttons:** the script counts your `Button:` lines per block (max 3) and picks the matching template layout (1 / 2 / 3 buttons).

## Formatting in the Doc

The Doc's actual formatting is read by the parser, not typed markdown. So:

- **Bold:** use the toolbar or `Ctrl+B`. Do NOT type `**bold**`.
- **Italic:** use the toolbar or `Ctrl+I`. Do NOT type `*italic*`.
- **Links:** use the hyperlink feature or `Ctrl+K`. Do NOT type `[text](url)`.
- **Bulleted lists:** use the toolbar's `•` button or `Ctrl+Shift+8`. Do NOT type `-` at the start of each line — the parser only sees real Google Docs list paragraphs, and typed `-` characters render literally.
- **Numbered lists:** toolbar's `1.` button or `Ctrl+Shift+7`. Same gotcha as bullets.

> The blank reference template ([`examples/master-template.txt`](../examples/master-template.txt)) uses the markdown-style syntax (`**bold**`, `[text](url)`, `-` for lists) as a plain-text stand-in so the file is readable outside a Doc. When you paste it into a real Doc, convert those into actual Doc formatting.

## Heading styles (visual only — does not affect the parser)

For navigation in the Doc's **Outline sidebar** (View → Show outline), apply heading styles:

- `Name:` line inside `[SECTION]` → **Heading 1**
- `Title:` line inside content blocks → **Heading 2**
- Opening/closing tags (`[HIGHLIGHT]`, `[/HIGHLIGHT]`) → leave as normal text

The parser reads plain text — heading styles change only what appears in the sidebar, making it one click to jump to any story.

## Gotchas to warn collaborators about

1. **Closing tags matter.** Deleting `[/HIGHLIGHT]` silently merges that block into the next one. Leave the tags alone.
2. **Lists must use the toolbar buttons.** See above.
3. **Bold/italic/links must use the toolbar.** See above.
4. **Images must be hosted somewhere.** The parser doesn't upload images — you paste an already-hosted URL into the `Image:` field. (Recommended hosts: Cloudinary, your website's media library, or the gallery your ESP provides.)
5. **The `Image Link:` field is optional.** Leave it off if you don't want the image to be clickable.

## Adding a new block type

If your newsletter needs something the existing block types don't cover:

1. Add the type name to `BLOCK_LAYOUT_DEFAULTS` in [`parser.py`](../parser.py), with the right default layout.
2. Define a rendering macro in [`templates/newsletter.html.j2`](../templates/newsletter.html.j2). Copy an existing macro and adapt.
3. Add a dispatcher case in the `render_single` macro (and `render_pair` if you want half-width support).
