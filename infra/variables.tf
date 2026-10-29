variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "resume-screener"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project))
    error_message = "Use 3-31 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "region" {
  description = "AWS region. ap-south-1 (Mumbai) supports every service used here, including Textract."
  type        = string
  default     = "ap-south-1"
}

variable "alert_email" {
  description = "Email for strong-candidate alerts, operational alarms and the budget alert. Leave empty to skip."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget; you're emailed at 80% of actual and 100% of forecast spend."
  type        = number
  default     = 5
}

variable "resume_retention_days" {
  description = "Uploaded resumes and extracted text are deleted automatically after this many days."
  type        = number
  default     = 90
}

variable "max_upload_mb" {
  description = "Largest resume file accepted (enforced by S3 through the presigned POST policy)."
  type        = number
  default     = 5
}

variable "allow_self_signup" {
  description = "Let anyone create a recruiter account from the sign-in page. Set false to invite users only."
  type        = bool
  default     = true
}

variable "enable_bedrock" {
  description = "Generate an AI summary per candidate with Amazon Bedrock (not free tier; enable model access first)."
  type        = bool
  default     = false
}

variable "bedrock_model_id" {
  description = "Bedrock model (or inference profile) used for summaries when enable_bedrock is true."
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "extra_allowed_origins" {
  description = "Additional browser origins allowed to call the API and upload (e.g. a custom domain)."
  type        = list(string)
  default     = []
}

variable "lambda_zip_path" {
  description = "Path to the Lambda bundle built by scripts/build_lambda.sh."
  type        = string
  default     = "../backend/dist/lambda.zip"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the Lambda functions and API access logs."
  type        = number
  default     = 14
}
