"""SQS-triggered Lambda: S3 'object created' notifications for uploaded resumes."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import unquote_plus

from screener.pipeline import process_resume

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            for s3_record in body.get("Records", []):  # absent for the s3:TestEvent sent on setup
                key = unquote_plus(s3_record["s3"]["object"]["key"])
                status = process_resume(key)
                log.info("Processed %s -> %s", key, status)
        except Exception:
            log.exception("Failed to process message %s", record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})
    # Partial batch response: only failed messages are retried (then sent to the DLQ).
    return {"batchItemFailures": failures}
