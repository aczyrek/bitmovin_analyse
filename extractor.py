import pandas as pd
import os
from datetime import datetime

# --- Konfiguracja ---
INPUT_FILENAME = 'new_fi_invoices_data.csv'
OUTPUT_FILENAME = 'invoices_id_date_taxes_post_20250701.csv'
COLUMNS_TO_EXTRACT = ['id', 'invoice_date', 'taxes']
# Data graniczna do filtrowania (01.07.2025)
CUTOFF_DATE_STR = '2025-07-01'

# --- Główna funkcja ---
def extract_and_filter_invoices(input_file: str, output_file: str, cutoff_date_str: str):
    """
    Wczytuje plik CSV, konwertuje daty, filtruje po dacie granicznej 
    i zapisuje wybrane kolumny do nowego pliku.
    """
    try:
        df = pd.read_csv(input_file)
        
        # 1. Określenie timestampu granicznego dla 01.07.2025 00:00:00 UTC
        # Musimy go użyć, ponieważ kolumna 'date' jest w sekundach (Unix Timestamp)
        cutoff_timestamp = pd.to_datetime(cutoff_date_str).timestamp()

        # 2. Utworzenie nowej, czytelnej kolumny daty
        # 'unit='s' informuje Pandas, że timestamp jest w sekundach
        df['invoice_date'] = pd.to_datetime(df['date'], unit='s').dt.strftime('%Y-%m-%d')

        # 3. Filtrowanie danych: tylko wiersze, gdzie data (timestamp) jest >= daty granicznej
        df_filtered = df[df['date'] >= cutoff_timestamp].copy()
        
        # 4. Wybór kolumn do zapisu
        df_extracted = df_filtered[COLUMNS_TO_EXTRACT]

        # 5. Zapisanie wyników do nowego pliku CSV
        df_extracted.to_csv(output_file, index=False)

        # 6. Potwierdzenie operacji
        print("-" * 50)
        print("✅ Operacja ekstrakcji i filtrowania zakończona sukcesem!")
        print(f"Zapisano dane ({len(df_extracted)} wierszy) do pliku: {output_file}")
        print(f"Filtrowane dla dat >= {cutoff_date_str}")
        print("-" * 50)
        
        if not df_extracted.empty:
            print("\nPierwsze 5 wierszy wyodrębnionego pliku:")
            print(df_extracted.head().to_markdown(index=False))
        else:
            print("Ważna informacja: Zbiór danych po filtrowaniu jest pusty.")

    except FileNotFoundError:
        print(f"BŁĄD: Plik wejściowy '{input_file}' nie został znaleziony.")
    except KeyError as e:
        print(f"BŁĄD: Brakuje wymaganej kolumny: {e}. Sprawdź, czy plik CSV ma nagłówki.")
    except Exception as e:
        print(f"Wystąpił nieoczekiwany błąd: {e}")

# --- Uruchomienie skryptu ---
if __name__ == "__main__":
    extract_and_filter_invoices(INPUT_FILENAME, OUTPUT_FILENAME, CUTOFF_DATE_STR)