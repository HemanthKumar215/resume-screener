# CLAUDE.md

Serverless resume screener: React app (CloudFront) → API Gateway + Cognito → Lambda (`handlers/api.py`); resumes upload straight to S3 → SQS → Lambda (`handlers/processor.py`) which extracts text, scores it, and writes to DynamoDB. Infrastructure is Terraform in `infra/`. See README.md.

## Commands

```bash
cd backend && pip install -r requirements-dev.txt
python local_server.py --seed        # full backend on :8001 with AWS mocked in memory (moto)
pytest                                # 48 tests
ruff check src tests local_server.py ../scripts && ruff format --check src tests local_server.py ../scripts

cd frontend && npm install && cp .env.example .env.local && npm run dev   # :5173, local auth mode
npm run lint && npm run build

./scripts/build_lambda.sh             # backend/dist/lambda.zip (arm64, py3.13)
./scripts/deploy.sh                   # build + terraform apply + upload frontend (needs AWS creds)
```

## Rules

- Scoring must stay explainable: every change to `screener/scoring.py` must keep the per-component `detail` text and the weights summing to 100. Never score on name, gender, age, photo or location.
- Skill aliases live in `screener/skills.py`. Words that are also ordinary English (Go, Rust, Express) belong in `AMBIGUOUS` so they only match when capitalised.
- File problems raise `ExtractionError`, which marks the candidate FAILED and is not retried. Everything else should raise so SQS retries it and eventually moves it to the DLQ.
- All AWS clients come from `screener.config.client()`/`table()` so moto tests work. Don't create boto3 clients at import time.
- DynamoDB keys: jobs `USER#<sub>/JOB#<id>`, candidates `JOB#<id>/CAND#<id>`. Always check job ownership before touching candidates (`_job_or_404`).
- S3 keys: `resumes/<sub>/<job>/<cand>/<file>` and `text/<sub>/<job>/<cand>.txt`. IAM policies are scoped to these prefixes.
- Lambda runtime deps go in `backend/requirements.txt` (pinned, pure Python preferred, the build targets arm64). boto3 comes from the runtime.
- Terraform must pass `terraform fmt -check` and `validate` (CI). Keep `=` aligned within attribute groups.
- Frontend: plain CSS with tokens in `src/index.css` (light + dark). Score helpers live in `src/score.ts`, not in component files (fast-refresh lint rule).
- Add tests for any API, scoring or processor change (`backend/tests/test_flow.py` covers the end-to-end path).
