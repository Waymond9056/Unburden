"use client";

import Image from "next/image";
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

export function PatientUploadView({ patientId }: { patientId: string }) {
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

  const statusMessage =
    ringPhase === "uploaded" && ringLabel
      ? `Uploaded “${ringLabel}”. Your care provider can review it now.`
      : lastUploaded && !error && ringPhase !== "uploaded"
        ? `Uploaded “${lastUploaded}”. Your care provider can review it now.`
        : null;
  const statusError = ringError || error;

  return (
    <section className="patient-upload-stage relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="patient-upload-mark-wrap absolute left-1/2 top-[46%] h-[min(92vw,40rem)] w-[min(92vw,40rem)] -translate-x-1/2 -translate-y-1/2">
          <Image
            src="/logo-mark.png"
            alt=""
            fill
            sizes="min(92vw, 40rem)"
            className="patient-upload-mark object-contain select-none"
            priority
          />
        </div>
        <div className="patient-upload-wash absolute inset-0" />
      </div>

      <div className="relative z-10 mx-auto flex min-h-[calc(100vh-5.5rem)] w-full max-w-2xl flex-col items-center justify-center px-5 py-16 text-center sm:px-8">
        <div className="patient-upload-enter patient-upload-glass w-full px-6 py-10 sm:px-10 sm:py-12">
          <h1 className="font-display text-4xl leading-tight text-ink sm:text-5xl">
            Send documents to your care team
          </h1>
          <p className="mx-auto mt-4 max-w-md text-base leading-7 text-ink-soft">
            {canRing
              ? "Upload a PDF, or upload with Chert to capture a document on camera."
              : "Upload a PDF for your care team to review."}
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <label
              className={`inline-flex min-w-[10.5rem] cursor-pointer items-center justify-center border border-accent bg-accent px-6 py-3.5 text-sm font-medium text-white transition hover:bg-accent-deep ${
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
                className={`inline-flex min-w-[10.5rem] items-center justify-center border border-ink/80 bg-white/35 px-6 py-3.5 text-sm font-medium text-ink transition hover:bg-white/55 disabled:cursor-not-allowed disabled:opacity-60 ${
                  ringingBusy ? "uploading-pulse" : ""
                }`}
              >
                {ringPhase === "preparing"
                  ? "Preparing…"
                  : ringPhase === "ringing"
                    ? "Ringing…"
                    : ringPhase === "active"
                      ? "On FaceTime…"
                      : "Upload with Chert"}
              </button>
            )}
          </div>

          {(statusMessage || statusError) && (
            <div className="mx-auto mt-8 max-w-md" aria-live="polite">
              {statusMessage && (
                <p className="text-sm text-accent-deep">{statusMessage}</p>
              )}
              {statusError && (
                <p className="mt-2 text-sm text-warning">{statusError}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
