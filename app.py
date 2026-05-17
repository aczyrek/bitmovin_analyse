import os
import logging
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# Importujemy funkcję uruchamiającą raport z naszego pliku bitmovin_report
from bitmovin_report import run_report

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AFA Bitmovin Report Automator",
    description="Automatyczny eksport raportów transkodowania Bitmovin bezpośrednio do Google Drive / Sheets.",
    version="1.0.0"
)

# Włączenie CORS, aby można było bezproblemowo odpytywać API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================================================
# SPRAWDZANIE STATUSU ŚRODOWISKA
# =======================================================
def get_env_status():
    bitmovin_key = os.getenv("BITMOVIN_API_KEY")
    bitmovin_org = os.getenv("BITMOVIN_ORG_ID")
    google_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("google_credentials.json")
    trigger_secret = os.getenv("TRIGGER_SECRET")
    
    return {
        "bitmovin_api": "Skonfigurowano ✅" if (bitmovin_key and bitmovin_org) else "Brak ❌ (Ustaw BITMOVIN_API_KEY oraz BITMOVIN_ORG_ID)",
        "bitmovin_configured": bool(bitmovin_key and bitmovin_org),
        "google_drive": "Skonfigurowano ✅" if google_creds else "Brak ❌ (Ustaw GOOGLE_CREDENTIALS_JSON lub utwórz plik google_credentials.json)",
        "google_configured": bool(google_creds),
        "security_token": "Aktywne (Wymaga tokenu) 🔐" if trigger_secret else "Wyłączone (Brak tokenu) 🔓",
        "security_configured": bool(trigger_secret)
    }

