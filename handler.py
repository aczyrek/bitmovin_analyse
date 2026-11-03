"""
Punkty wejścia dla AWS Lambda.

Dwa handlery:
  - lambda_handler          -> HTTP (Function URL): cała aplikacja FastAPI bez zmian, przez Mangum
  - scheduled_report_handler -> wywołanie z EventBridge Scheduler: raport za poprzedni miesiąc,
                                bez pośrednictwa HTTP (brak limitów czasu bramki)
"""

import datetime
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Na Lambdzie zapisywać można wyłącznie do /tmp
os.environ.setdefault("OUTPUT_DIR", "/tmp/reports")


def _load_secrets_from_ssm():
    """
    Opcjonalnie: dociąga sekrety z SSM Parameter Store do zmiennych środowiskowych.
    Aktywne tylko gdy ustawiono SSM_PREFIX (np. /bitmovin-report/).
    Uruchamiane raz na zimny start.
    """
    prefix = os.getenv("SSM_PREFIX")
    if not prefix:
        return

    try:
        import boto3
        ssm = boto3.client("ssm")
        paginator = ssm.get_paginator("get_parameters_by_path")
        loaded = []
        for page in paginator.paginate(Path=prefix, Recursive=True, WithDecryption=True):
            for param in page["Parameters"]:
                name = param["Name"].rsplit("/", 1)[-1]
                os.environ[name] = param["Value"]
                loaded.append(name)
        logger.info(f"Wczytano sekrety z SSM ({prefix}): {', '.join(loaded) or 'brak'}")
    except Exception as e:
        # Nie przerywamy startu — zmienne mogą być podane bezpośrednio w konfiguracji Lambdy
        logger.error(f"Nie udało się wczytać sekretów z SSM ({prefix}): {e}")


_load_secrets_from_ssm()

from app import app  # noqa: E402  (import po wczytaniu sekretów)
from bitmovin_report import run_report  # noqa: E402

try:
    from mangum import Mangum
    lambda_handler = Mangum(app, lifespan="off")
except ImportError:  # pozwala importować moduł lokalnie bez mangum
    lambda_handler = None
    logger.warning("Brak pakietu 'mangum' — handler HTTP nie jest dostępny.")


def scheduled_report_handler(event, context):
    """
    Odpowiednik endpointu /run/auto — raport za poprzedni miesiąc.
    Rok/miesiąc można nadpisać payloadem: {"year": 2026, "month": 3}
    """
    event = event or {}
    year = event.get("year")
    month = event.get("month")

    if not (year and month):
        today = datetime.date.today()
        prev = today.replace(day=1) - datetime.timedelta(days=1)
        year, month = prev.year, prev.month

    logger.info(f"Harmonogram: generowanie raportu za {year}-{month:02d}")
    results = run_report(year=year, month=month)

    if not results:
        logger.info(f"Brak zakończonych zadań w Bitmovin za {year}-{month:02d}.")
        return {"status": "success", "period": f"{year}-{month:02d}", "reports": []}

    uploaded = sum(1 for r in results if r.get("uploaded"))
    logger.info(f"Gotowe: {len(results)} raportów, przesłanych na Drive: {uploaded}")
    return {
        "status": "success",
        "period": f"{year}-{month:02d}",
        "reports": results
    }
