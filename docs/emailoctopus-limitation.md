# Why the pipeline stops at HTML (and doesn't auto-create a campaign)

**Short version:** EmailOctopus's public API does not support creating or sending campaigns. It's read-only for that area.

## What we tried

The original plan was three phases:

1. ✅ **Phase 1: Doc → HTML file.** Shipped.
2. ❌ **Phase 2: Auto-upload the HTML to EmailOctopus as a draft campaign via API.**
3. ❌ **Phase 3: Auto-send a test email to a configured address.**

When we went to build Phase 2, we discovered EmailOctopus's API only supports reading existing campaigns (`GET /campaigns`, `GET /campaigns/{id}/reports/*`), not creating new ones. Both API v1 (legacy) and v2 (current) have this limitation.

## Sources

- [EmailOctopus API v2 documentation](https://emailoctopus.com/api-documentation/v2) — no POST endpoint for campaigns.
- [EmailOctopus API limits article](https://help.emailoctopus.com/article/91-api-limits) — explicit statement: campaigns must be created in the dashboard.

## Workarounds we considered and rejected

1. **Switch ESPs.** Mailchimp, Beehiiv, Buttondown, ConvertKit, Substack all have full campaign-creation APIs. But migrating a list is non-trivial (re-confirming subscribers in some jurisdictions, losing engagement history, retraining collaborators). For a monthly newsletter, the cost of switching dwarfs the cost of one manual paste.

2. **Browser automation (Playwright/Selenium).** A script that drives EmailOctopus's web UI like a human user. Possible, but fragile — every UI change from EmailOctopus would break it, and it's a lot of code for a tiny payoff.

3. **Clipboard mitigation.** Instead, we added `--copy-to-clipboard` and `--open-preview` flags to the parser. The flow becomes: run the parser → browser pops open with preview → switch to EmailOctopus tab → Ctrl+V → review → send. Total marginal time saved by a hypothetical Phase 2: ~10 seconds per month.

## If you're forking this for a different ESP

If your ESP has a full campaign-creation API, you can extend Phase 1 with a real Phase 2. The hook point is the end of `main()` in `parser.py` after the HTML is rendered — call your ESP's "create campaign" endpoint with the HTML as the body content. Mailchimp's `POST /campaigns` + `PUT /campaigns/{id}/content` is the most common pattern.

The HTML the parser produces is email-safe (table-based layout, inline CSS, no `<style>` blocks beyond a minimal reset, no JavaScript) and should drop into any ESP's "Custom HTML" or "Paste HTML" mode cleanly.
