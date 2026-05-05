# AI Dashboard — Offline Intranet Deployment Guide

> **Target OS:** Windows Server 2019  
> **Stack:** React + Tailwind (IIS) → FastAPI + LangChain → Ollama (Llama 3) → ChromaDB + SQLite

---

## Project Structure

```
D:\Model-AI\
├── backend\
│   ├── app\
│   │   ├── __init__.py
│   │   ├── config.py            # All settings (paths, model names, CORS)
│   │   ├── database.py          # SQLite chat history CRUD
│   │   ├── document_loader.py   # PDF / DOCX / PPTX loaders
│   │   ├── llm.py               # Ollama LLM + embeddings + ChromaDB factory
│   │   ├── main.py              # FastAPI app with all routes
│   │   ├── models.py            # Pydantic request/response schemas
│   │   ├── prompts.py           # Prompt templates for both agents
│   │   └── agents\
│   │       ├── __init__.py
│   │       ├── chat_agent.py    # General conversational chain
│   │       └── exam_agent.py    # RAG-based exam paper generator
│   ├── requirements.txt
│   ├── run.py                   # Uvicorn entry-point
│   └── win_service.py           # Windows Service wrapper
│
├── frontend\
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src\
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js               # All fetch helpers
│       ├── index.css
│       └── components\
│           ├── Sidebar.jsx      # Agent selector + conversation history
│           ├── ChatPanel.jsx    # General AI Chat interface
│           ├── ExamPanel.jsx    # Exam generator (upload + instructions)
│           └── MessageBubble.jsx
│
└── deployment\
    ├── setup-all.ps1            # Master setup (runs everything)
    ├── setup-https.ps1          # Self-signed cert + IIS HTTPS binding
    └── web.config               # IIS rewrite rules for SPA + API proxy
```

---

## Phase 1 — Prerequisites (On a Machine with Internet)

You need to download all dependencies **once** on an internet-connected machine, then transfer them to the air-gapped server.

### 1.1  Python Packages

```powershell
# On internet machine (same Python version as server)
mkdir D:\offline-packages\python
cd D:\Model-AI\backend
pip download -r requirements.txt -d D:\offline-packages\python
pip download pywin32 -d D:\offline-packages\python
```

### 1.2  Node.js / npm Packages

```powershell
cd D:\Model-AI\frontend
# Install normally first so you get a lock file
npm install
# Pack the cache
npm cache ls   # verify
# Copy the entire node_modules or use npm-pack-all
# Simplest: just copy node_modules to a USB drive
xcopy /E /I node_modules D:\offline-packages\node_modules
```

### 1.3  Ollama + Llama 3 Model

1. Download the Ollama Windows installer from https://ollama.com/download/windows
2. Download the Llama 3 GGUF model:
   ```powershell
   ollama pull llama3
   ```
3. The model files are stored in `%USERPROFILE%\.ollama\models\`.
   Copy the entire `.ollama` folder to the server.

### 1.4  Transfer to Server

Copy the following to the Windows Server via USB/network share:
- `D:\Model-AI\` (this project)
- `D:\offline-packages\` (Python wheels + node_modules)
- Ollama installer + `.ollama` models folder

---

## Phase 2 — Server Setup (Offline)

### 2.1  Install Ollama

1. Run the Ollama installer.
2. Copy the `.ollama` models folder to `C:\Users\<ServiceAccount>\.ollama\`.
3. Start Ollama:
   ```powershell
   ollama serve
   ```
4. Verify:
   ```powershell
   ollama list        # Should show llama3
   curl http://localhost:11434/api/tags   # Should return model list
   ```

### 2.2  Install Python Backend

```powershell
# Install Python 3.11+ if not present (offline installer)
cd D:\Model-AI\backend

# Create venv
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install from offline wheels
pip install --no-index --find-links=D:\offline-packages\python -r requirements.txt
pip install --no-index --find-links=D:\offline-packages\python pywin32

# Quick smoke test
python run.py
# Visit http://localhost:8000/docs — you should see the Swagger UI
# Ctrl+C to stop
```

### 2.3  Install as Windows Service

```powershell
cd D:\Model-AI\backend
.\venv\Scripts\Activate.ps1

# Install and start the service
python win_service.py install
python win_service.py start

# Verify
Get-Service AIDashboardBackend
# Status should be "Running"
```

To manage later:
```powershell
python win_service.py stop
python win_service.py remove
```

### 2.4  Build Frontend

```powershell
cd D:\Model-AI\frontend

# Copy pre-downloaded node_modules
xcopy /E /I D:\offline-packages\node_modules .\node_modules

