import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.repositories import analyze_repository
from app.normalization import normalize_analysis
from app.normalization.normalizer import NormalizationError
from app.schemas.repository import RepositoryRequest


COMMIT_SHA = "c" * 40


class AnalysisNormalizationIntegrationTests(unittest.TestCase):
    def _analyze(self, normalizer=None):
        captured_payloads = []
        normalized_results = []

        def normalize(payload):
            captured_payloads.append(payload)
            if normalizer is not None:
                normalized = normalizer(payload)
            else:
                normalized = normalize_analysis(payload)
            normalized_results.append(normalized)
            return normalized

        def collect_issues(owner, repo, collection_status):
            collection_status.update(limit_reached=True)
            return [{
                "issue_number": 11,
                "title": "Sample issue",
                "description": "Example body",
                "state": "open",
                "created_at": "2025-02-03T00:00:00Z",
                "labels": ["bug"],
                "author": "reporter",
                "comments": 0,
                "html_url": f"https://github.com/{owner}/{repo}/issues/11",
            }]

        def collect_pull_requests(owner, repo, collection_status):
            return [{
                "repository": f"{owner}/{repo}",
                "number": 12,
                "title": "Sample PR",
                "description": "Closes #11",
                "state": "closed",
                "merged": True,
                "merged_at": "2025-02-04T00:00:00Z",
                "created_at": "2025-02-03T00:00:00Z",
                "updated_at": "2025-02-04T00:00:00Z",
                "author": "contributor",
                "commits_count": 1,
                "changed_files_count": 1,
                "html_url": f"https://github.com/{owner}/{repo}/pull/12",
            }]

        def collect_commits(owner, repo, limit, collection_status):
            collection_status.update(limit_reached=True)
            return [{
                "repository": f"{owner}/{repo}",
                "sha": COMMIT_SHA,
                "message": "Sample change",
                "author": "contributor",
                "date": "2025-02-04T00:00:00Z",
                "html_url": f"https://github.com/{owner}/{repo}/commit/{COMMIT_SHA}",
                "changed_files": [{"filename": "src/sample.py", "status": "modified", "additions": 1,
                                   "deletions": 0}],
            }]

        def collect_relationships(owner, repo, pull_requests, collection_status):
            collection_status.update(partial=False)
            return {
                "relationships": [{
                    "repository": f"{owner}/{repo}",
                    "pull_request_number": 12,
                    "pull_request_title": "Sample PR",
                    "pull_request_state": "closed",
                    "merged_at": "2025-02-04T00:00:00Z",
                    "commits": [{"commit_sha": COMMIT_SHA, "message": "Sample change", "author": "contributor",
                                 "date": "2025-02-04T00:00:00Z", "changed_files": []}],
                    "commit_count": 1,
                    "changed_files": ["src/sample.py"],
                    "changed_file_count": 1,
                    "changed_file_details": [{"filename": "src/sample.py", "status": "modified",
                                               "additions": 1, "deletions": 0}],
                    "issue_references": [{
                        "repository": f"{owner}/{repo}",
                        "issue_number": 11,
                        "relationship": "explicit_closing_reference",
                        "source": "pull_request_description",
                        "evidence": "Closes #11",
                        "source_pull_request_merged": True,
                    }],
                }],
                "failed_pull_requests": [],
                "skipped_pull_requests": 2,
            }

        with patch("app.api.repositories.get_repository_details", return_value={
            "full_name": "example/project", "html_url": "https://github.com/example/project",
        }) as metadata_mock, \
             patch("app.api.repositories.get_repository_issues", side_effect=collect_issues) as issues_mock, \
             patch("app.api.repositories.get_repository_pull_requests", side_effect=collect_pull_requests) as prs_mock, \
             patch("app.api.repositories.get_repository_commits", side_effect=collect_commits) as commits_mock, \
             patch("app.api.repositories.collect_pull_request_relationships", side_effect=collect_relationships) as relations_mock, \
             patch("app.api.repositories.normalize_analysis", side_effect=normalize) as normalizer_mock, \
             patch("app.api.repositories.logger") as logger_mock:
            response = analyze_repository(RepositoryRequest(
                repository_url="https://github.com/example/project"
            ))

        calls = (metadata_mock, issues_mock, prs_mock, commits_mock, relations_mock)
        return response, captured_payloads, normalized_results, calls, normalizer_mock, logger_mock

    def test_successful_analysis_normalizes_collected_payload_without_changing_api_contract(self):
        response, payloads, _, collector_calls, normalizer_mock, _ = self._analyze()

        self.assertEqual(normalizer_mock.call_count, 1)
        self.assertEqual(payloads[0], response)
        self.assertTrue(all(mock.call_count == 1 for mock in collector_calls))
        self.assertEqual(set(response), {
            "repository", "repository_url", "repository_details", "status", "warnings", "counts",
            "collection", "empty_results", "issues", "pull_requests", "commits", "relationships",
            "failed_pull_requests", "skipped_pull_requests", "total_bugs", "bugs", "persistence",
        })
        self.assertEqual(response["persistence"]["status"], "not_configured")
        self.assertIsInstance(response["issues"], list)
        self.assertIsInstance(response["pull_requests"], list)
        self.assertIsInstance(response["relationships"], list)
        self.assertEqual(response["bugs"], response["issues"])
        self.assertEqual(response["total_bugs"], len(response["issues"]))

    def test_partial_collection_metadata_and_explicit_evidence_survive_in_memory_normalization(self):
        _, _, normalized_results, _, _, _ = self._analyze()
        normalized = normalized_results[0]

        self.assertEqual(normalized.collection_run.status, "partial")
        self.assertEqual(normalized.collection_run.counts["issues"], 1)
        self.assertEqual(normalized.collection_run.counts["skipped_relationships"], 2)
        self.assertEqual(normalized.collection_run.skipped_pull_requests, 2)
        self.assertTrue(normalized.collection_run.warnings)
        issue_edges = [edge for edge in normalized.relationships if edge.target_entity_type == "issue"]
        self.assertEqual(len(issue_edges), 1)
        self.assertEqual(issue_edges[0].relation_type, "explicitly_references_issue")
        self.assertEqual(issue_edges[0].evidence[0].kind, "explicit_text")

    def test_normalization_failure_is_logged_safely_and_api_payload_still_returns(self):
        def fail(_payload):
            raise NormalizationError("do-not-log-this-sensitive-detail")

        response, _, normalized_results, _, normalizer_mock, logger_mock = self._analyze(normalizer=fail)

        normalizer_mock.assert_called_once()
        self.assertEqual(normalized_results, [])
        logger_mock.error.assert_called_once()
        log_message = " ".join(str(part) for part in logger_mock.error.call_args.args)
        self.assertIn("NormalizationError", log_message)
        self.assertNotIn("do-not-log-this-sensitive-detail", log_message)
        self.assertIn("issues", response)
        self.assertIn("relationships", response)
        self.assertEqual(response["persistence"]["status"], "failed")

    def test_persistence_is_confirmed_only_for_matching_database_acknowledgement(self):
        def acknowledge(*_args, **kwargs):
            analysis = kwargs["json"]["analysis"]
            return Mock(
                raise_for_status=Mock(),
                json=Mock(return_value={
                    "persisted": True,
                    "run_id": analysis["collection_run"]["run_id"],
                    "repository_key": analysis["repository"]["repository_key"],
                }),
            )

        with patch.dict("os.environ", {"BUGSCOPE_INGEST_TOKEN": "test-only-token"}), \
             patch("app.api.repositories.requests.post", side_effect=acknowledge) as post:
            response, _, normalized, _, _, _ = self._analyze()

        self.assertEqual(response["persistence"]["status"], "persisted")
        self.assertEqual(response["persistence"]["run_id"], normalized[0].collection_run.run_id)
        self.assertEqual(post.call_count, 1)

    def test_http_success_without_matching_persistence_ack_is_reported_failed(self):
        fake_response = Mock(raise_for_status=Mock(), json=Mock(return_value={"ok": True}))
        with patch.dict("os.environ", {"BUGSCOPE_INGEST_TOKEN": "test-only-token"}), \
             patch("app.api.repositories.requests.post", return_value=fake_response):
            response, *_ = self._analyze()

        self.assertEqual(response["persistence"]["status"], "failed")
        self.assertEqual(response["persistence"]["reason"], "invalid_persistence_confirmation")


if __name__ == "__main__":
    unittest.main()
