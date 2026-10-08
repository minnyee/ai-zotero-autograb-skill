"""Fictional fixtures and a loopback mock; never connects to real desktop Zotero."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "zotero-literature-search" / "scripts" / "zotero_library.py"
spec = importlib.util.spec_from_file_location("zotero_library", SCRIPT)
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def paper(doi="10.1234/fixture-a", title="Fictional topic study", categories=None, abstract="A fictional study compares two methods."):
    result = {"metadata": {"itemType": "journalArticle", "title": title,
                         "DOI": doi, "date": "2025", "publicationTitle": "Fixture Journal",
                         "creators": [{"creatorType": "author", "firstName": "Test", "lastName": "Author"}],
                         "abstractNote": abstract, "url": "https://example.org/fixture"},
            "sources": ["https://example.org/fixture"],
            "classification": {"categories": categories if categories is not None else ["方法-比较", "对象-样本"],
                               "basis": "abstract", "evidence": "The abstract explicitly describes a comparison."}}
    result["bibliographic_verification"] = {"authority": "publisher", "source_url": "https://example.org/fixture",
        "status": "verified" if doi else "no_doi", "record": copy.deepcopy(result["metadata"])}
    return result


def manifest(papers=None, topic="Fictional research topic"):
    return {"topic": topic, "scope": lib.resolve_scope(topic, "fixture-task", "Global"),
            "search_plan": {"topic": topic, "task_id": "fixture-task", "confirmed": True,
                            "keyword_groups": {"Objects": ["fictional system"], "Methods": ["control synthesis"]},
                            "queries": ['"fictional system" "control synthesis"']},
            "search_log": [{"query": "fictional", "source": "mock", "retrieved_at": "2026-01-01"}],
            "papers": [paper()] if papers is None else papers}


class MockState:
    def __init__(self):
        self.items = {}
        self.collections = {}
        self.sessions = {}
        self.writes = []
        self.sequence = 0
        self.version = 1
        self.selected_library = 1
        self.personal_library = 1
        self.fail_save_after_commit = False
        self.conflict_once = False
        self.reject_key_once = False
        self.deny_authorization = False
        self.authorizations = 0

    def record(self, data):
        self.sequence += 1
        self.version += 1
        key = f"K{self.sequence:07d}"
        return {"key": key, "version": self.version, "data": dict(data, key=key, version=self.version)}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, payload=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Zotero-Server-ID", "fixture-instance")
        self.send_header("X-Zotero-Version", "10.0.5")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode())

    def data(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")

    def listing(self, values):
        params = parse_qs(urlsplit(self.path).query)
        start, limit = int(params.get("start", [0])[0]), int(params.get("limit", [100])[0])
        self.respond(200, list(values)[start:start + limit])

    def do_GET(self):
        state = self.server.state
        path = urlsplit(self.path).path
        if path in {"/api/", "/connector/ping"}:
            self.respond(200, {})
        elif path == "/api/users/0/collections":
            self.listing(state.collections.values())
        elif path == "/api/users/0/items/top":
            self.listing(i for i in state.items.values() if i["data"].get("itemType") != "note")
        elif path.endswith("/children"):
            key = path.split("/")[-2]
            self.listing(i for i in state.items.values() if i["data"].get("parentItem") == key)
        elif path.startswith("/api/users/0/items/"):
            item = state.items.get(path.rsplit("/", 1)[1])
            self.respond(200 if item else 404, item)
        else:
            self.respond(404)

    def do_POST(self):
        state = self.server.state
        path, data = urlsplit(self.path).path, self.data()
        if path == "/connector/getSelectedCollection":
            self.respond(200, {"libraryID": state.selected_library, "libraryEditable": True,
                               "targets": [{"id": f"L{state.personal_library}", "level": 0},
                                           {"id": "L99", "level": 0}]})
            return
        state.writes.append(path)
        if path == "/api/local/authorize":
            state.authorizations += 1
            if self.headers.get("Zotero-Server-ID") != "fixture-instance":
                self.respond(428)
            elif state.deny_authorization:
                self.respond(403, {"denied": True})
            else:
                self.respond(200, {"key": "fixture-key", "remember": False})
        elif path == "/connector/saveItems":
            saved = []
            for metadata in data["items"]:
                cleaned = {k: v for k, v in metadata.items() if k not in {"id", "attachments", "notes"}}
                item = state.record(dict(cleaned, collections=["SELECTED"], tags=[]))
                state.items[item["key"]] = item
                saved.append(item["key"])
            state.sessions[data["sessionID"]] = saved
            if state.fail_save_after_commit:
                state.fail_save_after_commit = False
                self.respond(500)
            else:
                self.respond(201)
        elif path == "/connector/updateSession":
            self.assert_target(data["target"])
            for key in state.sessions[data["sessionID"]]:
                state.items[key]["data"]["collections"] = []
            self.respond(200, {})
        elif path in {"/api/users/0/collections", "/api/users/0/items"}:
            if not self.check_auth():
                return
            target = state.collections if path.endswith("collections") else state.items
            successful = {}
            for i, value in enumerate(data):
                record = state.record(value)
                target[record["key"]] = record
                successful[str(i)] = record
            self.respond(200, {"successful": successful, "failed": {}})
        else:
            self.respond(404)

    def assert_target(self, target):
        if target != f"L{self.server.state.personal_library}":
            raise AssertionError("Not the personal library")

    def check_auth(self):
        state = self.server.state
        if self.headers.get("Zotero-Server-ID") != "fixture-instance":
            self.respond(428)
            return False
        if state.reject_key_once:
            state.reject_key_once = False
            self.respond(401)
            return False
        if self.headers.get("Zotero-API-Key") != "fixture-key":
            self.respond(401)
            return False
        return True

    def do_PATCH(self):
        state = self.server.state
        data = self.data()
        state.writes.append(self.path)
        if not self.check_auth():
            return
        item = state.items[self.path.rsplit("/", 1)[1]]
        if state.conflict_once:
            state.conflict_once = False
            item["version"] += 1
            item["data"]["collections"].append("USER-ADDED")
            self.respond(412)
            return
        if self.headers.get("If-Unmodified-Since-Version") != str(item["version"]):
            self.respond(412)
            return
        item["data"].update(data)
        item["version"] += 1
        item["data"]["version"] = item["version"]
        self.respond(204)


class ScopeAndMetadataTests(unittest.TestCase):
    def test_new_topic_requires_choice_and_presets_are_not_a_default(self):
        result = lib.resolve_scope("Topic A", "task-a")
        self.assertTrue(result["needs_confirmation"])
        self.assertFalse(result["confirmed"])
        self.assertEqual(set(result["options"]), set(lib.PRESETS))

    def test_each_preset_and_custom_scope(self):
        for preset in lib.PRESETS:
            with self.subTest(preset=preset):
                self.assertTrue(lib.resolve_scope("Topic", "task", preset)["confirmed"])
        custom = lib.resolve_scope("Topic", "task", "IEEE-Trans", ["Publisher of choice"],
                                   ["preprint"], {"from": 2020, "to": 2025}, filters=["reviews only"], scope_change_confirmed=True)
        self.assertEqual(custom["preset"], "Custom")
        self.assertNotIn("venue_filter", custom)
        self.assertEqual(custom["article_types"], ["preprint"])

    def test_reuse_only_same_topic_and_task(self):
        previous = lib.resolve_scope("Topic A", "task-a", "IEEE-Trans")
        self.assertTrue(lib.resolve_scope("Topic A", "task-a", previous=previous)["reused"])
        self.assertTrue(lib.resolve_scope("Topic B", "task-a", previous=previous)["needs_confirmation"])
        self.assertTrue(lib.resolve_scope("Topic A", "task-b", previous=previous)["needs_confirmation"])

    def test_partial_scope_and_conflicts(self):
        self.assertTrue(lib.resolve_scope("Topic", "task", years={"from": 2020})["needs_confirmation"])
        with self.assertRaises(lib.LibraryError):
            lib.resolve_scope("Topic", "task", "IEEE-Trans", article_types=["conferencePaper"])
        with self.assertRaises(lib.LibraryError):
            lib.resolve_scope("Topic", "task", "Global", years={"from": 2025, "to": 2020})

    def test_partial_continuation_updates_without_reasking_sources(self):
        previous = lib.resolve_scope("Topic", "task", "Global", filters=["reviews only"])
        result = lib.resolve_scope("Topic", "task", years={"from": 2021}, previous=previous)
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["preset"], "Global")
        self.assertEqual(result["years"], {"from": 2021})
        self.assertEqual(result["filters"], ["reviews only"])
        result = lib.resolve_scope("New topic", "task", years={"from": 2021}, previous=previous)
        self.assertTrue(result["needs_confirmation"])

    def test_missing_scope_wrong_type_and_provenance_rejected(self):
        bad = manifest()
        bad["scope"]["confirmed"] = False
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(bad)

    def test_query_plan_requires_confirmation_for_current_topic_and_task(self):
        for change in [{"confirmed": False}, {"topic": "Different topic"}, {"task_id": "Different task"},
                       {"queries": []}, {"keyword_groups": {}}, {"keyword_groups": {"Objects": [""]}}]:
            bad = manifest()
            bad["search_plan"].update(change)
            with self.subTest(change=change), self.assertRaises(lib.LibraryError):
                lib.prepare_manifest(bad)
        bad = manifest()
        del bad["search_plan"]
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(bad)
        bad = manifest()
        bad["papers"][0]["sources"] = []
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(bad)
        bad = manifest()
        bad["papers"][0]["metadata"]["itemType"] = "thesis"
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(bad)

    def test_no_abstract_or_evidence_means_pending(self):
        for fixture in [paper(abstract=""), paper()]:
            if fixture["metadata"].get("abstractNote"):
                fixture["classification"]["evidence"] = ""
            result = lib.prepare_manifest(manifest([fixture]))["papers"][0]["classification"]
            self.assertEqual(result["categories"], [])
            self.assertEqual(result["status"], "pending")

    def test_categories_are_arbitrary_and_deduplicated(self):
        fixture = paper(categories=["  Observations-optical ", "Observations-optical", "Material-ceramic"])
        result = lib.prepare_manifest(manifest([fixture], "Another discipline"))["papers"][0]
        self.assertEqual(result["classification"]["categories"], ["Observations-optical", "Material-ceramic"])

    def test_doi_normalization_and_distinct_versions(self):
        self.assertEqual(lib.normalize_doi("https://doi.org/10.1234/ABC"), "10.1234/abc")
        existing = [{"key": "A", "data": paper()["metadata"]}]
        self.assertEqual(lib.find_existing(paper(doi="DOI: 10.1234/FIXTURE-A"), existing)["key"], "A")
        self.assertIsNone(lib.find_existing(paper(doi="10.1234/different-version"), existing))

    def test_doi_less_verified_metadata_and_ambiguity(self):
        fixture = paper(doi="")
        lib.prepare_manifest(manifest([fixture]))
        existing = [{"key": "A", "data": fixture["metadata"]}]
        self.assertEqual(lib.find_existing(fixture, existing)["key"], "A")
        existing.append({"key": "B", "data": fixture["metadata"]})
        with self.assertRaises(lib.LibraryError):
            lib.find_existing(fixture, existing)

    def test_distinct_venues_without_doi_are_not_merged(self):
        fixture = paper(doi="")
        older = copy.deepcopy(fixture["metadata"])
        older["publicationTitle"] = "A different journal"
        self.assertIsNone(lib.find_existing(fixture, [{"key": "A", "data": older}]))

    def test_malformed_manifest_reports_input_error(self):
        for value in [[], {"topic": []}, manifest(["not a paper"]), manifest([{"metadata": []}])]:
            with self.subTest(value=value), self.assertRaises(lib.LibraryError):
                lib.prepare_manifest(value)

    def test_remote_endpoint_is_not_allowed(self):
        for url in ["https://example.org", "http://example.org", "http://localhost/path", "http://user@localhost"]:
            with self.assertRaises(lib.LibraryError):
                lib.Zotero(url)

    def test_ieee_preset_cannot_silently_become_custom(self):
        with self.assertRaises(lib.LibraryError):
            lib.resolve_scope("Topic", "task", "IEEE-Trans", sources=["IEEE primary; others supplementary"])
        self.assertEqual(lib.resolve_scope("Topic", "task", "IEEE-Trans", sources=["IEEE"])["preset"], "IEEE-Trans")
        previous = lib.resolve_scope("Topic", "task", "IEEE-Trans")
        with self.assertRaises(lib.LibraryError):
            lib.resolve_scope("Topic", "task", preset="Global", previous=previous)

    def test_transactions_guard_cannot_be_removed_with_venue_filter(self):
        bad = manifest()
        bad["scope"] = lib.resolve_scope(bad["topic"], "fixture-task", "IEEE-Trans")
        del bad["scope"]["venue_filter"]
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(bad)

    def test_joint_transactions_allowed_but_access_and_conferences_excluded(self):
        fixture = manifest()
        fixture['scope'] = lib.resolve_scope(fixture['topic'], 'fixture-task', 'IEEE-Trans')
        p = fixture['papers'][0]
        p['metadata']['publicationTitle'] = p['bibliographic_verification']['record']['publicationTitle'] = 'IEEE/ASME Transactions on Mechatronics'
        lib.prepare_manifest(fixture)
        p['metadata']['publicationTitle'] = p['bibliographic_verification']['record']['publicationTitle'] = 'IEEE Access'
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(fixture)
        p['metadata']['itemType'] = 'conferencePaper'
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(fixture)

    def test_doi_requires_authoritative_record_not_only_format(self):
        bad = paper()
        del bad["bibliographic_verification"]
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(manifest([bad]))
        bad = paper()
        bad["bibliographic_verification"]["record"]["DOI"] = "10.1234/existing-but-wrong"
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(manifest([bad]))

    def test_valid_doi_but_wrong_title_authors_or_venue_rejected(self):
        for field, value in [("title", "Another real paper"), ("publicationTitle", "Another Journal"),
                             ("itemType", "conferencePaper"),
                             ("creators", [{"lastName": "SomeoneElse"}])]:
            fixture = paper()
            fixture["bibliographic_verification"]["record"][field] = value
            with self.subTest(field=field), self.assertRaises(lib.LibraryError):
                lib.prepare_manifest(manifest([fixture]))

    def test_online_and_issue_years_and_typography(self):
        fixture = paper(title="Control: Study-A")
        record = fixture["bibliographic_verification"]["record"]
        record.update(title="Control — Study A", date="2024", publication_years=[2024, 2025])
        lib.prepare_manifest(manifest([fixture]))
        fixture = paper(title="LPV H∞ Control")
        fixture["metadata"]["publicationTitle"] = "Systems & Control"
        fixture["bibliographic_verification"]["record"].update(title=r"LPV $\mathcal {H}_\infty$ Control", publicationTitle="Systems &amp; Control")
        lib.prepare_manifest(manifest([fixture]))
        self.assertNotEqual(lib.bibliographic_title("H∞ control"), lib.bibliographic_title("H2 control"))

    def test_unverified_doi_cannot_be_hidden_as_doi_less(self):
        fixture = paper()
        fixture["metadata"]["DOI"] = ""
        fixture["bibliographic_verification"]["status"] = "no_doi"
        with self.assertRaises(lib.LibraryError):
            lib.prepare_manifest(manifest([fixture]))

    def test_existing_wrong_doi_is_conflict_not_a_match(self):
        fixture = paper()
        original = copy.deepcopy(fixture["metadata"])
        original["title"] = "An unrelated old paper"
        with self.assertRaises(lib.LibraryError):
            lib.find_existing(fixture, [{"key": "OLD", "data": original}])

    def test_pending_content_keeps_verified_source_and_candidate_path(self):
        fixture = paper(abstract="")
        fixture["classification"]["source_path"] = ["Selected sources"]
        result = lib.prepare_manifest(manifest([fixture]))["papers"][0]["classification"]
        self.assertEqual(result["categories"], [])
        self.assertEqual(result["collection_paths"], [["Selected sources", "Pending verification"]])

    @unittest.skipUnless(os.name == "nt", "Windows user-bound credential protection")
    def test_windows_key_protection_roundtrip(self):
        raw = b"fictional-test-key"
        protected = lib.windows_protect(raw)
        self.assertNotEqual(raw, protected)
        self.assertEqual(lib.windows_protect(protected, decrypt=True), raw)


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        self.server.state = MockState()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = lib.Zotero(f"http://127.0.0.1:{self.server.server_port}", state_dir=self.temp.name)
        self.client.key = ""  # Do not inherit a real environment key into the test mock.
        self.state = self.server.state

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def regular_items(self):
        return [i for i in self.state.items.values() if i["data"]["itemType"] != "note"]

    def notes(self):
        return [i for i in self.state.items.values() if i["data"]["itemType"] == "note"]

    def test_import_multimembership_and_repeat_is_idempotent(self):
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result["stats"]["imported"], 1)
        self.assertEqual(len(self.regular_items()), 1)
        self.assertEqual(len(self.state.collections), 3)
        self.assertEqual(len(self.regular_items()[0]["data"]["collections"]), 3)
        self.assertEqual(len(self.notes()), 1)
        second = lib.ingest(manifest(), self.client)
        self.assertEqual(second["stats"]["existing"], 1)
        self.assertEqual(len(self.regular_items()), 1)
        self.assertEqual(len(self.state.collections), 3)
        self.assertEqual(len(self.notes()), 1)

    def test_dry_run_never_writes_or_authorizes(self):
        result = lib.ingest(manifest([paper(), paper()]), self.client, dry_run=True)
        self.assertEqual(result["stats"]["would_import"], 1)
        self.assertEqual(result["stats"]["would_reuse"], 1)
        self.assertEqual(self.state.writes, [])
        self.assertEqual(self.state.authorizations, 0)

    def test_missing_abstract_only_creates_parent(self):
        result = lib.ingest(manifest([paper(abstract="")]), self.client)
        self.assertEqual(result["stats"]["pending"], 1)
        self.assertEqual(len(self.state.collections), 1)
        self.assertIn({"tag": "zls:pending"}, self.regular_items()[0]["data"]["tags"])

    def test_existing_user_memberships_tags_and_metadata_preserved(self):
        record = self.state.record(dict(paper()["metadata"], collections=["USER-COLLECTION"],
                                        tags=[{"tag": "my-tag"}], extra="Personal field"))
        self.state.items[record["key"]] = record
        lib.ingest(manifest(), self.client, allow_existing_changes=True)
        data = self.state.items[record["key"]]["data"]
        self.assertIn("USER-COLLECTION", data["collections"])
        self.assertIn({"tag": "my-tag"}, data["tags"])
        self.assertEqual(data["extra"], "Personal field")
        self.assertNotIn("/connector/saveItems", self.state.writes)

    def test_existing_library_is_completely_unchanged_by_default(self):
        collection = self.state.record({'name': 'Fictional research topic', 'parentCollection': False})
        self.state.collections[collection['key']] = collection
        record = self.state.record(dict(paper()["metadata"], collections=[collection['key']],
                                        tags=[{"tag": "user-tag"}], extra="Private annotation"))
        self.state.items[record['key']] = record
        for kind in ['note', 'attachment']:
            child = self.state.record({'itemType': kind, 'parentItem': record['key'],
                                       'note': 'User note', 'filename': 'user.pdf'})
            self.state.items[child['key']] = child
        before = copy.deepcopy((self.state.items, self.state.collections))
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result['stats']['existing_untouched'], 1)
        self.assertFalse(result['results'][0]['classification_saved'])
        self.assertEqual((self.state.items, self.state.collections), before)
        self.assertEqual(self.state.writes, [])
        self.assertEqual(self.state.authorizations, 0)

    def test_new_results_are_isolated_from_existing_topic_parent(self):
        collection = self.state.record({'name': 'Fictional research topic', 'parentCollection': False})
        self.state.collections[collection['key']] = collection
        original = copy.deepcopy(collection)
        result = lib.ingest(manifest(), self.client)
        self.assertNotEqual(result['parent_key'], collection['key'])
        self.assertEqual(self.state.collections[collection['key']], original)
        self.assertNotIn(collection['key'], self.regular_items()[0]['data']['collections'])

    def test_unowned_parent_is_rejected_before_writes(self):
        collection = self.state.record({'name': 'User collection', 'parentCollection': False})
        self.state.collections[collection['key']] = collection
        with self.assertRaises(lib.LibraryError):
            lib.ingest(manifest(), self.client, parent_key=collection['key'])
        self.assertEqual(self.state.writes, [])
        result = lib.ingest(manifest(), self.client, parent_key=collection['key'], allow_existing_changes=True)
        self.assertEqual(result['parent_key'], collection['key'])

    def test_other_task_cannot_change_previous_task_items(self):
        first = lib.ingest(manifest(), self.client)
        before = copy.deepcopy((self.state.items, self.state.collections))
        other = manifest()
        other['scope']['task_id'] = other['search_plan']['task_id'] = 'independent-task'
        result = lib.ingest(other, self.client)
        self.assertEqual(result['stats']['existing_untouched'], 1)
        self.assertEqual((self.state.items, self.state.collections), before)
        self.assertEqual(first['stats']['imported'], 1)

    def test_unconfirmed_plan_is_rejected_before_any_library_access(self):
        bad = manifest()
        bad['search_plan']['confirmed'] = False
        with self.assertRaises(lib.LibraryError):
            lib.ingest(bad, self.client)
        self.assertIsNone(self.client.server_id)
        self.assertEqual(self.state.writes, [])

    def test_unowned_collection_name_collision_is_not_reused(self):
        collection = self.state.record({'name': '检索 - Fictional research topic - fixture-task', 'parentCollection': False})
        self.state.collections[collection['key']] = collection
        before = copy.deepcopy(collection)
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result['stats']['failed'], 1)
        self.assertEqual(self.state.collections[collection['key']], before)
        self.assertEqual(self.state.writes, [])

    def test_http_failure_after_save_commit_is_not_resubmitted(self):
        self.state.fail_save_after_commit = True
        result = lib.ingest(manifest([paper(), paper()]), self.client)
        self.assertEqual(result["stats"]["failed"], 1)
        self.assertEqual(result["stats"]["existing_untouched"], 1)
        self.assertTrue(result["results"][0]["item_present"])
        self.assertEqual(self.state.writes.count("/connector/saveItems"), 1)
        self.assertEqual(len(self.regular_items()), 1)
        recovery = result['results'][0]['connector_session']
        self.assertEqual(recovery['target'], 'L1')
        self.assertTrue(Path(recovery['journal_path']).exists())
        self.assertNotIn(result['results'][0]['item_key'], recovery['before_item_keys'])

    def test_concurrent_patch_preserves_new_user_collection(self):
        self.state.conflict_once = True
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result["stats"]["imported"], 1)
        self.assertIn("USER-ADDED", self.regular_items()[0]["data"]["collections"])

    def test_reauthorization_only_after_rejected_key(self):
        self.client.key = "expired-fixture-key"
        self.state.reject_key_once = True
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result["stats"]["imported"], 1)
        self.assertEqual(self.state.authorizations, 1)

    def test_selected_group_prevents_connector_save(self):
        self.state.selected_library = 2
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result["stats"]["failed"], 1)
        self.assertNotIn("/connector/saveItems", self.state.writes)
        self.assertEqual(self.regular_items(), [])

    def test_personal_library_target_is_discovered_not_hardcoded(self):
        self.state.personal_library = self.state.selected_library = 42
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result["stats"]["imported"], 1)

    def test_denied_authorization_makes_no_collection(self):
        self.state.deny_authorization = True
        result = lib.ingest(manifest(), self.client)
        self.assertEqual(result['stats']['failed'], 1)
        self.assertEqual(self.state.collections, {})
        self.assertEqual(self.regular_items(), [])

    def test_pagination_reads_all_records(self):
        for i in range(101):
            record = self.state.record(dict(paper(doi=f"10.1234/fixture-{i}")["metadata"], collections=[], tags=[]))
            self.state.items[record["key"]] = record
        self.client.initialize()
        self.assertEqual(len(self.client.items()), 101)

    def test_parent_key_and_different_topics_do_not_reuse_children(self):
        lib.ingest(manifest(), self.client)
        lib.ingest(manifest([paper(doi="10.1234/fixture-b", categories=["New-dimension"])], "Independent topic"), self.client)
        self.assertEqual(len(self.state.collections), 5)
        parents = [c for c in self.state.collections.values() if not c["data"].get("parentCollection")]
        self.assertEqual(len(parents), 2)
        with self.assertRaises(lib.LibraryError):
            lib.ingest(manifest(), self.client, parent_key="MISSING")

    def test_relocated_cli_with_unicode_path_and_arbitrary_workdir(self):
        target = Path(self.temp.name) / "不同安装目录 with spaces" / "scripts" / "zotero_library.py"
        target.parent.mkdir(parents=True)
        target.write_bytes(SCRIPT.read_bytes())
        run = subprocess.run([sys.executable, str(target), "scope", "--topic", "不同研究主题", "--task-id", "new"],
                             cwd=self.temp.name, capture_output=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["needs_confirmation"])
        run = subprocess.run([sys.executable, str(target), "--base-url", self.client.base, "doctor"],
                             cwd=self.temp.name, capture_output=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["local_api"])
        self.assertFalse(json.loads(run.stdout)["writes_tested"])
        self.assertEqual(self.state.writes, [])

    def test_confirmed_existing_destination_adds_only_memberships_and_reuses_on_continuation(self):
        collection = self.state.record({"name": "Original topic", "parentCollection": False})
        self.state.collections[collection["key"]] = collection
        original = self.state.record(dict(paper()["metadata"], collections=["USER-OTHER"], tags=[{"tag": "user"}], extra="Keep"))
        self.state.items[original["key"]] = original
        before = copy.deepcopy(original["data"])
        fixture = manifest()
        fixture["destination"] = {"mode": "existing", "parent_key": collection["key"], "confirmed": True}
        fixture["papers"][0]["classification"]["source_path"] = ["Source-A"]
        result = lib.ingest(fixture, self.client)
        self.assertEqual(result["stats"]["existing"], 1)
        self.assertEqual(result["parent_key"], collection["key"])
        data = self.state.items[original["key"]]["data"]
        self.assertEqual({k:v for k,v in data.items() if k not in {"collections", "version"}},
                         {k:v for k,v in before.items() if k not in {"collections", "version"}})
        self.assertIn(collection["key"], data["collections"])
        self.assertIn("USER-OTHER", data["collections"])
        self.assertEqual(len(self.notes()), 0)
        children = [c for c in self.state.collections.values() if c["data"].get("parentCollection") == collection["key"]]
        self.assertEqual([c["data"]["name"] for c in children], ["Source-A"])
        source = children[0]
        leaves = [c for c in self.state.collections.values() if c["data"].get("parentCollection") == source["key"]]
        self.assertEqual(len(leaves), 2)
        self.assertTrue(all(c["key"] in data["collections"] for c in leaves))
        del fixture["destination"]
        second = lib.ingest(fixture, self.client)
        self.assertEqual(second["parent_key"], collection["key"])
        self.assertEqual(len(self.state.collections), 4)
        self.assertEqual(len(self.regular_items()), 1)

    def test_missing_saved_destination_does_not_create_replacement(self):
        first = lib.ingest(manifest(), self.client)
        del self.state.collections[first["parent_key"]]
        self.state.writes.clear()
        with self.assertRaises(lib.LibraryError):
            lib.ingest(manifest(), self.client)
        self.assertEqual(self.state.writes, [])

    def test_new_destination_name_collision_requires_explicit_existing_choice(self):
        original = self.state.record({'name': 'Selected name', 'parentCollection': False})
        self.state.collections[original['key']] = original
        fixture = manifest()
        fixture['destination'] = {'mode': 'new', 'name': 'Selected name', 'confirmed': True}
        with self.assertRaises(lib.LibraryError):
            lib.ingest(fixture, self.client)
        self.assertEqual(self.state.writes, [])

    def test_explicit_new_destination_is_honored_and_then_reused(self):
        fixture = manifest()
        fixture['destination'] = {'mode': 'new', 'name': 'First topic root', 'confirmed': True}
        first = lib.ingest(fixture, self.client)
        repeated = lib.ingest(fixture, self.client)
        self.assertEqual(first['parent_key'], repeated['parent_key'])
        fixture['destination']['name'] = 'New chosen root'
        second = lib.ingest(fixture, self.client)
        self.assertNotEqual(first['parent_key'], second['parent_key'])
        self.assertEqual(len(self.regular_items()), 1)
        memberships = self.regular_items()[0]['data']['collections']
        self.assertIn(first['parent_key'], memberships)
        self.assertIn(second['parent_key'], memberships)

    def test_doi_conflict_does_not_modify_or_duplicate_old_item(self):
        old = self.state.record(dict(paper()["metadata"], title="Wrong DOI on an unrelated item", collections=[], tags=[]))
        self.state.items[old["key"]] = old
        before = copy.deepcopy(self.state.items)
        result = lib.ingest(manifest(), self.client, append_existing=True)
        self.assertEqual(result["stats"]["failed"], 1)
        self.assertEqual(self.state.items, before)
        self.assertEqual(self.state.writes, [])


if __name__ == "__main__":
    unittest.main()
