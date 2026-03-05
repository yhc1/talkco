#!/usr/bin/env bash

set -euo pipefail

# Usage:
#   export GCP_PROJECT_ID="your-project-id"
#   export GCP_REGION="asia-east1"
#   export GAR_LOCATION="asia-east1"
#   export GAR_REPOSITORY="talkco-backend-api"
#   export CLOUD_RUN_SERVICE="talkco-backend-api"
#   export GCP_WORKLOAD_IDENTITY_PROVIDER="projects/123456789/locations/global/workloadIdentityPools/pool/providers/provider"
#   export GCP_SERVICE_ACCOUNT_EMAIL="github-actions-deployer@your-project-id.iam.gserviceaccount.com"
#   ./scripts/set_github_actions_config.sh
#
# Optional:
#   export GITHUB_REPOSITORY="owner/repo"


# export GCP_PROJECT_ID="your-project-id"
# export GCP_REGION="asia-east1"
# export GAR_LOCATION="asia-east1"
# export GAR_REPOSITORY="talkco-backend"
# export CLOUD_RUN_SERVICE="talkco-backend"
# export GCP_WORKLOAD_IDENTITY_PROVIDER="projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
# export GCP_SERVICE_ACCOUNT_EMAIL="github-actions@your-project-id.iam.gserviceaccount.com"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1" >&2
    exit 1
  fi
}

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_cmd gh
require_cmd git

if ! gh auth status >/dev/null 2>&1; then
  echo "gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  remote_url="$(git config --get remote.origin.url || true)"
  if [[ -z "${remote_url}" ]]; then
    echo "Cannot detect repository from git remote. Set GITHUB_REPOSITORY=owner/repo." >&2
    exit 1
  fi
  if [[ "${remote_url}" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    GITHUB_REPOSITORY="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  else
    echo "Cannot parse GitHub repo from remote URL: ${remote_url}" >&2
    echo "Set GITHUB_REPOSITORY=owner/repo and retry." >&2
    exit 1
  fi
fi

require_var GCP_PROJECT_ID
require_var GCP_REGION
require_var GAR_LOCATION
require_var GAR_REPOSITORY
require_var CLOUD_RUN_SERVICE
require_var GCP_WORKLOAD_IDENTITY_PROVIDER
require_var GCP_SERVICE_ACCOUNT_EMAIL

echo "Setting GitHub Actions variables for ${GITHUB_REPOSITORY} ..."
gh variable set GCP_PROJECT_ID --repo "${GITHUB_REPOSITORY}" --body "${GCP_PROJECT_ID}"
gh variable set GCP_REGION --repo "${GITHUB_REPOSITORY}" --body "${GCP_REGION}"
gh variable set GAR_LOCATION --repo "${GITHUB_REPOSITORY}" --body "${GAR_LOCATION}"
gh variable set GAR_REPOSITORY --repo "${GITHUB_REPOSITORY}" --body "${GAR_REPOSITORY}"
gh variable set CLOUD_RUN_SERVICE --repo "${GITHUB_REPOSITORY}" --body "${CLOUD_RUN_SERVICE}"

echo "Setting GitHub Actions secrets for ${GITHUB_REPOSITORY} ..."
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "${GITHUB_REPOSITORY}" --body "${GCP_WORKLOAD_IDENTITY_PROVIDER}"
gh secret set GCP_SERVICE_ACCOUNT_EMAIL --repo "${GITHUB_REPOSITORY}" --body "${GCP_SERVICE_ACCOUNT_EMAIL}"

echo "Done."
echo "Repo: ${GITHUB_REPOSITORY}"
