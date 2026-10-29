#!/usr/bin/env bash
# Build and deploy everything: Lambda bundle, infrastructure, then the web app.
# Requires: AWS CLI (configured), Terraform >= 1.10, Python 3.13, Node 20+.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/scripts/build_lambda.sh"

cd "$ROOT/infra"
terraform init -input=false
terraform apply -input=false ${TF_AUTO_APPROVE:+-auto-approve}

out() { terraform output -raw "$1"; }
APP_URL="$(out app_url)"
SITE_BUCKET="$(out site_bucket)"
DIST_ID="$(out cloudfront_distribution_id)"

cat > "$ROOT/frontend/.env.production" <<ENV
VITE_API_URL=$(out api_url)
VITE_AUTH_MODE=cognito
VITE_COGNITO_DOMAIN=$(out cognito_domain)
VITE_COGNITO_CLIENT_ID=$(out cognito_client_id)
VITE_REDIRECT_URI=$APP_URL/
ENV

cd "$ROOT/frontend"
npm ci
npm run build
aws s3 sync dist "s3://$SITE_BUCKET" --delete --cache-control "public,max-age=31536000,immutable" --exclude index.html
aws s3 cp dist/index.html "s3://$SITE_BUCKET/index.html" --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/index.html" > /dev/null

echo
echo "Deployed: $APP_URL"
