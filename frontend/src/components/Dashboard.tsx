"use client";

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  getDocument,
  getPatient,
  listDocuments,
  listEvidenceCandidates,
  reseedDemo,
  uploadDocument,
} from "@/lib/api";
import type {
  DocumentDetail,
  DocumentSummary,
  EvidenceCandidate,
  Patient,
} from "@/lib/types";
import { EvidenceCandidates } from "./EvidenceCandidates";
import { DocumentLibrary } from "./DocumentLibrary";
import { DocumentViewer } from "./DocumentViewer";
import { PlaceholderPanel } from "./PlaceholderPanel";

const DEFAULT_PATIENT_ID = "patient-raymond-yao";
const STACKED_LAYOUT = "(max-width: 1023px)";
type WorkspaceTab = "documents" | "evidence";

export function Dashboard() {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [evidenceCandidates, setEvidenceCandidates] = useState<EvidenceCandidate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [failedDocId, setFailedDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [bootLoading, setBootLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("documents");
  const [showViewerOnMobile, setShowViewerOnMobile] = useState(false);
  const libraryRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const scrollIntent = useRef<"viewer" | "library" | null>(null);

  const visibleDoc =
    selectedId && selectedDoc?.id === selectedId ? selectedDoc : null;
  const docLoading =
    Boolean(selectedId) && !visibleDoc && failedDocId !== selectedId;

  async function refreshLibrary(selectId?: string | null) {
    const [nextPatient, nextDocs, nextCandidates] = await Promise.all([
      getPatient(DEFAULT_PATIENT_ID),
      listDocuments(DEFAULT_PATIENT_ID),
      listEvidenceCandidates(DEFAULT_PATIENT_ID),
    ]);
    setPatient(nextPatient);
    setDocuments(nextDocs);
    setEvidenceCandidates(nextCandidates);
    const nextSelected =
      selectId === undefined
        ? (nextDocs[0]?.id ?? null)
        : selectId && nextDocs.some((d) => d.id === selectId)
          ? selectId
          : (nextDocs[0]?.id ?? null);
    setFailedDocId(null);
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
    if (!selectedId) return;
    let cancelled = false;
    const id = selectedId;
    (async () => {
      try {
        const detail = await getDocument(DEFAULT_PATIENT_ID, id);
        if (!cancelled) setSelectedDoc(detail);
      } catch (err) {
        if (!cancelled) {
          setFailedDocId(id);
          setError(
            err instanceof Error ? err.message : "Failed to load document",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    const intent = scrollIntent.current;
    if (!intent) return;
    scrollIntent.current = null;
    if (!window.matchMedia(STACKED_LAYOUT).matches) return;
    const node = intent === "viewer" ? viewerRef.current : libraryRef.current;
    node?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeTab, showViewerOnMobile, selectedId]);

  function handleSelect(id: string) {
    const alreadyShowing =
      showViewerOnMobile && selectedId === id && visibleDoc?.id === id;
    setFailedDocId(null);
    setSelectedId(id);
    setShowViewerOnMobile(true);
    if (!window.matchMedia(STACKED_LAYOUT).matches) return;
    if (alreadyShowing) {
      viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    scrollIntent.current = "viewer";
  }

  function handleBackToLibrary() {
    scrollIntent.current = "library";
    setShowViewerOnMobile(false);
  }

  function handleOpenEvidenceSource(id: string) {
    scrollIntent.current = "viewer";
    setActiveTab("documents");
    setFailedDocId(null);
    setSelectedId(id);
    setShowViewerOnMobile(true);
  }

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
    const confirmed = window.confirm(
      "Reload demo documents? Uploaded PDFs will be removed.",
    );
    if (!confirmed) return;

    // Drop the preview before the reseed deletes the file it points at.
    flushSync(() => {
      setError(null);
      setBootLoading(true);
      setSelectedId(null);
      setSelectedDoc(null);
      setFailedDocId(null);
      setShowViewerOnMobile(false);
    });

    try {
      await reseedDemo();
      await refreshLibrary();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reseed failed");
    } finally {
      setBootLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-5 py-8 sm:px-8">
      <header className="mb-8">
 
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-5xl text-ink">Unburden</h1>

          </div>
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <button
              type="button"
              onClick={() => void handleReseed()}
              className="border border-line bg-white/50 px-4 py-2 text-sm text-ink-soft hover:border-ink/30 hover:bg-white"
            >
              Reload demo documents
            </button>
            <p className="text-xs text-muted">Uploaded PDFs will be removed.</p>
          </div>
        </div>
      </header>

      {patient && (
        <div className="mb-6 border-y border-line/80 py-4">
        
          <p className="mt-1 font-display text-2xl text-ink">
            {patient.display_name}
          </p>
     
        </div>
      )}

      {error && (
        <div className="mb-6 border border-warning/40 bg-[#fff8ef] px-4 py-3 text-sm text-warning">
          {error}
        </div>
      )}

      <div
        role="tablist"
        aria-label="Unburden workspace"
        className="mb-8 flex border-b border-line"
      >
        <button
          type="button"
          role="tab"
          id="documents-tab"
          aria-selected={activeTab === "documents"}
          aria-controls="documents-panel"
          onClick={() => setActiveTab("documents")}
          className={`border-b-2 px-4 py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 ${
            activeTab === "documents"
              ? "border-accent text-ink"
              : "border-transparent text-muted hover:border-line hover:text-ink-soft"
          }`}
        >
          Documents
        </button>
        <button
          type="button"
          role="tab"
          id="evidence-tab"
          aria-selected={activeTab === "evidence"}
          aria-controls="evidence-panel"
          onClick={() => setActiveTab("evidence")}
          className={`border-b-2 px-4 py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 ${
            activeTab === "evidence"
              ? "border-accent text-ink"
              : "border-transparent text-muted hover:border-line hover:text-ink-soft"
          }`}
        >
          Requirement evidence
          {evidenceCandidates.length > 0 && (
            <span className="ml-2 bg-mist px-2 py-0.5 text-xs text-ink-soft">
              {evidenceCandidates.length}
            </span>
          )}
        </button>
      </div>

      {bootLoading ? (
        <p className="text-sm text-muted">Loading workspace…</p>
      ) : activeTab === "documents" ? (
        <div
          role="tabpanel"
          id="documents-panel"
          aria-labelledby="documents-tab"
        >
          <div className="grid min-h-[520px] gap-8 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
            <div
              ref={libraryRef}
              className={`min-w-0 scroll-mt-4 ${showViewerOnMobile ? "hidden lg:block" : ""}`}
            >
              <DocumentLibrary
                documents={documents}
                selectedId={selectedId}
                onSelect={handleSelect}
                onUpload={handleUpload}
                uploading={uploading}
              />
            </div>
            <div
              ref={viewerRef}
              className={`flex h-full min-h-0 min-w-0 scroll-mt-4 flex-col ${
                showViewerOnMobile ? "" : "hidden lg:flex"
              }`}
            >
              <button
                type="button"
                onClick={handleBackToLibrary}
                className="mb-3 self-start border border-line bg-white px-3 py-1.5 text-sm text-ink focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 lg:hidden"
              >
                Back to library
              </button>
              <div className="min-h-0 flex-1">
                <DocumentViewer
                  patientId={DEFAULT_PATIENT_ID}
                  document={visibleDoc}
                  loading={docLoading}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div
          role="tabpanel"
          id="evidence-panel"
          aria-labelledby="evidence-tab"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="md:col-span-2">
              <EvidenceCandidates
                candidates={evidenceCandidates}
                onOpenSource={handleOpenEvidenceSource}
              />
            </div>
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
        </div>
      )}
    </div>
  );
}
