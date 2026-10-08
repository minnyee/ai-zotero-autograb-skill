#!/usr/bin/env python3
"""Standard-library Zotero desktop adapter; search/classification belong to the agent."""
from __future__ import annotations

import argparse
import collections
import ctypes
import hashlib
import html
import json
import os
from pathlib import Path
import re
import socket
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

PRESETS = {
    "IEEE-Trans": {"sources": ["IEEE"], "article_types": ["journalArticle"],
                   "venue_filter": "IEEE Transactions, including jointly published Transactions"},
    "IEEE-Journals": {"sources": ["IEEE"], "article_types": ["journalArticle"]},
    "IEEE-Papers": {"sources": ["IEEE"], "article_types": ["journalArticle", "conferencePaper"]},
    "Global": {"sources": ["scholarly sources across publishers"],
               "article_types": ["journalArticle", "conferencePaper"]},
}


class LibraryError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def normalize(value):
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(c for c in value if c.isalnum())


def normalize_doi(value):
    value = urllib.parse.unquote(str(value or "")).strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", value, flags=re.I)
    if value and not re.fullmatch(r"10\.\d{4,9}/\S+", value, re.I):
        raise LibraryError("Invalid DOI; use a DOI or doi.org URL, without extra citation text.")
    return value.casefold()


def bibliographic_title(value):
    value = re.sub(r"<[^>]*>", "", html.unescape(str(value)))
    value = re.sub(r"\\(?:mathcal|mathbb|mathrm|mathbf|text)\s*\{\s*([^{}]*)\s*\}", r"\1", value)
    value = re.sub(r"\\infty\b", "∞", value)
    return normalize(value.replace("∞", "infinity"))


def bibliographic_mismatch(metadata, record):
    """Compare records, not just a syntactically valid identifier."""
    if bibliographic_title(metadata.get("title", "")) != bibliographic_title(record.get("title", "")):
        return "title"
    if record.get("itemType") and metadata.get("itemType") != record["itemType"]:
        return "publication type"
    venue = metadata.get("publicationTitle") or metadata.get("proceedingsTitle", "")
    other = record.get("publicationTitle") or record.get("proceedingsTitle", "")
    if not venue or not other or bibliographic_title(venue) != bibliographic_title(other):
        return "publication"
    authors, year = author_year(metadata)
    other_authors, other_year = author_year(record)
    if not authors or not other_authors or authors != other_authors:
        return "authors"
    years = {str(y) for y in record.get("publication_years", [])}
    if other_year:
        years.add(other_year)
    if not year or year not in years:
        return "publication year (include online and issue years in the authoritative record)"
    return None


def verify_bibliography(paper):
    evidence = paper.get("bibliographic_verification")
    if not isinstance(evidence, dict) or evidence.get("authority") not in {"publisher", "doi_registry"}:
        raise LibraryError("Authoritative bibliographic verification is required before import.")
    url = evidence.get("source_url", "")
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        raise LibraryError("Bibliographic verification requires an authoritative record URL.")
    record = evidence.get("record")
    if not isinstance(record, dict):
        raise LibraryError("Bibliographic verification requires the actual authoritative metadata record.")
    mismatch = bibliographic_mismatch(paper["metadata"], record)
    if mismatch:
        raise LibraryError("Bibliographic verification mismatch: " + mismatch)
    doi, other = normalize_doi(paper["metadata"].get("DOI")), normalize_doi(record.get("DOI"))
    if doi:
        if evidence.get("status") != "verified" or doi != other:
            raise LibraryError("DOI does not match the authoritative record, or is unverified.")
    elif evidence.get("status") != "no_doi" or other:
        raise LibraryError("DOI-less import requires a verified no_doi record; do not hide an unverified DOI.")
    return evidence


