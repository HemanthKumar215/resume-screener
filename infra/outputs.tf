output "app_url" {
  description = "Open this in a browser."
  value       = local.site_origin
}

output "api_url" {
  value = aws_apigatewayv2_api.http.api_endpoint
}

output "region" {
  value = var.region
}

output "cognito_domain" {
  value = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dlq.url
}
