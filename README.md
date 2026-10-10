# AI Zotero AutoGrab Skill

**AI-powered literature search, dynamic classification, and automatic Zotero import.**

[简体中文](README_CN.md)

**An AI Agent Skill that connects literature search and classification to automatic Zotero import.** Tell your AI what to find: it searches within your chosen publication scope, screens papers, derives categories from article evidence, and saves verified records into your Zotero collections.

## Highlights

- **One connected workflow:** AI searches and classifies; the bundled Python helper verifies supplied bibliographic evidence, deduplicates records, and automatically imports them into local Zotero.
- **Evidence-based organization:** categories follow the topic and papers rather than a fixed taxonomy. Multi-category membership reuses one item, with all results directly visible in the topic root.
- **Controlled and repeatable:** confirm keywords and publication scope, preview imports, and append later discoveries while preserving existing records and attachments.
- **Your collection, your choice:** create a new collection or append to an existing one. Imports reuse matching items and never delete or overwrite existing records, attachments, or notes.
- **Lightweight setup:** Python standard library and Zotero 10+, with no extra MCP server or Zotero browser extension.

Install this [Agent Skill](https://agentskills.io/specification) in a capable AI client, such as ChatGPT Work with local execution or Codex; it is not a Zotero plugin or a standalone search engine. Full-text retrieval stays with your Zotero setup.

## Requirements

- An AI client supporting local filesystem skills, web search, and local Python execution. **A Windows local agent runtime is tested**. ChatGPT Work, Codex, and other clients are suitable when their available tools and permissions provide these capabilities and can reach local Zotero. Ordinary web chat or a cloud-only runtime is insufficient without access to the computer running Zotero.
- **Python 3.10+**, standard library only.
- Running **Zotero 10+** with an editable **My Library**. Group libraries are unsupported.
- In Zotero, enable **Settings → Advanced → Allow other applications on this computer to communicate with Zotero**. Approve Zotero's authorization dialog when first writing through the local API.

The execution environment must reach `127.0.0.1:23119` on the computer running Zotero; client sandbox permissions may also apply. Enabling Zotero's setting alone does not connect a remote cloud runtime to your computer. See the [Zotero Local API documentation](https://www.zotero.org/support/dev/web_api/v3/local_api).

**No additional MCP, Python packages, or Zotero browser extension is required.** The helper uses Zotero's built-in Connector protocol and local API; it does not click the browser extension or run browser translators.

Full-text retrieval is separate: use Zotero's built-in capabilities or an independently configured plugin, such as a Sci-Hub-type plugin. This skill neither supplies nor configures such plugins. Saving an item does not guarantee an automatic PDF download or plugin trigger.

## Install and use

Share the [repository link](https://github.com/minnyee/ai-zotero-autograb-skill). In a client with a local skill installer, ask:

> Install the skill from https://github.com/minnyee/ai-zotero-autograb-skill/tree/main/skills/ai-zotero-autograb-skill

Alternatively, copy the entire `skills/ai-zotero-autograb-skill` folder into your client's configured local skill directory. Current OpenAI documentation lists `~/.agents/skills` for user skills; existing clients may use a configured or legacy location. See [local skill locations](https://learn.chatgpt.com/docs/build-skills). Reload discovery if needed; keep scripts and references with `SKILL.md`.

Example request:

> Use ai-zotero-autograb-skill to find papers on [your topic] within [your publication scope]. Append to my existing [collection name]. Show the keywords before searching and preview the import. Save bibliographic records only; no full-text download.

1. **Confirm scope, keywords, and destination.** Choose an existing collection or a new topic. Explicit choices are reused; same-topic supplements append by default, while new topics do not inherit old restrictions.
2. **Search and screen.** Cover synonyms, abbreviations and full names, pagination, and citation links. Reuse cached results and report uncovered branches or access limits.
3. **Verify and preview.** Retrieve publisher metadata or official exports and check that each DOI belongs to the actual paper, not merely that it resolves. Unresolved bibliographic conflicts stay outside Zotero in a candidate report.
4. **Save and classify.** Reuse matching items and derive categories from user intent and article evidence. One paper can belong to several categories without duplication; it is also added directly to the topic root and intermediate collections.
5. **Report results.** Return imported/reused/candidate/conflict counts, destination, classification evidence, and remaining search gaps.

## Scope and safeguards

| Scope option | Publication scope |
| --- | --- |
| IEEE-Trans | IEEE Transactions, including joint Transactions |
| IEEE-Journals | IEEE journals |
| IEEE-Papers | IEEE journals and conferences |
| Global | Scholarly publications across publishers |
| Custom | User-defined publishers, journals, dates and article types |

Custom publishers, journals, dates, and article types are accepted. For a publisher or journal restriction, **search its official platform or an already configured official API first**—IEEE scopes use IEEE Xplore. Global searches use suitable scholarly databases. An official website's entire catalog is not automatically in scope; check every paper's actual publication.

The shortcuts are optional, not an exclusive list. See [search entry points](skills/ai-zotero-autograb-skill/references/search-sources.md) for official publisher routes, optional cross-publisher discovery and coverage notes. The reference is a navigation aid, not a requirement to search all listed sites.

Other sites are not compulsory parallel searches. For a demonstrated access or coverage gap, explain the purpose and obtain the user's choice before using another discovery entry point or widening publication scope. Single-DOI verification is separate from topic searching.

Existing metadata, attachments, notes, tags, and memberships are protected. Normal imports add authorized memberships only and never delete items or collections. Requested cleanup is a separate, explicitly authorized operation. Venue prestige alone does not establish relevance or quality; complete retrieval or full-paper reading requires evidence.

## Data and authorization

Authorization credentials and runtime state stay on the installer's computer, separate from the skill files and excluded from the GitHub distribution. The user approves the first local API write in Zotero and can later revoke authorization in Zotero's settings.

Normal use is through requests to the AI; manual script execution is not required. For commands, runtime locations and troubleshooting, see the [technical reference](skills/ai-zotero-autograb-skill/references/manifest.md).

## Contributing

Suggestions, bug reports, feature requests and contributions are welcome.

Help maintain the [search entry-point reference](skills/ai-zotero-autograb-skill/references/search-sources.md) by adding official journal or publisher search routes, correcting platform details and links, or reporting broken or unavailable entry points.

- Open an [Issue](https://github.com/minnyee/ai-zotero-autograb-skill/issues) to share feedback, ask questions or propose an improvement.
- Submit a [Pull Request](https://github.com/minnyee/ai-zotero-autograb-skill/pulls) for a ready-to-review fix to the skill, documentation or references. Small documentation and link corrections can go straight to a PR; an issue is not required first.

For a new search entry point, include the source name, official URL and a short coverage note. Help distinguish publisher platforms from cross-publisher discovery services.

## Validation and license

Run `python -m unittest discover -s tests` from the repository root. **48 automated tests** use fictional records and a local mock server, never real Zotero. They cover DOI correspondence/conflicts, strict IEEE scope, destination continuation, hierarchical membership, preservation, authorization, partial saves, pagination, and relocated Unicode paths. Passing tests does not establish search completeness or scientific quality.

| Environment | Validation |
| --- | --- |
| Windows / Python / local AI agent runtime | Automated tests and skill-format validation passed |
| Windows / Zotero 10.0.5 | Previously verified live import, deduplication, classification, library preservation, and recovery of a committed save after a response failure |
| macOS, Linux, other AI clients | Not run-tested |

Live Zotero checks are historical validation, not part of the automated suite. The distribution contains only code, tests, documentation, and licenses—no personal library data or credentials. Licensed under [MIT](LICENSE).
