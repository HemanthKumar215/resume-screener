# S3 "object created" events go to SQS rather than straight to Lambda, so a burst of
# uploads is buffered, failures are retried, and poison messages land in a dead-letter queue.

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-processing-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

# Visibility timeout is 6x the processor timeout, per AWS guidance for Lambda + SQS.
resource "aws_sqs_queue" "processing" {
  name                       = "${local.name}-processing"
  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "processing_queue" {
  statement {
    sid       = "AllowUploadsBucket"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.processing.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.uploads.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "processing" {
  queue_url = aws_sqs_queue.processing.id
  policy    = data.aws_iam_policy_document.processing_queue.json
}

resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  queue {
    queue_arn     = aws_sqs_queue.processing.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "resumes/"
  }

  depends_on = [aws_sqs_queue_policy.processing]
}
