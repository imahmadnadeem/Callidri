#!/usr/bin/env python3
"""
test_system_apis.py
-------------------
Verifies that all backend APIs are reachable and correctly wired.

Endpoints tested:
  GET    /dashboard/stats
  GET    /dashboard/calls
  GET    /knowledge/list
  POST   /knowledge/upload
  DELETE /knowledge/{doc_id}

Lifecycle test:
  1. Upload test_doc.txt
  2. Confirm it appears in /knowledge/list
  3. Delete it
  4. Confirm it disappears from /knowledge/list

Usage:
  python test_system_apis.py [--base-url http://localhost:8000]
"""

import argparse
import json
import os
import sys
import tempfile

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' library is not installed.")
    print("        Run:  pip install requests")
    sys.exit(1)


# ── configuration ─────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "http://localhost:8000"
TEST_DOC_FILENAME = "test_doc.txt"
TEST_DOC_CONTENT = (
    "This is a test document created by test_system_apis.py.\n"
    "It is used to verify the knowledge base upload, list, and delete endpoints.\n"
    "VoxAgent API smoke test — safe to delete.\n"
)
TIMEOUT = 15  # seconds per request


# ── helpers ───────────────────────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details: list[str] = []

    def ok(self, label: str, extra: str = "") -> None:
        msg = f"  [OK]   {label}"
        if extra:
            msg += f"  →  {extra}"
        print(msg)
        self.details.append(("OK", label))
        self.passed += 1

    def fail(self, label: str, reason: str = "") -> None:
        msg = f"  [FAIL] {label}"
        if reason:
            msg += f"  →  {reason}"
        print(msg)
        self.details.append(("FAIL", label))
        self.failed += 1

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


def _get(results: TestResult, base_url: str, path: str, label: str, **params) -> dict | None:
    """
    Perform a GET request and print result.
    Returns the parsed JSON body on success, None on failure.
    """
    url = base_url.rstrip("/") + path
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        if resp.status_code == 200:
            results.ok(label, f"HTTP {resp.status_code}")
            try:
                return resp.json()
            except Exception:
                return {}
        else:
            results.fail(label, f"HTTP {resp.status_code}: {resp.text[:120]}")
            return None
    except requests.exceptions.ConnectionError:
        results.fail(label, f"endpoint missing — could not connect to {url}")
        return None
    except requests.exceptions.Timeout:
        results.fail(label, f"request timed out after {TIMEOUT}s")
        return None
    except Exception as exc:
        results.fail(label, f"unexpected error: {exc}")
        return None


def _post_file(
    results: TestResult, base_url: str, path: str, label: str, filename: str, content: str
) -> dict | None:
    """
    Perform a multipart POST with a text file and print result.
    Returns the parsed JSON body on success, None on failure.
    """
    url = base_url.rstrip("/") + path
    try:
        files = {"file": (filename, content.encode("utf-8"), "text/plain")}
        resp = requests.post(url, files=files, timeout=TIMEOUT)
        if resp.status_code == 200:
            results.ok(label, f"HTTP {resp.status_code}")
            try:
                return resp.json()
            except Exception:
                return {}
        else:
            results.fail(label, f"HTTP {resp.status_code}: {resp.text[:120]}")
            return None
    except requests.exceptions.ConnectionError:
        results.fail(label, f"endpoint missing — could not connect to {url}")
        return None
    except requests.exceptions.Timeout:
        results.fail(label, f"request timed out after {TIMEOUT}s")
        return None
    except Exception as exc:
        results.fail(label, f"unexpected error: {exc}")
        return None


