# Open Match Scanner (Kite Connect + FastAPI + HTML/JS)

A local web app for VS Code that scans a user-managed watchlist using Zerodha Kite Connect market quotes. It identifies stocks where today's open equals the previous session close and supports up to 50 NSE symbols.

## Requirements
- Python 3.10+ (3.11+ recommended)
- VS Code
- A Zerodha Kite Connect app with an API key, API secret, and registered redirect URL.

## Run on Windows (VS Code terminal)
1. Extract this ZIP and open the `open_match_scanner` folder in VS Code.
2. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again, or use `\.venv\Scripts\python.exe` directly.
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Create `.env` and add your real token:
   ```env
   KITE_API_KEY=your_api_key
   KITE_API_SECRET=your_api_secret
   KITE_ACCESS_TOKEN=
   KITE_REDIRECT_URL=http://127.0.0.1:8000/auth/kite/callback
   APP_TIMEZONE=Asia/Kolkata
   MATCH_TOLERANCE=0
MAX_DIFFERENCE=10
   ```
5. Start the app:
   ```powershell
   uvicorn app.main:app --reload
   ```
6. Open http://127.0.0.1:8000/auth/kite/login, complete Zerodha login, then open http://127.0.0.1:8000.

## Free deployment with a custom domain

This project includes [render.yaml](./render.yaml) for a free Render web service. Render supports FastAPI, free web instances, custom domains, and managed TLS. Free instances sleep after 15 minutes without traffic, so the scheduled 09:15 scan is not guaranteed while the service is asleep; use **Refresh now** when needed. The free service also has ephemeral storage, so watchlist edits made in the web UI can be lost after a restart.

1. Create a GitHub repository and upload this project. Do not upload `.env`; it is excluded by `.gitignore`.
2. In Render, choose **New → Blueprint**, select the repository, and deploy [render.yaml](./render.yaml).
3. Set `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_REDIRECT_URL` in Render. Open `https://divinecode369.in/auth/kite/login` each morning to create that day's access token.
4. Open the generated `onrender.com` URL and confirm `/api/status` works.
5. In the Render service, open **Settings → Custom Domains**, add your domain, then copy the DNS record Render gives you into your domain registrar. Render will issue HTTPS automatically.

Render documents the free-service sleep behavior and ephemeral filesystem limitations in its [FAQ](https://render.com/docs/faq), and the custom-domain setup in its [custom domains guide](https://render.com/docs/custom-domains).

## New filters and 8-session history
- **Stock filters**: set a minimum and maximum absolute difference between today's open and the previous session close, or show matching stocks only. Click Apply filters; Clear filters resets them.
- **Previous 8 trading sessions**: choose one watchlist symbol and click Load 8-day history to view date, open, close, high, low and volume using Kite historical candles.
- Historical data is loaded for one selected stock at a time. Current-day bars may not yet be available at 09:15, depending on Kite and exchange status.

## Configure the watchlist
- Use the web page's **Your watchlist** area to save up to 50 symbols, one per line or comma-separated.
- Or edit `data/watchlist.txt` while the app is stopped.
- Use Zerodha-recognized NSE trading symbols.

## Daily schedule
The backend schedules a scan at **09:15 Asia/Kolkata, Monday through Friday**. Keep your computer awake and the backend running at that time. The latest scan is held in memory until the app process stops. It does not currently skip exchange holidays automatically. You can also click **Refresh now** manually.

## Match rule
Only stocks with `abs(today_open - previous_close) <= MAX_DIFFERENCE` are shown. The configured `MAX_DIFFERENCE=10` means the app shows stocks within ₹10, while only `abs(today_open - previous_close) == 0` is marked as a match.

Default tolerance is ₹0.01. Set `MATCH_TOLERANCE=0` for exact numeric equality. A missing open or previous close is always marked **DATA N/A**, never a match.

## API quota and data timing
- Kite's quote endpoint supports up to 500 instruments per request, so this app scans the 50-symbol watchlist in one request.
- Kite access tokens expire at 6 AM the next day. Use `/auth/kite/login` after the daily session expires.
- Live quote availability depends on Kite's market status and account permissions.
- This is a local application. It does not bypass exchange licensing or provide a guarantee of exchange-direct real-time data.

## Security
- `.env` contains your API secret and should never be committed or shared.
- Keep API calls on the backend; the token is not exposed in frontend JavaScript.

## Project structure
```text
open_match_scanner/
  app/
    main.py       # FastAPI routes + 09:15 scheduler
    provider.py   # Kite Connect API adapter
    scanner.py    # Watchlist and match logic
    config.py
  static/
    index.html
    style.css
    app.js
  data/watchlist.txt
  .env.example
  requirements.txt
```
