"use client";

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  deleteDocument,
  downloadEvidencePacketPdf,
  evaluatePolicy,
  getDocument,
  getEvidencePacket,
  getPatient,
  getPolicyEvaluation,
  listDocuments,
  listEvidenceCandidates,
  reseedDemo,
  uploadDocument,
} from "@/lib/api";
import { DEFAULT_PATIENT_ID } from "@/lib/constants";
import type {
  DocumentDetail,
  DocumentSummary,
  EvidenceCandidate,
  EvidencePacket,
  Patient,
  PolicyEvaluation,
} from "@/lib/types";
import { EvidenceCandidates } from "./EvidenceCandidates";
import { EvidencePacketPanel } from "./EvidencePacketPanel";
import { DocumentLibrary } from "./DocumentLibrary";
import { DocumentViewer } from "./DocumentViewer";
import {
  RequirementsChecklist,
  type RequirementStatusChange,
} from "./RequirementsChecklist";

const STACKED_LAYOUT = "(max-width: 1023px)";
type WorkspaceTab = "documents" | "evidence" | "requirements" | "packet";

function diffRequirementStatuses(
  previous: PolicyEvaluation | null,
  next: PolicyEvaluation | null,
): RequirementStatusChange[] {
  if (!previous || !next) return [];
  const prevById = new Map(
    previous.requirements.map((item) => [item.requirement_id, item]),
  );
  const changes: RequirementStatusChange[] = [];
  for (const item of next.requirements) {
    const before = prevById.get(item.requirement_id);
    if (!before || before.status === item.status) continue;
    changes.push({
      requirement_id: item.requirement_id,
      title: item.title,
      from: before.status,
      to: item.status,
    });
  }
  return changes;
}