def resolve_scope(topic, task_id, preset=None, sources=None, article_types=None,
                  years=None, previous=None, filters=None, scope_change_confirmed=False):
    if not topic.strip() or not task_id.strip():
        raise LibraryError("A nonempty topic and task_id are required.")
    explicit = bool(preset or sources or article_types or years or filters)
    same_task = bool(isinstance(previous, dict) and previous.get("confirmed") is True
                     and previous.get("topic") == topic and previous.get("task_id") == task_id)
    if not explicit:
        if same_task:
            return dict(previous, reused=True)
        return {"confirmed": False, "needs_confirmation": True,
                "topic": topic, "task_id": task_id, "options": PRESETS}
    if preset and preset not in PRESETS:
        raise LibraryError("Unknown scope preset.")
    prior_preset = previous.get("preset") if same_task else None
    restricted = (preset or prior_preset or "").startswith("IEEE-")
    if restricted and sources and sources != ["IEEE"] and not scope_change_confirmed:
        raise LibraryError("Changing an IEEE preset's publication sources requires explicit scope-change confirmation.")
    if same_task and prior_preset != preset and preset and not scope_change_confirmed:
        raise LibraryError("Changing the confirmed publication preset requires explicit scope-change confirmation.")
    if not preset and not sources and not same_task:
        return {"confirmed": False, "needs_confirmation": True,
                "topic": topic, "task_id": task_id, "options": PRESETS,
                "reason": "Article types/years alone do not specify the search sources."}
    chosen = dict(PRESETS[preset]) if preset else dict(previous if same_task else {})
    custom_sources = bool(sources and not (restricted and sources == ["IEEE"]))
    if custom_sources:
        chosen["sources"] = sources
        # An explicit replacement source does not silently retain a venue restriction.
        chosen.pop("venue_filter", None)
    if article_types:
        chosen["article_types"] = article_types
    chosen.setdefault("article_types", ["journalArticle", "conferencePaper"])
    effective_preset = "Custom" if custom_sources else preset or (previous.get("preset") if same_task else "Custom")
    if effective_preset == "IEEE-Trans" and chosen["article_types"] != ["journalArticle"]:
        raise LibraryError("IEEE-Trans conflicts with non-journal types; clarify the requested scope.")
    if years and years.get("from") and years.get("to") and years["from"] > years["to"]:
        raise LibraryError("The start year is later than the end year.")
    return dict(chosen, topic=topic, task_id=task_id, preset=effective_preset,
                years=years if years is not None else (previous.get("years", {}) if same_task else {}),
                filters=filters if filters is not None else (previous.get("filters", []) if same_task else []),
        confirmed=True, reused=False, scope_change_confirmed=scope_change_confirmed)


