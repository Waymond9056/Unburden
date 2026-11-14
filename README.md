# Unburden

Hackathon MVP: an AI-assisted **prior authorization evidence engine** for pulmonology practices.

Unburden turns messy medical PDFs into a source-verifiable insurance evidence packet. It is **not** a medical summarizer and does **not** approve insurance coverage.

## Stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, SQLite, PyMuPDF
- **LLM:** Configurable OpenAI-compatible API with deterministic demo fallback

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
# LLM_API_KEY is optional and reserved for later candidate verification

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
| GET | `/api/policies` | List fictional example policies |
| GET | `/api/policies/{id}` | Policy detail + requirements |
| GET | `/api/policies/{id}/requirements` | Active policy requirements |
| GET | `/api/patients/{id}/evidence-candidates` | Requirement-linked source passages |
| POST | `/api/patients/{id}/evidence-candidates/retrieve` | Re-run candidate retrieval |
| POST | `/api/patients/{id}/evaluate` | Run structured policy verification |
| GET | `/api/patients/{id}/policy-evaluation` | Requirements checklist statuses |
| GET | `/api/patients/{id}/evidence-packet` | Optimized review packet + missing checklist |
| GET | `/api/patients/{id}/evidence-packet/export` | Download PA packet PDF (cover + attached docs) |
| POST | `/api/demo/seed` | Regenerate / reload synthetic docs |

## Workspace

Open http://localhost:3000:

- Documents: library, PDF upload, page text, and PDF preview
- Requirement evidence: retrieved passages with verification status
- Insurance requirements: SUPPORTED / NOT_ESTABLISHED / NEEDS_REVIEW
- Evidence packet: selected documents, missing items, and packet PDF download
- Click a citation to open the source document on the cited page

The sample policy is **fictional** and labeled as such. Candidates from M2 are not
automatically accepted; M3 applies temporal, numeric, document-type, and quote-in-source
constraints before marking a requirement supported.

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
- Lexical retrieval is sufficient for the small demo corpus; semantic retrieval can be added if evaluation shows recall gaps.
