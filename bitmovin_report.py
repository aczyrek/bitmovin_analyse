import requests
import pandas as pd
import json
import datetime
import os
import argparse
import sys
import calendar
import numpy as np

# Import helper do Google Drive
try:
    from google_drive_helper import upload_report_to_google_drive
except ImportError:
    upload_report_to_google_drive = None

BASE_URL = "https://api.bitmovin.com/v1/encoding/encodings"
API_KEY = os.getenv("BITMOVIN_API_KEY")
ORG_ID = os.getenv("BITMOVIN_ORG_ID")

# =======================================================
# KONFIGURACJA OKRESU
# =======================================================
def get_date_range(year=None, month=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if year and month:
        # User defined month
        start_date = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        # End of the specified month
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime.datetime(year, month, last_day, 23, 59, 59, tzinfo=datetime.timezone.utc)
        
        # We also need to look back a bit for tasks created before the month but finished IN the month
        # Fetch data starting 14 days before the target month to catch stragglers
        fetch_start = start_date - datetime.timedelta(days=14)
        fetch_end = end_date + datetime.timedelta(days=1) # Little buffer
        
        return fetch_start, fetch_end, start_date, end_date
    else:
        # Default: Last 60 days
        start_date = now - datetime.timedelta(days=60)
        end_date = now
        return start_date, end_date, None, None

# =======================================================
# FUNKCJA POBIERAJĄCA DANE
# =======================================================
def get_bitmovin_encodings(fetch_start, fetch_end):
    all_encodings = []
    offset = 0
    limit = 100

    start_date_str = fetch_start.isoformat().replace('+00:00', 'Z')
    end_date_str = fetch_end.isoformat().replace('+00:00', 'Z')

    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json",
        "X-Tenant-Org-Id": ORG_ID
    }

    print(f"Pobieranie danych z Bitmovin (okno od {start_date_str} do {end_date_str})...")

    while True:
        params = {
            "offset": offset,
            "limit": limit,
            "status": "FINISHED",
            "sort": "createdAt:ASC",
            "createdAtNewerThan": start_date_str,
            "createdAtOlderThan": end_date_str
        }

        response = requests.get(BASE_URL, headers=headers, params=params)

        if response.status_code != 200:
            print(f"\n--- BŁĄD KRYTYCZNY: Status {response.status_code} ---")
            try:
                print(json.dumps(response.json(), indent=4))
            except:
                print(response.text)
            raise RuntimeError(f"Błąd Bitmovin API: Status {response.status_code}")

        data = response.json()
        if not data.get('data') or not data['data'].get('result'):
            break

        results = data['data']['result'].get('items', [])
        if not results:
            break

        all_encodings.extend(results)
        if len(results) < limit:
            break

        offset += limit
        print(f"Pobrano {len(all_encodings)} zadań...")

    return all_encodings

# =======================================================
# FUNKCJA POBIERAJĄCA LIVE ENCODING OPTIONS
# =======================================================
def get_live_encoding_options(encoding_id):
    url = f"https://api.bitmovin.com/v1/encoding/statistics/encodings/live/{encoding_id}/options"
    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json",
        "X-Tenant-Org-Id": ORG_ID
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and data['data'].get('result'):
                result = data['data']['result']
                return {
                    'type': result.get('type'),
                    'unitsUsed': result.get('unitsUsed')
                }
    except Exception as e:
        print(f"Błąd live options dla {encoding_id}: {e}")

    return {'type': None, 'unitsUsed': None}