def prepare_manifest(manifest):
    if not isinstance(manifest, dict):
        raise LibraryError("Manifest must be a JSON object.")
    if not isinstance(manifest.get("topic", ""), str) or not isinstance(manifest.get("scope", {}), dict):
        raise LibraryError("topic must be text and scope must be an object.")
    topic = manifest.get("topic", "").strip()
    scope = manifest.get("scope", {})
    if not topic or scope.get("confirmed") is not True or scope.get("topic") != topic:
        raise LibraryError("Confirm the current topic's search scope before preparing an import.")
    if not scope.get("task_id") or not scope.get("sources") or not scope.get("article_types"):
        raise LibraryError("Scope requires task_id, sources and article_types.")
    plan = manifest.get("search_plan")
    if (not isinstance(plan, dict) or plan.get("confirmed") is not True
            or plan.get("topic") != topic or plan.get("task_id") != scope["task_id"]):
        raise LibraryError("Present the keyword/query plan to the user and record confirmation for this topic/task before importing.")
    groups, queries = plan.get("keyword_groups"), plan.get("queries")
    if (not isinstance(groups, dict) or not groups
            or any(not isinstance(k, str) or not isinstance(v, list) or not v
                   or any(not isinstance(t, str) or not t.strip() for t in v) for k, v in groups.items())
            or not isinstance(queries, list) or not queries
            or any(not isinstance(q, str) or not q.strip() for q in queries)):
        raise LibraryError("The confirmed search plan needs nonempty keyword groups and actual query strings.")
    papers = manifest.get("papers")
    if not isinstance(papers, list):
        raise LibraryError("papers must be a list.")
    prepared = []
    for number, paper in enumerate(papers, 1):
        if not isinstance(paper, dict) or not isinstance(paper.get("metadata", {}), dict):
            raise LibraryError(f"Paper {number}: paper and metadata must be objects.")
        metadata = dict(paper.get("metadata", {}))
        for field in ("title", "itemType", "DOI", "date", "publicationTitle", "url", "abstractNote"):
            if field in metadata and not isinstance(metadata[field], str):
                raise LibraryError(f"Paper {number}: {field} must be text.")
        if not metadata.get("title", "").strip() or not metadata.get("itemType"):
            raise LibraryError(f"Paper {number}: title and itemType are required.")
        if metadata["itemType"] in {"note", "attachment", "annotation"}:
            raise LibraryError(f"Paper {number}: import bibliographic items, not child items.")
        if metadata["itemType"] not in scope["article_types"]:
            raise LibraryError(f"Paper {number}: itemType is outside the confirmed scope.")
        if scope.get("preset") == "IEEE-Trans":
            if not re.match(r"^IEEE(?:/[A-Z]+)?\s+Transactions\b",
                            metadata.get("publicationTitle", ""), re.I):
                raise LibraryError(f"Paper {number}: verify the IEEE Transactions venue.")
        doi = normalize_doi(metadata.get("DOI"))
        if doi:
            metadata["DOI"] = doi
        # A manifest never supplies Zotero keys, collection IDs or executable payloads.
        for key in ("key", "version", "library", "collections", "attachments", "notes", "id", "tags"):
            metadata.pop(key, None)
        metadata.setdefault("creators", [])
        if not isinstance(metadata["creators"], list):
            raise LibraryError(f"Paper {number}: creators must be a list.")
        if any(not isinstance(c, dict) for c in metadata["creators"]):
            raise LibraryError(f"Paper {number}: each creator must be an object.")
        sources = paper.get("sources", [])
        if not isinstance(sources, list) or not sources or any(
                not isinstance(s, str) or urllib.parse.urlsplit(s).scheme not in {"http", "https"}
                for s in sources):
            raise LibraryError(f"Paper {number}: verified bibliographic source URLs are required.")
        if not doi and (not metadata["creators"] or not metadata.get("date")):
            raise LibraryError(f"Paper {number}: without a DOI, verified creators and date are required.")
        verification = verify_bibliography(dict(paper, metadata=metadata))
        classification = paper.get("classification", {})
        if not isinstance(classification, dict) or not isinstance(classification.get("evidence", ""), str):
            raise LibraryError(f"Paper {number}: classification must be an object with text evidence.")
        categories = classification.get("categories", [])
        if not isinstance(categories, list) or any(not isinstance(c, str) or not c.strip() for c in categories):
            raise LibraryError(f"Paper {number}: categories must be nonempty strings in a list.")
        basis = classification.get("basis", "abstract")
        if basis not in {"abstract", "fulltext"}:
            raise LibraryError(f"Paper {number}: basis must be abstract or fulltext.")
        evidence = classification.get("evidence", "").strip()
        supported = bool(evidence and (basis == "fulltext" or metadata.get("abstractNote", "").strip()))
        categories = list(dict.fromkeys(c.strip() for c in categories)) if supported else []
        source_path = classification.get("source_path", [])
        if not isinstance(source_path, list) or any(not isinstance(p, str) or not p.strip() for p in source_path):
            raise LibraryError(f"Paper {number}: source_path must be a list of collection names.")
        source_path = [p.strip() for p in source_path]
        status = classification.get("status", "initial" if categories else "pending")
        if status not in {"initial", "pending", "candidate"}:
            raise LibraryError(f"Paper {number}: unsupported classification status.")
        if not categories and status != "candidate":
            status = "pending"
        pending_label = manifest.get("pending_collection", "Pending verification")
        if not isinstance(pending_label, str) or not pending_label.strip():
            raise LibraryError("pending_collection must be nonempty text.")
        leaves = categories or ([pending_label.strip()] if source_path else [])
        if status == "candidate" and pending_label.strip() not in leaves:
            leaves = leaves + [pending_label.strip()]
        paths = [source_path + [c] for c in leaves]
        prepared.append({"metadata": metadata, "sources": sources,
                         "bibliographic_verification": verification,
                         "classification": {"categories": categories, "evidence": evidence,
                                            "basis": basis, "status": status, "source_path": source_path,
                                            "collection_paths": paths}})
    return dict(manifest, topic=topic, scope=scope, papers=prepared)


def author_year(metadata):
    authors = [c for c in metadata.get("creators", []) if c.get("creatorType", "author") == "author"]
    names = tuple(normalize(c.get("lastName") or c.get("name", "")) for c in authors)
    year = re.search(r"\b(?:18|19|20|21)\d{2}\b", str(metadata.get("date", "")))
    return names, year.group() if year else ""


