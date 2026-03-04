# Plan: Activate Reference Links + Autonomous Link Checker

**Date**: 2026-03-03

## Context

The previous hyperlinking plan is complete — body text has active `[[N]](#ref-N)` footnote links and proper noun hyperlinks. However, the **reference citation strings** rendered at the bottom of each essay are still plain text. The `references.html` partial outputs `{{ ref }}` verbatim — bare domain names like `indieweb.org/POSSE` and book titles are not clickable.

Additionally, with ~150+ links now across 9 files, there's no automated way to detect broken links. Manual checking doesn't scale.

**Goal**: (1) Make reference citations clickable. (2) Build an autonomous link checker that runs in CI and on schedule.

---

## Part 1: Activate Reference Citations (4 essays)

### Approach

Embed markdown links in the YAML reference strings and render them with Jekyll's `markdownify` filter. No schema change needed — references remain `list[string]`.

### 1a. Template Change

**File**: `public-process/_includes/references.html`

Change line 7 from:
```html
<li id="ref-{{ forloop.index }}">{{ ref }}</li>
```
To:
```html
<li id="ref-{{ forloop.index }}">{{ ref | markdownify | replace: '<p>', '' | replace: '</p>', '' | strip }}</li>
```

This renders markdown links and italics within citation strings while stripping the `<p>` wrapper that `markdownify` adds.

### 1b. Update Reference Strings (40 citations across 4 essays)

Embed `[text](url)` markdown links on the title/source of each citation. For URLs containing parentheses (Wikipedia), use angle-bracket syntax: `[text](<url>)`.

#### Essay 1: `_posts/2026-02-21-the-distribution-problem.md`

| # | Link target | URL |
|---|-------------|-----|
| 1 | POSSE | `https://indieweb.org/POSSE` |
| 2 | tantek.com | `https://tantek.com/` |
| 3 | "The Internet's Enshittification" | `https://pluralistic.net/2023/01/21/potemkin-ai/` |
| 4 | *The Long Tail* | `https://en.wikipedia.org/wiki/The_Long_Tail_(book)` |
| 5 | *Tribes* | `https://en.wikipedia.org/wiki/Tribes_(Seth_Godin_book)` |
| 6 | RSS 2.0 Specification | `https://www.rssboard.org/rss-specification` |
| 7 | RFC 4287 | `https://datatracker.ietf.org/doc/html/rfc4287` |
| 8 | "The Web We Lost" | `https://anildash.com/2012/12/13/the_web_we_lost/` |
| 9 | "The Web We Have to Save" | `https://medium.com/matter/the-web-we-have-to-save-2eb1fe15a426` |
| 10 | *Ruined by Design* | `https://www.ruinedby.design/` |

#### Essay 2: `_posts/2026-02-24-community-infrastructure-for-one.md`

| # | Link target | URL |
|---|-------------|-----|
| 1 | *Communities of Practice* | `https://en.wikipedia.org/wiki/Community_of_practice` |
| 2 | *Gödel, Escher, Bach* | `https://en.wikipedia.org/wiki/G%C3%B6del,_Escher,_Bach` |
| 3 | *A Thousand Plateaus* | `https://en.wikipedia.org/wiki/A_Thousand_Plateaus` |
| 4 | *Social Systems* | `https://en.wikipedia.org/wiki/Social_Systems_(book)` |
| 5 | *Steps to an Ecology of Mind* | `https://en.wikipedia.org/wiki/Steps_to_an_Ecology_of_Mind` |
| 6 | *The Lean Startup* | `https://en.wikipedia.org/wiki/The_Lean_Startup` |
| 7 | *Working in Public* | `https://press.stripe.com/working-in-public` |
| 8 | *Where Good Ideas Come From* | `https://en.wikipedia.org/wiki/Where_Good_Ideas_Come_From` |
| 9 | *Deschooling Society* | `https://en.wikipedia.org/wiki/Deschooling_Society` |
| 10 | *Bowling Alone* | `https://en.wikipedia.org/wiki/Bowling_Alone` |

#### Essay 3: `_posts/2026-02-27-writing-as-system-architecture.md`

