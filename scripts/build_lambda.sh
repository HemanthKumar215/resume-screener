#!/usr/bin/env bash
# Bundle the Lambda code and its dependencies into backend/dist/lambda.zip (arm64, Python 3.13).
set -euo pipefail
cd "$(dirname "$0")/../backend"

rm -rf build dist
mkdir -p build dist
python3 -m pip install --quiet --target build --platform manylinux2014_aarch64 --python-version 3.13 \
  --implementation cp --only-binary=:all: -r requirements.txt
cp -r src/screener src/handlers build/
find build -name "__pycache__" -type d -prune -exec rm -rf {} +

# Fixed timestamps so the zip (and Terraform's source_code_hash) only changes when code does.
find build -exec touch -t 202001010000 {} +
(cd build && find . -type f | LC_ALL=C sort | zip -q -X -@ ../dist/lambda.zip)
echo "Built $(du -h dist/lambda.zip | cut -f1) -> backend/dist/lambda.zip"
