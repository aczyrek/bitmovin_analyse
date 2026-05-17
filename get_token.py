"""
Jednorazowy skrypt do uzyskania tokena OAuth2 dla Google Drive.

Jak użyć:
1. W Google Cloud Console (console.cloud.google.com):
   - APIs & Services → Credentials → "+ Create Credentials" → OAuth 2.0 Client ID
   - Application type: Desktop app
   - Pobierz JSON i zapisz jako: oauth_client_secrets.json (w tym samym folderze)

2. Uruchom ten skrypt:
   python get_token.py

3. Zaloguj się w przeglądarce i autoryzuj dostęp.

4. Skopiuj wydrukowany JSON i ustaw jako zmienną środowiskową GOOGLE_TOKEN_JSON
   (lokalnie w .env, na Render.com w Environment Variables).
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']

flow = InstalledAppFlow.from_client_secrets_file('oauth_client_secrets.json', SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': list(creds.scopes)
}

print("\n=== SKOPIUJ PONIŻSZY JSON JAKO GOOGLE_TOKEN_JSON ===\n")
print(json.dumps(token_data))
print("\n====================================================\n")