| # | Link target | URL |
|---|-------------|-----|
| 1 | "Literate Programming" | `https://en.wikipedia.org/wiki/Literate_programming` |
| 2 | "Documenting Architecture Decisions" | `https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions` |
| 3 | *Science and Sanity* | `https://en.wikipedia.org/wiki/Science_and_Sanity` |
| 4 | *The Reflective Practitioner* | `https://en.wikipedia.org/wiki/The_Reflective_Practitioner` |
| 5 | *Design Patterns* | `https://en.wikipedia.org/wiki/Design_Patterns` |
| 6 | "Continuous Integration" | `https://martinfowler.com/articles/continuousIntegration.html` |
| 7 | *The Data Warehouse Toolkit* | `https://en.wikipedia.org/wiki/The_Data_Warehouse_Toolkit` |
| 8 | *The Mythical Man-Month* | `https://en.wikipedia.org/wiki/The_Mythical_Man-Month` |
| 9 | *How Buildings Learn* | `https://en.wikipedia.org/wiki/How_Buildings_Learn` |
| 10 | *A Pattern Language* | `https://en.wikipedia.org/wiki/A_Pattern_Language` |

#### Essay 4: `_posts/2026-03-02-two-weeks-and-forty-six-essays.md`

| # | Link target | URL |
|---|-------------|-----|
| 1 | "The Age of the Essay" | `https://paulgraham.com/essay.html` |
| 2 | *Bird by Bird* | `https://en.wikipedia.org/wiki/Bird_by_Bird` |
| 3 | *On Writing* | `https://en.wikipedia.org/wiki/On_Writing:_A_Memoir_of_the_Craft` |
| 4 | *Deep Work* | `https://calnewport.com/deep-work/` |
| 5 | *Agile Retrospectives* | `https://pragprog.com/titles/dlret/agile-retrospectives/` |
| 6 | *On Writing Well* | `https://en.wikipedia.org/wiki/On_Writing_Well` |
| 7 | "Politics and the English Language" | `https://en.wikipedia.org/wiki/Politics_and_the_English_Language` |
| 8 | *Thinking, Fast and Slow* | `https://en.wikipedia.org/wiki/Thinking,_Fast_and_Slow` |
| 9 | *The Pragmatic Programmer* | `https://en.wikipedia.org/wiki/The_Pragmatic_Programmer` |
| 10 | *Extreme Programming Explained* | `https://en.wikipedia.org/wiki/Extreme_programming` |

---

## Part 2: Autonomous Link Checker

### 2a. New Module: `src/link_checker.py`

**Location**: `essay-pipeline/src/link_checker.py`

**CLI**:
```bash
python -m src.link_checker \
  --posts-dir ../public-process/_posts/ \
  --logs-dir ../public-process/_logs/ \
  --output link-report.json \
  --timeout 10 \
  --retries 2
```

**Architecture** (follows existing module patterns — argparse CLI, type hints, error collection):

```
extract_urls(filepath) → list[UrlEntry]
  - Parse markdown for [text](url) links
  - Parse references YAML for embedded markdown links
  - Filter out internal anchors (#ref-N), Jekyll post_url, mailto:

check_url(url, timeout, retries) → UrlResult
  - HTTP HEAD with fallback to GET
  - Follow redirects (report 301 permanent redirects)
  - Return status: ok | redirect | broken | timeout | error
  - Per-domain rate limiting (0.5s between requests to same host)

check_all(posts_dir, logs_dir, timeout, retries) → Report
  - Walk all .md files, extract URLs, deduplicate
  - Check each unique URL once
  - Map results back to source files

generate_report(report) → JSON
  - Per-file breakdown of link statuses
  - Summary: total links, ok, broken, redirected, timeout
  - List of broken URLs with source file and line context
```

**Key design decisions**:
- Use `httpx` (modern, sync HTTP client with connection pooling)
- HEAD first, GET fallback (some servers reject HEAD)
- Per-domain 0.5s delay to avoid hammering
- Configurable timeout (default 10s) and retries (default 2)
- Skip internal anchors, `post_url` tags, and `mailto:` links
- Cache file (`~/.cache/link-checker.json`) with 7-day TTL to speed up repeated runs

### 2b. Dependency Addition

**File**: `essay-pipeline/pyproject.toml`

Add `httpx` to dependencies:
```toml
dependencies = ["pyyaml>=6.0", "httpx>=0.27"]
```

Add script entry:
```toml
link-check = "src.link_checker:main"
```

### 2c. Tests

**File**: `essay-pipeline/tests/test_link_checker.py`

