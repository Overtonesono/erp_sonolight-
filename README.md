# ERP Sonolight (MVP skeleton)

**Windows-only** desktop ERP/CRM for DJ & lighting freelance activity.
Tech stack: Python 3.10+, PySide6 UI, JSON storage (no DB).

## Quick start
1. Create and activate a venv (Windows PowerShell):
   ```powershell
   py -3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Run the app:
   ```powershell
   python app.py
   ```

> This is a minimal MVP scaffold: UI opens with tabs, data lives in `data/` as JSON.
> Next iterations will add full CRUD, quotes workflow, invoices, PDFs, and Google Calendar.

## Data files
Stored under `data/` as JSON lists (edit manually for now):
- `clients.json`, `products.json`, `services.json`, `quotes.json`, `invoices.json`, `events.json`, `accounting_entries.json`, `settings.json`

## Google Calendar (future)
OAuth & API calls are stubbed in `integrations/google/`. We will implement them next.
For now, plan events locally and export ICS in `exports/` (to be added).

## Push to GitHub
```powershell
git init
git add .
git commit -m "chore: bootstrap MVP skeleton"
git branch -M main
git remote add origin https://github.com/Overtonesono/erp_sonolight.git
git push -u origin main
```
