#!/usr/bin/env bash

set -euo pipefail

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_var PROJECT_ID
require_var GCP_REGION
require_var GAR_LOCATION
require_var GAR_REPOSITORY
require_var CLOUD_RUN_SERVICE

IMAGE_NAME="${IMAGE_NAME:-talkco-backend}"
IMAGE_TAG="${IMAGE_TAG:-manual-$(date +%Y%m%d-%H%M%S)}"
SECRET_BINDINGS="${SECRET_BINDINGS:-OPENAI_API_KEY=OPENAI_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_URI="${GAR_LOCATION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Using project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Configuring Docker auth for ${GAR_LOCATION}-docker.pkg.dev"
gcloud auth configure-docker "${GAR_LOCATION}-docker.pkg.dev" --quiet

echo "Building image: ${IMAGE_URI}"
docker build -f "${REPO_ROOT}/backend/Dockerfile" -t "${IMAGE_URI}" "${REPO_ROOT}"

echo "Pushing image: ${IMAGE_URI}"
docker push "${IMAGE_URI}"

echo "Deploying Cloud Run service: ${CLOUD_RUN_SERVICE}"
gcloud run deploy "${CLOUD_RUN_SERVICE}" \
  --image "${IMAGE_URI}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-secrets "${SECRET_BINDINGS}"

SERVICE_URL="$(gcloud run services describe "${CLOUD_RUN_SERVICE}" --region "${GCP_REGION}" --format='value(status.url)')"
echo "Deploy complete: ${SERVICE_URL}"
