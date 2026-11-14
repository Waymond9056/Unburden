# Unburden

Hackathon MVP: an AI-assisted **prior authorization evidence engine** for pulmonology practices.

Unburden turns messy medical PDFs into a source-verifiable insurance evidence packet. It is **not** a medical summarizer and does **not** approve insurance coverage.

## Stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, SQLite, PyMuPDF
- **LLM:** Configurable OpenAI-compatible API (used from Milestone 2)

## Project layout

```
backend/          FastAPI app, evidence engine, tests
frontend/         Next.js clinician UI (shell in Milestone 1)
data/seed/        Synthetic demo PDFs
data/uploads/     Stored original uploads
data/db/          SQLite database
MVP.md            Full product / milestone spec
```

## Prerequisites

- Python 3.11+
- Node.js 20+

## Setup

```bash
# 1) Environment
cp .env.example .env
# Add LLM_API_KEY when you reach Milestone 2

# 2) Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) Frontend
cd ../frontend
npm install
```

## Run locally

Terminal A — API (http://localhost:8000):

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Terminal B — UI shell (http://localhost:3000):

```bash
cd frontend
npm run dev
```

On first API boot, Unburden creates the synthetic patient **Raymond Yao** and loads seed PDFs.

## Milestone 1 API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/patients` | List patients |
| GET | `/api/patients/{id}` | Patient detail |
| POST | `/api/patients/{id}/documents` | Upload PDF |
| GET | `/api/patients/{id}/documents` | List documents |
| GET | `/api/patients/{id}/documents/{doc_id}` | Document + page text |
| GET | `/api/patients/{id}/documents/{doc_id}/file` | Original PDF (inline preview) |
| GET | `/api/patients/{id}/observations` | Observations (empty until M2) |
| POST | `/api/demo/seed` | Regenerate / reload synthetic docs |

## Milestone 1.5 UI

Open http://localhost:3000 for the clinician workspace:

- Document library + PDF upload
- Side-by-side PDF preview and extracted page text
- Placeholder panels for observations, requirements, and evidence packet

Default patient id: `patient-raymond-yao`

Example upload:

```bash
curl -X POST "http://localhost:8000/api/patients/patient-raymond-yao/documents" \
  -F "file=@data/seed/lab_eosinophils.pdf" \
  -F "document_type=laboratory_report"
```

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Notes

- Sample insurance policy criteria are **fictional** and for demo only.
- No real patient data.
- If no LLM key is configured, later milestones fall back to deterministic fixture observations so the evidence engine stays testable.
