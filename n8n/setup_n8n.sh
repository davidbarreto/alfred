#!/bin/bash
# Idempotent n8n setup: creates owner user, imports credentials and workflows.
# Designed to run on every deploy — all steps are safe to re-run.
#
# Required env vars (add to infra/.env):
#   N8N_PORT, N8N_OWNER_EMAIL, N8N_OWNER_PASSWORD,
#   N8N_OWNER_FIRST_NAME, N8N_OWNER_LAST_NAME
#
# Credential template vars are auto-discovered from n8n/credentials/*.template.json.
# All referenced ${VAR} placeholders must be present in infra/.env before running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"
N8N_CONTAINER="n8n"
CREDS_TEMPLATE_DIR="$REPO_DIR/n8n/credentials"
WORKFLOWS_DIR="$REPO_DIR/n8n/workflows"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
if [ ! -f "$INFRA_DIR/.env" ]; then
  echo -e "${RED}Error: $INFRA_DIR/.env not found${NC}"
  exit 1
fi

set -a
source "$INFRA_DIR/.env"
set +a

REQUIRED_VARS=(
  N8N_PORT
  N8N_OWNER_EMAIL
  N8N_OWNER_PASSWORD
  N8N_OWNER_FIRST_NAME
  N8N_OWNER_LAST_NAME
)

for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo -e "${RED}Error: required variable '$var' is not set in .env${NC}"
    exit 1
  fi
done

N8N_BASE_URL="http://localhost:${N8N_PORT}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_wait_for_n8n() {
  echo -e "${BLUE}Waiting for n8n to be ready...${NC}"
  local max=150
  for i in $(seq 1 $max); do
    if curl -sf "${N8N_BASE_URL}/healthz" > /dev/null 2>&1; then
      echo -e "${GREEN}✓ n8n is ready${NC}"
      return 0
    fi
    if [ "$i" -eq "$max" ]; then
      echo -e "${RED}Error: n8n failed to start within $((max * 2))s${NC}"
      echo -e "${RED}--- n8n container logs ---${NC}"
      docker logs --tail 50 "$N8N_CONTAINER" 2>&1 || true
      exit 1
    fi
    sleep 2
  done
}

# ---------------------------------------------------------------------------
# Step 1 — Create owner user (no-op if already configured)
# ---------------------------------------------------------------------------
_setup_owner() {
  echo -e "${BLUE}Setting up n8n owner user...${NC}"

  response=$(curl -s -w "\n%{http_code}" \
    -X POST "${N8N_BASE_URL}/rest/owner/setup" \
    -H "Content-Type: application/json" \
    -d "{
      \"email\": \"${N8N_OWNER_EMAIL}\",
      \"firstName\": \"${N8N_OWNER_FIRST_NAME}\",
      \"lastName\": \"${N8N_OWNER_LAST_NAME}\",
      \"password\": \"${N8N_OWNER_PASSWORD}\",
      \"skipTrial\": true
    }")

  http_status=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n 1)

  case "$http_status" in
    200)
      echo -e "${GREEN}✓ Owner user created${NC}"
      token=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('token',''))" 2>/dev/null || true)
      [ -n "$token" ] && _skip_onboarding "$token"
      _wait_for_n8n
      ;;
    400)
      if echo "$body" | grep -qi "already setup\|already configured"; then
        echo -e "${YELLOW}Owner user already configured, skipping${NC}"
      else
        echo -e "${RED}Error: owner setup failed (HTTP 400):${NC}"
        echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','(no message)'))" 2>/dev/null || echo "$body"
        exit 1
      fi
      ;;
    404)
      # Newer n8n removes the /rest/owner/setup route once the instance is configured.
      echo -e "${YELLOW}Owner user already configured, skipping${NC}"
      ;;
    *)
      echo -e "${RED}Error: unexpected response from owner setup (HTTP $http_status):${NC}"
      echo "$body"
      exit 1
      ;;
  esac
}

