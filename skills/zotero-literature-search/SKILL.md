---
name: zotero-literature-search
description: Search scholarly literature within the user's chosen publication scope, verify bibliographic identifiers, and save/classify records in local Zotero. 用于通用学术文献检索、DOI 核实、Zotero 入库及动态分类。
license: MIT
---

# Zotero Literature Search

The agent searches and judges relevance; the standard-library Python helper saves and classifies verified records using Zotero Connector and Zotero 10+ Local API. Requires a skills-compatible agent with scholarly/web access and Python 3.10+. No additional MCP or Python packages. PDF acquisition is the installer's Zotero/plugin configuration; do not promise that importing an item triggers a plugin or downloads its full text. Respect search-only requests.

The execution environment must reach the local Zotero instance, normally at `127.0.0.1:23119`. Enable Zotero **Settings → Advanced → Allow other applications on this computer to communicate with Zotero** and let the user approve the first Local API write grant. This setting does not connect a remote cloud runtime to the user's computer. No Zotero browser extension is required: the helper submits metadata using the built-in Connector protocol, without invoking browser translators.

## Preserve the library and choose the destination

Existing metadata, PDFs, attachments, notes, tags and collection structure are protected. Never treat import, search, or API write authorization as permission to overwrite or reorganize them.

For a new topic, establish whether to append to an existing collection or create a new topic collection. Offer the actual matching collections when available. An explicit user choice is sufficient; do not ask again. Persist the confirmed destination's exact key in task state. Supplementing the same topic reuses this destination by default, including existing matching items, without creating a separate batch root. If the saved target is missing, ask for a replacement.

A confirmed destination or `--append-existing` authorizes adding collection memberships to existing bibliographic records. It does **not** authorize modifying their metadata, tags, notes, files, or removing other memberships. A paper in several collections is one item, not several copies. Without a destination choice, preview freely but do not silently choose to reorganize the library. The legacy `--allow-existing-changes` flag additionally permits additive tags/notes only when explicitly requested; ordinary destination selection does not require it.

Only an explicit restructuring request permits migration/cleanup of agent-created collections. Preview the exact keys and membership mapping, prove ownership from task state or pre/post creation snapshots, add and verify all replacement memberships first, then remove only authorized redundant collections. Retain unaccounted or concurrently modified collections; never delete/trash items or PDFs. Report suspected missing data using read-only evidence before attempting repairs.

## Confirm publication scope and search entry point

When source scope is unspecified for a new topic, ask once, offering:
- **IEEE-Trans**: IEEE Transactions journal articles, including joint Transactions.
- **IEEE-Journals**: IEEE journals.
- **IEEE-Papers**: IEEE journals and conferences.
- **Global**: scholarly publications across publishers.
Accept custom sources, dates and article types. New topics do not inherit old restrictions. Same-topic supplements reuse the confirmed scope. Explicit instructions take precedence.

Publication scope is a binding inclusion rule. Never silently replace IEEE-Trans with "IEEE mainly plus supplements", Custom, or a broader preset. Explain the reason and obtain a separate user decision before expanding publication scope or adding another discovery entry point. Candidate status never bypasses publication scope. Explicitly authorized historical out-of-scope candidates are a separately recorded action, not a change to ongoing search scope.

For a restricted publisher or journal scope, search its **official search platform or an already configured official API first**; this applies to IEEE, Elsevier and other publishers. IEEE presets use **IEEE Xplore first**. For Global scope, choose a suitable scholarly database rather than requiring separate passes through every publisher. The discovery platform does not define inclusion: verify each paper's actual publication against the confirmed scope. Institutional full-text access does not imply an API key. Do not invent unsupported endpoints or require a new MCP. If access is blocked, record the specific response, affected branches and unsearched pages; do not automatically switch to Crossref/OpenAlex/general web topic searches.

Other databases are not mandatory parallel passes. Propose one only for a demonstrated coverage/access gap and use it after the user chooses it. A targeted DOI metadata check is verification, not a new thematic search. Prefer already retrieved publisher records and cached registration metadata.

## Keywords, retrieval and coverage

Before a new systematic search or a material keyword expansion, present the complete keyword groups appropriate to the topic, acronyms **and full names**, variants, exclusions and representative queries for confirmation. Preserve this plan per topic/task. Do not hardcode a domain vocabulary or require a universal object/method/task structure.

