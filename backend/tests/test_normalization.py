import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.normalization import NormalizationError, normalize_analysis


SHA_A = "a" * 40
SHA_B = "b" * 40


def response(**overrides):
    value = {
        "repository": "pallets/flask",
        "repository_url": "https://github.com/pallets/flask",
        "repository_details": {"full_name": "pallets/flask", "html_url": "https://github.com/pallets/flask"},
        "status": "partial",
        "warnings": ["Pull request limit reached"],
        "counts": {"issues": 1, "pull_requests": 1, "commits": 1, "changed_files": 1,
                   "relationships": 1, "failed_relationships": 0, "skipped_relationships": 4},
        "collection": {"issues": {"status": "complete", "returned": 1},
                       "relationships": {"status": "partial", "returned": 1, "skipped": 4}},
        "empty_results": [],
        "issues": [{"issue_number": 7, "title": "Issue", "description": "Details", "state": "closed",
                    "created_at": "2025-01-01T03:00:00+03:00", "labels": ["bug"], "author": "alice",
                    "comments": 2, "html_url": "https://github.com/pallets/flask/issues/7"}],
        "pull_requests": [{"repository": "pallets/flask", "number": 9, "title": "PR", "description": "Closes #7",
                           "state": "closed", "merged": True, "merged_at": "2025-01-02T00:00:00Z",
                           "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-01-02T00:00:00Z",
                           "author": "bob", "commits_count": 1, "changed_files_count": 1,
                           "html_url": "https://github.com/pallets/flask/pull/9"}],
        "commits": [{"repository": "pallets/flask", "sha": SHA_A, "message": "Fixes #7", "author": "bob",
                     "date": "2025-01-02T00:00:00Z", "html_url": "https://github.com/pallets/flask/commit/" + SHA_A,
                     "changed_files": [{"filename": "src/app.py", "status": "modified", "additions": 3,
                                        "deletions": 1}], "issue_references": []}],
        "relationships": [{"repository": "pallets/flask", "pull_request_number": 9, "commits": [
            {"commit_sha": SHA_A, "message": "Fixes #7", "author": "bob", "date": "2025-01-02T00:00:00Z",
             "changed_files": []}], "commit_count": 1, "changed_files": ["src/app.py"],
            "changed_file_details": [{"filename": "src/app.py", "status": "modified", "additions": 3,
                                       "deletions": 1}], "issue_references": [
                {"repository": "pallets/flask", "issue_number": 7, "relationship": "explicit_closing_reference",
                 "source": "pull_request_description", "evidence": "Closes #7",
                 "target_in_collected_issues": True, "source_pull_request_merged": True}]}],
        "failed_pull_requests": [],
        "skipped_pull_requests": 4,
        "total_bugs": 1,
        "bugs": [],
    }
    value.update(overrides)
    return value