def find_existing(paper, items):
    metadata = paper["metadata"]
    doi = normalize_doi(metadata.get("DOI"))
    exact = []
    for item in items:
        data = item.get("data", {})
        try:
            existing_doi = normalize_doi(data.get("DOI"))
        except LibraryError:
            existing_doi = ""
        if doi and existing_doi == doi:
            # A corrupt old DOI must not cause unrelated metadata to be reused.
            record = paper.get("bibliographic_verification", {}).get("record", metadata)
            mismatch = bibliographic_mismatch(data, record)
            if mismatch:
                raise LibraryError("Existing item DOI conflict: " + mismatch + "; original item was not changed.")
            exact.append(item)
        elif normalize(data.get("title", "")) == normalize(metadata["title"]):
            if doi and existing_doi and doi != existing_doi:
                continue  # Do not merge distinct identifiers/versions.
            a, y = author_year(metadata)
            b, z = author_year(data)
            venue = normalize(metadata.get("publicationTitle", ""))
            old_venue = normalize(data.get("publicationTitle", ""))
            same_venue = not venue or not old_venue or venue == old_venue
            if a and y and a == b and y == z and same_venue and data.get("itemType") == metadata["itemType"]:
                exact.append(item)
    unique = {i["key"]: i for i in exact}
    if len(unique) > 1:
        raise LibraryError("Multiple matching Zotero items; resolve duplicates before importing this paper.")
    return next(iter(unique.values()), None)


def default_state_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "zotero-literature-search"


