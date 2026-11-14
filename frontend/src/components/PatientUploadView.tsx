"use client";

import { useEffect, useRef, useState } from "react";
import { ringDocumentAssistant, getChertSession, uploadDocument } from "@/lib/api";
import type { ChertSession } from "@/lib/types";
import { DEFAULT_PATIENT_ID } from "@/lib/constants";

type RingPhase =
  | "idle"
  | "preparing"
  | "ringing"
  | "active"
  | "uploaded"
  | "failed";

function phaseFromSession(session: ChertSession): RingPhase {
  const status = session.status.toLowerCase();
  if (session.document_id || status === "uploaded") return "uploaded";
  if (status === "failed" || status === "ended") return "failed";
  if (
    status === "active" ||
    status === "answered" ||
    status === "bridge_ready" ||
    status === "in_call"
  ) {
    return "active";
  }
  if (status === "ringing" || status === "queued" || status === "dialing" || status === "allocated") {
    return "ringing";
  }
  if (status === "preparing") return "preparing";
  return "ringing";
}

export function PatientUploadView({
  patientId,
  patientName,
}: {
  patientId: string;
  patientName: string;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<string | null>(null);

  const [ringPhase, setRingPhase] = useState<RingPhase>("idle");
  const [ringError, setRingError] = useState<string | null>(null);
  const [ringLabel, setRingLabel] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const canRing = patientId === DEFAULT_PATIENT_ID;

  useEffect(() => {
    if (ringPhase === "idle" || ringPhase === "uploaded" || ringPhase === "failed") {
      return;
    }
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const session = await getChertSession(patientId, sessionId);
        if (cancelled) return;
        const next = phaseFromSession(session);
        setRingPhase(next);
        if (session.source_label) setRingLabel(session.source_label);
        if (session.error && next === "failed") setRingError(session.error);
        if (next === "uploaded" && session.source_label) {
          setLastUploaded(session.source_label);
        }
      } catch (err) {
        if (!cancelled) {
          setRingError(err instanceof Error ? err.message : "Could not refresh call status");
        }
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [ringPhase, patientId]);

  async function handleUpload(file: File) {
    try {
      setUploading(true);
      setError(null);
      const created = await uploadDocument(patientId, file);
      setLastUploaded(created.source_label || created.original_filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleRing() {
    try {
      setRingError(null);
      setRingLabel(null);
      setRingPhase("preparing");
      const session = await ringDocumentAssistant(patientId);
      sessionIdRef.current = session.session_id;
      setRingPhase(phaseFromSession(session));
      if (session.error) setRingError(session.error);
    } catch (err) {
      setRingPhase("failed");
      setRingError(err instanceof Error ? err.message : "Could not start FaceTime call");
    }
  }

  const ringingBusy =
    ringPhase === "preparing" || ringPhase === "ringing" || ringPhase === "active";

  return (
    <div className="relative z-10 mx-auto flex min-h-[70vh] w-full max-w-3xl flex-col justify-center px-5 py-16 sm:px-8">
      <p className="max-w-xl text-lg leading-7 text-ink-soft">
        Upload medical PDFs for your care team. Your clinician reviews them in
        the care provider workspace.
      </p>

      <div className="mt-10 border-y border-line/80 py-8">
        <h2 className="font-display text-2xl text-ink">Document upload</h2>
        <p className="mt-2 text-sm text-muted">
          PDF only. Files are stored for {patientName}’s chart and appear
          immediately in the care provider view.
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <label
            className={`inline-flex cursor-pointer border border-accent bg-accent px-5 py-3 text-sm font-medium text-white transition hover:bg-accent-deep ${
              uploading ? "uploading-pulse pointer-events-none opacity-70" : ""
            }`}
          >
            {uploading ? "Uploading…" : "Upload PDF"}
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              disabled={uploading}
              onChange={async (event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) await handleUpload(file);
              }}
            />
          </label>

          {canRing && (
            <button
              type="button"
              onClick={() => void handleRing()}
              disabled={ringingBusy}
              className={`inline-flex border border-ink px-5 py-3 text-sm font-medium text-ink transition hover:bg-mist/60 disabled:cursor-not-allowed disabled:opacity-60 ${
                ringingBusy ? "uploading-pulse" : ""
              }`}
            >
              {ringPhase === "preparing"
                ? "Preparing agent…"
                : ringPhase === "ringing"
                  ? "Ringing your phone…"
                  : ringPhase === "active"
                    ? "On FaceTime…"
                    : "Ring document assistant"}
            </button>
          )}
        </div>

        {canRing && (
          <p className="mt-3 max-w-xl text-sm text-muted">
            FaceTime Video: the assistant calls you, asks you to hold up a
            document, captures camera frames, and saves a PDF to your chart.
          </p>
        )}

        {ringPhase === "uploaded" && ringLabel && (
          <p className="mt-4 text-sm text-[#0f5a51]">
            FaceTime uploaded “{ringLabel}”. Your care provider can review it now.
          </p>
        )}
        {ringError && (
          <p className="mt-4 text-sm text-warning">{ringError}</p>
        )}

        {lastUploaded && !error && ringPhase !== "uploaded" && (
          <p className="mt-4 text-sm text-[#0f5a51]">
            Uploaded “{lastUploaded}”. Your care provider can review it now.
          </p>
        )}
        {error && (
          <p className="mt-4 text-sm text-warning">{error}</p>
        )}
      </div>
    </div>
  );
}