# =======================================================
# STRONA GŁÓWNA - PREMIUM UI (HTML/CSS)
# =======================================================
@app.get("/", response_class=HTMLResponse)
async def read_root():
    status = get_env_status()
    
    # Tworzymy stany klas CSS dla wskaźników
    bitmovin_class = "status-ok" if status["bitmovin_configured"] else "status-error"
    google_class = "status-ok" if status["google_configured"] else "status-error"
    security_class = "status-warn" if status["security_configured"] else "status-off"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AFA Bitmovin Automator</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-gradient: linear-gradient(135deg, #0b0f19 0%, #111827 50%, #1e1b4b 100%);
                --card-bg: rgba(17, 24, 39, 0.7);
                --card-border: rgba(255, 255, 255, 0.08);
                --text-main: #f3f4f6;
                --text-muted: #9ca3af;
                --accent-primary: #6366f1;
                --accent-secondary: #a855f7;
                --accent-glow: rgba(99, 102, 241, 0.15);
                --success: #10b981;
                --error: #ef4444;
                --warning: #f59e0b;
            }}

            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
                font-family: 'Outfit', sans-serif;
            }}

            body {{
                background: var(--bg-gradient);
                color: var(--text-main);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 2rem 1rem;
                overflow-x: hidden;
            }}

            .container {{
                max-width: 800px;
                width: 100%;
                z-index: 10;
            }}

            header {{
                text-align: center;
                margin-bottom: 2.5rem;
                position: relative;
            }}

            header h1 {{
                font-size: 2.8rem;
                font-weight: 700;
                background: linear-gradient(to right, #818cf8, #c084fc);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
                letter-spacing: -0.02em;
            }}

            header p {{
                color: var(--text-muted);
                font-size: 1.1rem;
                font-weight: 300;
            }}

            .card {{
                background: var(--card-bg);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border: 1px solid var(--card-border);
                border-radius: 24px;
                padding: 2.5rem;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3), 
                            inset 0 1px 0 rgba(255, 255, 255, 0.05);
                margin-bottom: 2rem;
                position: relative;
                overflow: hidden;
            }}

            .card::before {{
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle, var(--accent-glow) 0%, transparent 60%);
                pointer-events: none;
                z-index: 0;
            }}

            .card-content {{
                position: relative;
                z-index: 1;
            }}

            h2 {{
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 1.5rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}

            .status-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 1.25rem;
                margin-bottom: 2.5rem;
            }}

            .status-item {{
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 16px;
                padding: 1.25rem;
                transition: transform 0.3s ease, border-color 0.3s ease;
            }}

            .status-item:hover {{
                transform: translateY(-2px);
                border-color: rgba(99, 102, 241, 0.2);
            }}

            .status-label {{
                font-size: 0.85rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: 0.5rem;
            }}

            .status-value {{
                font-size: 1.05rem;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}

            .status-indicator {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                display: inline-block;
            }}

            .status-ok .status-indicator {{
                background-color: var(--success);
                box-shadow: 0 0 8px var(--success);
            }}

            .status-error .status-indicator {{
                background-color: var(--error);
                box-shadow: 0 0 8px var(--error);
            }}

            .status-warn .status-indicator {{
                background-color: var(--warning);
                box-shadow: 0 0 8px var(--warning);
            }}

            .status-off .status-indicator {{
                background-color: var(--text-muted);
            }}

            .control-panel {{
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                padding-top: 2rem;
            }}

            .form-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1.25rem;
                margin-bottom: 1.5rem;
            }}

            @media (max-width: 600px) {{
                .form-grid {{
                    grid-template-columns: 1fr;
                }}
            }}

            .form-group {{
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
            }}

            label {{
                font-size: 0.9rem;
                color: var(--text-muted);
                font-weight: 500;
            }}

            input, select {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 0.75rem 1rem;
                color: var(--text-main);
                font-size: 1rem;
                transition: border-color 0.3s ease, box-shadow 0.3s ease;
                outline: none;
            }}

            input:focus, select:focus {{
                border-color: var(--accent-primary);
                box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25);
            }}

            .btn {{
                background: linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
                border: none;
                border-radius: 14px;
                padding: 1rem;
                color: white;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s ease, box-shadow 0.3s ease, opacity 0.2s ease;
                width: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 0.75rem;
                box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
            }}

            .btn:hover {{
                transform: translateY(-1px);
                box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45);
            }}

            .btn:active {{
                transform: translateY(1px);
            }}

            .btn:disabled {{
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }}

            .result-panel {{
                margin-top: 2rem;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 16px;
                padding: 1.5rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
                display: none;
                max-height: 400px;
                overflow-y: auto;
            }}

            .result-title {{
                font-size: 0.95rem;
                font-weight: 600;
                color: var(--text-main);
                margin-bottom: 0.75rem;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}

            pre {{
                font-family: 'Courier New', Courier, monospace;
                font-size: 0.85rem;
                white-space: pre-wrap;
                word-break: break-all;
                color: #a7f3d0;
            }}

            .spinner {{
                width: 20px;
                height: 20px;
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top-color: white;
                animation: spin 1s ease-in-out infinite;
                display: none;
            }}

            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}

            footer {{
                text-align: center;
                color: var(--text-muted);
                font-size: 0.85rem;
                margin-top: 1rem;
            }}

            footer a {{
                color: var(--accent-primary);
                text-decoration: none;
            }}

            footer a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>AFA Reports</h1>
                <p>Bitmovin Transcoding Report Automator ☁️</p>
            </header>

            <div class="card">
                <div class="card-content">
                    <h2>🔍 Status Połączeń</h2>
                    <div class="status-grid">
                        <div class="status-item {bitmovin_class}">
                            <div class="status-label">Bitmovin API</div>
                            <div class="status-value">
                                <span class="status-indicator"></span>
                                {status["bitmovin_api"]}
                            </div>
                        </div>

                        <div class="status-item {google_class}">
                            <div class="status-label">Google Drive (Cloud)</div>
                            <div class="status-value">
                                <span class="status-indicator"></span>
                                {status["google_drive"]}
                            </div>
                        </div>

                        <div class="status-item {security_class}">
                            <div class="status-label">Token Bezpieczeństwa</div>
                            <div class="status-value">
                                <span class="status-indicator"></span>
                                {status["security_token"]}
                            </div>
                        </div>
                    </div>

                    <div class="control-panel">
                        <h2>⚙️ Wygeneruj Raport</h2>
                        <form id="reportForm">
                            <div class="form-grid">
                                <div class="form-group">
                                    <label for="year">Rok</label>
                                    <select id="year" name="year">
                                        <option value="">Wybierz rok (opcjonalnie)</option>
                                        <option value="2026" selected>2026</option>
                                        <option value="2025">2025</option>
                                        <option value="2024">2024</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label for="month">Miesiąc</label>
                                    <select id="month" name="month">
                                        <option value="">Wybierz miesiąc (opcjonalnie)</option>
                                        <option value="1">Styczeń (01)</option>
                                        <option value="2">Luty (02)</option>
                                        <option value="3">Marzec (03)</option>
                                        <option value="4">Kwiecień (04)</option>
                                        <option value="5" selected>Maj (05)</option>
                                        <option value="6">Czerwiec (06)</option>
                                        <option value="7">Lipiec (07)</option>
                                        <option value="8">Sierpień (08)</option>
                                        <option value="9">Wrzesień (09)</option>
                                        <option value="10">Październik (10)</option>
                                        <option value="11">Listopad (11)</option>
                                        <option value="12">Grudzień (12)</option>
                                    </select>
                                </div>
                            </div>
                            
                            <div class="form-group" style="margin-bottom: 1.5rem; display: flex; flex-direction: row; align-items: center; gap: 0.5rem;">
                                <input type="checkbox" id="defaultRange" name="defaultRange" style="width: auto; cursor: pointer;">
                                <label for="defaultRange" style="cursor: pointer;">Użyj domyślnego zakresu (ostatnie 60 dni)</label>
                            </div>

                            <div class="form-group" id="tokenGroup" style="margin-bottom: 1.5rem; display: {'flex' if status['security_configured'] else 'none'}; flex-direction: column;">
                                <label for="secret">Token Autoryzacyjny (TRIGGER_SECRET)</label>
                                <input type="password" id="secret" placeholder="Wpisz token bezpieczeństwa...">
                            </div>

                            <button type="submit" class="btn" id="submitBtn">
                                <span class="spinner" id="btnSpinner"></span>
                                <span id="btnText">Uruchom i wyślij do Google Drive ⚡</span>
                            </button>
                        </form>

                        <div class="result-panel" id="resultPanel">
                            <div class="result-title">
                                <span>LOGI I WYNIK OPERACJI</span>
                                <span id="resultStatus" style="font-weight: bold;">W toku...</span>
                            </div>
                            <pre id="resultOutput"></pre>
                        </div>
                    </div>
                </div>
            </div>

            <footer>
                AFA Reports Team &copy; 2026. Powered by <a href="https://render.com" target="_blank">Render.com</a>, Bitmovin & Google Cloud.
            </footer>
        </div>

        <script>
            const form = document.getElementById('reportForm');
            const submitBtn = document.getElementById('submitBtn');
            const btnSpinner = document.getElementById('btnSpinner');
            const btnText = document.getElementById('btnText');
            const resultPanel = document.getElementById('resultPanel');
            const resultOutput = document.getElementById('resultOutput');
            const resultStatus = document.getElementById('resultStatus');
            const defaultCheckbox = document.getElementById('defaultRange');
            const yearSelect = document.getElementById('year');
            const monthSelect = document.getElementById('month');

            // Automatyczne włączanie/wyłączanie pól w zależności od checkboxa
            defaultCheckbox.addEventListener('change', function() {{
                const isDisabled = this.checked;
                yearSelect.disabled = isDisabled;
                monthSelect.disabled = isDisabled;
                if (isDisabled) {{
                    yearSelect.style.opacity = 0.5;
                    monthSelect.style.opacity = 0.5;
                }} else {{
                    yearSelect.style.opacity = 1;
                    monthSelect.style.opacity = 1;
                }}
            }});

            form.addEventListener('submit', async (e) => {{
                e.preventDefault();
                
                // Zablokuj przycisk i pokaż spinner
                submitBtn.disabled = true;
                btnSpinner.style.display = 'block';
                btnText.textContent = 'Generowanie i przesyłanie...';
                resultPanel.style.display = 'block';
                resultOutput.textContent = 'Trwa nawiązywanie połączenia z serwerem i pobieranie danych z Bitmovin API. Może to potrwać kilkanaście sekund...';
                resultStatus.textContent = 'W TOKU ⏳';
                resultStatus.style.color = 'var(--warning)';

                // Przygotuj parametry
                let url = '/run?';
                
                if (!defaultCheckbox.checked) {{
                    const year = yearSelect.value;
                    const month = monthSelect.value;
                    if (year) url += `year=${{year}}&`;
                    if (month) url += `month=${{month}}&`;
                }}
                
                const secret = document.getElementById('secret').value;
                if (secret) {{
                    url += `secret=${{encodeURIComponent(secret)}}`;
                }}

                try {{
                    const response = await fetch(url, {{
                        method: 'POST'
                    }});
                    
                    const data = await response.json();
                    
                    if (response.ok) {{
                        resultStatus.textContent = 'SUKCES 🎉';
                        resultStatus.style.color = 'var(--success)';
                        resultOutput.textContent = JSON.stringify(data, null, 4);
                    }} else {{
                        resultStatus.textContent = 'BŁĄD ❌';
                        resultStatus.style.color = 'var(--error)';
                        resultOutput.textContent = `Błąd serwera (Status ${{response.status}}):\\n${{JSON.stringify(data, null, 4)}}`;
                    }}
                }} catch (error) {{
                    resultStatus.textContent = 'BŁĄD SIECI ❌';
                    resultStatus.style.color = 'var(--error)';
                    resultOutput.textContent = `Wystąpił błąd sieciowy podczas komunikacji z serwerem: \\n${{error.message}}\\n\\nUpewnij się, że serwer na Render.com jest aktywny.`;
                }} finally {{
                    submitBtn.disabled = false;
                    btnSpinner.style.display = 'none';
                    btnText.textContent = 'Uruchom i wyślij do Google Drive ⚡';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

# =======================================================
# ENDPOINT STRZYKAWKA / WYZWALACZ (RUN)
# =======================================================
@app.post("/run")
async def run_report_endpoint(
    year: Optional[int] = Query(None, description="Docelowy rok raportu (np. 2026)"),
    month: Optional[int] = Query(None, description="Docelowy miesiąc raportu (1-12)"),
    secret: Optional[str] = Query(None, description="Opcjonalny token autoryzacyjny")
):
    """
    Wyzwala pobieranie danych z Bitmovin i ich przesyłanie do Google Drive / Google Sheets.
    Można go wywołać przez POST. Chroniony przez opcjonalną zmienną środowiskową TRIGGER_SECRET.
    """
    # 1. Zabezpieczenie tokenem (jeśli zdefiniowano w środowisku)
    expected_secret = os.getenv("TRIGGER_SECRET")
    if expected_secret and secret != expected_secret:
        raise HTTPException(
            status_code=401,
            detail="Nieautoryzowany dostęp. Podany token bezpieczeństwa jest błędny lub go brakuje."
        )
        
    try:
        logger.info(f"Ręczne wyzwolenie raportu. Parametry: year={year}, month={month}")
        
        # Wywołujemy funkcję generującą raporty i przesyłającą na Google Drive
        results = run_report(year=year, month=month)
        
        if not results:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Raport zakończył się sukcesem, ale nie wykryto żadnych zakończonych zadań w Bitmovin w wybranym przedziale czasowym.",
                    "reports": []
                }
            )
            
        return {
            "status": "success",
            "message": "Raport wygenerowany i zsynchronizowany pomyślnie z Google Drive!",
            "reports": results
        }
        
    except ValueError as ve:
        logger.error(f"Błąd konfiguracji lub walidacji: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Błąd krytyczny podczas działania endpointu /run: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Wystąpił błąd krytyczny na serwerze: {str(e)}"
        )

# =======================================================
# START APLIKACJI
# =======================================================
if __name__ == "__main__":
    import uvicorn
    # Render.com przekazuje port w zmiennej środowiskowej PORT
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
