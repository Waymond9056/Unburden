"use client";

import { useEffect, useState, useTransition } from "react";
import {
  getDocument,
  getPatient,
  listDocuments,
  reseedDemo,
  uploadDocument,
} from "@/lib/api";
import type { DocumentDetail, DocumentSummary, Patient } from "@/lib/types";
import { DocumentLibrary } from "./DocumentLibrary";
import { DocumentViewer } from "./DocumentViewer";
import { PlaceholderPanel } from "./PlaceholderPanel";

const DEFAULT_PATIENT_ID = "patient-raymond-yao";

export function Dashboard() {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [bootLoading, setBootLoading] = useState(true);
  const [docLoading, setDocLoading] = useState(false);
  const [, startTransition] = useTransition();

  async function refreshLibrary(selectId?: string | null) {
    const [nextPatient, nextDocs] = await Promise.all([
      getPatient(DEFAULT_PATIENT_ID),
      listDocuments(DEFAULT_PATIENT_ID),
    ]);
    setPatient(nextPatient);
    setDocuments(nextDocs);
    const nextSelected =
      selectId === undefined
        ? nextDocs[0]?.id ?? null
        : selectId && nextDocs.some((d) => d.id === selectId)
          ? selectId
          : nextDocs[0]?.id ?? null;
    setSelectedId(nextSelected);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setBootLoading(true);
        setError(null);
        await refreshLibrary();
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not reach the Unburden API. Is it running on :8000?",
          );
        }
      } finally {
        if (!cancelled) setBootLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDoc(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setDocLoading(true);
        const detail = await getDocument(DEFAULT_PATIENT_ID, selectedId);
        if (!cancelled) setSelectedDoc(detail);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load document");
        }
      } finally {
        if (!cancelled) setDocLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  async function handleUpload(file: File) {
    try {
      setUploading(true);
      setError(null);
      const created = await uploadDocument(DEFAULT_PATIENT_ID, file);
      await refreshLibrary(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleReseed() {
    try {
      setError(null);
      setBootLoading(true);
      await reseedDemo();
      await refreshLibrary();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reseed failed");
    } finally {
      setBootLoading(false);
    }
  }

  return (
    <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-8 sm:px-8">
      <header className="animate-rise mb-8">
        <p className="text-xs uppercase tracking-[0.22em] text-muted">
          Prior authorization evidence engine
        </p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-5xl tracking-tight text-ink sm:text-6xl">
              Unburden
            </h1>
            <p className="mt-3 max-w-xl text-base leading-7 text-ink-soft">
              Review source documents, verify extracted evidence, and assemble a
              compact packet for insurance review.
            </p>
          </div>
          <button
            type="button"
            onClick={() => startTransition(() => void handleReseed())}
            className="border border-line bg-white/50 px-4 py-2 text-sm text-ink-soft transition hover:border-ink/30 hover:bg-white"
          >
            Reload demo documents
          </button>
        </div>
      </header>

      {patient && (
        <div className="animate-rise stagger-1 mb-6 border-y border-line/80 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-muted">Patient</p>
          <p className="mt-1 font-display text-2xl text-ink">{patient.display_name}</p>
          <p className="text-sm text-muted">
            DOB {patient.date_of_birth ?? "—"} · id {patient.id}
          </p>
        </div>
      )}

      {error && (
        <div className="mb-6 border border-warning/40 bg-[#fff8ef] px-4 py-3 text-sm text-warning">
          {error}
        </div>
      )}

      {bootLoading ? (
        <p className="animate-fade text-sm text-muted">Loading workspace…</p>
      ) : (
        <>
          <div className="grid min-h-[520px] gap-8 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
            <DocumentLibrary
              documents={documents}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onUpload={handleUpload}
              uploading={uploading}
            />
            <DocumentViewer
              patientId={DEFAULT_PATIENT_ID}
              document={selectedDoc}
              loading={docLoading}
            />
          </div>

          <div className="mt-10 grid gap-8 md:grid-cols-3">
            <PlaceholderPanel
              title="Clinical observations"
              milestone="Milestone 2"
              description="Structured findings with source citations will appear here after extraction lands."
            />
            <PlaceholderPanel
              title="Insurance requirements"
              milestone="Milestone 3"
              description="Supported / not established / needs review statuses will populate this checklist."
            />
            <PlaceholderPanel
              title="Evidence packet"
              milestone="Milestone 4"
              description="Optimized document selection and missing-evidence guidance will show here."
            />
          </div>
        </>
      )}
    </div>
  );
}