Combine equivalents with OR where the database supports it; do not require every term group simultaneously. Expand abbreviated names into their own searchable full forms. Use different combinations only where they add coverage. An application may appear only in the abstract/body, so a title without the topic noun is not sufficient grounds for exclusion.

Cache results by database, query, field, filters and page/cursor; reuse verified DOI metadata by identifier. Supplements search new combinations, previously incomplete branches and new papers, rather than repeating all sources. Complete result pagination where accessible; a ranking cutoff or first page is a coverage limitation.

Use references and cited-by links from the chosen source to find missing terminology and relevant papers within scope. Distinguish actual queries from proposed queries. Track each keyword branch, fields, filters, pages, retrieved counts and access limits. Two unproductive rounds may support a stopping decision, but never prove exhaustive retrieval; unresolved capped/blocked branches remain explicit. Do not manufacture scope expansion to compensate for few results.

## Verify the bibliography before saving

A DOI's format or successful resolution does not prove that it identifies the intended article. Obtain the actual publisher record/official citation export and compare DOI, title, authors, publication and dates. Allow punctuation/markup differences and explicitly recorded online/issue publication years.

If publisher information is missing or conflicting, check **that single DOI** in its registration agency. Cache the actual returned record and provenance; never guess identifiers from titles or populate a DOI based only on a secondary search snippet. Conflicting/unverified identifiers stay in the local candidate report until resolved. Genuinely DOI-less records can be imported using verified authors, date and publication; do not hide an uncertain DOI by declaring no_doi.

Do not assume every DOI is registered at Crossref. A Crossref 404 is not proof of an invalid DOI: use the DOI registration-agency lookup or content negotiation, then inspect the correct agency's record. A year embedded in a DOI is not a publication date.

The helper requires `bibliographic_verification` with authoritative record metadata. It checks DOI equality and bibliographic correspondence before import, and flags existing items whose DOI matches but bibliography conflicts. It does not fetch verification evidence itself or prove that an agent's supplied source is authentic: the agent must retrieve and inspect that source. Do not overwrite a conflicting existing DOI automatically.

## Dynamic classification and saving

Derive categories from the user's purpose and actual abstract/body evidence. Confirm the hierarchy when it materially affects navigation. Source groups may sit above dynamic content categories, or another agreed hierarchy may fit the task. Do not hardcode category names, domains or a universal depth.

Keep publication/source, topical relevance and verification status distinct. A prestigious venue does not establish an individual paper's quality. Preserve the exact venue in bibliographic fields and the result report. A task-defined candidate collection holds high-relevance papers with unresolved methodological details, provided their bibliography and publication scope are verified.

Use `classification.source_path` plus arbitrary `categories` for nested paths. Add each saved item to the **topic root and every intermediate source/category collection**, so the parent directly displays all results without depending on Zotero's recursive-view preference. Multiple classifications reuse the same item. Missing abstracts/content evidence produce a pending category, while verified source membership remains possible.

Never infer a paper's assumptions, methods, contributions, results or validation from its title alone. Identify its actual structure rather than imposing a universal paper template. Mark whether evidence is an abstract, a body excerpt or the whole paper; a paragraph read is not a full-paper review. The helper's legacy fulltext basis means body-derived evidence: state its extent in evidence.

For manifest schema and CLI examples, read [references/manifest.md](references/manifest.md). The helper is `scripts/zotero_library.py`, resolved relative to this skill's location. Run doctor, prepare evidence, preview with `ingest --dry-run`, inspect conflicts and paths, then save within the already authorized task. Check partial failures before retrying; a failed response may follow a committed save.

Runtime credentials, caches, manifests and migration snapshots belong outside the distributable skill. Keep Zotero on an editable My Library collection when saving. Group libraries are unsupported. Local API grants come from Zotero's own dialog, not from the agent.

## Report

Return destination and scope, actual keyword/query coverage and access gaps, imported/reused/candidate/conflict counts, DOI verification results, classification evidence limits, and any authorized migration/cleanup. Report whether the parent includes all expected items and whether original items/attachments were preserved. Do not claim full-text reading, full retrieval or successful PDF downloads without evidence.
