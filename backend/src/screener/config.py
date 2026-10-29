"""Settings from environment variables and lazily created AWS clients."""

from __future__ import annotations

import os
from functools import cache

import boto3


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def table_name() -> str:
    return env("TABLE_NAME", "resume-screener")


def bucket_name() -> str:
    return env("BUCKET_NAME", "resume-screener-uploads")


def shortlist_topic_arn() -> str:
    return env("SHORTLIST_TOPIC_ARN")


def max_upload_bytes() -> int:
    return int(env("MAX_UPLOAD_MB", "5")) * 1024 * 1024


def bedrock_enabled() -> bool:
    return env("ENABLE_BEDROCK", "false").lower() == "true"


def bedrock_model_id() -> str:
    return env("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


def local_mode() -> bool:
    """Local dev server: uploads/downloads go through localhost instead of S3 presigned URLs."""
    return env("LOCAL_MODE", "false").lower() == "true"


def local_base_url() -> str:
    return env("LOCAL_BASE_URL", "http://localhost:8001")


@cache
def client(service: str):
    return boto3.client(service, region_name=env("AWS_REGION", env("AWS_DEFAULT_REGION", "ap-south-1")))


@cache
def table():
    return boto3.resource("dynamodb", region_name=env("AWS_REGION", env("AWS_DEFAULT_REGION", "ap-south-1"))).Table(
        table_name()
    )


def reset_clients() -> None:
    """Used by tests so each test gets clients bound to its own mocked AWS."""
    for fn in (client, table):
        if hasattr(fn, "cache_clear"):  # tests may have monkeypatched these
            fn.cache_clear()
