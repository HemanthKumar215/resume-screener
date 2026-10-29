locals {
  lambda_env = {
    TABLE_NAME          = aws_dynamodb_table.main.name
    BUCKET_NAME         = aws_s3_bucket.uploads.bucket
    SHORTLIST_TOPIC_ARN = aws_sns_topic.shortlist.arn
    MAX_UPLOAD_MB       = tostring(var.max_upload_mb)
    ENABLE_BEDROCK      = tostring(var.enable_bedrock)
    BEDROCK_MODEL_ID    = var.bedrock_model_id
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ─── API function ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  statement {
    sid       = "Table"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.main.arn]
  }

  # s3:PutObject is what the presigned POST forms are signed with.
  statement {
    sid       = "Objects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/resumes/*", "${aws_s3_bucket.uploads.arn}/text/*"]
  }

  statement {
    sid       = "ListForCleanup"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.uploads.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["resumes/*", "text/*"]
    }
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handlers.api.handler"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  memory_size      = 256
  timeout          = 29

  environment {
    variables = local.lambda_env
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

# ─── Processor function ───────────────────────────────────────────────────────

resource "aws_iam_role" "processor" {
  name               = "${local.name}-processor"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "processor" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.processor.arn}:*"]
  }

  statement {
    sid       = "Queue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = [aws_sqs_queue.processing.arn]
  }

  statement {
    sid       = "Table"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.main.arn]
  }

  statement {
    sid       = "ReadResumes"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/resumes/*"]
  }

  statement {
    sid       = "WriteExtractedText"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/text/*"]
  }

  # Textract's synchronous OCR API doesn't support resource-level permissions.
  statement {
    sid       = "Ocr"
    actions   = ["textract:DetectDocumentText"]
    resources = ["*"]
  }

  statement {
    sid       = "Notify"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.shortlist.arn]
  }

  dynamic "statement" {
    for_each = var.enable_bedrock ? [1] : []

    content {
      sid       = "Summaries"
      actions   = ["bedrock:InvokeModel"]
      resources = ["arn:${local.partition}:bedrock:*::foundation-model/*", "arn:${local.partition}:bedrock:${var.region}:${local.account_id}:inference-profile/*"]
    }
  }
}

resource "aws_iam_role_policy" "processor" {
  role   = aws_iam_role.processor.id
  policy = data.aws_iam_policy_document.processor.json
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/aws/lambda/${local.name}-processor"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "processor" {
  function_name    = "${local.name}-processor"
  role             = aws_iam_role.processor.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handlers.processor.handler"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  memory_size      = 512
  timeout          = 60

  environment {
    variables = local.lambda_env
  }

  depends_on = [aws_cloudwatch_log_group.processor, aws_iam_role_policy.processor]
}

resource "aws_lambda_event_source_mapping" "processor" {
  event_source_arn                   = aws_sqs_queue.processing.arn
  function_name                      = aws_lambda_function.processor.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]

  # New AWS accounts have low concurrency limits; cap how many processors run at once.
  scaling_config {
    maximum_concurrency = 2
  }
}
