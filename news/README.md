# 🗓 RaazNet Security Calendar — how it works

An automated daily watch on Iran-related cybersecurity news, in English and Persian.
No programming needed to use it.

## What happens, twice a day

At **06:00 and 18:00 UTC** (~09:30 and 21:30 Tehran), GitHub runs a script that:

1. reads every source listed in [`../sources.yml`](../sources.yml)
2. also runs fresh web searches (Google News, English + Persian) — the "surf for hints" part
3. checks public Telegram channels, X/Twitter accounts, Reddit and Mastodon
4. throws away anything that isn't about **both Iran and cybersecurity**
5. throws away anything it already showed you on an earlier day
6. writes the survivors into `news/YYYY-MM-DD.md` and updates [`index.md`](index.md)

You just open `index.md` and click a date.

## Two ways to add a source

**The Source Desk page** — https://claude.ai/code/artifact/26e7cfaf-e3fe-468f-b9d2-40a6db556eab

Add, pause and remove sources with a form, then press **Save changes**. Because
published pages are sandboxed and can't write to GitHub, it hands you the
finished file and a button that opens `sources.yml` on GitHub ready to paste
into. Copy, paste, commit — done, no YAML to hand-edit.

The page keeps your work-in-progress in your own browser, so you can add a few
sources over the week and save them all at once.

**Or edit `sources.yml` directly** — the format is below.

## The file itself: `sources.yml`

It's plain text, organised into labelled blocks:

| Block | What it is |
|---|---|
| `main_feeds` | **Your main sources.** Shown first, in their own section. Each has a `filter:` switch (see below). |
| `security_feeds` | Big security news sites, filtered for Iran mentions. |
| `persian_feeds` | Persian-language outlets. |
| `search_queries` | Web searches, `en` and `fa`. Write anything you'd type into a search box. |
| `social` | **The social media block** — Telegram, X/Twitter, Reddit, Mastodon, each its own list. |
| `keywords` | How "is this relevant?" is decided. Add words to widen or narrow it. |

To switch something off, put a `#` in front of the line. To add a source, copy the
line above it and change the name and URL. That's the whole skill.

### Adding your main sources

```yaml
main_feeds:
  - name: Whatever you want to call it
    url: https://thesite.com/feed/      # the site's RSS feed address
    lang: fa                            # fa for Persian, en for English
    filter: true                        # see below
```

**The `filter` switch matters.** `filter: true` keeps only that source's
Iran-related items. `filter: false` keeps *everything* it publishes.

Use `filter: false` only for a source that is already narrowly about Iran.
Setting it on a general outlet like SecurityWeek or Reuters would pour their
entire global output into your digest — dozens of unrelated items a day. All
the main sources currently listed are general outlets, so they're all
`filter: true`.

Most news sites have an RSS feed at `/feed`, `/rss`, or `/feed/`. If a site has none,
add it as a `search_queries` entry instead (e.g. `site:thesite.com Iran cyber`).

## Running it yourself, right now

On GitHub: **Actions** tab → *RaazNet Security Calendar* → **Run workflow**.

On your own machine:

```bash
pip install feedparser pyyaml
python3 scripts/collect.py
```

## Tuning it

- **Too much noise?** In `sources.yml` → `settings`, keep `require_both_topics: true`,
  and trim the broader `keywords` (`internet`, `surveillance`, `apt`).
- **Missing things?** Add search queries — they're the widest net.
- **A site with no RSS feed?** Add a search query instead:
  `site:thatsite.com Iran cyber`. That's how Reuters is covered here, since
  they block automated feed readers.
- **Different times?** Edit the `cron` line in
  `.github/workflows/raaznet-calendar.yml`. It's in UTC; Tehran is UTC+3:30.
- **A source went quiet?** Dead feeds are skipped silently. Check the Actions log —
  each skipped URL is printed with the reason.

## Two honest caveats

- **Nothing here is verified.** It's a lead list, not reporting. Telegram and search
  results especially will surface rumours and state media. Check before you trust.
- **Nitter (X/Twitter) mirrors break constantly.** When they do, that block just
  returns nothing. Telegram and Reddit are the dependable social sources.
