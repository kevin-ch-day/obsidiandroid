"""Read-only WSGI adapter for the existing operational assessment service."""

from __future__ import annotations

import argparse
import hmac
from http import HTTPStatus
import json
import os
import re
from urllib.parse import parse_qs

from .composition import validate_sha256
from .revisions import validate_page
from .service import AssessmentService


def create_app(service: AssessmentService, *, token: str):
    """Create an authenticated retrieval-only app; never compose assessments.

    No repository HTTP/auth framework exists. This dependency-free WSGI boundary
    requires an explicit bearer token and does not grant cross-origin access.
    Database retrieval keeps the store's server-enforced read-only transactions.
    """
    if (
        not isinstance(token, str)
        or len(token) < 32
        or not token.isascii()
        or any(c.isspace() for c in token)
    ):
        raise ValueError(
            "An explicit ASCII bearer token of at least 32 characters is required"
        )
    if service.source is not None:
        raise ValueError("HTTP retrieval requires a service without an evidence source")
    expected = ("Bearer " + token).encode()

    def app(environ, start_response):
        def response(status, body, extra=()):
            encoded = json.dumps(
                body, ensure_ascii=True, sort_keys=True, allow_nan=False
            ).encode()
            start_response(
                f"{status} {HTTPStatus(status).phrase}",
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Content-Length", str(len(encoded))),
                    ("Cache-Control", "no-store"),
                    ("X-Content-Type-Options", "nosniff"),
                    *extra,
                ],
            )
            return [encoded]

        supplied = environ.get("HTTP_AUTHORIZATION", "").encode("utf-8")
        if len(supplied) > 4096 or not hmac.compare_digest(supplied, expected):
            return response(
                401, {"error": "unauthorized"}, [("WWW-Authenticate", "Bearer")]
            )
        if environ.get("REQUEST_METHOD") != "GET":
            return response(405, {"error": "read_only_api"}, [("Allow", "GET")])
        match = re.fullmatch(
            r"/artifact/([^/]+)(/history)?", environ.get("PATH_INFO", "")
        )
        if not match:
            return response(404, {"error": "route_not_found"})
        try:
            sha = validate_sha256(match[1])
            raw_query = environ.get("QUERY_STRING", "")
            if len(raw_query) > 2048:
                raise ValueError("Query too long")
            query = parse_qs(
                raw_query, keep_blank_values=True, strict_parsing=True, max_num_fields=2
            )
            allowed = {"limit", "after_revision"} if match[2] else set()
            if query.keys() - allowed or any(len(v) != 1 for v in query.values()):
                raise ValueError("Unsupported or duplicate parameter")
            limit = int(query.get("limit", ["50"])[0])
            after = int(query.get("after_revision", ["0"])[0])
            validate_page(limit, after)
        except (ValueError, TypeError):
            return response(400, {"error": "invalid_request"})
        try:
            if match[2]:
                # An exhausted page is valid; distinguish it from unknown SHA.
                result = service.history_page(sha, limit=limit, after_revision=after)
                missing = not result["records"] and service.current(sha) is None
            else:
                result = service.current(sha)
                missing = result is None
            if missing:
                return response(404, {"status": "not_assessed", "artifact_sha256": sha})
            return response(200, result)
        except Exception:
            # Never return connector messages, SQL, paths, or credentials.
            return response(503, {"error": "assessment_retrieval_unavailable"})

    return app


def main(argv=None):
    """Run a loopback-only development server; production hosting is separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-option-file", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    token = os.environ.get("OBSIDIANDROID_ASSESSMENT_API_TOKEN", "")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    from .mariadb_store import MariaDBAssessmentStore
    import mysql.connector
    from wsgiref.simple_server import make_server

    try:
        store = MariaDBAssessmentStore(
            lambda: mysql.connector.connect(
                option_files=args.db_option_file,
                database=args.database,
                autocommit=False,
                connection_timeout=5,
            ),
            database=args.database,
            allow_production=args.allow_production,
        )
        app = create_app(AssessmentService(None, store), token=token)
    except ValueError as exc:
        parser.error(str(exc))
    with make_server("127.0.0.1", args.port, app) as server:
        print(
            f"Assessment retrieval API on http://127.0.0.1:{args.port}; loopback development server"
        )
        server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
