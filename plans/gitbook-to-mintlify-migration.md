# OpenAlex Documentation Migration: GitBook → Mintlify

## Status: PLAN CREATED - AWAITING REVIEW

**Created**: January 2025
**Last updated**: January 2025
**Stage**: Claude Code has created a migration plan. Jason has NOT yet reviewed or approved it.

---

## Background & Context

### Why this migration?
- Current docs at docs.openalex.org are hosted on **GitBook**
- GitBook feels "static and document-y and 2008" (Jason's words)
- Goal: Modern API docs like OpenAI and Anthropic

### Key finding: Both OpenAI and Anthropic use Mintlify
- Mintlify is the de facto standard for modern AI/developer companies
- Also used by: Cursor, Perplexity, Zapier, Stripe
- Features: docs-as-code, interactive API playground, AI search, polished themes

### Current docs location
- **Source files**: `/Users/jasonpriem/Documents/openalex-docs/`
- **GitBook config**: `.gitbook.yaml` (has redirect mappings)
- **Structure file**: `SUMMARY.md` (table of contents)
- **Total**: ~101 markdown files

### Current doc structure
```
openalex-docs/
├── README.md                    # Overview
├── SUMMARY.md                   # GitBook TOC
├── api-guide-for-llms.md        # LLM-specific guide (valuable!)
├── quickstart-tutorial.md
├── api-entities/                # 62 files - bulk of content
│   ├── works/                   # 10 files
│   ├── authors/                 # 9 files
│   ├── sources/                 # 7 files
│   ├── institutions/            # 7 files
│   ├── topics/                  # 7 files
│   ├── publishers/              # 7 files
│   ├── funders/                 # 7 files
│   ├── concepts/                # 7 files
│   ├── keywords/                # 1 file
│   └── geo/                     # 3 files
├── how-to-use-the-api/          # 15 files
├── download-all-data/           # 7 files (snapshot docs)
└── additional-help/             # 3 files (FAQ, tutorials, bugs)
```

### Related: Zendesk Knowledge Base
- Located at: help.openalex.org/hc/en-us
- Contains conceptual articles (e.g., FWCI explanation)
- Jason hates Zendesk KB but moving from there is a separate project
- Some GitBook docs already link to Zendesk articles

---

## Decisions Made

1. **Platform**: Mintlify (confirmed)

2. **Snapshot docs location**: Keep in Mintlify
   - Recommendation: It's another access method for the same data, belongs with API docs
   - Will be a separate "Data Snapshot" section, not mixed with API reference

3. **OpenAPI spec**: Create one as part of migration
   - Currently no OpenAPI spec exists
   - Will generate from existing markdown docs
   - Enables interactive "try it" playground in Mintlify

4. **Approach**: Maximize automation, minimize human input
   - Claude Code handles: file conversion, OpenAPI creation, structure, config
   - Human tasks deferred to later: account setup, DNS, branding, final review

---

## The Migration Plan

### Phase 1: Mintlify Project Setup
- Create new directory structure
- Create `docs.json` configuration
- Set up navigation hierarchy

### Phase 2: OpenAPI Spec Creation
- Generate OpenAPI 3.0 spec covering all 10 entities
- Include all endpoints: list, get single, autocomplete, random, search, filter, group
- Define all object schemas (Work, Author, etc.) with properties from *-object.md files
- Extract example responses from current docs

### Phase 3: Content Migration
- Convert ~94 markdown files to MDX
- Transform GitBook syntax to Mintlify:
  - `{% hint %}` → `<Info>`, `<Warning>`
  - Image paths
  - Internal links
  - HTML entities cleanup
- Migrate images from `.gitbook/assets/` to `images/`

### Phase 4: Navigation & Structure
- Configure docs.json with logical groupings
- Integrate OpenAPI spec for playground
- Set base URL to api.openalex.org

### Phase 5: Redirects
- Preserve all old URLs
- Map from `.gitbook.yaml` redirects

---

## Proposed New Structure

```
openalex-mintlify-docs/
├── docs.json              # Main config
├── introduction.mdx       # Overview/landing
├── quickstart.mdx         # Getting started
├── api-reference/         # API docs
│   ├── overview.mdx
│   ├── authentication.mdx
│   ├── pagination.mdx
│   ├── filtering.mdx
│   ├── sorting.mdx
│   └── grouping.mdx
├── entities/              # Entity reference
│   ├── works/
│   ├── authors/
│   ├── sources/
│   ├── institutions/
│   ├── topics/
│   ├── keywords/
│   ├── publishers/
│   ├── funders/
│   ├── geo/
│   └── concepts/
├── data-snapshot/         # Bulk download
│   ├── overview.mdx
│   ├── data-format.mdx
│   ├── download.mdx
│   └── database-setup/
├── resources/             # Help content
│   ├── faq.mdx
│   ├── tutorials.mdx
│   └── llm-guide.mdx      # Keep prominent!
└── openapi.yaml           # NEW
```

---

## Human Tasks (Deferred)

These require human action and are pushed to later:

1. **Mintlify account setup** - Sign up at mintlify.com, connect GitHub repo
2. **Branding assets** - Provide logo files, confirm brand colors
3. **Domain configuration** - Point docs.openalex.org to Mintlify
4. **Content review** - Quick pass to catch any conversion errors
5. **API key for playground** - Decide if playground needs auth
6. **GitBook deprecation** - Remove old GitBook after cutover

---

## Useful Links

- Mintlify docs: https://www.mintlify.com/docs
- Mintlify OpenAPI integration: https://www.mintlify.com/docs/api-playground/openapi
- Anthropic on Mintlify: https://www.mintlify.com/customers/anthropic
- Current OpenAlex docs: https://docs.openalex.org
- OpenAlex Zendesk KB: https://help.openalex.org/hc/en-us

---

## Next Steps When Resuming

1. Review this plan and the proposed structure
2. If approved, Claude Code will:
   - Create the Mintlify project
   - Convert all docs
   - Generate OpenAPI spec
   - Set up configuration
3. You'll need to handle the human tasks (account, DNS, etc.)
4. Test locally with `mintlify dev`
5. Deploy and cut over from GitBook
