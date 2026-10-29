"""End-to-end flow on mocked AWS: API -> S3 upload -> SQS message -> processor -> ranked results."""

import json

import boto3
import pytest

from conftest import FakeTextract
from handlers import api, processor
from screener import config

USER = "11111111-aaaa-bbbb-cccc-000000000001"
OTHER = "22222222-aaaa-bbbb-cccc-000000000002"


def call(method, path, body=None, user=USER):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}, "stage": "$default"},
        "body": json.dumps(body) if body is not None else None,
    }
    if user:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": user}}}
    resp = api.handler(event, None)
    is_json = resp["headers"]["Content-Type"] == "application/json"
    return resp["statusCode"], (json.loads(resp["body"]) if is_json else resp["body"])


def s3_event(*keys):
    """What SQS delivers to the processor after S3 'ObjectCreated' notifications."""
    return {
        "Records": [
            {"messageId": f"m{i}", "body": json.dumps({"Records": [{"s3": {"object": {"key": k.replace(" ", "+")}}}]})}
            for i, k in enumerate(keys)
        ]
    }


def upload(job_id, paths, user=USER):
    status, body = call(
        "POST",
        f"/jobs/{job_id}/uploads",
        {"files": [{"filename": p.name, "size": p.stat().st_size} for p in paths]},
        user,
    )
    assert status == 200, body
    s3 = boto3.client("s3", region_name="ap-south-1")
    keys = []
    for up, p in zip(body["uploads"], paths, strict=True):
        assert up["url"].startswith("https://") and "policy" in {k.lower() for k in up["fields"]}
        s3.put_object(Bucket="test-bucket", Key=up["fields"]["key"], Body=p.read_bytes())
        keys.append(up["fields"]["key"])
    assert processor.handler(s3_event(*keys), None) == {"batchItemFailures": []}
    return body["uploads"]


@pytest.fixture
def job(aws, sample_job):
    status, body = call("POST", "/jobs", sample_job)
    assert status == 201
    return body


def test_health_and_auth(aws):
    assert call("GET", "/health", user=None)[0] == 200
    assert call("GET", "/jobs", user=None)[0] == 401
    assert call("GET", "/nope")[0] == 404


def test_full_screening_flow(job, samples):
    files = sorted(p for p in samples.iterdir() if p.suffix in (".pdf", ".docx"))
    upload(job["id"], files)

    status, cands = call("GET", f"/jobs/{job['id']}/candidates")
    assert status == 200 and len(cands) == len(files)
    assert all(c["status"] == "SCORED" for c in cands)
    scores = [c["score"] for c in cands]
    assert scores == sorted(scores, reverse=True)
    assert cands[0]["name"] == "Ananya Iyer"
    assert call("GET", "/jobs")[1][0]["candidate_count"] == len(files)

    # detail includes the breakdown and a short-lived download link
    status, detail = call("GET", f"/jobs/{job['id']}/candidates/{cands[0]['id']}")
    assert detail["result"]["missing_required"] == []
    assert "X-Amz-Signature" in detail["download_url"] or "Signature" in detail["download_url"]
    assert "owner" not in detail

    # stage + notes
    status, upd = call(
        "PATCH", f"/jobs/{job['id']}/candidates/{cands[0]['id']}", {"stage": "shortlisted", "notes": "Call Monday"}
    )
    assert status == 200 and upd["stage"] == "shortlisted"
    assert call("PATCH", f"/jobs/{job['id']}/candidates/{cands[0]['id']}", {"stage": "hired!"})[0] == 422

    # CSV export
    status, csv_text = call("GET", f"/jobs/{job['id']}/export")
    assert status == 200 and csv_text.splitlines()[1].startswith("1,Ananya Iyer")


def test_rescore_after_changing_requirements(job, samples):
    upload(job["id"], [samples / "karthik_subramanian.pdf", samples / "ananya_iyer.pdf"])
    before = {c["name"]: c["score"] for c in call("GET", f"/jobs/{job['id']}/candidates")[1]}

    status, _ = call(
        "PUT",
        f"/jobs/{job['id']}",
        {
            "required_skills": ["Java", "Spring Boot", "Kubernetes"],
            "nice_to_have_skills": [],
            "description": "Java platform role",
        },
    )
    assert status == 200
    assert call("POST", f"/jobs/{job['id']}/rescore")[1] == {"rescored": 2}
    after = call("GET", f"/jobs/{job['id']}/candidates")[1]
    assert after[0]["name"] == "Karthik Subramanian"
    assert after[0]["score"] > before["Karthik Subramanian"]


def test_users_are_isolated(job, samples):
    upload(job["id"], [samples / "rohan_verma.pdf"])
    assert call("GET", "/jobs", user=OTHER)[1] == []
    assert call("GET", f"/jobs/{job['id']}", user=OTHER)[0] == 404
    assert call("GET", f"/jobs/{job['id']}/candidates", user=OTHER)[0] == 404
    assert call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "x.pdf"}]}, user=OTHER)[0] == 404
    assert call("DELETE", f"/jobs/{job['id']}", user=OTHER)[0] == 404


