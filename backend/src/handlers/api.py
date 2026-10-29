"""HTTP API Lambda (API Gateway HTTP API, payload v2, Cognito JWT authorizer)."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from botocore.exceptions import ClientError

from screener import config, store
from screener.extract import SUPPORTED_EXTENSIONS, extension
from screener.parsing import EDUCATION_RANK
from screener.pipeline import rescore_job, resume_key, text_key
from screener.scoring import suggest_skills

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

MAX_FILES_PER_REQUEST = 25


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


Handler = Callable[[dict[str, Any], str, dict[str, str]], Any]
ROUTES: list[tuple[str, re.Pattern[str], Handler]] = []


def route(method: str, path: str):
    pattern = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[A-Za-z0-9_-]+)", path) + "$")

    def wrap(fn: Handler) -> Handler:
        ROUTES.append((method, pattern, fn))
        return fn

    return wrap


# ─── Entry point ───────────────────────────────────────────────────────────────


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath") or "/"
    stage = event.get("requestContext", {}).get("stage")
    if stage and stage != "$default" and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1 :]

    try:
        if path == "/health":
            return _json(200, {"status": "ok"})
        owner = _owner(event)
        for m, pattern, fn in ROUTES:
            if m == method and (match := pattern.match(path)):
                result = fn(event, owner, match.groupdict())
                if isinstance(result, dict) and "statusCode" in result:
                    return result
                return _json(200, result)
        raise HttpError(404, "Not found")
    except HttpError as exc:
        return _json(exc.status, {"message": exc.message})
    except Exception:
        log.exception("Unhandled error on %s %s", method, path)
        return _json(500, {"message": "Internal server error"})


def _owner(event: dict[str, Any]) -> str:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    sub = claims.get("sub")
    if not sub or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", sub):
        raise HttpError(401, "Unauthorized")
    return sub


def _json(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpError(400, "Body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise HttpError(400, "Body must be a JSON object")
    return data


def _job_or_404(owner: str, job_id: str) -> dict[str, Any]:
    job = store.get_job(owner, job_id)
    if job is None:
        raise HttpError(404, "Job not found")
    return job


def _candidate_or_404(owner: str, job_id: str, cand_id: str) -> dict[str, Any]:
    _job_or_404(owner, job_id)  # ownership check
    cand = store.get_candidate(job_id, cand_id)
    if cand is None:
        raise HttpError(404, "Candidate not found")
    return cand


# ─── Validation ────────────────────────────────────────────────────────────────


def _skills(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 30:
        raise HttpError(422, f"{field} must be a list of up to 30 skills")
    out = []
    for s in value:
        if not isinstance(s, str) or not s.strip() or len(s) > 50:
            raise HttpError(422, f"Each entry in {field} must be 1-50 characters")
        if s.strip() not in out:
            out.append(s.strip())
    return out


def _job_fields(data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if not partial or "title" in data:
        title = str(data.get("title") or "").strip()
        if not 1 <= len(title) <= 120:
            raise HttpError(422, "Title is required (max 120 characters)")
        fields["title"] = title
    if not partial or "description" in data:
        desc = str(data.get("description") or "")
        if len(desc) > 10000:
            raise HttpError(422, "Description is too long (max 10,000 characters)")
        fields["description"] = desc
    if not partial or "required_skills" in data:
        fields["required_skills"] = _skills(data.get("required_skills"), "required_skills")
    if not partial or "nice_to_have_skills" in data:
        fields["nice_to_have_skills"] = _skills(data.get("nice_to_have_skills"), "nice_to_have_skills")
    if not partial or "min_years" in data:
        try:
            years = float(data.get("min_years") or 0)
        except (TypeError, ValueError) as exc:
            raise HttpError(422, "min_years must be a number") from exc
        if not 0 <= years <= 40:
            raise HttpError(422, "min_years must be between 0 and 40")
        fields["min_years"] = years
    if not partial or "min_education" in data:
        edu = data.get("min_education") or "None"
        if edu not in EDUCATION_RANK:
            raise HttpError(422, f"min_education must be one of {', '.join(EDUCATION_RANK)}")
        fields["min_education"] = edu
    if not partial or "alert_threshold" in data:
        try:
            threshold = int(data.get("alert_threshold") if data.get("alert_threshold") is not None else 80)
        except (TypeError, ValueError) as exc:
            raise HttpError(422, "alert_threshold must be a whole number") from exc
        if not 0 <= threshold <= 100:
            raise HttpError(422, "alert_threshold must be between 0 and 100 (0 turns alerts off)")
        fields["alert_threshold"] = threshold
    return fields


# ─── Jobs ──────────────────────────────────────────────────────────────────────


@route("GET", "/jobs")
def list_jobs(event, owner, params):
    return store.list_jobs(owner)


@route("POST", "/jobs")
def create_job(event, owner, params):
    job = store.create_job(owner, _job_fields(_body(event)))
    return {"statusCode": 201, "headers": {"Content-Type": "application/json"}, "body": json.dumps(job, default=str)}


@route("GET", "/jobs/{job_id}")
def get_job(event, owner, params):
    return _job_or_404(owner, params["job_id"])


@route("PUT", "/jobs/{job_id}")
def update_job(event, owner, params):
    _job_or_404(owner, params["job_id"])
    return store.update_job(owner, params["job_id"], _job_fields(_body(event), partial=True))


@route("DELETE", "/jobs/{job_id}")
def delete_job(event, owner, params):
    _job_or_404(owner, params["job_id"])
    store.delete_job(owner, params["job_id"])
    _delete_prefixes([f"resumes/{owner}/{params['job_id']}/", f"text/{owner}/{params['job_id']}/"])
    return {"deleted": True}


@route("POST", "/jobs/{job_id}/rescore")
def rescore(event, owner, params):
    job = _job_or_404(owner, params["job_id"])
    return {"rescored": rescore_job(owner, job)}


@route("POST", "/skills/suggest")
def suggest(event, owner, params):
    text = str(_body(event).get("text") or "")[:10000]
    return {"skills": suggest_skills(text)}


# ─── Candidates ────────────────────────────────────────────────────────────────

_STATUS_ORDER = {"SCORED": 0, "PROCESSING": 1, "UPLOADING": 2, "FAILED": 3}


def _summary(c: dict[str, Any]) -> dict[str, Any]:
    r = c.get("result") or {}
    return {
        "id": c["id"],
        "job_id": c["job_id"],
        "filename": c.get("filename", ""),
        "status": c.get("status"),
        "error": c.get("error", ""),
        "score": c.get("score"),
        "tier": c.get("tier"),
        "name": c.get("name", ""),
        "email": c.get("email", ""),
        "stage": c.get("stage", "new"),
        "created_at": c.get("created_at"),
        "scored_at": c.get("scored_at"),
        "matched_required": r.get("matched_required", []),
        "missing_required": r.get("missing_required", []),
        "experience_years": (r.get("experience") or {}).get("years"),
        "education": r.get("education"),
    }


def _ranked(job_id: str) -> list[dict[str, Any]]:
    cands = [_summary(c) for c in store.list_candidates(job_id)]
    return sorted(cands, key=lambda c: (_STATUS_ORDER.get(c["status"], 9), -(c["score"] or 0), c["created_at"] or ""))


@route("GET", "/jobs/{job_id}/candidates")
def list_candidates(event, owner, params):
    _job_or_404(owner, params["job_id"])
    return _ranked(params["job_id"])


@route("POST", "/jobs/{job_id}/uploads")
def create_uploads(event, owner, params):
    """Create candidate records and return presigned S3 POST forms, one per file.

    The browser uploads straight to S3, so file bytes never pass through Lambda or API Gateway.
    A presigned POST (rather than PUT) lets S3 itself enforce the maximum file size.
    """
    job_id = params["job_id"]
    _job_or_404(owner, job_id)
    files = _body(event).get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES_PER_REQUEST:
        raise HttpError(422, f"Send between 1 and {MAX_FILES_PER_REQUEST} files")

    max_bytes = config.max_upload_bytes()
    prepared = []
    for f in files:
        name = str((f or {}).get("filename") or "").strip()
        size = (f or {}).get("size")
        if not name or len(name) > 200:
            raise HttpError(422, "Each file needs a filename (max 200 characters)")
        if extension(name) not in SUPPORTED_EXTENSIONS:
            raise HttpError(422, f'"{name}" is not a supported type. Use PDF, DOCX, TXT, PNG or JPG.')
        if isinstance(size, int) and size > max_bytes:
            raise HttpError(422, f'"{name}" is larger than {max_bytes // (1024 * 1024)} MB')
        prepared.append(name)

    uploads = []
    s3 = config.client("s3")
    for name in prepared:
        cand_id = store.new_id()
        key = resume_key(owner, job_id, cand_id, name)
        store.create_candidate(owner, job_id, {"id": cand_id, "filename": name, "s3_key": key})
        if config.local_mode():
            form = {"url": f"{config.local_base_url()}/local-upload", "fields": {"key": key}}
        else:
            form = s3.generate_presigned_post(
                Bucket=config.bucket_name(),
                Key=key,
                Conditions=[["content-length-range", 1, max_bytes]],
                ExpiresIn=900,
            )
        uploads.append({"candidate_id": cand_id, "filename": name, "url": form["url"], "fields": form["fields"]})
    return {"uploads": uploads}


@route("GET", "/jobs/{job_id}/candidates/{cand_id}")
def get_candidate(event, owner, params):
    cand = _candidate_or_404(owner, params["job_id"], params["cand_id"])
    if cand.get("s3_key"):
        cand["download_url"] = _download_url(cand["s3_key"], cand.get("filename", "resume"))
    cand.pop("owner", None)
    return cand


@route("PATCH", "/jobs/{job_id}/candidates/{cand_id}")
def update_candidate(event, owner, params):
    _candidate_or_404(owner, params["job_id"], params["cand_id"])
    data = _body(event)
    fields: dict[str, Any] = {}
    if "stage" in data:
        if data["stage"] not in store.CANDIDATE_STAGES:
            raise HttpError(422, f"stage must be one of {', '.join(store.CANDIDATE_STAGES)}")
        fields["stage"] = data["stage"]
    if "notes" in data:
        notes = str(data["notes"] or "")
        if len(notes) > 2000:
            raise HttpError(422, "Notes are limited to 2,000 characters")
        fields["notes"] = notes
    if not fields:
        raise HttpError(422, "Nothing to update")
    return _summary(store.update_candidate(params["job_id"], params["cand_id"], fields))


@route("DELETE", "/jobs/{job_id}/candidates/{cand_id}")
def delete_candidate(event, owner, params):
    cand = _candidate_or_404(owner, params["job_id"], params["cand_id"])
    store.delete_candidate(owner, params["job_id"], params["cand_id"])
    keys = [k for k in (cand.get("s3_key"), text_key(owner, params["job_id"], params["cand_id"])) if k]
    _delete_keys(keys)
    return {"deleted": True}


@route("GET", "/jobs/{job_id}/export")
def export_csv(event, owner, params):
    job = _job_or_404(owner, params["job_id"])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Rank",
            "Name",
            "Email",
            "Score",
            "Tier",
            "Stage",
            "Experience (years)",
            "Education",
            "Matched required skills",
            "Missing required skills",
            "File",
        ]
    )
    rank = 0
    for c in _ranked(job["id"]):
        if c["status"] != "SCORED":
            continue
        rank += 1
        writer.writerow(
            [
                rank,
                c["name"],
                c["email"],
                c["score"],
                c["tier"],
                c["stage"],
                c["experience_years"],
                c["education"],
                "; ".join(c["matched_required"]),
                "; ".join(c["missing_required"]),
                c["filename"],
            ]
        )
    slug = re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-") or "candidates"
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{slug}.csv"',
        },
        "body": buf.getvalue(),
    }


# ─── S3 helpers ────────────────────────────────────────────────────────────────


def _download_url(key: str, filename: str) -> str:
    if config.local_mode():
        from urllib.parse import quote

        return f"{config.local_base_url()}/local-download?key={quote(key)}"
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)
    return config.client("s3").generate_presigned_url(
        "get_object",
        Params={"Bucket": config.bucket_name(), "Key": key, "ResponseContentDisposition": f'inline; filename="{safe}"'},
        ExpiresIn=300,
    )


def _delete_keys(keys: list[str]) -> None:
    if not keys:
        return
    try:
        for i in range(0, len(keys), 1000):
            config.client("s3").delete_objects(
                Bucket=config.bucket_name(), Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]], "Quiet": True}
            )
    except ClientError:
        log.exception("Failed to delete S3 objects")  # lifecycle rules clean up anything left behind


def _delete_prefixes(prefixes: list[str]) -> None:
    s3 = config.client("s3")
    keys: list[str] = []
    for prefix in prefixes:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=config.bucket_name(), Prefix=prefix):
            keys.extend(o["Key"] for o in page.get("Contents", []))
    _delete_keys(keys)
