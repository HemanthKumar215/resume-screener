data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

# Globally unique suffix for S3 bucket names and the Cognito domain.
resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  name       = var.project
  suffix     = random_id.suffix.hex
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  site_origin = "https://${aws_cloudfront_distribution.site.domain_name}"
  dev_origin  = "http://localhost:5173"

  allowed_origins = concat([local.site_origin, local.dev_origin], var.extra_allowed_origins)
  callback_urls   = concat(["${local.site_origin}/", "${local.dev_origin}/"], [for o in var.extra_allowed_origins : "${o}/"])
}
