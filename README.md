# IAT Insurance — AI Email Automation Platform

> AI-powered email triage and case management for IAT Insurance.

---

## Overview

This platform automatically processes insurance emails arriving at the client Outlook mailbox:

1. **Monitors** the mailbox via Microsoft Graph API webhook (certificate-based auth)
2. **Parses** PDF, DOCX, scanned, and handwritten attachments
3. **OCR** via Azure Document Intelligence (ACI) for scanned documents
4. **Crawls URLs** found in documents using Playwright + BeautifulSoup
5. **Masks all PII** using Microsoft Presidio (AES-256 encrypted in Cosmos DB)
6. **Classifies** emails into 8 categories using Azure OpenAI GPT-4o-mini
7. **Creates cases** with chain detection (In-Reply-To / References / subject fallback)
8. **Notifies** downstream teams via Graph API email
9. **Read-only UI** secured with Azure AD MSAL for operations staff

---

## Project Structure

```
IAT-POC/
├── backend/                  # FastAPI + Python
│   ├── main.py               # App entry, lifespan events
│   ├── config.py             # Pydantic-settings
│   ├── api/                  # FastAPI routers
│   │   ├── webhook.py        # POST /webhook/email
│   │   ├── cases.py          # GET /api/cases/*
│   │   └── health.py         # GET /health, /api/stats
│   ├── services/             # Business logic
│   │   ├── keyvault.py       # Azure Key Vault
│   │   ├── cosmos_db.py      # All DB operations
│   │   ├── blob_storage.py   # Azure Blob Storage
│   │   ├── graph_client.py   # Microsoft Graph API
│   │   ├── document_parser.py# PDF / DOCX / image
│   │   ├── ocr_service.py    # Azure Doc Intelligence
│   │   ├── web_crawler.py    # Playwright + BS4
│   │   ├── pii_masker.py     # Presidio + AES-256
│   │   ├── classifier.py     # GPT-4o-mini
│   │   ├── pipeline.py       # 9-step orchestrator
│   │   ├── case_manager.py   # Chain detection
│   │   └── notifier.py       # Downstream email
│   ├── middleware/
│   │   └── auth.py           # JWT validation
│   ├── models/               # Pydantic v2 schemas
│   ├── utils/
│   │   └── logging.py        # JSON logging
│   └── tests/                # Pytest unit tests
├── frontend/                 # React + Vite + TypeScript
│   └── src/
│       ├── auth/             # MSAL config
│       ├── api/              # Axios API client
│       ├── components/       # Shared UI components
│       ├── pages/            # CaseListPage, CaseDetailPage
│       └── types/            # TypeScript interfaces
├── nginx/
│   └── nginx.conf            # Reverse proxy config
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Prerequisites

- **Azure Subscription** with:
  - Azure Key Vault
  - Azure Cosmos DB (Serverless, Core SQL API)
  - Azure Blob Storage
  - Azure OpenAI (GPT-4o-mini deployment)
  - Azure Container Instance running Document Intelligence
  - Azure AD App Registration (for UI auth)
  - Azure AD App Registration on client tenant (for Graph API, Mail.Read permission)
- **Certificate** for Graph API auth (PFX stored in Key Vault, public key on client app reg)
- Docker + Docker Compose installed on the Azure VM

---

## Local Development Setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd IAT-POC
cp .env.example .env
# Fill in your Azure values in .env
```

### 2. Run backend locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_lg
playwright install chromium
uvicorn main:app --reload --port 8000
```

### 3. Run frontend locally

```bash
cd frontend
npm install
npm run dev
# Visit http://localhost:5173
```

---

## Docker Deployment (Production)

### 1. Setup SSL certificates (for Nginx)

```bash
mkdir -p nginx/certs
# For dev (self-signed):
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/server.key -out nginx/certs/server.crt \
  -subj "/CN=your-domain.com"
```

### 2. Build and start all services

```bash
docker-compose up -d --build
```

### 3. Verify health

```bash
curl http://localhost/health
# Expected: {"status": "healthy", "service": "IAT Insurance Email Automation"}
```

---

## Azure Infrastructure Setup

### Cosmos DB Containers

Create database `iatinsurance-db` with these containers (auto-created on first startup):

| Container | Partition Key |
|---|---|
| `cases` | `/case_id` |
| `emails` | `/email_id` |
| `documents` | `/document_id` |
| `classification_results` | `/result_id` |
| `pii_mapping` | `/mapping_id` |

### Blob Storage Containers

Create these containers in your storage account:
- `raw-emails`
- `raw-attachments`
- `extracted-text`

### Key Vault Secrets Required

| Secret Name | Value |
|---|---|
| `graph-api-certificate` | PFX certificate (base64) |
| `pii-encryption-key` | Base64-encoded 32-byte key |

Generate PII encryption key:
```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### Graph API Webhook Registration

The webhook subscription is auto-registered on application startup. Ensure:
1. `WEBHOOK_URL` in `.env` points to a publicly accessible HTTPS endpoint
2. The Graph API app registration has `Mail.Read` application permission with Admin Consent

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

Tests use mocks for all Azure services — no real credentials needed for testing.

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/webhook/email` | Graph clientState | Email notification webhook |
| GET | `/health` | None | Health check |
| GET | `/api/stats` | JWT | Dashboard stats |
| GET | `/api/cases` | JWT | List cases (search, filter, paginate) |
| GET | `/api/cases/{case_id}` | JWT | Case detail |
| GET | `/api/cases/{case_id}/emails` | JWT | Case email chain |
| GET | `/api/cases/{case_id}/documents` | JWT | Case documents |
| GET | `/api/cases/{case_id}/classification` | JWT | Classification result |
| GET | `/api/cases/{case_id}/timeline` | JWT | Processing timeline |

---

## Classification Categories

| # | Category | Description |
|---|---|---|
| 1 | New | New policy applications |
| 2 | Renewal | Policy renewal requests |
| 3 | Query/General | General questions |
| 4 | Follow-up | Follow-up on submitted items |
| 5 | Complaint/Escalation | Formal complaints |
| 6 | Regulatory/Legal | FCA/legal communications |
| 7 | Documentation/Evidence | Supporting documents |
| 8 | Spam/Irrelevant | Non-insurance emails |

---

## Security Notes

- **All secrets** loaded from Azure Key Vault at startup — never in `.env` or code
- **Graph API** uses certificate auth — no client secrets
- **PII masking** runs before any AI call — GPT-4o-mini never sees real PII
- **PII mapping** stored AES-256 encrypted — never exposed via any API endpoint
- **Azure AD** authentication required for all UI access
- **HTTPS** enforced via Nginx (TLS 1.2+)

---

## Development Notes

- Python: `async/await` throughout, Pydantic v2, structured JSON logging
- Frontend: TypeScript strict mode, MSAL React v2, Tailwind CSS v4
- All errors caught and logged; case status updated to `FAILED` on pipeline errors
- Graph webhook subscription auto-renewed every 48 hours
