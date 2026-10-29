"""Run the whole backend locally with AWS simulated in memory (moto). No AWS account needed.

    pip install -r requirements-dev.txt
    python local_server.py --seed        # http://localhost:8001

The Lambda handlers run unchanged. Differences from AWS:
  - auth: the frontend sends "Bearer local:<email>" instead of a Cognito token
  - uploads/downloads go through this server instead of presigned S3 URLs
  - the processor runs in a background thread instead of being triggered by SQS
  - OCR (Textract) for images/scanned PDFs isn't available; use text-based PDFs or DOCX
Data lives in memory and is lost when the server stops.
"""

from __future__ import annotations

import argparse
import email.parser
import email.policy
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

PORT = int(os.environ.get("PORT", "8001"))
os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "local",
        "AWS_SECRET_ACCESS_KEY": "local",
        "AWS_DEFAULT_REGION": "ap-south-1",
        "AWS_REGION": "ap-south-1",
        "TABLE_NAME": "resume-screener-local",
        "BUCKET_NAME": "resume-screener-local",
        "LOCAL_MODE": "true",
        "LOCAL_BASE_URL": f"http://localhost:{PORT}",
    }
)

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from handlers import api, processor  # noqa: E402
from screener import config  # noqa: E402

LOCK = threading.Lock()  # moto's in-memory backend isn't built for concurrent writes


def owner_for(email: str) -> str:
    return "local-" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]


def setup_aws() -> None:
    boto3.client("dynamodb").create_table(
        TableName=config.table_name(),
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    )
    boto3.client("s3").create_bucket(
        Bucket=config.bucket_name(), CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
    )


def process_async(key: str, delay: float = 1.0) -> None:
    """Mimic S3 -> SQS -> Lambda: process shortly after the upload lands."""

    def run() -> None:
        time.sleep(delay)
        event = {"Records": [{"messageId": key, "body": json.dumps({"Records": [{"s3": {"object": {"key": key}}}]})}]}
        with LOCK:
            processor.handler(event, None)

    threading.Thread(target=run, daemon=True).start()


def call_api(method: str, path: str, body: str | None, sub: str | None) -> dict:
    event = {"rawPath": path, "requestContext": {"http": {"method": method}, "stage": "$default"}, "body": body}
    if sub:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub}}}
    with LOCK:
        return api.handler(event, None)


def seed(email: str) -> None:
    samples = HERE.parent / "samples"
    sub = owner_for(email)
    job = json.loads((samples / "job_backend_engineer.json").read_text())
    created = json.loads(call_api("POST", "/jobs", json.dumps(job), sub)["body"])
    files = sorted(p for p in samples.iterdir() if p.suffix in (".pdf", ".docx"))
    payload = {"files": [{"filename": p.name, "size": p.stat().st_size} for p in files]}
    uploads = json.loads(call_api("POST", f"/jobs/{created['id']}/uploads", json.dumps(payload), sub)["body"])[
        "uploads"
    ]
    s3 = boto3.client("s3")
    for up, path in zip(uploads, files, strict=True):
        s3.put_object(Bucket=config.bucket_name(), Key=up["fields"]["key"], Body=path.read_bytes())
        process_async(up["fields"]["key"], delay=0)
    print(f"Seeded job '{job['title']}' with {len(files)} sample resumes for {email}")


class Handler(BaseHTTPRequestHandler):
    server_version = "ResumeScreenerLocal/1.0"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
        self.send_header("Access-Control-Expose-Headers", "content-disposition")

    def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self._cors()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/local-download":
            key = parse_qs(url.query).get("key", [""])[0]
            try:
                with LOCK:
                    obj = boto3.client("s3").get_object(Bucket=config.bucket_name(), Key=key)
                    data = obj["Body"].read()
            except Exception:
                return self._send(404, b"Not found")
            ctype = "application/pdf" if key.lower().endswith(".pdf") else "application/octet-stream"
            name = key.rsplit("/", 1)[-1]
            return self._send(200, data, {"Content-Type": ctype, "Content-Disposition": f'inline; filename="{name}"'})
        self._proxy("GET")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/local-upload":
            return self._upload()
        self._proxy("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy("DELETE")

    def _proxy(self, method: str) -> None:
        auth = self.headers.get("Authorization", "")
        sub = owner_for(auth.split("local:", 1)[1]) if auth.startswith("Bearer local:") else None
        body = self._body().decode("utf-8") if method in ("POST", "PUT", "PATCH") else None
        resp = call_api(method, urlparse(self.path).path, body, sub)
        self._send(resp["statusCode"], resp["body"].encode("utf-8"), resp.get("headers"))

    def _upload(self) -> None:
        """Accepts the same multipart form the browser would POST to S3."""
        ctype = self.headers.get("Content-Type", "")
        raw = self._body()
        msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
            f"Content-Type: {ctype}\r\n\r\n".encode() + raw
        )
        fields, data = {}, None
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name == "file":
                data = part.get_payload(decode=True)
            elif name:
                fields[name] = part.get_content().strip() if part.get_content_maintype() == "text" else ""
        key = fields.get("key", "")
        if not key.startswith("resumes/") or data is None:
            return self._send(400, b"Bad upload")
        if len(data) > config.max_upload_bytes():
            return self._send(400, b"File too large")
        with LOCK:
            boto3.client("s3").put_object(Bucket=config.bucket_name(), Key=key, Body=data)
        process_async(key)
        self._send(204, b"")

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"{self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", action="store_true", help="create a sample job with the sample resumes")
    parser.add_argument("--seed-email", default="demo@example.com", help="account to seed (default demo@example.com)")
    args = parser.parse_args()

    with mock_aws():
        config.reset_clients()
        setup_aws()
        if args.seed:
            seed(args.seed_email)
        print(f"Local API on http://localhost:{PORT}  (AWS simulated in memory; Ctrl+C to stop)")
        try:
            HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
