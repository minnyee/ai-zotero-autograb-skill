# Manifest and local helper

The script validates supplied evidence; the agent retrieves the real authoritative record. Copying the intended metadata into the verification record without consulting its source is not verification.

```json
{
  "topic": "User's topic",
  "scope": {
    "topic": "User's topic", "task_id": "stable-task-id", "confirmed": true,
    "preset": "Global", "sources": ["chosen publications"],
    "article_types": ["journalArticle"]
  },
  "destination": {"mode": "existing", "parent_key": "EXACTKEY", "confirmed": true},
  "pending_collection": "High relevance candidates / Pending verification",
  "search_plan": {
    "topic": "User's topic", "task_id": "stable-task-id", "confirmed": true,
    "keyword_groups": {"Objects": ["full name", "abbreviation"], "Methods": ["method"]},
    "queries": ["actual source query"]
  },
  "papers": [{
    "metadata": {
      "itemType": "journalArticle", "title": "Verified title", "DOI": "10.1234/example",
      "publicationTitle": "Verified Journal", "date": "2025",
      "creators": [{"creatorType": "author", "lastName": "Author", "firstName": "First"}],
      "abstractNote": "Actual abstract or clearly attributed summary", "url": "https://publisher.example/article"
    },
    "sources": ["https://publisher.example/article"],
    "bibliographic_verification": {
      "authority": "publisher", "status": "verified", "source_url": "https://publisher.example/article",
      "record": {
        "title": "Verified title", "DOI": "10.1234/example", "publicationTitle": "Verified Journal",
        "date": "2025", "publication_years": [2024, 2025],
        "creators": [{"creatorType": "author", "lastName": "Author", "firstName": "First"}]
      }
    },
    "classification": {
      "source_path": ["User-selected source group"], "categories": ["Evidence-supported category"],
      "basis": "abstract", "status": "initial", "evidence": "What the abstract explicitly supports"
    }
  }]
}
```

This is a fictional schema example, not a citable record. `authority` is `publisher` or `doi_registry`; `status` is `verified` for a DOI or `no_doi` only when the reliable record has none. `record` is independently retrieved authoritative metadata, including all known online/issue years. Authors are compared by ordered family/corporate names, allowing differing first-name initials. Missing/incomplete or conflicting evidence must be resolved before importing that record.

Classification status is `initial`, `pending` or `candidate`. Source membership does not require an abstract; content categories do. Pending/candidate items can be saved when bibliography and scope are verified. An empty source_path retains legacy flat categories. Neither candidate status nor a source folder label changes the publication scope enforced by `scope.preset`.

For a new destination use `{"mode":"new","name":"Chosen topic name","confirmed":true}`. The name must not collide with an existing root: choose existing mode and its exact key to append, or a distinct new name. Continuations can omit destination after the helper persists its key. Changing the destination explicitly does not change publication scope or permit annotation edits.

```sh
python <skill>/scripts/zotero_library.py doctor
python <skill>/scripts/zotero_library.py scope --topic "Topic" --task-id stable --preset IEEE-Trans --output scope.json
python <skill>/scripts/zotero_library.py ingest --manifest manifest.json --dry-run --report preview.json
python <skill>/scripts/zotero_library.py ingest --manifest manifest.json --report import.json
```

`--parent-key KEY --append-existing` is an explicit membership-only CLI alternative to a confirmed destination. Legacy `--allow-existing-changes` permits additive tags/notes as well and requires separate authorization for those annotations. IEEE scope changes need `scope --confirm-scope-change` only after an explicit user decision; the flag is not a substitute for that decision.

Stdout stays compact; inspect the report for per-item errors. Exit codes: 0 success/preview, 1 item failures, 2 invalid input/setup. No DOI network verification or topic searching is performed by this helper. No item-deletion endpoint exists. Authorized collection cleanup is a separate audited migration, not a side effect of ingest.

If saveItems committed but its response or updateSession failed, the failure report includes connector_session and a private session journal. Verify the unique saved item is absent from before_item_keys and matches the authoritative bibliography. Complete that exact native updateSession using the recorded sessionID/target before reapplying intended memberships; do not submit saveItems again. Preserve any user memberships added after the failed save, and stop for inspection if the session is expired or its ownership is ambiguous. Mere ingest retry can deduplicate the item but does not by itself repair an unintended initial Connector collection.
