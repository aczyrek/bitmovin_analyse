import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

def get_drive_service():
    """Autoryzuje i buduje usługę Google Drive API."""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    if creds_json:
        try:
            creds_data = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            logger.info("Zautoryzowano pomyślnie z użyciem zmiennej GOOGLE_CREDENTIALS_JSON.")
        except Exception as e:
            logger.error(f"Błąd parsowania GOOGLE_CREDENTIALS_JSON: {e}")
            raise
    else:
        # Alternatywne ładowanie z lokalnego pliku (przydatne do testów lokalnych)
        local_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google_credentials.json")
        if os.path.exists(local_creds_path):
            try:
                creds = service_account.Credentials.from_service_account_file(local_creds_path, scopes=SCOPES)
                logger.info(f"Zautoryzowano pomyślnie z użyciem pliku: {local_creds_path}")
            except Exception as e:
                logger.error(f"Błąd ładowania pliku poświadczeń {local_creds_path}: {e}")
                raise
        else:
            raise ValueError(
                "Brak poświadczeń Google Sheets/Drive! "
                "Ustaw zmienną środowiskową GOOGLE_CREDENTIALS_JSON (z zawartością pliku JSON) "
                "lub umieść plik google_credentials.json w głównym folderze projektu."
            )
            
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name, parent_id=None):
    """Szuka folderu po nazwie (i ewentualnym parent ID). Jeśli nie istnieje, tworzy go."""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    try:
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        
        if files:
            folder_id = files[0]['id']
            logger.info(f"Znaleziono istniejący folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
                
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            logger.info(f"Utworzono nowy folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
    except Exception as e:
        logger.error(f"Błąd podczas szukania/tworzenia folderu '{folder_name}': {e}")
        raise

def upload_file_to_drive(service, local_path, filename, folder_id, convert_to_sheet=False):
    """
    Przesyła plik lokalny do wskazanego folderu w Google Drive.
    Jeśli plik o tej samej nazwie już istnieje, aktualizuje jego zawartość (nadpisuje) zamiast duplikować.
    Opcjonalnie konwertuje plik CSV bezpośrednio na Google Sheet.
    """
    # 1. Sprawdź czy plik o takiej nazwie już istnieje w tym folderze
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    try:
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        
        # Określenie typów MIME
        mime_type = 'text/csv' if local_path.endswith('.csv') else 'application/octet-stream'
        
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        
        if files:
            # Aktualizacja (nadpisanie)
            file_id = files[0]['id']
            logger.info(f"Plik '{filename}' już istnieje. Aktualizacja (ID: {file_id})...")
            
            # W przypadku aktualizacji przesyłamy tylko zawartość (media_body) i ewentualnie nazwę
            updated_file = service.files().update(
                fileId=file_id,
                body={'name': filename},
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"Pomyślnie zaktualizowano plik na Google Drive (ID: {updated_file.get('id')})")
            return updated_file.get('id')
        else:
            # Tworzenie nowego pliku
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            # Jeśli convert_to_sheet=True, Google Drive automatycznie skonwertuje CSV na Arkusz Google
            if convert_to_sheet and local_path.endswith('.csv'):
                file_metadata['mimeType'] = 'application/vnd.google-apps.spreadsheet'
                logger.info(f"Przesyłanie nowego pliku '{filename}' z automatyczną konwersją do Google Sheets...")
            else:
                logger.info(f"Przesyłanie nowego pliku '{filename}' jako surowy plik...")
                
            created_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"Pomyślnie przesłano nowy plik na Google Drive (ID: {created_file.get('id')})")
            return created_file.get('id')
            
    except Exception as e:
        logger.error(f"Błąd podczas przesyłania pliku '{filename}' na Google Drive: {e}")
        raise

def upload_report_to_google_drive(local_csv_path, ym):
    """
    Główna funkcja koordynująca:
    1. Łączy się z Google Drive.
    2. Szuka/tworzy folder główny 'AFA_Reports'.
    3. Szuka/tworzy podfolder dla danego miesiąca (np. '2026-05') wewnątrz 'AFA_Reports'.
    4. Przesyła plik CSV.
    5. Przesyła ten sam plik przekonwertowany na Google Sheet (dzięki temu użytkownik ma wygodny podgląd tabelaryczny).
    """
    try:
        service = get_drive_service()
        
        # 1. Pobierz lub utwórz folder główny 'AFA_Reports'
        root_folder_id = get_or_create_folder(service, "AFA_Reports")
        
        # 2. Pobierz lub utwórz podfolder dla danego miesiąca
        month_folder_name = ym  # np. "2026-05"
        month_folder_id = get_or_create_folder(service, month_folder_name, parent_id=root_folder_id)
        
        # Nazwa bazowa pliku
        base_filename = os.path.basename(local_csv_path)  # np. bitmovin_transcoding_report_2026-05.csv
        name_without_ext = os.path.splitext(base_filename)[0]
        
        # 3. Prześlij surowy plik CSV
        csv_file_id = upload_file_to_drive(
            service=service,
            local_path=local_csv_path,
            filename=base_filename,
            folder_id=month_folder_id,
            convert_to_sheet=False
        )
        
        # 4. Prześlij jako Google Sheet (dla łatwej edycji i podglądu online)
        sheet_filename = f"{name_without_ext}"  # Arkusz nie musi mieć rozszerzenia .csv w nazwie
        sheet_file_id = upload_file_to_drive(
            service=service,
            local_path=local_csv_path,
            filename=sheet_filename,
            folder_id=month_folder_id,
            convert_to_sheet=True
        )
        
        logger.info(f"🎉 Sukces! Zapisano raporty w chmurze (Google Drive) w folderze: AFA_Reports -> {month_folder_name}")
        return {
            "folder_id": month_folder_id,
            "csv_id": csv_file_id,
            "sheet_id": sheet_file_id
        }
        
    except Exception as e:
        logger.error(f"Błąd podczas pełnego przepływu przesyłania na Google Drive: {e}")
        raise
