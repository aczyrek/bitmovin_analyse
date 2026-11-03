#!/usr/bin/env bash
# Deploy automatyzacji raportów Bitmovin na AWS Lambda.
# Wymaga: Docker Desktop uruchomiony, aws cli skonfigurowane (aws configure), sam cli.
#
# Sekrety czytane są z lokalnego .env — nie są zapisywane w repozytorium.
set -euo pipefail

STACK_NAME="${STACK_NAME:-bitmovin-report}"
REGION="${AWS_REGION:-eu-central-1}"
# Dedykowany profil IAM tego projektu (nie mieszamy z fb-ads / legia-deployer)
export AWS_PROFILE="${AWS_PROFILE:-bitmovin}"

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "❌ Profil AWS '$AWS_PROFILE' nie ma działających poświadczeń."
  echo "   Uzupełnij: aws configure --profile $AWS_PROFILE"
  exit 1
fi
echo "👤 Deploy jako: $(aws sts get-caller-identity --query Arn --output text)"

if [ ! -f .env ]; then
  echo "❌ Brak pliku .env — potrzebne są BITMOVIN_API_KEY, BITMOVIN_ORG_ID, GOOGLE_TOKEN_JSON, TRIGGER_SECRET."
  exit 1
fi

set -a; . ./.env; set +a

: "${BITMOVIN_API_KEY:?Brak BITMOVIN_API_KEY w .env}"
: "${BITMOVIN_ORG_ID:?Brak BITMOVIN_ORG_ID w .env}"

TRIGGER_SECRET="${TRIGGER_SECRET:-}"
GOOGLE_DRIVE_FOLDER_ID="${GOOGLE_DRIVE_FOLDER_ID:-}"
GOOGLE_TOKEN_JSON="${GOOGLE_TOKEN_JSON:-}"

# Poświadczenia Google: token OAuth2 (prywatny My Drive) LUB service account (Shared Drive).
# Gdy w .env nie ma żadnego, bierzemy lokalny plik service accountu.
GOOGLE_CREDENTIALS_JSON="${GOOGLE_CREDENTIALS_JSON:-}"
if [ -z "$GOOGLE_TOKEN_JSON" ] && [ -z "$GOOGLE_CREDENTIALS_JSON" ]; then
  if [ -f google_credentials.json ]; then
    GOOGLE_CREDENTIALS_JSON=$(python3 -c "import json,sys;print(json.dumps(json.load(open('google_credentials.json'))))")
    echo "🔐 Poświadczenia Google: service account z google_credentials.json"
  else
    echo "❌ Brak poświadczeń Google — ustaw GOOGLE_TOKEN_JSON lub GOOGLE_CREDENTIALS_JSON w .env."
    exit 1
  fi
elif [ -n "$GOOGLE_TOKEN_JSON" ]; then
  echo "🔐 Poświadczenia Google: token OAuth2 z .env"
fi

echo "🔨 Budowanie obrazu kontenera (arm64)..."
sam build

# Parametry przekazujemy PLIKIEM, nie w linii poleceń: SAM tnie wartości na spacjach,
# a JSON service accountu zawiera spacje (np. "-----BEGIN PRIVATE KEY-----").
# Puste wartości pomijamy — template ma dla nich Default: ''.
# SAM wymaga rozszerzenia .json/.yaml, więc plik tworzymy w tymczasowym katalogu
PARAMS_DIR=$(mktemp -d -t bitmovin-params)
trap 'rm -rf "$PARAMS_DIR"' EXIT
chmod 700 "$PARAMS_DIR"
PARAMS_FILE="$PARAMS_DIR/params.yaml"

BITMOVIN_API_KEY="$BITMOVIN_API_KEY" BITMOVIN_ORG_ID="$BITMOVIN_ORG_ID" \
GOOGLE_TOKEN_JSON="$GOOGLE_TOKEN_JSON" GOOGLE_CREDENTIALS_JSON="$GOOGLE_CREDENTIALS_JSON" \
GOOGLE_DRIVE_FOLDER_ID="$GOOGLE_DRIVE_FOLDER_ID" TRIGGER_SECRET="$TRIGGER_SECRET" \
ALERT_EMAIL="${ALERT_EMAIL:-}" \
python3 -c "
import json, os, sys
mapping = [
    ('BitmovinApiKey',        'BITMOVIN_API_KEY'),
    ('BitmovinOrgId',         'BITMOVIN_ORG_ID'),
    ('GoogleTokenJson',       'GOOGLE_TOKEN_JSON'),
    ('GoogleCredentialsJson', 'GOOGLE_CREDENTIALS_JSON'),
    ('GoogleDriveFolderId',   'GOOGLE_DRIVE_FOLDER_ID'),
    ('TriggerSecret',         'TRIGGER_SECRET'),
    ('AlertEmail',            'ALERT_EMAIL'),
]
# SAM oczekuje płaskiej mapy nazwa_parametru -> wartość (JSON jest poprawnym YAML-em)
params = {k: os.environ[e] for k, e in mapping if os.environ.get(e)}
json.dump(params, open(sys.argv[1], 'w'))
" "$PARAMS_FILE"

echo "🚀 Deploy stacku '$STACK_NAME' w regionie $REGION..."
sam deploy \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --resolve-image-repos \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides "file://$PARAMS_FILE"

echo
echo "✅ Gotowe. Adres panelu:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text