_skip_onboarding() {
  local token="$1"
  curl -s -o /dev/null \
    -X POST "${N8N_BASE_URL}/rest/me/survey" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${token}" \
    -d '{"companyType":"personal","companySize":"<20","workArea":"other","automationGoal":"other","codingSkill":"4"}'
  echo -e "${GREEN}✓ Onboarding survey skipped${NC}"
}

# ---------------------------------------------------------------------------
# Pre-flight — check all vars referenced in templates are defined
# ---------------------------------------------------------------------------
_validate_cred_vars() {
  local missing=()

  for template in "$CREDS_TEMPLATE_DIR"/*.template.json; do
    [ -f "$template" ] || continue
    while IFS= read -r var; do
      [ -z "${!var:-}" ] && missing+=("  \${${var}} — $(basename "$template")")
    done < <(python3 -c "import re,sys; [print(m) for m in sorted(set(re.findall(r'\$\{(\w+)\}', sys.stdin.read())))]" < "$template")
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    echo -e "${RED}Error: the following vars are missing or empty in .env:${NC}"
    printf '%s\n' "${missing[@]}"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Step 2 — Import credentials (envsubst templates)
# ---------------------------------------------------------------------------
_import_credentials() {
  echo -e "${BLUE}Importing credentials...${NC}"

  templates=("$CREDS_TEMPLATE_DIR"/*.template.json)
  if [ ! -f "${templates[0]}" ]; then
    echo -e "${YELLOW}No credential templates found, skipping${NC}"
    return
  fi

  echo "  Creating temp dir in container..."
  CONTAINER_CREDS_DIR=$(docker exec "$N8N_CONTAINER" mktemp -d)

  for template in "${templates[@]}"; do
    filename=$(basename "$template" .template.json)
    echo "  → ${filename} (substituting vars...)"
    tmp_file=$(mktemp /tmp/n8n_cred_XXXXXX.json)
    envsubst < "$template" > "$tmp_file"
    chmod 644 "$tmp_file"
    echo "  → ${filename} (copying to container...)"
    docker cp "$tmp_file" "${N8N_CONTAINER}:${CONTAINER_CREDS_DIR}/${filename}.json"
    rm -f "$tmp_file"
  done

  echo "  Running n8n import:credentials..."
  set +e
  docker exec "$N8N_CONTAINER" n8n import:credentials --separate --input "$CONTAINER_CREDS_DIR" 2>&1 | sed 's/^/  /'
  import_exit=${PIPESTATUS[0]}
  set -e

  if [ $import_exit -eq 0 ]; then
    echo -e "${GREEN}✓ Credentials imported${NC}"
  else
    echo -e "${YELLOW}Warning: credential import exited with code $import_exit${NC}"
  fi

  docker exec "$N8N_CONTAINER" rm -rf "$CONTAINER_CREDS_DIR"
}

# ---------------------------------------------------------------------------
# Step 3 — Import workflows
# ---------------------------------------------------------------------------
_import_workflows() {
  echo -e "${BLUE}Importing workflows...${NC}"

  workflow_files=("$WORKFLOWS_DIR"/*.json)
  if [ ! -f "${workflow_files[0]}" ]; then
    echo -e "${YELLOW}No workflow files found, skipping${NC}"
    return
  fi

  CONTAINER_WF_DIR=$(docker exec "$N8N_CONTAINER" mktemp -d)

  for workflow in "${workflow_files[@]}"; do
    filename=$(basename "$workflow")
    docker cp "$workflow" "${N8N_CONTAINER}:${CONTAINER_WF_DIR}/${filename}"
    echo "  → ${filename}"
  done

  if docker exec "$N8N_CONTAINER" n8n import:workflow --separate --input "$CONTAINER_WF_DIR" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Workflows imported${NC}"
  else
    echo -e "${YELLOW}Warning: workflow import reported errors${NC}"
  fi

  docker exec "$N8N_CONTAINER" rm -rf "$CONTAINER_WF_DIR"
}

# ---------------------------------------------------------------------------
# Step 4 — Publish all workflows (promote draft → live version)
# ---------------------------------------------------------------------------
_publish_workflows() {
  echo -e "${BLUE}Publishing workflows...${NC}"

  local cookie_jar
  cookie_jar=$(mktemp)

  local http_status
  http_status=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$cookie_jar" \
    -X POST "${N8N_BASE_URL}/rest/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"${N8N_OWNER_EMAIL}\", \"password\": \"${N8N_OWNER_PASSWORD}\"}")

  if [ "$http_status" != "200" ]; then
    echo -e "${YELLOW}Warning: login failed (HTTP $http_status) — skipping workflow publish${NC}"
    rm -f "$cookie_jar"
    return
  fi

  local workflows
  workflows=$(curl -s -b "$cookie_jar" "${N8N_BASE_URL}/rest/workflows")

  local wf_ids
  wf_ids=$(echo "$workflows" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('data', []):
    print(str(w['id']) + ' ' + w.get('name', '(unnamed)'))
")

  local count=0
  while IFS=' ' read -r wf_id wf_name; do
    [ -z "$wf_id" ] && continue
    local pub_status
    pub_status=$(curl -s -o /dev/null -w "%{http_code}" \
      -b "$cookie_jar" \
      -X POST "${N8N_BASE_URL}/rest/workflows/${wf_id}/publish")
    if [ "$pub_status" = "200" ]; then
      echo "  → published: ${wf_name} (id=${wf_id})"
      count=$((count + 1))
    else
      echo -e "  ${YELLOW}⚠ failed to publish: ${wf_name} (id=${wf_id}, HTTP $pub_status)${NC}"
    fi
  done <<< "$wf_ids"

  rm -f "$cookie_jar"
  echo -e "${GREEN}✓ Published ${count} workflow(s)${NC}"
}

# ---------------------------------------------------------------------------
# Step 5 — Activate all workflows
# ---------------------------------------------------------------------------
_activate_workflows() {
  echo -e "${BLUE}Activating workflows...${NC}"

  local cookie_jar
  cookie_jar=$(mktemp)

  local http_status
  http_status=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$cookie_jar" \
    -X POST "${N8N_BASE_URL}/rest/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"${N8N_OWNER_EMAIL}\", \"password\": \"${N8N_OWNER_PASSWORD}\"}")

  if [ "$http_status" != "200" ]; then
    echo -e "${YELLOW}Warning: login failed (HTTP $http_status) — skipping workflow activation${NC}"
    rm -f "$cookie_jar"
    return
  fi

  local workflows
  workflows=$(curl -s -b "$cookie_jar" "${N8N_BASE_URL}/rest/workflows")

  # Emit "<id> <name>" lines for inactive workflows
  local inactive
  inactive=$(echo "$workflows" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for w in data.get('data', []):
    if not w.get('active', False):
        print(str(w['id']) + ' ' + w.get('name', '(unnamed)'))
")

  local count=0
  while IFS=' ' read -r wf_id wf_name; do
    [ -z "$wf_id" ] && continue
    local patch_status
    patch_status=$(curl -s -o /dev/null -w "%{http_code}" \
      -b "$cookie_jar" \
      -X PATCH "${N8N_BASE_URL}/rest/workflows/${wf_id}" \
      -H "Content-Type: application/json" \
      -d '{"active": true}')
    if [ "$patch_status" = "200" ]; then
      echo "  → activated: ${wf_name} (id=${wf_id})"
      count=$((count + 1))
    else
      echo -e "  ${YELLOW}⚠ failed to activate: ${wf_name} (id=${wf_id}, HTTP $patch_status)${NC}"
    fi
  done <<< "$inactive"

  rm -f "$cookie_jar"

  if [ -z "$inactive" ]; then
    echo -e "${GREEN}✓ All workflows already active${NC}"
  else
    echo -e "${GREEN}✓ Activated ${count} workflow(s)${NC}"
  fi
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}n8n Setup${NC}"
echo -e "${BLUE}======================================${NC}"

_validate_cred_vars
_wait_for_n8n
_setup_owner
_import_credentials
_import_workflows
_publish_workflows
_activate_workflows

echo ""
echo -e "${GREEN}✓ n8n setup complete${NC}"