# Build production bundle
npm run build
# Output → D:\Model-AI\frontend\build\
```

---

## Phase 3 — IIS Setup

### 3.1  Install IIS Features

```powershell
# Run as Administrator
Install-WindowsFeature -Name Web-Server,Web-Default-Doc,Web-Static-Content,`
  Web-Http-Redirect,Web-Filtering,Web-Mgmt-Console -IncludeManagementTools

# Install URL Rewrite Module (download .msi from Microsoft, transfer offline)
# https://www.iis.net/downloads/microsoft/url-rewrite
# Also install Application Request Routing (ARR) for the API proxy:
# https://www.iis.net/downloads/microsoft/application-request-routing
```

### 3.2  Enable ARR Proxy

```powershell
# After installing ARR, enable proxy mode:
Set-WebConfigurationProperty -Filter "system.webServer/proxy" `
  -PSPath "MACHINE/WEBROOT/APPHOST" -Name "enabled" -Value "True"
```

### 3.3  Create IIS Site

```powershell
$sitePath = "C:\inetpub\AIDashboard"
New-Item -ItemType Directory -Path $sitePath -Force

# Copy React build output
Copy-Item -Recurse "D:\Model-AI\frontend\build\*" $sitePath -Force
Copy-Item "D:\Model-AI\deployment\web.config" $sitePath -Force

# Create IIS site
Import-Module WebAdministration
New-Website -Name "AIDashboard" -PhysicalPath $sitePath -Port 80 -Force

# Stop Default Web Site to free port 80
Stop-Website -Name "Default Web Site"

# Start our site
Start-Website -Name "AIDashboard"
```

Test: Open `http://localhost` in a browser  — you should see the dashboard.

---

## Phase 4 — HTTPS with Self-Signed Certificate

### 4.1  Automated Script

```powershell
# Run as Administrator
Set-ExecutionPolicy Bypass -Scope Process
cd D:\Model-AI\deployment
.\setup-https.ps1 -SiteName "AIDashboard" -DnsName "YOUR-SERVER-HOSTNAME"
```

This script:
1. Creates a self-signed certificate valid for 5 years (RSA 2048 / SHA-256).
2. Adds it to the machine's Trusted Root CA store.
3. Binds it to port 443 on the IIS site.
4. Adds an HTTP → HTTPS redirect rule.

### 4.2  Trust the Certificate on Client Machines

Every intranet PC that accesses the dashboard needs the cert in its Trusted Root store:

```powershell
# On the server — export the cert
$thumb = (Get-ChildItem Cert:\LocalMachine\My | Where-Object {
    $_.FriendlyName -eq "AI Dashboard Intranet"
}).Thumbprint

Export-Certificate -Cert "Cert:\LocalMachine\My\$thumb" -FilePath "C:\certs\ai-dashboard.cer"
```

Distribute `ai-dashboard.cer` to client machines. On each client (admin PowerShell):

```powershell
Import-Certificate -FilePath "\\server\share\ai-dashboard.cer" `
    -CertStoreLocation "Cert:\LocalMachine\Root"
```

Or deploy via Group Policy (Computer Config → Windows Settings → Security Settings → Public Key Policies → Trusted Root CAs).

### 4.3  Verify

```
https://YOUR-SERVER-HOSTNAME
```
You should see the AI Dashboard with a valid (green) lock icon on machines that trust the cert.

---

## Phase 5 — Firewall Rules

```powershell
# Allow HTTPS inbound
New-NetFirewallRule -DisplayName "AI Dashboard HTTPS" `
    -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow

# Block external access to the backend API (only IIS proxy should reach it)
New-NetFirewallRule -DisplayName "Block External API" `
    -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Block `
    -RemoteAddress "0.0.0.0/0"
New-NetFirewallRule -DisplayName "Allow Localhost API" `
    -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow `
    -RemoteAddress "127.0.0.1"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ollama` not found | Ensure Ollama is in PATH or run from install dir. |
| LLM timeout | Llama 3 needs ~8 GB RAM; check server resources. |
| IIS 502 error on `/api/*` | Ensure ARR proxy is enabled and backend is running on port 8000. |
| HTTPS cert warning | Import the self-signed cert into client's Trusted Root CA store. |
| Upload fails | Check `UPLOAD_DIR` permissions; the IIS app pool identity needs write access. |
| ChromaDB errors | Ensure `CHROMA_DIR` exists and is writable. |

---

## Quick Reference — All Services

| Component | How to Run | Port |
|-----------|-----------|------|
| Ollama | `ollama serve` | 11434 |
| FastAPI Backend | Windows Service `AIDashboardBackend` | 8000 |
| React Frontend | IIS Site `AIDashboard` | 443 (HTTPS) |