export function Dashboard() {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [evidenceCandidates, setEvidenceCandidates] = useState<
    EvidenceCandidate[]
  >([]);
  const [evaluation, setEvaluation] = useState<PolicyEvaluation | null>(null);
  const [packet, setPacket] = useState<EvidencePacket | null>(null);
  const [statusChanges, setStatusChanges] = useState<RequirementStatusChange[]>(
    [],
  );
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [packetLoading, setPacketLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [focusPage, setFocusPage] = useState<number | null>(null);
  const [highlightQuote, setHighlightQuote] = useState<string | null>(null);
  const [failedDocId, setFailedDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("documents");
  const [showViewerOnMobile, setShowViewerOnMobile] = useState(false);
  const libraryRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const scrollIntent = useRef<"viewer" | "library" | null>(null);
  const previousEvaluationRef = useRef<PolicyEvaluation | null>(null);
  const skipStatusDiffRef = useRef(true);

  const visibleDoc =
    selectedId && selectedDoc?.id === selectedId ? selectedDoc : null;
  const docLoading =
    Boolean(selectedId) && !visibleDoc && failedDocId !== selectedId;

  function applyEvaluation(nextEvaluation: PolicyEvaluation) {
    if (skipStatusDiffRef.current) {
      skipStatusDiffRef.current = false;
      setStatusChanges([]);
    } else {
      setStatusChanges(
        diffRequirementStatuses(previousEvaluationRef.current, nextEvaluation),
      );
    }
    previousEvaluationRef.current = nextEvaluation;
    setEvaluation(nextEvaluation);
  }

  async function refreshLibrary(selectId?: string | null) {
    const [nextPatient, nextDocs, nextCandidates, nextEvaluation, nextPacket] =
      await Promise.all([
        getPatient(DEFAULT_PATIENT_ID),
        listDocuments(DEFAULT_PATIENT_ID),
        listEvidenceCandidates(DEFAULT_PATIENT_ID),
        getPolicyEvaluation(DEFAULT_PATIENT_ID),
        getEvidencePacket(DEFAULT_PATIENT_ID),
      ]);
    setPatient(nextPatient);
    setDocuments(nextDocs);
    setEvidenceCandidates(nextCandidates);
    applyEvaluation(nextEvaluation);
    setPacket(nextPacket);
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
  }, [activeTab, showViewerOnMobile, selectedId, focusPage]);

  function handleSelect(id: string) {
    const alreadyShowing =
      showViewerOnMobile && selectedId === id && visibleDoc?.id === id;
    setFailedDocId(null);
    setFocusPage(null);
    setHighlightQuote(null);
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

  function handleOpenEvidenceSource(
    id: string,
    page?: number,
    quote?: string,
  ) {
    scrollIntent.current = "viewer";
    setActiveTab("documents");
    setFailedDocId(null);
    setSelectedId(id);
    setFocusPage(page ?? null);
    setHighlightQuote(quote ?? null);
    setShowViewerOnMobile(true);
  }

  async function handleReevaluate() {
    try {
      setError(null);
      setEvaluationLoading(true);
      setPacketLoading(true);
      const nextEvaluation = await evaluatePolicy(DEFAULT_PATIENT_ID);
      const changes = diffRequirementStatuses(
        previousEvaluationRef.current,
        nextEvaluation,
      );
      applyEvaluation(nextEvaluation);
      const [nextCandidates, nextPacket] = await Promise.all([
        listEvidenceCandidates(DEFAULT_PATIENT_ID),
        getEvidencePacket(DEFAULT_PATIENT_ID),
      ]);
      setEvidenceCandidates(nextCandidates);
      setPacket(nextPacket);
      if (changes.length > 0) setActiveTab("requirements");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setEvaluationLoading(false);
      setPacketLoading(false);
    }
  }

  async function handleRebuildPacket() {
    try {
      setError(null);
      setPacketLoading(true);
      const nextPacket = await getEvidencePacket(DEFAULT_PATIENT_ID);
      setPacket(nextPacket);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Packet build failed");
    } finally {
      setPacketLoading(false);
    }
  }

  async function handleExportPacket() {
    try {
      setError(null);
      await downloadEvidencePacketPdf(DEFAULT_PATIENT_ID);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Packet export failed");
    }
  }

  async function handleUpload(file: File) {
    try {
      setUploading(true);
      setError(null);
      const created = await uploadDocument(DEFAULT_PATIENT_ID, file);
      await refreshLibrary(created.id);
      setActiveTab("requirements");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(documentId: string) {
    const doc = documents.find((item) => item.id === documentId);
    const label = doc?.source_label || doc?.original_filename || "this document";
    const confirmed = window.confirm(`Delete “${label}”? This cannot be undone.`);
    if (!confirmed) return;

    try {
      setDeletingId(documentId);
      setError(null);
      if (selectedId === documentId) {
        setSelectedId(null);
        setSelectedDoc(null);
        setFocusPage(null);
        setHighlightQuote(null);
      }
      await deleteDocument(DEFAULT_PATIENT_ID, documentId);
      await refreshLibrary(selectedId === documentId ? null : selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleReseed() {
    const confirmed = window.confirm(
      "Reload demo documents? Uploaded PDFs will be removed.",
    );
    if (!confirmed) return;

    flushSync(() => {
      setError(null);
      setBootLoading(true);
      setSelectedId(null);
      setSelectedDoc(null);
      setFocusPage(null);
      setHighlightQuote(null);
      setFailedDocId(null);
      setShowViewerOnMobile(false);
      setStatusChanges([]);
      skipStatusDiffRef.current = true;
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
            <p className="text-xs uppercase tracking-[0.18em] text-muted">
              Care provider view
            </p>
            <h1 className="mt-1 font-display text-3xl text-ink">Unburden</h1>
          </div>
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <button
              type="button"
              onClick={() => void handleReseed()}
              className="border border-line bg-white/50 px-4 py-2 text-sm text-ink-soft hover:border-ink/30 hover:bg-white focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
            >
              Reload demo documents
            </button>
            <p className="text-xs text-muted">Uploaded PDFs will be removed.</p>
          </div>
        </div>
      </header>

      {patient && (
        <div className="mb-6 border-y border-line/80 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-muted">
            Patient
          </p>
          <p className="mt-1 font-display text-2xl text-ink">
            {patient.display_name}
          </p>
          <p className="text-sm text-muted">
            DOB {patient.date_of_birth ?? "—"}
          </p>
        </div>
      )}

      {error && (
        <div className="mb-6 border border-warning/40 bg-[#fff8ef] px-4 py-3 text-sm text-warning">
          {error}
        </div>
      )}

      {statusChanges.length > 0 && activeTab !== "requirements" && (
        <button
          type="button"
          onClick={() => setActiveTab("requirements")}
          className="mb-6 w-full border border-[#c48a2e]/40 bg-[#fff8ef] px-4 py-3 text-left text-sm text-[#8a6230] hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
        >
          {statusChanges.length} insurance requirement
          {statusChanges.length === 1 ? "" : "s"} changed — view checklist
        </button>
      )}

      <div
        role="tablist"
        aria-label="Unburden workspace"
        className="mb-8 flex flex-wrap border-b border-line"
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
        <button
          type="button"
          role="tab"
          id="requirements-tab"
          aria-selected={activeTab === "requirements"}
          aria-controls="requirements-panel"
          onClick={() => setActiveTab("requirements")}
          className={`border-b-2 px-4 py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 ${
            activeTab === "requirements"
              ? "border-accent text-ink"
              : "border-transparent text-muted hover:border-line hover:text-ink-soft"
          }`}
        >
          Insurance requirements
          {evaluation && (
            <span className="ml-2 bg-mist px-2 py-0.5 text-xs text-ink-soft">
              {evaluation.overall_status.replaceAll("_", " ")}
            </span>
          )}
        </button>
        <button
          type="button"
          role="tab"
          id="packet-tab"
          aria-selected={activeTab === "packet"}
          aria-controls="packet-panel"
          onClick={() => setActiveTab("packet")}
          className={`border-b-2 px-4 py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 ${
            activeTab === "packet"
              ? "border-accent text-ink"
              : "border-transparent text-muted hover:border-line hover:text-ink-soft"
          }`}
        >
          Evidence packet
          {packet && (
            <span className="ml-2 bg-mist px-2 py-0.5 text-xs text-ink-soft">
              {packet.selected_documents.length}
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
                onDelete={handleDelete}
                uploading={uploading}
                deletingId={deletingId}
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
                  focusPage={focusPage}
                  highlightQuote={highlightQuote}
                />
              </div>
            </div>
          </div>
        </div>
      ) : activeTab === "evidence" ? (
        <div
          role="tabpanel"
          id="evidence-panel"
          aria-labelledby="evidence-tab"
        >
          <EvidenceCandidates
            candidates={evidenceCandidates}
            onOpenSource={handleOpenEvidenceSource}
          />
        </div>
      ) : activeTab === "requirements" ? (
        <div
          role="tabpanel"
          id="requirements-panel"
          aria-labelledby="requirements-tab"
        >
          <RequirementsChecklist
            evaluation={evaluation}
            loading={evaluationLoading}
            statusChanges={statusChanges}
            onOpenCandidate={handleOpenEvidenceSource}
            onReevaluate={() => void handleReevaluate()}
          />
        </div>
      ) : (
        <div role="tabpanel" id="packet-panel" aria-labelledby="packet-tab">
          <EvidencePacketPanel
            packet={packet}
            loading={packetLoading}
            onOpenDocument={(documentId) =>
              handleOpenEvidenceSource(documentId)
            }
            onRefresh={() => void handleRebuildPacket()}
            onExport={() => void handleExportPacket()}
          />
        </div>
      )}
    </div>
  );
}