def windows_protect(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.c_void_p)]
    buffer = ctypes.create_string_buffer(data)
    incoming, outgoing = Blob(len(data), ctypes.cast(buffer, ctypes.c_void_p)), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise LibraryError("Windows could not protect/unprotect the local authorization key.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


class Zotero:
    def __init__(self, base_url="http://127.0.0.1:23119", timeout=15, state_dir=None):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise LibraryError("Use a loopback Zotero desktop URL (http://127.0.0.1:23119).")
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.state_dir = Path(state_dir) if state_dir else default_state_dir()
        self.server_id = None
        self.key = os.environ.get("ZOTERO_LOCAL_API_KEY", "")
        self.key_path = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None, timeout=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged = {"Zotero-Allowed-Request": "1", "Zotero-API-Version": "3",
                  "Content-Type": "application/json", "Accept": "application/json"}
        if self.server_id:
            merged["Zotero-Server-ID"] = self.server_id
        merged.update(headers or {})
        request = urllib.request.Request(self.base + path, data=data, headers=merged, method=method)
        try:
            with self.opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
                try:
                    result = json.loads(raw) if raw else None
                except ValueError:
                    result = None
                return result, dict(response.headers.items())
        except urllib.error.HTTPError as error:
            # Do not echo remote bodies: they can contain metadata or authorization keys.
            message = f"Zotero returned HTTP {error.code} for {method} {path.split('?')[0]}."
            if error.code == 403 and path == "/api/":
                message += " Enable Settings > Advanced > Allow other applications on this computer to communicate with Zotero."
            raise LibraryError(message, error.code) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            raise LibraryError("Zotero connection failed or timed out. Check that desktop Zotero is running; writes are not blindly retried.") from None

    def initialize(self):
        _, headers = self.request("GET", "/api/")
        self.server_id = next((v for k, v in headers.items() if k.lower() == "zotero-server-id"), None)
        if not self.server_id:
            raise LibraryError("Zotero 10+ with a writable Local API is required (missing Zotero-Server-ID).")
        identity = hashlib.sha256((self.base + self.server_id).encode()).hexdigest()[:24]
        self.key_path = self.state_dir / (identity + ".auth")
        if not self.key and self.key_path.exists():
            try:
                raw = self.key_path.read_bytes()
                self.key = (windows_protect(raw, decrypt=True) if os.name == "nt" else raw).decode("ascii")
            except (OSError, UnicodeError, LibraryError):
                self.key = ""
        return {"local_api": True, "server_id": self.server_id}

    def authorize(self):
        response, _ = self.request("POST", "/api/local/authorize",
                                   {"appName": "Zotero Literature Search Skill"}, timeout=120)
        if not response or not response.get("key"):
            raise LibraryError("Zotero did not grant local write authorization.")
        self.key = response["key"]
        if response.get("remember") and self.key_path:
            raw = self.key.encode("ascii")
            if os.name == "nt":
                raw = windows_protect(raw)
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
            if os.name != "nt":
                self.key_path.chmod(0o600)

    def write(self, method, path, body, headers=None):
        for attempt in range(2):
            if not self.key:
                self.authorize()
            try:
                result, _ = self.request(method, path, body,
                                        dict(headers or {}, **{"Zotero-API-Key": self.key}))
                return result
            except LibraryError as error:
                if error.status == 401 and attempt == 0:
                    self.key = ""
                    continue  # An explicit authentication rejection means no write was applied.
                raise
        raise LibraryError("Could not authorize Zotero writes.")

    def get_all(self, endpoint):
        results, start = [], 0
        while True:
            separator = "&" if "?" in endpoint else "?"
            batch, _ = self.request("GET", endpoint + separator + urllib.parse.urlencode({"limit": 100, "start": start}))
            if not isinstance(batch, list):
                raise LibraryError("Unexpected Zotero list response.")
            results.extend(batch)
            if len(batch) < 100:
                return results
            start += len(batch)

    def items(self):
        return self.get_all("/api/users/0/items/top")

    def get_item(self, key):
        return self.request("GET", f"/api/users/0/items/{key}")[0]

    def selected_target(self):
        return self.request("POST", "/connector/getSelectedCollection", {})[0]

    def check_target(self):
        selected = self.selected_target()
        # Native getSelectedCollection orders libraries with the personal library first.
        # Derive its local ID rather than confusing local library IDs with Web API user IDs.
        root = next((t for t in (selected or {}).get("targets", [])
                     if t.get("level") == 0 and re.fullmatch(r"L\d+", str(t.get("id", "")))), None)
        if (not root or selected.get("libraryID") != int(root["id"][1:])
                or not selected.get("libraryEditable")):
            raise LibraryError("Select an editable collection in My Library in Zotero before saving. Group libraries are not supported by this adapter.")
        return root["id"]

    def save(self, paper, known_keys=None):
        target = self.check_target()
        session = uuid.uuid4().hex
        metadata = dict(paper["metadata"], id=uuid.uuid4().hex, attachments=[], notes=[], tags=[])
        body = {"sessionID": session, "uri": metadata.get("url") or paper["sources"][0],
                "items": [metadata]}
        journal = {"sessionID": session, "target": target, "endpoint": self.base,
                   "server_id": self.server_id, "title": metadata["title"], "DOI": metadata.get("DOI", ""),
                   "before_item_keys": known_keys if known_keys is not None else [i["key"] for i in self.items()],
                   "status": "pending"}
        self.pending_connector_save = dict(journal, journal_path=str(self.state_dir / "connector_sessions" / (session + ".json")))
        write_json(self.pending_connector_save["journal_path"], journal, private=True)
        self.request("POST", "/connector/saveItems", body)
        # Move only this new session's items out of the formerly selected collection.
        self.request("POST", "/connector/updateSession", {"sessionID": session, "target": target})
        item = find_existing(paper, self.items())
        if not item:
            raise LibraryError("Connector save was not confirmed by the Local API; do not blindly resubmit.")
        write_json(self.pending_connector_save["journal_path"], dict(journal, status="completed", item_key=item["key"]), private=True)
        self.pending_connector_save = None
        return item

    def ensure_collection(self, name, parent, known, owned_keys=None, on_created=None):
        matches = [c for c in known if normalize(c["data"]["name"]) == normalize(name)
                   and (c["data"].get("parentCollection") or False) == (parent or False)]
        if len(matches) > 1:
            raise LibraryError("Multiple matching collections under this parent; specify an unambiguous parent key.")
        if matches:
            if owned_keys is not None and matches[0]["key"] not in owned_keys:
                raise LibraryError("Protected mode will not reuse an existing user collection. Choose a different task ID/name or explicitly authorize existing-library additions.")
            return matches[0]["key"]
        result = self.write("POST", "/api/users/0/collections",
                            [{"name": name, "parentCollection": parent or False}])
        success = (result or {}).get("successful", {}).get("0")
        if not success:
            raise LibraryError("Zotero did not confirm collection creation.")
        known.append(success)
        if on_created:
            on_created(success["key"])
        return success["key"]

    def add_memberships(self, key, collection_keys, classification, annotate=True):
        tag = "zls:" + (classification["basis"] + "-initial" if classification["categories"] else "pending")
        for attempt in range(2):
            item = self.get_item(key)
            current = item["data"]
            memberships = list(dict.fromkeys(current.get("collections", []) + collection_keys))
            tags = list(current.get("tags", []))
            if annotate and not any(t.get("tag") == tag for t in tags):
                tags.append({"tag": tag})
            if memberships == current.get("collections", []) and tags == current.get("tags", []):
                return
            try:
                patch = {"collections": memberships}
                if annotate:
                    patch["tags"] = tags
                self.write("PATCH", f"/api/users/0/items/{key}", patch,
                           {"If-Unmodified-Since-Version": str(item["version"])})
                verified = self.get_item(key)["data"]
                if not set(collection_keys).issubset(verified.get("collections", [])):
                    raise LibraryError("Zotero did not confirm collection membership.")
                return
            except LibraryError as error:
                if error.status == 412 and attempt == 0:
                    continue  # Re-read and merge, preserving concurrent user edits.
                raise

    def add_note(self, key, topic, paper):
        classification = paper["classification"]
        payload = {"topic": topic, "sources": paper["sources"], "classification": classification}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
        marker = "zls-classification:" + digest
        children = self.get_all(f"/api/users/0/items/{key}/children")
        if any(marker in c.get("data", {}).get("note", "") for c in children):
            return
        esc = html.escape
        categories = "; ".join(classification["categories"]) or "Pending / 待判定"
        note = (f'<p>{marker}</p><p>Topic: {esc(topic)}</p>'
                f'<p>Classification: {esc(categories)}; basis: {esc(classification["basis"])}; '
                f'status: {esc(classification["status"])}</p>'
                f'<p>Evidence: {esc(classification["evidence"] or "Insufficient evidence")}</p>'
                '<p>Initial classification, not a full-text verification unless explicitly marked fulltext.</p>'
                '<ul>' + ''.join(f'<li><a href="{esc(s, quote=True)}">{esc(s)}</a></li>' for s in paper["sources"]) + '</ul>')
        result = self.write("POST", "/api/users/0/items", [{"itemType": "note", "parentItem": key,
                             "note": note, "tags": [{"tag": "zls:classification"}]}])
        if not (result or {}).get("successful", {}).get("0"):
            raise LibraryError("Zotero did not confirm classification note creation.")


def ingest(manifest, zotero, dry_run=False, parent_key=None, allow_existing_changes=False, append_existing=False):
    manifest = prepare_manifest(manifest)
    zotero.initialize()
    known_items = zotero.items()
    known_collections = zotero.get_all("/api/users/0/collections")
    topic = manifest["topic"]
    identity = {"topic": topic, "task_id": manifest["scope"]["task_id"],
                "server_id": zotero.server_id, "endpoint": zotero.base}
    task_hash = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    ownership_path = zotero.state_dir / "tasks" / (task_hash + ".json")
    ownership = load_json(ownership_path) if ownership_path.exists() else dict(identity, items=[], collections=[], parent_key=None)
    if (any(ownership.get(k) != v for k, v in identity.items())
            or any(not isinstance(ownership.get(k), list) or any(not isinstance(x, str) for x in ownership[k])
                   for k in ["items", "collections"])):
        raise LibraryError("Invalid task ownership state; existing-library protection cannot be established.")
    owned_items, owned_collections = set(ownership["items"]), set(ownership["collections"])
    destination = manifest.get("destination")
    if destination is not None:
        if not isinstance(destination, dict) or destination.get("confirmed") is not True or destination.get("mode") not in {"existing", "new"}:
            raise LibraryError("Confirm an existing or new destination before writing.")
        if destination["mode"] == "existing":
            if not destination.get("parent_key"):
                raise LibraryError("An existing destination requires its exact collection key.")
            if parent_key and parent_key != destination["parent_key"]:
                raise LibraryError("CLI parent and confirmed destination disagree.")
            parent_key = destination["parent_key"]
        append_existing = True  # Confirmed saving/classifying permits memberships, not annotations.
    elif ownership.get("append_existing"):
        append_existing = True
    new_choice = bool(destination and destination["mode"] == "new")
    if new_choice and parent_key:
        raise LibraryError("A new destination conflicts with an existing CLI parent key.")
    reuse_saved = not new_choice or destination == ownership.get("destination")
    if not parent_key and ownership.get("parent_key") and reuse_saved:
        if not any(c["key"] == ownership["parent_key"] for c in known_collections):
            raise LibraryError("The previous destination is missing; confirm a replacement instead of creating one.")
        parent_key = ownership["parent_key"]
    if destination and destination["mode"] == "new" and not parent_key:
        name = destination.get("name") or f"检索 - {topic} - {manifest['scope']['task_id']}"
        if any(not c["data"].get("parentCollection") and normalize(c["data"]["name"]) == normalize(name)
               for c in known_collections):
            raise LibraryError("A new destination name already exists; choose its exact key or a distinct new name.")

    def remember(kind, key):
        target = owned_items if kind == "items" else owned_collections
        target.add(key)
        ownership[kind] = sorted(target)
        write_json(ownership_path, ownership, private=True)

    def ensure(name, parent):
        return zotero.ensure_collection(name, parent, known_collections,
                                       None if allow_existing_changes or append_existing else owned_collections,
                                       lambda key: remember("collections", key))

    if parent_key:
        if not any(c["key"] == parent_key for c in known_collections):
            raise LibraryError("The supplied parent collection key is not in My Library.")
        if not dry_run and not (allow_existing_changes or append_existing) and parent_key not in owned_collections:
            raise LibraryError("An existing parent requires a confirmed destination or --append-existing authorization.")
    elif reuse_saved and ownership.get("parent_key") in owned_collections:
        saved_parent = ownership["parent_key"]
        if any(c["key"] == saved_parent for c in known_collections):
            parent_key = saved_parent
    outcomes = []
    if not dry_run and parent_key:
        ownership.update(parent_key=parent_key, append_existing=append_existing)
        if destination:
            ownership["destination"] = destination
        write_json(ownership_path, ownership, private=True)
    for paper in manifest["papers"]:
        zotero.pending_connector_save = None
        metadata = paper["metadata"]
        outcome = {"title": metadata["title"], "DOI": metadata.get("DOI", ""),
                   "categories": paper["classification"]["categories"],
                   "classification": paper["classification"]["status"],
                   "collection_paths": paper["classification"]["collection_paths"]}
        item = None
        try:
            item = find_existing(paper, known_items)
            if dry_run:
                outcome.update(status="would_reuse" if item else "would_import",
                               item_key=item["key"] if item else None)
                outcome["library_action"] = ("leave_existing_unchanged" if item and item["key"] not in owned_items
                                             and not (allow_existing_changes or append_existing) else "save_or_append_memberships")
                # Simulate the first import so in-manifest duplicates are recognized too.
                if not item:
                    preview_key = "preview-" + uuid.uuid4().hex
                    known_items.append({"key": preview_key, "data": metadata})
                    owned_items.add(preview_key)
            else:
                if item and item["key"] not in owned_items and not (allow_existing_changes or append_existing):
                    outcome.update(status="existing_untouched", item_key=item["key"],
                                   library_action="leave_existing_unchanged",
                                   classification_saved=False)
                    outcomes.append(outcome)
                    continue
                if not parent_key:
                    parent_name = (destination or {}).get("name") or (topic if allow_existing_changes else f"检索 - {topic} - {manifest['scope']['task_id']}")
                    parent_key = ensure(parent_name, False)
                    ownership["parent_key"] = parent_key
                    ownership["append_existing"] = append_existing
                    if destination:
                        ownership["destination"] = destination
                    write_json(ownership_path, ownership, private=True)
                status = "existing" if item else "imported"
                if not item:
                    item = zotero.save(paper, known_keys=[i["key"] for i in known_items])
                    remember("items", item["key"])
                    known_items.append(item)
                outcome["item_key"] = item["key"]
                keys = [parent_key]
                for path in paper["classification"]["collection_paths"]:
                    parent = parent_key
                    for name in path:
                        parent = ensure(name, parent)
                        keys.append(parent)
                keys = list(dict.fromkeys(keys))
                annotate = allow_existing_changes or status == "imported"
                zotero.add_memberships(item["key"], keys, paper["classification"], annotate=annotate)
                if annotate:
                    zotero.add_note(item["key"], topic, paper)
                outcome["status"] = status
                outcome["classification_saved"] = True
        except LibraryError as error:
            # Refresh after an ambiguous write; never submit the same save again in this run.
            outcome.update(status="failed", error=str(error))
            if getattr(zotero, "pending_connector_save", None):
                outcome["connector_session"] = zotero.pending_connector_save
            try:
                known_items = zotero.items()
                recovered = find_existing(paper, known_items)
                if recovered:
                    outcome.update(item_key=recovered["key"], item_present=True)
            except LibraryError:
                pass
        outcomes.append(outcome)
    stats = dict(collections.Counter(o["status"] for o in outcomes))
    stats["pending"] = sum(o["classification"] in {"pending", "candidate"} for o in outcomes)
    return {"topic": topic, "scope": manifest["scope"], "dry_run": dry_run,
            "search_plan": manifest["search_plan"], "protect_existing": not allow_existing_changes,
            "append_existing": append_existing,
            "parent_key": parent_key, "stats": stats, "results": outcomes,
            "search_log": manifest.get("search_log", [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:23119")
    parser.add_argument("--state-dir", help="Local runtime state, outside the distributable skill")
    parser.add_argument("--timeout", type=float, default=15)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Read-only connection check; never requests write authorization")
    scope = sub.add_parser("scope", help="Resolve explicit scope or signal that the agent must ask")
    scope.add_argument("--topic", required=True)
    scope.add_argument("--task-id", required=True)
    scope.add_argument("--preset", choices=PRESETS)
    scope.add_argument("--sources", nargs="+")
    scope.add_argument("--article-types", nargs="+")
    scope.add_argument("--year-from", type=int)
    scope.add_argument("--year-to", type=int)
    scope.add_argument("--filters", nargs="+")
    scope.add_argument("--previous", help="Previously resolved scope JSON, same topic and task only")
    scope.add_argument("--output")
    scope.add_argument("--confirm-scope-change", action="store_true", help="Only after the user explicitly changes the publication scope")
    imp = sub.add_parser("ingest", help="Import a verified agent-prepared manifest")
    imp.add_argument("--manifest", required=True)
    imp.add_argument("--dry-run", action="store_true")
    imp.add_argument("--parent-key")
    imp.add_argument("--append-existing", action="store_true", help="User-authorized collection memberships only; preserves old metadata, tags and notes")
    imp.add_argument("--allow-existing-changes", action="store_true",
                     help="Only after explicit user authorization: allow additive memberships/tags/notes on existing items and reuse an existing parent; never deletes or overwrites metadata")
    imp.add_argument("--report", help="Full local report; stdout stays compact")
    args = parser.parse_args(argv)
    try:
        if args.command == "scope":
            years = {"from": args.year_from, "to": args.year_to} if args.year_from or args.year_to else None
            result = resolve_scope(args.topic, args.task_id, args.preset, args.sources,
                                   args.article_types, years,
                                   load_json(args.previous) if args.previous else None, args.filters, args.confirm_scope_change)
            if args.output:
                write_json(args.output, result)
        else:
            zotero = Zotero(args.base_url, args.timeout, args.state_dir)
            if args.command == "doctor":
                _, ping_headers = zotero.request("GET", "/connector/ping")
                version = next((v for k, v in ping_headers.items() if k.lower() == "x-zotero-version"), "unknown")
                result = dict(zotero.initialize(), connector=True, zotero_version=version,
                              writes_tested=False, imports_tested=False)
            else:
                report = ingest(load_json(args.manifest), zotero, args.dry_run, args.parent_key,
                                args.allow_existing_changes, args.append_existing)
                report_path = Path(args.report) if args.report else zotero.state_dir / "reports" / (uuid.uuid4().hex + ".json")
                write_json(report_path, report, private=True)
                result = {"topic": report["topic"], "dry_run": report["dry_run"], "stats": report["stats"],
                          "report": str(report_path.resolve()),
                          "errors": [{"title": r["title"], "error": r["error"]}
                                     for r in report["results"] if r["status"] == "failed"][:10]}
                print(json.dumps(result, ensure_ascii=False))
                return 1 if report["stats"].get("failed") else 0
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (LibraryError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
