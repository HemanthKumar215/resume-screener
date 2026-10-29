"""DynamoDB access (single-table design).

    Job:        PK = USER#<owner>   SK = JOB#<job_id>
    Candidate:  PK = JOB#<job_id>   SK = CAND#<candidate_id>

Jobs are partitioned by owner, so a recruiter can only ever query their own jobs. Candidates
are partitioned by job, so ranking a job's candidates is a single Query.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from . import config

CANDIDATE_STAGES = ("new", "shortlisted", "interview", "rejected")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


def _public(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    item = from_dynamo(item)
    item.pop("pk", None)
    item.pop("sk", None)
    if "result" in item and isinstance(item["result"], str):
        item["result"] = json.loads(item["result"])
    return item


# ─── Jobs ──────────────────────────────────────────────────────────────────────


def create_job(owner: str, fields: dict[str, Any]) -> dict[str, Any]:
    job_id = new_id()
    ts = now_iso()
    item = {
        "pk": f"USER#{owner}",
        "sk": f"JOB#{job_id}",
        "id": job_id,
        "owner": owner,
        "candidate_count": 0,
        "created_at": ts,
        "updated_at": ts,
        **fields,
    }
    config.table().put_item(Item=to_dynamo(item))
    return _public(item)


def get_job(owner: str, job_id: str) -> dict[str, Any] | None:
    resp = config.table().get_item(Key={"pk": f"USER#{owner}", "sk": f"JOB#{job_id}"})
    return _public(resp.get("Item"))


def list_jobs(owner: str) -> list[dict[str, Any]]:
    items = _query(Key("pk").eq(f"USER#{owner}") & Key("sk").begins_with("JOB#"))
    jobs = [_public(i) for i in items]
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)


def update_job(owner: str, job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    fields = {**fields, "updated_at": now_iso()}
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": to_dynamo(v) for k, v in fields.items()}
    resp = config.table().update_item(
        Key={"pk": f"USER#{owner}", "sk": f"JOB#{job_id}"},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(pk)",
        ReturnValues="ALL_NEW",
    )
    return _public(resp["Attributes"])


def delete_job(owner: str, job_id: str) -> list[dict[str, Any]]:
    """Delete a job and its candidates. Returns the deleted candidates (for S3 cleanup)."""
    candidates = list_candidates(job_id)
    with config.table().batch_writer() as batch:
        for c in candidates:
            batch.delete_item(Key={"pk": f"JOB#{job_id}", "sk": f"CAND#{c['id']}"})
        batch.delete_item(Key={"pk": f"USER#{owner}", "sk": f"JOB#{job_id}"})
    return candidates


def _adjust_count(owner: str, job_id: str, delta: int) -> None:
    config.table().update_item(
        Key={"pk": f"USER#{owner}", "sk": f"JOB#{job_id}"},
        UpdateExpression="ADD candidate_count :d",
        ExpressionAttributeValues={":d": delta},
    )


# ─── Candidates ────────────────────────────────────────────────────────────────


def create_candidate(owner: str, job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    cand_id = fields.pop("id", None) or new_id()
    item = {
        "pk": f"JOB#{job_id}",
        "sk": f"CAND#{cand_id}",
        "id": cand_id,
        "job_id": job_id,
        "owner": owner,
        "status": "UPLOADING",
        "stage": "new",
        "notes": "",
        "created_at": now_iso(),
        **fields,
    }
    config.table().put_item(Item=to_dynamo(item))
    _adjust_count(owner, job_id, 1)
    return _public(item)


def get_candidate(job_id: str, cand_id: str) -> dict[str, Any] | None:
    resp = config.table().get_item(Key={"pk": f"JOB#{job_id}", "sk": f"CAND#{cand_id}"})
    return _public(resp.get("Item"))


def list_candidates(job_id: str) -> list[dict[str, Any]]:
    items = _query(Key("pk").eq(f"JOB#{job_id}") & Key("sk").begins_with("CAND#"))
    return [_public(i) for i in items]


def update_candidate(job_id: str, cand_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    if "result" in fields and not isinstance(fields["result"], str):
        fields = {**fields, "result": json.dumps(fields["result"])}
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": to_dynamo(v) for k, v in fields.items()}
    resp = config.table().update_item(
        Key={"pk": f"JOB#{job_id}", "sk": f"CAND#{cand_id}"},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(pk)",
        ReturnValues="ALL_NEW",
    )
    return _public(resp["Attributes"])


def delete_candidate(owner: str, job_id: str, cand_id: str) -> None:
    config.table().delete_item(Key={"pk": f"JOB#{job_id}", "sk": f"CAND#{cand_id}"})
    _adjust_count(owner, job_id, -1)


def _query(condition) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"KeyConditionExpression": condition}
    while True:
        resp = config.table().query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
