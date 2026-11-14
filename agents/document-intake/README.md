# Unburden document-intake agent

FaceTime Video agent for the patient **Ring document assistant** button.

Flow:
1. Backend creates a LiveKit room and asks Chert to place an outbound FaceTime Video call.
2. This agent joins, greets on `bridge_ready`, and asks the caller to hold up a document.
3. It samples caller camera frames, builds a PDF, and `POST`s it to  
   `/api/patients/{id}/documents` with a `FaceTime capture — …` source label.

## Prerequisites

1. **LiveKit Cloud** project → put `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` in:
   - `agents/document-intake/.env.local`
   - repo-root `.env` (for the FastAPI ring API)
2. **Chert** values in repo-root `.env`: `CHERT_API_KEY`, `CHERT_PROJECT_ID`, `CHERT_LINE_ID`, `CHERT_DESTINATION_PHONE`
3. Optional but recommended: `OPENAI_API_KEY` with Realtime access (spoken coach). Without it, capture still runs after `bridge_ready`.
4. Use **Node 22 / 24 / 26** (not Node 25) when running Chert CLI commands.

## Run (outbound ring demo)

Terminal A — agent worker:

```sh
cd agents/document-intake
npm install
npm start
```

Terminal B — Unburden API:

```sh
cd backend
uvicorn app.main:app --reload --port 8000
```

Terminal C — frontend:

```sh
cd frontend
npm run dev
```

Open the patient view for Raymond → **Ring document assistant**.

`chert dev` is **not** required for outbound BYOR. Keep the agent worker running so LiveKit can dispatch it into the room the backend creates.

## Inbound smoke test (optional)

If you want to FaceTime the Chert line directly (no ring button), clear LiveKit keys in `.env.local` and run `chert dev` alongside `npm start` (Chert rooms mode).
