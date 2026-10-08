# Zotero Literature Search

[简体中文](README_CN.md)

An [Agent Skill](https://agentskills.io/specification) for finding scholarly papers within a chosen scope, verifying their bibliography, and saving them into dynamic Zotero collections. The AI searches and judges relevance; a bundled Python helper checks supplied evidence, deduplicates records, and manages collection memberships. This is an AI workflow, not a standalone search engine.

## Requirements

- An AI client supporting skills, web search, and local Python execution. **Codex on Windows is tested**, but is not mandatory. ChatGPT and other clients are suitable only if their execution environment provides these capabilities and can reach local Zotero.
- **Python 3.10+**, standard library only.
- Running **Zotero 10+** with an editable **My Library**. Group libraries are unsupported.
- In Zotero, enable **Settings → Advanced → Allow other applications on this computer to communicate with Zotero**. Approve Zotero's authorization dialog when first writing through the local API.

The execution environment must reach `127.0.0.1:23119` on the computer running Zotero; client sandbox permissions may also apply. Enabling Zotero's setting alone does not connect a remote cloud runtime to your computer. See the [Zotero Local API documentation](https://www.zotero.org/support/dev/web_api/v3/local_api).

**No additional MCP, Python packages, or Zotero browser extension is required.** The helper uses Zotero's built-in Connector protocol and local API; it does not click the browser extension or run browser translators.

Full-text retrieval is separate: use Zotero's built-in capabilities or an independently configured plugin, such as a Sci-Hub-type plugin. This skill neither supplies nor configures such plugins. Saving an item does not guarantee an automatic PDF download or plugin trigger.

## Install and use

Copy the entire `skills/zotero-literature-search` folder into your client's skill directory. Codex defaults to `~/.codex/skills/zotero-literature-search`, or `$CODEX_HOME/skills/zotero-literature-search`; other clients use their own locations. Reload skill discovery if needed. Keep the scripts and references with `SKILL.md`.

Example request:

> Use zotero-literature-search to find papers on [your topic] within [your publication scope]. Append to my existing [collection name]. Show the keywords before searching and preview the import. Save bibliographic records only; no full-text download.

1. **Confirm scope, keywords, and destination.** Choose an existing collection or a new topic. Explicit choices are reused; same-topic supplements append by default, while new topics do not inherit old restrictions.
2. **Search and screen.** Cover synonyms, abbreviations and full names, pagination, and citation links. Reuse cached results and report uncovered branches or access limits.
3. **Verify and preview.** Retrieve publisher metadata or official exports and check that each DOI belongs to the actual paper, not merely that it resolves. Unresolved bibliographic conflicts stay outside Zotero in a candidate report.
4. **Save and classify.** Reuse matching items and derive categories from user intent and article evidence. One paper can belong to several categories without duplication; it is also added directly to the topic root and intermediate collections.
5. **Report results.** Return imported/reused/candidate/conflict counts, destination, classification evidence, and remaining search gaps.

## Scope and safeguards

| Shortcut | Publication scope |
| --- | --- |
| IEEE-Trans | IEEE Transactions, including joint Transactions |
| IEEE-Journals | IEEE journals |
| IEEE-Papers | IEEE journals and conferences |
| Global | Scholarly publications across publishers |

Custom publishers, journals, dates, and article types are accepted. For a publisher or journal restriction, **search its official platform or an already configured official API first**—IEEE scopes use IEEE Xplore. Global searches use suitable scholarly databases. An official website's entire catalog is not automatically in scope; check every paper's actual publication.

Other sites are not compulsory parallel searches. For a demonstrated access or coverage gap, explain the purpose and obtain the user's choice before using another discovery entry point or widening publication scope. Single-DOI verification is separate from topic searching.

Existing metadata, attachments, notes, tags, and memberships are protected. Normal imports add authorized memberships only and never delete items or collections. Requested cleanup is a separate, explicitly authorized operation. Venue prestige alone does not establish relevance or quality; complete retrieval or full-paper reading requires evidence.

## Helper and local data

Run these commands from the installed skill directory. The AI prepares the manifest using the [schema and examples](skills/zotero-literature-search/references/manifest.md); the helper does not search websites or fetch DOI verification evidence itself.

```sh
python scripts/zotero_library.py doctor
python scripts/zotero_library.py ingest --manifest manifest.json --dry-run --report preview.json
python scripts/zotero_library.py ingest --manifest manifest.json --report import.json
```

`doctor` checks connectivity, not actual writing. Inspect partial failures before retrying: a save may have committed before its response failed. Global options and recovery details are in the manifest reference.

Credentials and runtime data stay on the installer's machine, outside the distributed skill. State defaults to `%LOCALAPPDATA%/zotero-literature-search` on Windows and `$XDG_STATE_HOME/zotero-literature-search` or `~/.local/state/zotero-literature-search` elsewhere. Windows credentials use user-bound DPAPI; other platforms use a private file. Keep manifests, reports, caches, and credentials out of Git. Revoke grants through Zotero's **Clear Write Authorizations** setting.

## Validation and license

Run `python -m unittest discover -s tests` from the repository root. **48 automated tests** use fictional records and a local mock server, never real Zotero. They cover DOI correspondence/conflicts, strict IEEE scope, destination continuation, hierarchical membership, preservation, authorization, partial saves, pagination, and relocated Unicode paths. Passing tests does not establish search completeness or scientific quality.

| Environment | Validation |
| --- | --- |
| Windows / Python / Codex | Automated tests and skill-format validation passed |
| Windows / Zotero 10.0.5 | Previously verified live import, deduplication, classification, library preservation, and recovery of a committed save after a response failure |
| macOS, Linux, other AI clients | Not run-tested |

Live Zotero checks are historical validation, not part of the automated suite. The distribution contains only code, tests, documentation, and licenses—no personal library data or credentials. Licensed under [MIT](LICENSE).
