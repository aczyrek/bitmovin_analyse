import requests
import pandas as pd
import json
import datetime
import os

BASE_URL = "https://api.bitmovin.com/v1/encoding/encodings"
API_KEY = os.getenv("BITMOVIN_API_KEY")
ORG_ID = os.getenv("BITMOVIN_ORG_ID")
now_utc = datetime.datetime.now(datetime.timezone.utc)
curr_month_start = datetime.datetime(now_utc.year, now_utc.month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
if curr_month_start.month == 1:
    prev_month_start = datetime.datetime(curr_month_start.year - 1, 12, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
else:
    prev_month_start = datetime.datetime(curr_month_start.year, curr_month_start.month - 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
START_DATE_OBJ = prev_month_start
END_DATE_OBJ = curr_month_start
OUTPUT_FILE = f"bitmovin_transcoding_report_{START_DATE_OBJ.year}-{START_DATE_OBJ.month:02d}.csv"

# =======================================================
# FUNKCJA POBIERAJĄCA DANE
# =======================================================
def get_bitmovin_encodings():
    all_encodings = []
    offset = 0
    limit = 100

    # Przekształcenie obiektów daty na format ISO-8601 ze strefą Z (wymagane przez Bitmovin)
    start_date_str = START_DATE_OBJ.isoformat().replace('+00:00', 'Z')
    end_date_str = END_DATE_OBJ.isoformat().replace('+00:00', 'Z')

    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json",
        "X-Tenant-Org-Id": ORG_ID
    }

    print(f"Rozpoczynanie pobierania danych transkodowania z Bitmovin (od {start_date_str} do {end_date_str})...")

    while True:
        # Definicja wszystkich poprawnych parametrów zapytania
        params = {
            "offset": offset,
            "limit": limit,
            "status": "FINISHED",
            "sort": "createdAt:ASC",

            # Parametry czasowe, które są akceptowane przez API
            "createdAtNewerThan": start_date_str,
            "createdAtOlderThan": end_date_str
        }

        # Zapytanie API
        response = requests.get(
            BASE_URL,
            headers=headers,
            params=params
        )

        # Obsługa błędów autoryzacji i niepoprawnych zapytań (4xx)
        if response.status_code != 200:
            print(f"\n--- BŁĄD KRYTYCZNY: Status {response.status_code} ---")
            print("PEŁNA ODPOWIEDŹ API:")
            try:
                # Wypisujemy pełną odpowiedź do diagnozy
                print(json.dumps(response.json(), indent=4))
            except json.JSONDecodeError:
                print(response.text)
            return []

        data = response.json()

        # Sprawdzamy, czy podstawowa struktura jest poprawna
        if not data.get('data') or not data['data'].get('result'):
            print("Błąd struktury odpowiedzi API.")
            break

        # Pobieramy listę elementów. Jeśli jest pusta, 'results' będzie puste.
        results = data['data']['result'].get('items', [])

        # Jeśli nie ma wyników, kończymy paginację
        if not results:
            if offset == 0:
                 print("Zapytanie API pomyślne, ale nie znaleziono żadnych zakończonych zadań w podanym okresie.")
            else:
                print("Paginacja zakończona: Nie ma więcej danych do pobrania.")
            break

        all_encodings.extend(results)

        # Jeśli otrzymaliśmy mniej wyników niż limit, oznacza to ostatnią stronę
        if len(results) < limit:
            print(f"Pobrano {len(all_encodings)} zadań (ostatnia strona).")
            break

        offset += limit
        print(f"Pobrano {len(all_encodings)} zadań...")

    return all_encodings

# =======================================================
# FUNKCJA POBIERAJĄCA LIVE ENCODING OPTIONS
# =======================================================
def get_live_encoding_options(encoding_id):
    """Pobiera opcje dla live encoding (typ HD/SD i wykorzystane jednostki)"""
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
        print(f"Błąd podczas pobierania opcji live dla {encoding_id}: {e}")

    return {'type': None, 'unitsUsed': None}

# =======================================================
# PRZETWARZANIE I ZAPIS DANYCH
# =======================================================
def process_and_save_data(encodings_data):
    if not encodings_data:
        print("Brak danych do przetworzenia. Zakończenie skryptu.")
        return

    df = pd.DataFrame(encodings_data)

    # Wybieranie kluczowych kolumn dostępnych w API
    df_clean = df[[
        'id',
        'name',
        'type',
        'createdAt',
        'startedAt',
        'finishedAt',
        'status',
        'progress'
    ]].copy()

    # Dla encodings typu LIVE, pobierz dodatkowe informacje
    print("Pobieranie informacji o live encodings...")
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

    # Kolumny do uzupełnienia ręcznego w Excelu
    df_clean['Transcoding Type (SD/HD)'] = 'DO UZUPEŁNIENIA'
    df_clean['Kategoria Kosztu'] = 'Transcoding'

    # Zapis do CSV (separator średnik dla polskiego Excela)
    df_clean.to_csv(OUTPUT_FILE, index=False, sep=';', decimal='.')

    # Podsumowanie Live Units
    total_live_units = df_clean['Live Units'].dropna().sum()
    total_hours = total_live_units / 60

    print("\n=======================================================")
    print(f"✅ Raport zapisany pomyślnie do pliku: {OUTPUT_FILE}")
    print(f"Znaleziono {len(df_clean)} zadań transkodowania.")
    print(f"Łączna suma 'Live Units': {total_live_units:.2f} min (~{total_hours:.2f} h)")
    print("=======================================================")
    print("❗ W kolejnym kroku, proszę ręcznie uzupełnić kolumnę 'Transcoding Type (SD/HD)' w pliku CSV.")

# Uruchomienie głównej logiki
if __name__ == "__main__":
    # Upewniamy się, że wymagane biblioteki są zainstalowane
    try:
        import requests, pandas
    except ImportError:
        print("Błąd: Brak wymaganych bibliotek (requests lub pandas).")
        print("Uruchom: python -m pip install requests pandas")
        exit()

    if not API_KEY or not ORG_ID:
        print("Brak BITMOVIN_API_KEY lub BITMOVIN_ORG_ID w zmiennych środowiskowych.")
        exit(1)
    encodings = get_bitmovin_encodings()
    process_and_save_data(encodings)