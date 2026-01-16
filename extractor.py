import pandas as pd
import os
from datetime import datetime
import calendar

# --- Konfiguracja ---
INPUT_FILENAME = 'new_fi_invoices_data.csv'
COLUMNS_TO_EXTRACT = ['id', 'invoice_date', 'taxes']

# Konfiguracja miesiąca do ekstrakcji
TARGET_YEAR = 2025
TARGET_MONTH = 7

# Generowanie nazwy pliku wyjściowego na podstawie roku i miesiąca
OUTPUT_FILENAME = f'invoices_id_date_{TARGET_YEAR}_{TARGET_MONTH:02d}.csv'

# --- Główna funkcja ---
def extract_and_filter_invoices(input_file: str, output_file: str, year: int, month: int):
    """
    Wczytuje plik CSV, konwertuje daty i filtruje dane dla podanego miesiąca
    (od 1. dnia 00:00:00 do ostatniego dnia 23:59:59).
    """
    try:
        df = pd.read_csv(input_file)
        
        # 1. Obliczenie zakresu dat dla podanego miesiąca
        # Początek miesiąca
        start_date = datetime(year, month, 1, 0, 0, 0)
        # Ostatni dzień miesiąca
        _, last_day = calendar.monthrange(year, month)
        end_date = datetime(year, month, last_day, 23, 59, 59)
        
        # Konwersja na timestamp (zakładając, że dane w CSV są w UTC/sekundach, jak wcześniej)
        start_timestamp = start_date.timestamp()
        end_timestamp = end_date.timestamp()

        # 2. Utworzenie nowej, czytelnej kolumny daty
        # 'unit='s' informuje Pandas, że timestamp jest w sekundach
        df['invoice_date'] = pd.to_datetime(df['date'], unit='s').dt.strftime('%Y-%m-%d')

        # 3. Filtrowanie danych: tylko wiersze w zakresie <start_timestamp, end_timestamp>
        df_filtered = df[(df['date'] >= start_timestamp) & (df['date'] <= end_timestamp)].copy()
        
        # 4. Wybór kolumn do zapisu
        df_extracted = df_filtered[COLUMNS_TO_EXTRACT]

        # 5. Zapisanie wyników do nowego pliku CSV
        df_extracted.to_csv(output_file, index=False)

        # 6. Potwierdzenie operacji
        print("-" * 50)
        print("✅ Operacja ekstrakcji i filtrowania zakończona sukcesem!")
        print(f"Zakres dat: {start_date} - {end_date}")
        print(f"Zapisano dane ({len(df_extracted)} wierszy) do pliku: {output_file}")
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
    extract_and_filter_invoices(INPUT_FILENAME, OUTPUT_FILENAME, TARGET_YEAR, TARGET_MONTH)