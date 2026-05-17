import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

def get_drive_service():
    # Priorytet 1: OAuth2 token użytkownika (wymagany do wgrywania na prywatny Google Drive)
    token_json = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json:
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            data = json.loads(token_json)
            creds = Credentials(
                token=data.get("token"),
                refresh_token=data["refresh_token"],
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                scopes=data.get("scopes", SCOPES)
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            logger.info("Zautoryzowano z użyciem GOOGLE_TOKEN_JSON (OAuth2).")
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Błąd autoryzacji OAuth2 (GOOGLE_TOKEN_JSON): {e}")
            raise

    # Priorytet 2: Service Account (dla Shared Drive lub Domain-Wide Delegation)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        try:
            creds_data = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            logger.info("Zautoryzowano z użyciem zmiennej GOOGLE_CREDENTIALS_JSON (Service Account).")
        except Exception as e:
            logger.error(f"Błąd parsowania GOOGLE_CREDENTIALS_JSON: {e}")
            raise
    else:
        local_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google_credentials.json")
        if os.path.exists(local_creds_path):
            try:
                creds = service_account.Credentials.from_service_account_file(local_creds_path, scopes=SCOPES)
                logger.info(f"Zautoryzowano z użyciem pliku: {local_creds_path} (Service Account).")
            except Exception as e:
                logger.error(f"Błąd ładowania pliku poświadczeń {local_creds_path}: {e}")
                raise
        else:
            raise ValueError(
                "Brak poświadczeń Google Drive! "
                "Ustaw GOOGLE_TOKEN_JSON (OAuth2) lub GOOGLE_CREDENTIALS_JSON (Service Account)."
            )

    return build('drive', 'v3', credentials=creds)


def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    try:
        response = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = response.get('files', [])

        if files:
            folder_id = files[0]['id']
            logger.info(f"Znaleziono folder: '{folder_name}' (ID: {folder_id})")
            return folder_id

        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        folder = service.files().create(
            body=file_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        folder_id = folder.get('id')
        logger.info(f"Utworzono folder: '{folder_name}' (ID: {folder_id})")
        return folder_id
    except Exception as e:
        logger.error(f"Błąd podczas szukania/tworzenia folderu '{folder_name}': {e}")
        raise


def upload_file_to_drive(service, local_path, filename, folder_id, convert_to_sheet=False):
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    try:
        response = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = response.get('files', [])

        mime_type = 'text/csv' if local_path.endswith('.csv') else 'application/octet-stream'
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

        if files:
            file_id = files[0]['id']
            logger.info(f"Plik '{filename}' istnieje — aktualizacja (ID: {file_id})...")
            updated_file = service.files().update(
                fileId=file_id,
                body={'name': filename},
                media_body=media,
                fields='id',
                supportsAllDrives=True
            ).execute()
            logger.info(f"Zaktualizowano plik (ID: {updated_file.get('id')})")
            return updated_file.get('id')

        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        if convert_to_sheet and local_path.endswith('.csv'):
            file_metadata['mimeType'] = 'application/vnd.google-apps.spreadsheet'
            logger.info(f"Przesyłanie '{filename}' z konwersją do Google Sheets...")
        else:
            logger.info(f"Przesyłanie '{filename}' jako CSV...")

        created_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        logger.info(f"Przesłano nowy plik (ID: {created_file.get('id')})")
        return created_file.get('id')

    except Exception as e:
        logger.error(f"Błąd podczas przesyłania pliku '{filename}': {e}")
        raise


def upload_report_to_google_drive(local_csv_path, ym, report_folder_name=None):
    try:
        service = get_drive_service()

        root_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID") or get_or_create_folder(service, "AFA_Reports")

        folder_name = report_folder_name or ym
        month_folder_id = get_or_create_folder(service, folder_name, parent_id=root_folder_id)

        base_filename = os.path.basename(local_csv_path)
        name_without_ext = os.path.splitext(base_filename)[0]

        csv_file_id = upload_file_to_drive(
            service=service,
            local_path=local_csv_path,
            filename=base_filename,
            folder_id=month_folder_id,
            convert_to_sheet=False
        )

        sheet_file_id = upload_file_to_drive(
            service=service,
            local_path=local_csv_path,
            filename=name_without_ext,
            folder_id=month_folder_id,
            convert_to_sheet=True
        )

        logger.info(f"Sukces! Raporty zapisane w: AFA_Reports -> {ym}")
        return {
            "folder_id": month_folder_id,
            "csv_id": csv_file_id,
            "sheet_id": sheet_file_id
        }

    except Exception as e:
        logger.error(f"Błąd podczas przesyłania na Google Drive: {e}")
        raise
