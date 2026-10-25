import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from fastapi import HTTPException

from app.api.repositories import analyze_repository
from app.schemas.repository import RepositoryRequest
from app.services.github import commit_service, issue_service, pull_request_service
from app.services.github.github_client import GitHubAPIError, get_github_auth_status
from app.services.github.relationship_service import (
    build_pull_request_relationship,
    extract_issue_references,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload


def issue_record(number, **extra):
    value = {
        "number": number,
        "title": f"Issue {number}",
        "state": "closed",
        "created_at": "2025-01-01T00:00:00Z",
        "labels": [],
        "user": {"login": "tester"},
    }
    value.update(extra)
    return value


class IssueCollectionTests(unittest.TestCase):
    @patch("app.services.github.issue_service.github_get")
    def test_collects_all_issue_labels_and_filters_pull_requests(self, get):
        get.side_effect = [
            FakeResponse([{}, issue_record(1), issue_record(2, pull_request={"url": "x"})]),
            FakeResponse([]),
        ]
        status = {}
        with patch.object(issue_service, "PER_PAGE", 2), patch.object(issue_service, "MAX_PAGES", 4):
            result = issue_service.get_repository_issues("pallets", "flask", status)
        self.assertEqual([item["issue_number"] for item in result], [1])
        self.assertEqual(result[0]["labels"], [])
        self.assertFalse(status["limit_reached"])

    @patch("app.services.github.issue_service.github_get")
    def test_marks_page_cap_instead_of_reporting_complete(self, get):
        get.return_value = FakeResponse([issue_record(1), issue_record(2)])
        status = {}
        with patch.object(issue_service, "PER_PAGE", 2), patch.object(issue_service, "MAX_PAGES", 1):
            issue_service.get_repository_issues("owner", "repo", status)
        self.assertTrue(status["limit_reached"])

    @patch("app.services.github.issue_service.github_get")
    def test_does_not_turn_first_page_api_error_into_empty_success(self, get):
        get.side_effect = GitHubAPIError(401, "unauthorized")
        with self.assertRaises(GitHubAPIError):
            issue_service.get_repository_issues("owner", "repo")


class AuthenticationTests(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_TOKEN": "secret-test-value"})
    @patch("app.services.github.github_client.github_get")
    def test_auth_success_never_returns_token_or_profile(self, get):
        get.return_value = FakeResponse({"login": "private-login"})
        result = get_github_auth_status()
        self.assertEqual(result["status"], "authenticated")
        self.assertNotIn("secret-test-value", str(result))
        self.assertNotIn("private-login", str(result))

    @patch.dict(os.environ, {"GITHUB_TOKEN": "secret-test-value"})
    @patch("app.services.github.github_client.github_get")
    def test_auth_distinguishes_invalid_token_and_rate_limit(self, get):
        get.side_effect = GitHubAPIError(401, "unauthorized")
        self.assertEqual(get_github_auth_status()["status"], "invalid_token")
        get.side_effect = GitHubAPIError(403, "limited", rate_limited=True)
        self.assertEqual(get_github_auth_status()["status"], "rate_limited")
        get.side_effect = GitHubAPIError(403, "forbidden")
        self.assertEqual(get_github_auth_status()["status"], "insufficient_permissions")

    @patch.dict(os.environ, {}, clear=True)
    def test_reports_missing_token_without_calling_github(self):
        self.assertEqual(get_github_auth_status()["status"], "not_configured")

    @patch.dict(os.environ, {"GITHUB_TOKEN": "safe-test-token"})
    @patch("app.services.github.github_client.requests.get")
    def test_api_error_classifies_rate_limit_without_exposing_token(self, get):
        from app.services.github.github_client import github_get
        get.return_value = FakeResponse({}, status_code=403, headers={"X-RateLimit-Remaining": "0"})
        with self.assertRaises(GitHubAPIError) as raised:
            github_get("https://api.github.com/rate_limit")
        self.assertTrue(raised.exception.rate_limited)
        self.assertNotIn("safe-test-token", str(raised.exception))
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer safe-test-token")


class PullRequestAndCommitTests(unittest.TestCase):
    @patch("app.services.github.pull_request_service.github_get")
    def test_pull_requests_are_newest_first_and_cap_is_reported(self, get):
        get.return_value = FakeResponse([{
            "number": n, "title": f"PR {n}", "state": "closed", "user": {},
            "created_at": "2025-01-01T00:00:00Z", "merged_at": None,
        } for n in range(2)])
        status = {}
        with patch.object(pull_request_service, "PER_PAGE", 2), patch.object(pull_request_service, "MAX_PAGES", 1):
            result = pull_request_service.get_repository_pull_requests("owner", "repo", status)
        self.assertEqual(len(result), 2)
        self.assertEqual(get.call_args.kwargs["params"]["direction"], "desc")
        self.assertTrue(status["limit_reached"])

    @patch("app.services.github.pull_request_service.github_get")
    def test_changed_file_pagination_collects_pages(self, get):
        get.side_effect = [
            FakeResponse([{"filename": "a.py"}, {"filename": "b.py"}]),
            FakeResponse([{"filename": "c.py"}]),
        ]
        with patch.object(pull_request_service, "PER_PAGE", 2):
            result = pull_request_service.get_pull_request_files("owner", "repo", 5)
        self.assertEqual([item["filename"] for item in result], ["a.py", "b.py", "c.py"])
        self.assertEqual(get.call_count, 2)

    @patch("app.services.github.commit_service.get_commit_details")
    @patch("app.services.github.commit_service.github_get")
    def test_repository_commit_collection_includes_changed_files(self, get, details):
        get.return_value = FakeResponse([{
            "sha": "abc123", "html_url": "https://github.com/o/r/commit/abc123",
            "commit": {"message": "Fixes #3", "author": {"name": "Dev", "date": "2025-01-01"}},
        }])
        details.return_value = {"sha": "abc123", "message": "Fixes #3", "author": "Dev", "date": "2025-01-01", "changed_files": [{"filename": "src/a.py"}]}
        result = commit_service.get_repository_commits("o", "r", limit=3)
        self.assertEqual(result[0]["changed_files"][0]["filename"], "src/a.py")
        self.assertEqual(result[0]["repository"], "o/r")


class RelationshipAndEndpointTests(unittest.TestCase):
    def test_only_explicit_scoped_closing_references_are_relationships(self):
        references = extract_issue_references("Fixes #12; see #13; closes other/project#14", "owner/repo", "commit_message", "sha")
        self.assertEqual([item["issue_number"] for item in references], [12, 14])
        self.assertEqual(references[0]["repository"], "owner/repo")
        self.assertEqual(references[1]["repository"], "other/project")
        self.assertEqual(references[0]["source_commit_sha"], "sha")

    def test_relationship_uses_github_pr_membership_and_file_evidence(self):
        result = build_pull_request_relationship(
            {"number": 4, "repository": "owner/repo", "description": "Fixes #12"},
            [{"sha": "abc", "message": "Fixes #13", "author": "Dev", "date": "today"}],
            [{"filename": "src/a.py"}],
        )
        self.assertEqual(result["commits"][0]["commit_sha"], "abc")
        self.assertEqual(result["changed_files"], ["src/a.py"])
        self.assertEqual([ref["issue_number"] for ref in result["issue_references"]], [13, 12])

    @patch("app.services.github.relationship_service.get_repository_pull_requests", return_value=[])
    def test_relationship_collection_accepts_a_successful_empty_pr_list(self, get_prs):
        from app.services.github.relationship_service import collect_pull_request_relationships
        result = collect_pull_request_relationships("owner", "repo", pull_requests=[])
        self.assertEqual(result["relationships"], [])
        self.assertEqual(result["failed_pull_requests"], [])
        self.assertEqual(result["skipped_pull_requests"], 0)

    def test_invalid_repository_url_is_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            RepositoryRequest(repository_url="not a URL")
        with self.assertRaises(ValidationError):
            RepositoryRequest()

    def test_repository_path_with_query_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            analyze_repository(RepositoryRequest(repository_url="https://github.com/o/r?tab=issues"))
        self.assertEqual(raised.exception.status_code, 400)

    @patch("app.api.repositories.get_repository_issues", side_effect=GitHubAPIError(401, "unauthorized"))
    def test_invalid_github_token_does_not_become_empty_success(self, collect_issues):
        with self.assertRaises(HTTPException) as raised:
            analyze_repository(RepositoryRequest(repository_url="https://github.com/o/r"))
        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("rejected", raised.exception.detail)

    def test_successful_empty_collections_are_explicit(self):
        with patch("app.api.repositories.get_repository_details", return_value={"html_url": "https://github.com/o/r"}), \
             patch("app.api.repositories.get_repository_issues", return_value=[]), \
             patch("app.api.repositories.get_repository_pull_requests", return_value=[]), \
             patch("app.api.repositories.get_repository_commits", return_value=[]):
                result = analyze_repository(RepositoryRequest(repository_url="https://github.com/o/r"))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["empty_results"], ["issues", "pull_requests", "commits"])
        self.assertEqual(result["counts"]["commits"], 0)
        self.assertTrue(all(stage["status"] == "complete" for stage in result["collection"].values()))

    def test_failed_pull_request_stage_is_not_reported_as_empty_relationship_success(self):
        with patch("app.api.repositories.get_repository_details", return_value={"html_url": "https://github.com/o/r"}), \
             patch("app.api.repositories.get_repository_issues", return_value=[]), \
             patch("app.api.repositories.get_repository_pull_requests", side_effect=GitHubAPIError(403, "forbidden")), \
             patch("app.api.repositories.get_repository_commits", return_value=[]):
                result = analyze_repository(RepositoryRequest(repository_url="https://github.com/o/r"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["collection"]["pull_requests"]["status"], "failed")
        self.assertEqual(result["collection"]["relationships"]["status"], "not_run")
        self.assertNotIn("pull_requests", result["empty_results"])


if __name__ == "__main__":
    unittest.main()