def _delete(results: TestResult, base_url: str, path: str, label: str) -> dict | None:
    """
    Perform a DELETE request and print result.
    Returns the parsed JSON body on success, None on failure.
    """
    url = base_url.rstrip("/") + path
    try:
        resp = requests.delete(url, timeout=TIMEOUT)
        if resp.status_code == 200:
            results.ok(label, f"HTTP {resp.status_code}")
            try:
                return resp.json()
            except Exception:
                return {}
        else:
            results.fail(label, f"HTTP {resp.status_code}: {resp.text[:120]}")
            return None
    except requests.exceptions.ConnectionError:
        results.fail(label, f"endpoint missing — could not connect to {url}")
        return None
    except requests.exceptions.Timeout:
        results.fail(label, f"request timed out after {TIMEOUT}s")
        return None
    except Exception as exc:
        results.fail(label, f"unexpected error: {exc}")
        return None


def _doc_id_in_list(list_response: dict, doc_id: str) -> bool:
    """Return True if doc_id appears in the /knowledge/list response."""
    docs = list_response.get("documents", [])
    return any(d.get("doc_id") == doc_id for d in docs)


# ── test sections ──────────────────────────────────────────────────────────────

def test_dashboard_stats(results: TestResult, base_url: str) -> None:
    print("\n─── GET /dashboard/stats ───────────────────────────────────────")
    body = _get(results, base_url, "/dashboard/stats", "GET /dashboard/stats reachable")
    if body is not None:
        # Validate expected keys
        expected_keys = {"total_calls", "calls_today", "average_call_duration", "active_calls"}
        missing = expected_keys - body.keys()
        if missing:
            results.fail(
                "GET /dashboard/stats response shape",
                f"missing keys: {', '.join(sorted(missing))}",
            )
        else:
            results.ok(
                "GET /dashboard/stats response shape",
                f"keys present: {', '.join(sorted(expected_keys))}",
            )


def test_dashboard_calls(results: TestResult, base_url: str) -> None:
    print("\n─── GET /dashboard/calls ───────────────────────────────────────")
    body = _get(results, base_url, "/dashboard/calls", "GET /dashboard/calls reachable")
    if body is not None:
        # Response is a list (possibly empty — that is valid)
        if isinstance(body, list):
            results.ok(
                "GET /dashboard/calls response is a list",
                f"{len(body)} record(s) returned",
            )
        else:
            results.fail(
                "GET /dashboard/calls response shape",
                f"expected list, got {type(body).__name__}",
            )


def test_knowledge_list(results: TestResult, base_url: str) -> dict | None:
    print("\n─── GET /knowledge/list ────────────────────────────────────────")
    body = _get(results, base_url, "/knowledge/list", "GET /knowledge/list reachable")
    if body is not None:
        if "documents" in body:
            results.ok(
                "GET /knowledge/list response shape",
                f"{len(body['documents'])} document(s) listed",
            )
        else:
            results.fail(
                "GET /knowledge/list response shape",
                "missing 'documents' key",
            )
    return body


def test_knowledge_upload(results: TestResult, base_url: str) -> str | None:
    print("\n─── POST /knowledge/upload ─────────────────────────────────────")
    body = _post_file(
        results,
        base_url,
        "/knowledge/upload",
        "POST /knowledge/upload reachable",
        TEST_DOC_FILENAME,
        TEST_DOC_CONTENT,
    )
    if body is None:
        return None

    doc_id = body.get("doc_id")
    if doc_id:
        results.ok(
            "POST /knowledge/upload returned doc_id",
            f"doc_id={doc_id}",
        )
    else:
        results.fail(
            "POST /knowledge/upload returned doc_id",
            f"'doc_id' missing in response: {body}",
        )
        return None

    # Validate other expected fields
    for key in ("filename", "chunk_count", "uploaded_at", "status"):
        if key in body:
            results.ok(f"  upload response has '{key}'", str(body[key]))
        else:
            results.fail(f"  upload response has '{key}'", "key missing")

    return doc_id


