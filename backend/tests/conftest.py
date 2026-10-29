import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "ap-south-1",
        "AWS_REGION": "ap-south-1",
        "TABLE_NAME": "test-table",
        "BUCKET_NAME": "test-bucket",
        "LOCAL_MODE": "false",
    }
)

from screener import config  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def samples() -> Path:
    return SAMPLES


@pytest.fixture
def sample_job() -> dict:
    return json.loads((SAMPLES / "job_backend_engineer.json").read_text())


def create_table(name: str = "test-table"):
    return boto3.client("dynamodb", region_name="ap-south-1").create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    )


@pytest.fixture
def aws(monkeypatch):
    """Mocked AWS with the table and bucket the Lambdas expect."""
    with mock_aws():
        config.reset_clients()
        create_table()
        boto3.client("s3", region_name="ap-south-1").create_bucket(
            Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        yield
        config.reset_clients()


class FakeTextract:
    """Stands in for the Textract client; returns fixed OCR lines."""

    class exceptions:  # noqa: N801 - mirrors boto3's client.exceptions namespace
        class UnsupportedDocumentException(Exception):
            pass

        class BadDocumentException(Exception):
            pass

    def __init__(self, text: str = "Scanned Person\nSkills: Python, AWS, Docker, SQL"):
        self.text = text
        self.calls = 0

    def detect_document_text(self, Document):  # noqa: N803 - boto3 casing
        self.calls += 1
        return {"Blocks": [{"BlockType": "LINE", "Text": line} for line in self.text.splitlines()]}
