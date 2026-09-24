"""HTTP auth, exact V1 retrieval, paging, failure redaction and read-only proof."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from obsidiandroid.assessment import AssessmentService, AssessmentStore
from obsidiandroid.assessment.http_api import create_app
from test_assessment_review import local_chain
from test_operational_assessment import SHA

TOKEN = "fixture-only-token-0123456789abcdef"


def request(app, path=None, *, query="", method="GET", token=TOKEN):
    captured = {}

    def start(status, headers):
        captured.update(status=int(status.split()[0]), headers=dict(headers))

    body = b"".join(
        app(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path or f"/artifact/{SHA}",
                "QUERY_STRING": query,
                "HTTP_AUTHORIZATION": "Bearer " + token,
            },
            start,
        )
    )
    return captured, json.loads(body)


@pytest.fixture
def api(tmp_path):
    store, rows = local_chain(tmp_path)
    ro = AssessmentStore(store.path, read_only=True)
    app = create_app(AssessmentService(None, ro), token=TOKEN)
    return app, rows, store.path


def test_current_and_history_are_identical_service_contract_without_writes(api):
    app, rows, path = api
    before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    status, current = request(app)
    assert status["status"] == 200 and current == rows[-1]
    assert status["headers"]["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in status["headers"]
    _, first = request(app, f"/artifact/{SHA}/history", query="limit=2")
    _, second = request(
        app,
        f"/artifact/{SHA}/history",
        query=f"limit=2&after_revision={first['next_after_revision']}",
    )
    assert first["records"] + second["records"] == rows
    assert second["next_after_revision"] is None
    status, empty = request(app, f"/artifact/{SHA}/history", query="after_revision=4")
    assert status["status"] == 200 and empty["records"] == []
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    "path", [f"/artifact/{'b' * 64}", f"/artifact/{'b' * 64}/history"]
)
def test_absent_artifact_is_404(api, path):
    status, body = request(api[0], path)
    assert status["status"] == 404 and body["status"] == "not_assessed"


@pytest.mark.parametrize("token", ["", "incorrect", "x" * 4097])
def test_auth_before_any_retrieval(token):
    class Never:
        source = None

        def current(self, *args):
            pytest.fail("unauthenticated store call")

    status, body = request(create_app(Never(), token=TOKEN), token=token)
    assert status["status"] == 401 and body == {"error": "unauthorized"}


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
def test_no_write_or_implicit_head_routes(api, method):
    status, _ = request(api[0], method=method)
    assert status["status"] == 405 and status["headers"]["Allow"] == "GET"


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=201",
        "after_revision=-1",
        "limit=one",
        "limit=2&limit=3",
        "unknown=1",
        "after_revision=",
        "a=" + ("a" * 2048),
    ],
)
def test_invalid_history_bounds(api, query):
    assert request(api[0], f"/artifact/{SHA}/history", query=query)[0]["status"] == 400


def test_invalid_identity_and_current_query(api):
    assert request(api[0], "/artifact/not-a-sha")[0]["status"] == 400
    assert request(api[0], query="limit=1")[0]["status"] == 400
    assert request(api[0], "/assess")[0]["status"] == 404


def test_store_failure_is_redacted():
    class Broken:
        source = None

        def current(self, sha):
            raise RuntimeError("secret-password /private/socket SELECT sensitive_data")

    status, body = request(create_app(Broken(), token=TOKEN))
    assert status["status"] == 503 and body == {
        "error": "assessment_retrieval_unavailable"
    }


def test_auth_configuration_and_read_only_service_required():
    for token in ["", "short", "a" * 31, "a " * 32, "é" * 32]:
        with pytest.raises(ValueError):
            create_app(AssessmentService(None, None), token=token)
    with pytest.raises(ValueError, match="without an evidence source"):
        create_app(AssessmentService(object(), None), token=TOKEN)


def test_help_requires_no_credentials_or_connection():
    result = subprocess.run(
        [sys.executable, "-m", "obsidiandroid.assessment.http_api", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and "--db-option-file" in result.stdout