def test_document_appears_in_list(
    results: TestResult, base_url: str, doc_id: str
) -> bool:
    print("\n─── Confirm doc appears in /knowledge/list ─────────────────────")
    body = _get(
        results,
        base_url,
        "/knowledge/list",
        "GET /knowledge/list reachable (post-upload)",
    )
    if body is None:
        return False

    if _doc_id_in_list(body, doc_id):
        results.ok("Uploaded doc visible in /knowledge/list", f"doc_id={doc_id}")
        return True
    else:
        results.fail(
            "Uploaded doc visible in /knowledge/list",
            f"doc_id={doc_id} not found in list",
        )
        return False


def test_knowledge_delete(results: TestResult, base_url: str, doc_id: str) -> bool:
    print("\n─── DELETE /knowledge/{doc_id} ─────────────────────────────────")
    body = _delete(
        results,
        base_url,
        f"/knowledge/{doc_id}",
        f"DELETE /knowledge/{doc_id} reachable",
    )
    if body is None:
        return False

    status = body.get("status")
    if status == "success":
        results.ok("DELETE response status is 'success'", f"doc_id={doc_id}")
        return True
    else:
        results.fail(
            "DELETE response status is 'success'",
            f"got status={status!r}  full response: {body}",
        )
        return False


def test_document_disappears_from_list(
    results: TestResult, base_url: str, doc_id: str
) -> None:
    print("\n─── Confirm doc is gone from /knowledge/list ───────────────────")
    body = _get(
        results,
        base_url,
        "/knowledge/list",
        "GET /knowledge/list reachable (post-delete)",
    )
    if body is None:
        return

    if not _doc_id_in_list(body, doc_id):
        results.ok(
            "Deleted doc no longer in /knowledge/list",
            f"doc_id={doc_id}",
        )
    else:
        results.fail(
            "Deleted doc no longer in /knowledge/list",
            f"doc_id={doc_id} still present — delete may have failed",
        )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="VoxAgent system API test suite"
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the running server (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()
    base_url: str = args.base_url.rstrip("/")

    print(f"\n{'='*60}")
    print(f"  VoxAgent System API Test")
    print(f"  Target: {base_url}")
    print(f"{'='*60}")

    results = TestResult()

    # ── Section 1: dashboard endpoints ────────────────────────────────────────
    print("\n══ DASHBOARD ENDPOINTS ══════════════════════════════════════════")
    test_dashboard_stats(results, base_url)
    test_dashboard_calls(results, base_url)

    # ── Section 2: knowledge baseline ─────────────────────────────────────────
    print("\n══ KNOWLEDGE ENDPOINTS ══════════════════════════════════════════")
    test_knowledge_list(results, base_url)

    # ── Section 3: full upload → list → delete → confirm lifecycle ────────────
    print("\n══ KNOWLEDGE LIFECYCLE (upload → list → delete → confirm) ═══════")
    doc_id = test_knowledge_upload(results, base_url)

    if doc_id:
        appeared = test_document_appears_in_list(results, base_url, doc_id)
        deleted = test_knowledge_delete(results, base_url, doc_id)
        if deleted:
            test_document_disappears_from_list(results, base_url, doc_id)
        else:
            results.fail(
                "Confirm doc disappears after delete",
                "skipped — delete step failed",
            )
    else:
        # Upload failed; mark downstream steps as skipped/failed
        for label in (
            "Uploaded doc visible in /knowledge/list",
            f"DELETE /knowledge/<doc_id> reachable",
            "DELETE response status is 'success'",
            "Deleted doc no longer in /knowledge/list",
        ):
            results.fail(label, "skipped — upload step failed")

    # ── Final summary ──────────────────────────────────────────────────────────
    total = results.passed + results.failed
    print(f"\n{'='*60}")
    print("  SYSTEM API TEST RESULT")
    print(f"  Passed : {results.passed}/{total}")
    print(f"  Failed : {results.failed}/{total}")
    print(f"{'='*60}")

    if results.all_passed:
        print("  ✅  All tests passed")
    else:
        print("  ❌  Some tests failed")

    print(f"{'='*60}\n")

    sys.exit(0 if results.all_passed else 1)


if __name__ == "__main__":
    main()