# =======================================================
# PRZETWARZANIE I ZAPIS DANYCH
# =======================================================
def process_and_save_data(encodings_data):
    if not encodings_data:
        print("Brak danych do przetworzenia.")
        return []

    df = pd.DataFrame(encodings_data)
    df['createdAtDT'] = pd.to_datetime(df['createdAt'])
    
    # Wybieranie kolumn
    df_clean = df[[
        'id', 'name', 'type', 'createdAt', 'startedAt', 'finishedAt', 
        'status', 'progress', 'createdAtDT'
    ]].copy()

    print("Pobieranie szczegółów dla Live Encodings...")
    live_units = []
    live_types = []

    for _, row in df_clean.iterrows():
        if row['type'] == 'LIVE':
            options = get_live_encoding_options(row['id'])
            live_units.append(options['unitsUsed'])
            live_types.append(options['type'])
        else:
            live_units.append(None)
            live_types.append(None)
    
    df_clean['Live Units'] = pd.to_numeric(pd.Series(live_units))
    
    # Platformy billingowe typowo zaokrąglają każdy ułamek zużycia w górę.
    # Następnie stosujemy mnożnik x2 zgodnie z poprzednią konfiguracją.
    df_clean['Live Units'] = np.ceil(df_clean['Live Units'].fillna(0)) * 2
    
    df_clean['Running Minutes'] = df_clean['Live Units'] / 2 # Oryginalne minuty przed mnożnikiem
    df_clean['Live Type (HD/SD)'] = live_types
    df_clean['Transcoding Type (SD/HD)'] = 'DO UZUPEŁNIENIA'
    df_clean['Kategoria Kosztu'] = 'Transcoding'

    # Grupowanie po miesiącu ZAKOŃCZENIA (finishedAt) i zapis do osobnych plików
    # Poprawka: Atrybucja kosztów do miesiąca w którym usługa została wykonana (zakończona)
    df_clean['finishedAtDT'] = pd.to_datetime(df['finishedAt'])
    df_clean['year_month'] = df_clean['finishedAtDT'].dt.strftime('%Y-%m')
    
    print(f"Dane zgrupowane po miesiącach: {df_clean['year_month'].unique()}")
    
    generated_reports = []
    for ym, group in df_clean.groupby('year_month'):
        # Pomijamy puste miesiące (np. jeśli brak wartości year_month)
        if pd.isna(ym):
            continue
            
        filename = f"bitmovin_transcoding_report_{ym}.csv"
        
        # Usuwamy kolumny pomocnicze przed zapisem
        final_group = group.drop(columns=['createdAtDT', 'finishedAtDT', 'year_month'])
        
        final_group.to_csv(filename, index=False, sep=';', decimal='.')
        
        units_sum = final_group['Live Units'].dropna().sum()
        print(f"✅ Zapisano lokalnie: {filename} ({len(final_group)} zadań, suma Live Units: {units_sum:.2f} min)")
        
        # Przesyłanie na Google Drive (jeśli poświadczenia są skonfigurowane)
        has_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("google_credentials.json")
        if has_creds and upload_report_to_google_drive:
            try:
                print(f"☁️ Przesyłanie raportu {filename} do Google Drive (AFA_Reports -> {ym})...")
                drive_info = upload_report_to_google_drive(filename, ym)
                generated_reports.append({
                    "month": ym,
                    "local_file": filename,
                    "uploaded": True,
                    "drive_folder_id": drive_info["folder_id"],
                    "drive_csv_id": drive_info["csv_id"],
                    "drive_sheet_id": drive_info["sheet_id"]
                })
            except Exception as e:
                print(f"❌ Błąd przesyłania na Google Drive dla {ym}: {e}")
                generated_reports.append({
                    "month": ym,
                    "local_file": filename,
                    "uploaded": False,
                    "error": str(e)
                })
        else:
            print("⚠️ Pominięto przesyłanie na Google Drive (brak poświadczeń w zmiennej GOOGLE_CREDENTIALS_JSON lub pliku google_credentials.json).")
            generated_reports.append({
                "month": ym,
                "local_file": filename,
                "uploaded": False,
                "reason": "Brak poświadczeń Google Drive"
            })
            
    return generated_reports

# =======================================================
# GŁÓWNA FUNKCJA URUCHOMIENIOWA (PROGRAMISTYCZNA)
# =======================================================
def run_report(year=None, month=None):
    """
    Główna funkcja, którą można zaimportować i wywołać w innych plikach (np. w FastAPI app.py)
    """
    global API_KEY, ORG_ID
    API_KEY = os.getenv("BITMOVIN_API_KEY")
    ORG_ID = os.getenv("BITMOVIN_ORG_ID")
    
    if not API_KEY or not ORG_ID:
        raise ValueError("Brak wymaganych zmiennych środowiskowych BITMOVIN_API_KEY lub BITMOVIN_ORG_ID.")
        
    fetch_start, fetch_end, target_start, target_end = get_date_range(year, month)
    
    encodings = get_bitmovin_encodings(fetch_start, fetch_end)
    if not encodings:
        print("Brak danych (encodings) dla zadanego okresu.")
        return []
        
    return process_and_save_data(encodings)

# =======================================================
# URUCHOMIENIE Z LINII KOMEND (CLI)
# =======================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generuj raport transkodowania Bitmovin i zapisz go lokalnie oraz w Google Drive.")
    parser.add_argument('--year', type=int, help='Docelowy rok (np. 2026)')
    parser.add_argument('--month', type=int, help='Docelowy miesiąc (1-12)')
    args = parser.parse_args()
    
    try:
        reports = run_report(args.year, args.month)
        print(f"\n🎉 Proces zakończony! Wygenerowano raportów: {len(reports)}")
        for r in reports:
            status = "Przesłano do chmury ☁️" if r.get("uploaded") else "Tylko lokalnie 💻"
            print(f"- Miesiąc {r['month']}: {r['local_file']} ({status})")
    except Exception as e:
        print(f"\n❌ Błąd krytyczny podczas uruchamiania skryptu: {e}")
        sys.exit(1)