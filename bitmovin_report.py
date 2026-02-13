import requests
import pandas as pd
import json
import datetime
import os

BASE_URL = "https://api.bitmovin.com/v1/encoding/encodings"
API_KEY = os.getenv("BITMOVIN_API_KEY")
ORG_ID = os.getenv("BITMOVIN_ORG_ID")

import argparse
import sys
import calendar

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

# Parse args
parser = argparse.ArgumentParser()
parser.add_argument('--year', type=int, help='Target year (e.g. 2026)')
parser.add_argument('--month', type=int, help='Target month (1-12)')
args = parser.parse_args()

FETCH_START, FETCH_END, TARGET_START, TARGET_END = get_date_range(args.year, args.month)

# =======================================================
# FUNKCJA POBIERAJĄCA DANE
# =======================================================
def get_bitmovin_encodings():
    all_encodings = []
    offset = 0
    limit = 200

    start_date_str = FETCH_START.isoformat().replace('+00:00', 'Z')
    end_date_str = FETCH_END.isoformat().replace('+00:00', 'Z')

    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json",
        "X-Tenant-Org-Id": ORG_ID
    }

    print(f"Pobieranie danych z Bitmovin (okno 60 dni: od {start_date_str} do {end_date_str})...")

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
            except:
                print(response.text)
            sys.exit(1)

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
        return

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

    df_clean['Live Units'] = pd.Series(live_units) * 2
    df_clean['Running Minutes'] = df_clean['Live Units']
    df_clean['Live Type (HD/SD)'] = live_types
    df_clean['Transcoding Type (SD/HD)'] = 'DO UZUPEŁNIENIA'
    df_clean['Kategoria Kosztu'] = 'Transcoding'

    # Grupowanie po miesiącu ZAKOŃCZENIA (finishedAt) i zapis do osobnych plików
    # Poprawka: Atrybucja kosztów do miesiąca w którym usługa została wykonana (zakończona)
    df_clean['finishedAtDT'] = pd.to_datetime(df['finishedAt'])
    df_clean['year_month'] = df_clean['finishedAtDT'].dt.strftime('%Y-%m')
    
    print(f"Dane zgrupowane po miesiącach: {df_clean['year_month'].unique()}")
    
    found_any = False
    for ym, group in df_clean.groupby('year_month'):
        found_any = True
        filename = f"bitmovin_transcoding_report_{ym}.csv"
        
        # Usuwamy kolumny pomocnicze przed zapisem
        final_group = group.drop(columns=['createdAtDT', 'finishedAtDT', 'year_month'])
        
        final_group.to_csv(filename, index=False, sep=';', decimal='.')
        
        units_sum = final_group['Live Units'].dropna().sum()
        units_sum = final_group['Live Units'].dropna().sum()
        print(f"✅ Zapisano: {filename} ({len(final_group)} zadań, suma Live Units: {units_sum:.2f} min)")

    if not found_any:
        print("Nie wygenerowano żadnego pliku raportu (brak grup).")
        sys.exit(1)

# =======================================================
# URUCHOMIENIE
# =======================================================
if __name__ == "__main__":
    if not API_KEY or not ORG_ID:
        print("Brak BITMOVIN_API_KEY lub BITMOVIN_ORG_ID.")
        sys.exit(1)
        
    encodings = get_bitmovin_encodings()
    if not encodings:
        print("Brak danych (encodings) dla zadanego okresu.")
        sys.exit(1)

    process_and_save_data(encodings)