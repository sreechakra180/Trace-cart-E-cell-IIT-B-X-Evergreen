"""Security and hardening tests for the TraceCart API server.

Tests:
1. Path traversal attacks on run_id endpoints are blocked (HTTP 400)
2. Scenario ID injection attacks are blocked (HTTP 400)
3. File uploads without valid .mp4 extension are rejected (HTTP 400)
4. File uploads without genuine MP4 container magic bytes are rejected (HTTP 400)
5. OWASP security response headers are attached to all HTTP responses
"""

import io
import pytest
from fastapi.testclient import TestClient
from app.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_path_traversal_on_run_id_rejected(client):
    """Path traversal payload in run_id must be rejected (HTTP 400 or 404)."""
    traversal_payloads = [
        "../../../../tmp/evil",
        "../run_123",
        "run/with/slashes",
        "run\\with\\backslashes",
        "run$bad*chars",
        "..",
        ".",
    ]
    for bad_id in traversal_payloads:
        # Test v1 run endpoint (query parameter -> explicitly hits _safe_run_id)
        res = client.post(f"/api/v1/run?run_id={bad_id}&scenario=S01")
        assert res.status_code == 400, f"Expected 400 for query run_id: {bad_id}, got {res.status_code}"

        # Test v1 get run metadata (path parameter -> rejected by router or validator)
        res = client.get(f"/api/v1/runs/{bad_id}")
        assert res.status_code in (400, 404), f"Expected 400/404 for path run_id: {bad_id}, got {res.status_code}"

        # Test v1 decisions endpoint
        res = client.get(f"/api/v1/runs/{bad_id}/decisions")
        assert res.status_code in (400, 404), f"Expected 400/404 for path run_id: {bad_id}, got {res.status_code}"


def test_invalid_scenario_id_rejected(client):
    """Malicious or non-conforming scenario_id must be rejected."""
    bad_scenarios = [
        "../../S01",
        "S01; DROP TABLE runs;",
        "<script>alert(1)</script>",
        "s01",  # Lowercase not allowed by strict schema
        "invalid",
    ]
    for bad_sc in bad_scenarios:
        # Test v1 run query param -> hits _safe_scenario_id
        res = client.post(f"/api/v1/run?run_id=run_safe_123&scenario={bad_sc}")
        assert res.status_code == 400, f"Expected 400 for scenario: {bad_sc}"

        # Test console run endpoint (path param) -> router or validator rejects
        res = client.post(f"/api/run/{bad_sc}")
        assert res.status_code in (400, 404), f"Expected 400/404 for scenario: {bad_sc}"


def test_upload_extension_validation(client):
    """Uploads with disallowed file extensions (.exe, .sh, .py, etc.) must be rejected."""
    bad_files = [
        ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00"),
        ("script.sh", b"#!/bin/bash\necho pwned"),
        ("video.mov", b"\x00\x00\x00\x14ftypqt  "),
    ]
    for filename, content in bad_files:
        files = {"file": (filename, io.BytesIO(content), "application/octet-stream")}
        res = client.post("/api/v1/upload", files=files)
        assert res.status_code == 400, f"Expected 400 for file: {filename}, got {res.status_code}"


def test_upload_magic_bytes_validation(client):
    """Uploads with .mp4 extension but invalid container magic bytes must be rejected."""
    # Renamed text/binary file
    fake_mp4 = b"This is not a real mp4 video container"
    files = {"file": ("fake_video.mp4", io.BytesIO(fake_mp4), "video/mp4")}
    res = client.post("/api/v1/upload", files=files)
    assert res.status_code == 400
    assert "not a valid MP4 container" in res.json()["detail"]


def test_upload_valid_mp4_accepted(client):
    """Uploads with valid MP4 container ftyp box header must be accepted."""
    # Minimal valid MP4 ftyp box (12 bytes minimum with ftyp at offset 4)
    valid_header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"
    files = {"file": ("sample.mp4", io.BytesIO(valid_header), "video/mp4")}
    res = client.post("/api/v1/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["filename"] == "sample.mp4"


def test_security_headers_present(client):
    """Responses must contain OWASP recommended security headers."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src" in headers.get("Content-Security-Policy", "")