def test_validation(aws):
    assert call("POST", "/jobs", {"title": ""})[0] == 422
    assert call("POST", "/jobs", {"title": "x", "min_years": 99})[0] == 422
    assert call("POST", "/jobs", {"title": "x", "min_education": "Wizard"})[0] == 422
    assert call("POST", "/jobs", {"title": "x", "required_skills": "Python"})[0] == 422
    _, job = call("POST", "/jobs", {"title": "x"})
    assert job["alert_threshold"] == 80 and job["required_skills"] == []
    assert call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "virus.exe"}]})[0] == 422
    assert (
        call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "a.pdf", "size": 50 * 1024 * 1024}]})[0]
        == 422
    )
    assert call("POST", f"/jobs/{job['id']}/uploads", {"files": []})[0] == 422


def test_bad_file_marks_candidate_failed(job):
    status, body = call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "broken.pdf"}]})
    key = body["uploads"][0]["fields"]["key"]
    boto3.client("s3", region_name="ap-south-1").put_object(Bucket="test-bucket", Key=key, Body=b"not a pdf")
    assert processor.handler(s3_event(key), None) == {"batchItemFailures": []}  # no retry for bad files
    cand = call("GET", f"/jobs/{job['id']}/candidates")[1][0]
    assert cand["status"] == "FAILED" and "couldn't be read" in cand["error"]


def test_transient_error_is_retried(job, monkeypatch):
    status, body = call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "a.pdf"}]})
    key = body["uploads"][0]["fields"]["key"]
    # Object never arrived in S3 (e.g. upload still in flight): ignored, not failed.
    assert processor.handler(s3_event(key), None) == {"batchItemFailures": []}

    def boom(*a, **k):
        raise RuntimeError("DynamoDB throttled")

    monkeypatch.setattr("screener.pipeline.store.get_candidate", boom)
    assert processor.handler(s3_event(key), None) == {"batchItemFailures": [{"itemIdentifier": "m0"}]}


def test_test_event_and_unknown_keys_are_ignored(aws):
    event = {"Records": [{"messageId": "t", "body": json.dumps({"Event": "s3:TestEvent"})}]}
    assert processor.handler(event, None) == {"batchItemFailures": []}
    assert processor.handler(s3_event("text/whatever.txt"), None) == {"batchItemFailures": []}


def test_scanned_resume_goes_through_textract(job, monkeypatch):
    fake = FakeTextract(
        "Vikram Rao\nvikram@example.com\nSkills: Python, AWS, Docker, SQL, REST APIs\nEngineer Jan 2019 - Present"
    )
    real_client = config.client
    monkeypatch.setattr(config, "client", lambda svc: fake if svc == "textract" else real_client(svc))
    status, body = call("POST", f"/jobs/{job['id']}/uploads", {"files": [{"filename": "scan.png"}]})
    key = body["uploads"][0]["fields"]["key"]
    boto3.client("s3", region_name="ap-south-1").put_object(Bucket="test-bucket", Key=key, Body=b"\x89PNG...")
    processor.handler(s3_event(key), None)
    cand = call("GET", f"/jobs/{job['id']}/candidates")[1][0]
    assert cand["status"] == "SCORED" and cand["name"] == "Vikram Rao" and fake.calls == 1


def test_strong_candidate_triggers_sns(job, samples, monkeypatch):
    sns = boto3.client("sns", region_name="ap-south-1")
    sqs = boto3.client("sqs", region_name="ap-south-1")
    topic = sns.create_topic(Name="shortlist")["TopicArn"]
    q = sqs.create_queue(QueueName="inbox")["QueueUrl"]
    q_arn = sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=q_arn)
    monkeypatch.setenv("SHORTLIST_TOPIC_ARN", topic)

    upload(job["id"], [samples / "ananya_iyer.pdf", samples / "sneha_kulkarni.pdf"])
    msgs = sqs.receive_message(QueueUrl=q, MaxNumberOfMessages=10)["Messages"]
    assert len(msgs) == 1  # only the strong candidate
    assert "Ananya Iyer" in json.loads(msgs[0]["Body"])["Subject"]


def test_bedrock_summary_when_enabled(job, samples, monkeypatch):
    class FakeBedrock:
        def converse(self, **kwargs):
            assert "<resume>" in kwargs["messages"][0]["content"][0]["text"]
            return {"output": {"message": {"content": [{"text": "- Strong AWS background"}]}}}

    real_client = config.client
    monkeypatch.setenv("ENABLE_BEDROCK", "true")
    monkeypatch.setattr(config, "client", lambda svc: FakeBedrock() if svc == "bedrock-runtime" else real_client(svc))
    upload(job["id"], [samples / "ananya_iyer.pdf"])
    cand_id = call("GET", f"/jobs/{job['id']}/candidates")[1][0]["id"]
    assert call("GET", f"/jobs/{job['id']}/candidates/{cand_id}")[1]["summary"] == "- Strong AWS background"


def test_delete_candidate_and_job_clean_up_s3(job, samples):
    ups = upload(job["id"], [samples / "rohan_verma.pdf", samples / "meera_joshi.pdf"])
    s3 = boto3.client("s3", region_name="ap-south-1")
    count = lambda: s3.list_objects_v2(Bucket="test-bucket").get("KeyCount", 0)  # noqa: E731
    assert count() == 4  # 2 resumes + 2 extracted texts
    assert call("DELETE", f"/jobs/{job['id']}/candidates/{ups[0]['candidate_id']}")[0] == 200
    assert count() == 2
    assert call("GET", "/jobs")[1][0]["candidate_count"] == 1
    assert call("DELETE", f"/jobs/{job['id']}")[0] == 200
    assert count() == 0 and call("GET", "/jobs")[1] == []