class AnalysisNormalizationTests(unittest.TestCase):
    def test_normalizes_records_and_converts_timestamps_to_utc(self):
        normalized = normalize_analysis(response())
        self.assertEqual(normalized.issues[0].entity_id, "pallets/flask#issue:7")
        self.assertEqual(normalized.pull_requests[0].entity_id, "pallets/flask#pull:9")
        self.assertEqual(normalized.commits[0].entity_id, f"pallets/flask#commit:{SHA_A}")
        self.assertEqual(normalized.issues[0].created_at, datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(normalized.changed_files[0].path, "src/app.py")
        self.assertEqual(normalized.changed_files[0].additions, 3)

    def test_duplicate_commit_is_merged_and_references_are_repo_scoped(self):
        source = response()
        source["commits"].append({"sha": SHA_A.upper(), "message": None, "date": None,
                                  "changed_files": [], "issue_references": []})
        normalized = normalize_analysis(source)
        self.assertEqual(len(normalized.commits), 1)
        # The PR-specific commit and explicit duplicate are both additional observations.
        self.assertEqual(normalized.duplicate_records_merged, 2)
        self.assertEqual(normalized.commits[0].message, "Fixes #7")
        second = normalize_analysis(response(repository="other/flask", repository_details={"full_name": "other/flask"}))
        self.assertNotEqual(normalized.issues[0].entity_id, second.issues[0].entity_id)

    def test_explicit_reference_stays_explicit_and_preserves_cross_repository_target(self):
        source = response()
        source["relationships"][0]["issue_references"] = [{
            "repository": "other/project", "issue_number": 22, "relationship": "explicit_closing_reference",
            "source": "pull_request_description", "evidence": "Closes other/project#22",
            "target_in_collected_issues": False, "source_pull_request_merged": False,
        }]
        normalized = normalize_analysis(source)
        issue_edges = [edge for edge in normalized.relationships if edge.target_entity_type == "issue"]
        self.assertEqual(len(issue_edges), 1)
        self.assertEqual(issue_edges[0].relation_type, "explicitly_references_issue")
        self.assertEqual(issue_edges[0].target_repository_key, "other/project")
        self.assertEqual(issue_edges[0].evidence[0].kind, "explicit_text")
        self.assertFalse(any(edge.relation_type == "inferred_candidate" for edge in normalized.relationships))

    def test_partial_collection_metadata_is_preserved(self):
        normalized = normalize_analysis(response())
        self.assertEqual(normalized.collection_run.status, "partial")
        self.assertEqual(normalized.collection_run.counts["skipped_relationships"], 4)
        self.assertEqual(normalized.collection_run.skipped_pull_requests, 4)
        self.assertEqual(normalized.collection_run.stages["relationships"]["status"], "partial")
        self.assertEqual(normalized.collection_run.warnings, ["Pull request limit reached"])

    def test_malformed_optional_fields_are_omitted_with_warnings(self):
        source = response()
        source["issues"][0]["created_at"] = "2025-01-01T12:00:00"
        source["issues"][0]["comments"] = -3
        source["pull_requests"][0]["merged"] = "yes"
        source["commits"][0]["date"] = "not-a-date"
        source["relationships"][0]["commits"][0]["date"] = "also-not-a-date"
        normalized = normalize_analysis(source)
        self.assertIsNone(normalized.issues[0].created_at)
        self.assertIsNone(normalized.issues[0].comments)
        self.assertIsNone(normalized.pull_requests[0].merged)
        self.assertIsNone(normalized.commits[0].authored_at)
        self.assertGreaterEqual(len(normalized.normalization_warnings), 4)

    def test_unhashable_issue_state_and_collection_status_are_safe(self):
        for malformed in ([], {}, 7):
            with self.subTest(issue_state=malformed):
                source = response()
                source["issues"][0]["state"] = malformed
                normalized = normalize_analysis(source)
                self.assertIsNone(normalized.issues[0].state)
                self.assertTrue(any("issues[0].state" in warning for warning in normalized.normalization_warnings))

            with self.subTest(collection_status=malformed):
                source = response(status=malformed)
                normalized = normalize_analysis(source)
                self.assertIsNone(normalized.collection_run.status)
                self.assertTrue(any("status:" in warning for warning in normalized.normalization_warnings))

    def test_orphan_pull_request_relationship_produces_no_orphan_edges(self):
        source = response()
        orphan = dict(source["relationships"][0])
        orphan["pull_request_number"] = 999
        source["relationships"].append(orphan)

        normalized = normalize_analysis(source)

        self.assertFalse(any(edge.source_entity_id == "pallets/flask#pull:999" for edge in normalized.relationships))
        self.assertTrue(any(edge.source_entity_id == "pallets/flask#pull:9" for edge in normalized.relationships))
        self.assertTrue(any("PR #999" in warning for warning in normalized.normalization_warnings))

    def test_valid_pull_request_relationship_still_normalizes(self):
        normalized = normalize_analysis(response())
        relations = [edge.relation_type for edge in normalized.relationships]
        self.assertIn("pull_request_contains_commit", relations)
        self.assertIn("pull_request_changes_file", relations)
        self.assertTrue(any(edge.source_entity_id == "pallets/flask#pull:9" for edge in normalized.relationships))

    def test_mismatched_or_malformed_repository_records_are_skipped(self):
        for repo_value in ("other/project", "not/a/repository/path", [], None):
            with self.subTest(repository=repo_value):
                source = response()
                source["pull_requests"][0]["repository"] = repo_value
                source["commits"][0]["repository"] = repo_value
                source["relationships"][0]["repository"] = repo_value

                normalized = normalize_analysis(source)

                self.assertEqual(normalized.pull_requests, [])
                self.assertEqual(normalized.commits, [])
                self.assertFalse(any(edge.source_entity_type == "pull_request" for edge in normalized.relationships))
                self.assertTrue(any("repository" in warning and "skipped" in warning
                                    for warning in normalized.normalization_warnings))

    def test_repository_identity_comparison_is_case_insensitive(self):
        source = response()
        source["pull_requests"][0]["repository"] = "Pallets/Flask"
        source["commits"][0]["repository"] = "PALLETS/FLASK"
        source["relationships"][0]["repository"] = "pAlLeTs/fLaSk"

        normalized = normalize_analysis(source)

        self.assertEqual(len(normalized.pull_requests), 1)
        self.assertEqual(len(normalized.commits), 1)
        self.assertTrue(any(edge.relation_type == "pull_request_contains_commit"
                            for edge in normalized.relationships))

    def test_mismatched_nested_commit_repository_skips_its_edge(self):
        source = response()
        source["relationships"][0]["commits"][0]["repository"] = "another/repo"

        normalized = normalize_analysis(source)

        self.assertFalse(any(edge.relation_type == "pull_request_contains_commit"
                            for edge in normalized.relationships))
        self.assertTrue(any(edge.relation_type == "pull_request_changes_file"
                            for edge in normalized.relationships))
        self.assertTrue(any("relationships[0].commits[0]" in warning
                            for warning in normalized.normalization_warnings))

    def test_malformed_required_identity_and_non_object_records_are_skipped(self):
        source = response(issues=[None, {"issue_number": "7"}], commits=[{"sha": "bad"}],
                          relationships=[None])
        normalized = normalize_analysis(source)
        self.assertEqual(normalized.issues, [])
        self.assertEqual(normalized.commits, [])
        self.assertTrue(normalized.normalization_warnings)

    def test_invalid_repository_raises_clear_error(self):
        with self.assertRaises(NormalizationError):
            normalize_analysis({"repository": "not-a-repository"})

    def test_does_not_mutate_response_and_keeps_existing_api_shape_outside_normalizer(self):
        source = response()
        before = repr(source)
        normalize_analysis(source)
        self.assertEqual(repr(source), before)
        # The normalizer is a separate adapter; it does not inject fields into the dashboard payload.
        self.assertNotIn("normalized", source)


if __name__ == "__main__":
    unittest.main()