Test cases:
- `test_extract_urls_markdown_links` — finds `[text](url)` in body
- `test_extract_urls_references` — finds links in YAML references
- `test_extract_urls_skips_anchors` — ignores `#ref-N` and `post_url`
- `test_extract_urls_skips_mailto` — ignores `mailto:` links
- `test_check_url_ok` — mock 200 response
- `test_check_url_redirect` — mock 301 response
- `test_check_url_broken` — mock 404 response
- `test_check_url_timeout` — mock timeout
- `test_generate_report_json` — correct JSON structure
- `test_full_scan_fixture` — integration test with fixture file

Use `pytest` with `httpx`'s built-in `MockTransport` for HTTP mocking (no extra dependency needed).

### 2d. CI Integration

**File**: `public-process/.github/workflows/link-check.yml` (new workflow)

```yaml
name: Link Health Check

on:
  schedule:
    - cron: "0 8 * * 1"  # Monday 08:00 UTC (weekly)
  workflow_dispatch:

jobs:
  check-links:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/checkout@v6
        with:
          repository: organvm-v-logos/essay-pipeline
          path: _pipeline
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e _pipeline/
      - name: Check all links
        working-directory: _pipeline
        run: |
          python -m src.link_checker \
            --posts-dir ../_posts/ \
            --logs-dir ../_logs/ \
            --output ../data/link-report.json \
            --timeout 15 \
            --retries 3
      - name: Report broken links
        if: failure()
        run: |
          echo "::warning::Broken links detected — see link-report.json"
          cat data/link-report.json | python -c "
          import json, sys
          r = json.load(sys.stdin)
          for u in r.get('broken', []):
            print(f'::error file={u[\"file\"]},line={u[\"line\"]}::{u[\"url\"]} returned {u[\"status\"]}')
          "
```

**Behavior**: Runs weekly on Monday. `workflow_dispatch` allows manual triggering. Reports broken links as GitHub annotations. Does NOT block merges (external links can flake).

Also add a **lightweight step** to `public-process/.github/workflows/ci.yml` that checks internal links only (fast, no network):
```yaml
- name: Check internal links
  working-directory: _pipeline
  run: |
    python -m src.link_checker \
      --posts-dir ../_posts/ \
      --logs-dir ../_logs/ \
      --internal-only \
      --output /dev/null
```

---

## Files Modified/Created

| File | Repo | Action |
|------|------|--------|
| `_includes/references.html` | public-process | Modify (add `markdownify` filter) |
| `_posts/2026-02-21-the-distribution-problem.md` | public-process | Modify (reference strings) |
| `_posts/2026-02-24-community-infrastructure-for-one.md` | public-process | Modify (reference strings) |
| `_posts/2026-02-27-writing-as-system-architecture.md` | public-process | Modify (reference strings) |
| `_posts/2026-03-02-two-weeks-and-forty-six-essays.md` | public-process | Modify (reference strings) |
| `.github/workflows/link-check.yml` | public-process | Create (weekly link health) |
| `.github/workflows/ci.yml` | public-process | Modify (add internal link check step) |
| `src/link_checker.py` | essay-pipeline | Create |
| `tests/test_link_checker.py` | essay-pipeline | Create |
| `pyproject.toml` | essay-pipeline | Modify (add httpx, script entry) |
| `data/essays-index.json` | public-process | Regenerate |
| `data/logs-index.json` | public-process | Regenerate |

## Verification

```bash
# 1. Jekyll build (test markdownify rendering)
cd /Users/4jp/Workspace/organvm-v-logos/public-process
bundle exec jekyll build --strict_front_matter
# Spot-check _site/ HTML for <a> tags in reference sections

# 2. Validator still passes
cd /Users/4jp/Workspace/organvm-v-logos/essay-pipeline
source .venv/bin/activate
python -m src.validator --posts-dir ../public-process/_posts/ --schema ../editorial-standards/schemas/frontmatter-schema.yaml
python -m src.validator --posts-dir ../public-process/_logs/ --schema ../editorial-standards/schemas/log-schema.yaml --content-type log

# 3. Indexer still clean
python -m src.indexer --posts-dir ../public-process/_posts/ --logs-dir ../public-process/_logs/ --output-dir ../public-process/data/

# 4. Link checker tests pass
pytest tests/test_link_checker.py -v

# 5. Link checker runs against live content
python -m src.link_checker --posts-dir ../public-process/_posts/ --logs-dir ../public-process/_logs/ --output /tmp/link-report.json --timeout 10
cat /tmp/link-report.json | python -c "import json,sys; r=json.load(sys.stdin); print(f'{r[\"summary\"][\"total\"]} links, {r[\"summary\"][\"ok\"]} ok, {r[\"summary\"][\"broken\"]} broken')"
```
