#!/usr/bin/env bash
# Wgrywa klucze dostępowe AWS do profilu z pliku CSV pobranego z konsoli
# (IAM -> Users -> Security credentials -> Create access key -> Download .csv file).
#
# Użycie:  ./import_aws_keys.sh ~/Downloads/bitmovin-deployer_accessKeys.csv [nazwa_profilu]
#
# Klucze nie są nigdzie wypisywane na ekran.
set -euo pipefail

CSV="${1:-}"
PROFILE="${2:-bitmovin}"
REGION="${AWS_REGION:-eu-central-1}"

if [ -z "$CSV" ] || [ ! -f "$CSV" ]; then
  echo "❌ Podaj ścieżkę do pliku CSV z konsoli AWS."
  echo "   np. ./import_aws_keys.sh ~/Downloads/bitmovin-deployer_accessKeys.csv"
  exit 1
fi

# CSV z AWS ma nagłówek "Access key ID,Secret access key" i jedną linię danych.
KEY_ID=$(tail -n +2 "$CSV" | head -1 | cut -d',' -f1 | tr -d '"\r\n ')
SECRET=$(tail -n +2 "$CSV" | head -1 | cut -d',' -f2 | tr -d '"\r\n ')

if [ -z "$KEY_ID" ] || [ -z "$SECRET" ]; then
  echo "❌ Nie udało się odczytać kluczy z $CSV — czy to na pewno plik pobrany z IAM?"
  exit 1
fi

aws configure set aws_access_key_id     "$KEY_ID" --profile "$PROFILE"
aws configure set aws_secret_access_key "$SECRET" --profile "$PROFILE"
aws configure set region                "$REGION" --profile "$PROFILE"
aws configure set output                json      --profile "$PROFILE"

echo "🔑 Zapisano klucz ${KEY_ID:0:4}****${KEY_ID: -4} w profilu '$PROFILE'."

if aws sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
  echo "✅ Działa: $(aws sts get-caller-identity --profile "$PROFILE" --query Arn --output text)"
  echo "   Możesz teraz skasować plik: rm \"$CSV\""
else
  echo "⚠️  Klucze zapisane, ale AWS ich jeszcze nie akceptuje."
  echo "   Nowy klucz bywa aktywny po ~10 s — spróbuj: aws sts get-caller-identity --profile $PROFILE"
fi
