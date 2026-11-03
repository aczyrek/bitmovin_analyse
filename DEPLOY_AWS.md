# Migracja z Render.com na AWS Lambda

## Stan wdrożenia (zdeployowane i przetestowane)

| | |
|---|---|
| Stack | `bitmovin-report`, region `eu-central-1`, account `862121602334` |
| Panel (Function URL) | https://nv4cnr4roa2denlwvriuo5rn540itprs.lambda-url.eu-central-1.on.aws/ |
| Funkcja z harmonogramu | `bitmovin-report-ScheduledFunction-2m3Q3BMFIyR9` |
| Harmonogram | `cron(0 6 1 * ? *)`, Europe/Warsaw, ENABLED — 1. dnia miesiąca o 06:00 |
| Poświadczenia Google | service account `python-api-54@…` (folder docelowy to Shared Drive, więc token OAuth nie jest potrzebny) |
| Alerty | e-mail na adrian.czyrek@herodot.com przy błędzie raportu (potwierdź subskrypcję SNS w mailu) |


Ta sama aplikacja, dwie funkcje Lambda z jednego obrazu kontenera:

| Funkcja | Handler | Rola |
|---|---|---|
| `ApiFunction` | `handler.lambda_handler` | FastAPI przez Mangum — panel statusu + ręczne `/run`. Publiczny URL (Function URL) zastępuje adres z Render. |
| `ScheduledFunction` | `handler.scheduled_report_handler` | Raport za poprzedni miesiąc, odpalany przez EventBridge Scheduler 1. dnia miesiąca o 06:00 (Europe/Warsaw). Nie idzie przez HTTP, więc nie dotyczą go limity czasu bramki. |

Pełne 900 s timeoutu i 1536 MB RAM — z zapasem na pętlę `get_live_encoding_options`
po wszystkich encodingach LIVE.

## Wymagania wstępne

1. **Docker Desktop uruchomiony** (obraz buduje się lokalnie).
2. **Profil AWS `bitmovin`** — dedykowany użytkownik IAM tego projektu, account `862121602334`.
   Region `eu-central-1` jest już wpisany w `~/.aws/config`; brakuje tylko kluczy:
   ```bash
   # w konsoli AWS: IAM -> Users -> Create user "bitmovin-deployer"
   #   -> Attach policies directly -> Create policy -> JSON
   #   -> wklej zawartość aws_iam_policy_deployer.json (nazwa np. BitmovinReportDeploy)
   #   -> Security credentials -> Create access key -> Command Line Interface
   aws configure --profile bitmovin   # wklej Access key ID i Secret
   aws sts get-caller-identity --profile bitmovin   # weryfikacja
   ```
   Polityka w [aws_iam_policy_deployer.json](aws_iam_policy_deployer.json) jest zawężona:
   IAM-owe role tylko dla `bitmovin-report-*`, S3 tylko dla bucketa `aws-sam-cli-managed-*`.
   Nie ruszamy profili `fb-ads` ani `legia-deployer`.
3. `sam` i `aws` CLI — oba są już zainstalowane.

## Deploy

Sekrety brane są z lokalnego `.env` (nie trafiają do repo):

```bash
# .env musi zawierać:
#   BITMOVIN_API_KEY, BITMOVIN_ORG_ID, GOOGLE_TOKEN_JSON, TRIGGER_SECRET, GOOGLE_DRIVE_FOLDER_ID
# opcjonalnie:
export ALERT_EMAIL=adrian.czyrek@herodot.com   # alert mailowy przy błędzie raportu

./deploy_aws.sh
```

Skrypt na końcu wypisze publiczny URL panelu. Region domyślny: `eu-central-1`
(zmiana: `AWS_REGION=eu-west-1 ./deploy_aws.sh`).

**Poświadczenia Google:** skrypt bierze `GOOGLE_TOKEN_JSON` z `.env`, a gdy go nie ma —
service account z `google_credentials.json`. Folder docelowy (`GOOGLE_DRIVE_FOLDER_ID`)
leży na **Shared Drive**, na którym service account ma prawo zapisu, więc token OAuth
nie jest potrzebny (limit miejsca service accountu nie obowiązuje na dyskach współdzielonych).

**Parametry idą do SAM plikiem YAML, nie w linii poleceń** — `sam deploy` tnie wartości
`--parameter-overrides` na spacjach, a JSON service accountu zawiera `-----BEGIN PRIVATE KEY-----`.
Plik powstaje w katalogu tymczasowym z prawami 700 i jest kasowany po deployu.

## Weryfikacja po deployu

```bash
# 1. Panel statusu — sprawdź, czy wszystkie zmienne mają ✅
curl -s "$(aws cloudformation describe-stacks --stack-name bitmovin-report \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)"

# 2. Testowy raport za konkretny miesiąc, bez czekania na harmonogram
#    (składnia dla AWS CLI v1 — zainstalowana wersja to 1.45; w v2 dochodzi --cli-binary-format)
aws lambda invoke --profile bitmovin --region eu-central-1 \
  --function-name bitmovin-report-ScheduledFunction-2m3Q3BMFIyR9 \
  --payload '{"year":2026,"month":7}' --cli-read-timeout 900 /tmp/out.json && cat /tmp/out.json

# 3. Logi
sam logs --stack-name bitmovin-report --name ScheduledFunction --tail
```

## Koszt

Kilkanaście wywołań miesięcznie × ~1–3 min. Mieści się w free tier Lambdy;
realnie płacisz groszowe kwoty za przechowywanie obrazu w ECR (~0,10 USD/mies.)
i logi w CloudWatch (retencja ustawiona na 30 dni). Kredyty AWS zostaną nietknięte.

## Różnice wobec Render.com

- **Zapis CSV**: na Lambdzie tylko `/tmp` jest zapisywalny. `OUTPUT_DIR=/tmp/reports`
  ustawia to automatycznie ([bitmovin_report.py](bitmovin_report.py#L182)). Pliki są efemeryczne —
  liczy się to, co wyleci na Google Drive.
- **Function URL jest publiczny** (`AuthType: NONE`), dokładnie jak URL na Renderze.
  Endpointy `/run` i `/run/auto` chroni `TRIGGER_SECRET`; strona główna pokazuje jedynie,
  czy zmienne są ustawione, bez ich wartości. Jeśli chcesz to domknąć — zmień
  `AuthType` na `AWS_IAM` w [template.yaml](template.yaml), ale wtedy wywołania wymagają podpisu SigV4.
- **Cron po stronie AWS**: `/run/auto` nie musi już być wołany z zewnątrz. Jeśli dziś odpala
  go Make/cron-job.org — po deployu można to wyłączyć, żeby raport nie generował się dwa razy.
- **Sekrety w konfiguracji Lambdy** (szyfrowane at rest). Jeśli wolisz SSM Parameter Store,
  ustaw zmienną `SSM_PREFIX` (np. `/bitmovin-report/`) i dodaj funkcji politykę
  `ssm:GetParametersByPath` — [handler.py](handler.py#L23) sam dociągnie parametry na zimnym starcie.
