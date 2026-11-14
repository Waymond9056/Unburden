"use client";

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  deleteDocument,
  downloadEvidencePacketPdf,
  evaluatePolicy,
  getDocument,
  getPatient,
  getPolicyEvaluation,
  listDocuments,
  listPolicies,
  reseedDemo,
  updateCandidateStatus,
  uploadDocument,
} from "@/lib/api";
import { DEFAULT_PATIENT_ID } from "@/lib/constants";
import type {
  CandidateStatus,
  DocumentDetail,
  DocumentSummary,
  EvidenceCandidate,
  Patient,
  PolicyEvaluation,
  PolicySummary,
} from "@/lib/types";
import {
  EvidencePacketPanel,
  documentIdsFromPacketSelections,
  eligiblePacketSelectionKeys,
  packetSelectionKey,
} from "./EvidencePacketPanel";
import { DocumentLibrary } from "./DocumentLibrary";
import { DocumentViewer } from "./DocumentViewer";
import {
  RequirementsChecklist,
  type RequirementStatusChange,
} from "./RequirementsChecklist";

const STACKED_LAYOUT = "(max-width: 1023px)";
type WorkspaceTab = "documents" | "requirements" | "packet";

function citationDisplayStatus(candidate: EvidenceCandidate): string {
  return (
    candidate.display_status ||
    candidate.clinician_override ||
    candidate.verification_status
  );
}

/** READY iff ≥1 support and zero contradiction (insufficient is fine). */
function rollupRequirementStatuses(
  evaluation: PolicyEvaluation,
): PolicyEvaluation {
  const requirements = evaluation.requirements.map((item) => {
    const citations = [
      ...(item.support_candidates ?? item.supporting_candidates ?? []),
      ...(item.insufficient_candidates ?? item.review_candidates ?? []),
      ...(item.contradiction_candidates ?? []),
    ];
    const statuses = citations.map(citationDisplayStatus);
    const hasSupport = statuses.includes("support");
    const hasContradiction = statuses.includes("contradiction");
    const status =
      hasContradiction || !hasSupport ? "NEEDS_REVIEW" : "READY";
    return { ...item, status, explanation: "" };
  });

  const statuses = requirements.map((item) => item.status);
  const overall =
    evaluation.logic.toUpperCase() === "OR"
      ? statuses.includes("READY")
        ? "READY"
        : "NEEDS_REVIEW"
      : statuses.length > 0 && statuses.every((s) => s === "READY")
        ? "READY"
        : "NEEDS_REVIEW";

  return { ...evaluation, overall_status: overall, requirements };
}

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

export function Dashboard({ patientId }: { patientId: string }) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [policies, setPolicies] = useState<PolicySummary[]>([]);
  const [policyId, setPolicyId] = useState<string>(
    "fictional-severe-asthma-policy",
  );
  const [evaluation, setEvaluation] = useState<PolicyEvaluation | null>(null);
  const policyIdRef = useRef(policyId);
  const [selectedPacketKeys, setSelectedPacketKeys] = useState<string[]>([]);
  const [statusChanges, setStatusChanges] = useState<RequirementStatusChange[]>(
    [],
  );
  const [evaluationLoading, setEvaluationLoading] = useState(false);
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

  function syncPacketSelection(nextEvaluation: PolicyEvaluation) {
    const eligible = new Set(eligiblePacketSelectionKeys(nextEvaluation));
    setSelectedPacketKeys((previous) => {
      const kept = previous.filter((key) => eligible.has(key));
      const keptSet = new Set(kept);
      // Newly support-eligible options start checked (per requirement).
      const added = [...eligible].filter((key) => !keptSet.has(key));
      return [...kept, ...added];
    });
  }

  function applyEvaluation(nextEvaluation: PolicyEvaluation) {
    const normalized = rollupRequirementStatuses(nextEvaluation);
    if (skipStatusDiffRef.current) {
      skipStatusDiffRef.current = false;
      setStatusChanges([]);
    } else {
      setStatusChanges(
        diffRequirementStatuses(previousEvaluationRef.current, normalized),
      );
    }
    previousEvaluationRef.current = normalized;
    setEvaluation(normalized);
    syncPacketSelection(normalized);
  }

  function applyCandidateOverrideLocally(
    current: PolicyEvaluation,
    updated: EvidenceCandidate,
    status: CandidateStatus,
  ): PolicyEvaluation {
    const requirements = current.requirements.map((item) => {
      if (item.requirement_id !== updated.requirement_id) return item;

      const patched = (candidate: EvidenceCandidate): EvidenceCandidate =>
        candidate.id !== updated.id
          ? candidate
          : {
              ...candidate,
              ...updated,
              clinician_override: status,
              display_status: status,
              verification_status: status,
            };

      const existing = [
        ...(item.support_candidates ?? item.supporting_candidates ?? []),
        ...(item.insufficient_candidates ?? item.review_candidates ?? []),
        ...(item.contradiction_candidates ?? []),
      ];
      const merged = existing.some((c) => c.id === updated.id)
        ? existing.map(patched)
        : [
            ...existing.map(patched),
            {
              ...updated,
              display_status: status,
              clinician_override: status,
              verification_status: status,
            },
          ];

      const bucket = (s: CandidateStatus) =>
        merged.filter(
          (c) => (c.display_status || c.verification_status) === s,
        );

      // Keep `merged` order so status switches do not reshuffle the checklist.
      const support = bucket("support");
      const insufficient = bucket("insufficient");
      const contradiction = bucket("contradiction");
      const nextStatus =
        contradiction.length > 0 || support.length === 0
          ? "NEEDS_REVIEW"
          : "READY";

      return {
        ...item,
        status: nextStatus,
        explanation: "",
        support_candidate_ids: support.map((c) => c.id),
        insufficient_candidate_ids: insufficient.map((c) => c.id),
        contradiction_candidate_ids: contradiction.map((c) => c.id),
        support_candidates: merged.filter((c) => support.some((s) => s.id === c.id)),
        insufficient_candidates: merged.filter((c) =>
          insufficient.some((s) => s.id === c.id),
        ),
        contradiction_candidates: merged.filter((c) =>
          contradiction.some((s) => s.id === c.id),
        ),
        supporting_candidates: undefined,
        review_candidates: undefined,
      };
    });

    const statuses = requirements.map((r) => r.status);
    const overall =
      current.logic.toUpperCase() === "OR"
        ? statuses.includes("READY")
          ? "READY"
          : "NEEDS_REVIEW"
        : statuses.every((s) => s === "READY")
          ? "READY"
          : "NEEDS_REVIEW";

    return { ...current, overall_status: overall, requirements };
  }

  async function refreshLibrary(selectId?: string | null) {
    const [nextPatient, nextDocs, nextPolicies] = await Promise.all([
      getPatient(patientId),
      listDocuments(patientId),
      listPolicies(),
    ]);
    setPolicies(nextPolicies);
    const activePolicyId =
      nextPolicies.some((policy) => policy.id === policyIdRef.current)
        ? policyIdRef.current
        : (nextPolicies[0]?.id ?? policyIdRef.current);
    if (activePolicyId !== policyIdRef.current) {
      setPolicyId(activePolicyId);
    }
    const nextEvaluation = await getPolicyEvaluation(
      patientId,
      activePolicyId,
    );
    setPatient(nextPatient);
    setDocuments(nextDocs);
    applyEvaluation(nextEvaluation);
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
    policyIdRef.current = policyId;
  }, [policyId]);

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
        const detail = await getDocument(patientId, id);
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
  }, [selectedId, patientId]);

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

  async function handlePolicyChange(nextPolicyId: string) {
    if (nextPolicyId === policyId) return;
    setPolicyId(nextPolicyId);
    try {
      setError(null);
      setEvaluationLoading(true);
      skipStatusDiffRef.current = true;
      const nextEvaluation = await getPolicyEvaluation(
        patientId,
        nextPolicyId,
      );
      applyEvaluation(nextEvaluation);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load insurance policy",
      );
    } finally {
      setEvaluationLoading(false);
    }
  }

  async function handleReevaluate() {
    try {
      setError(null);
      setEvaluationLoading(true);
      const nextEvaluation = await evaluatePolicy(patientId, policyId);
      const changes = diffRequirementStatuses(
        previousEvaluationRef.current,
        rollupRequirementStatuses(nextEvaluation),
      );
      applyEvaluation(nextEvaluation);
      if (changes.length > 0) setActiveTab("requirements");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setEvaluationLoading(false);
    }
  }

  async function handleUpdateCandidateStatus(
    candidateId: string,
    status: CandidateStatus,
  ) {
    const previous = previousEvaluationRef.current;
    try {
      setError(null);
      // Optimistic local update — never blank the checklist or re-run DeBERTa.
      const syncEvaluation = (next: PolicyEvaluation) => {
        const normalized = rollupRequirementStatuses(next);
        previousEvaluationRef.current = normalized;
        setEvaluation(normalized);
        syncPacketSelection(normalized);
      };

      if (previous) {
        const provisional: EvidenceCandidate = {
          id: candidateId,
          patient_id: patientId,
          document_id: "",
          policy_id: previous.policy_id,
          requirement_id: "",
          requirement_title: "",
          source_page: 0,
          supporting_quote: "",
          extracted_details: {},
          relevance_score: 0,
          retrieval_method: "",
          verification_status: status,
          created_at: "",
          source_document_name: null,
          source_document_type: null,
          clinician_override: status,
          display_status: status,
        };
        for (const item of previous.requirements) {
          const hit = [
            ...(item.support_candidates ?? item.supporting_candidates ?? []),
            ...(item.insufficient_candidates ?? item.review_candidates ?? []),
            ...(item.contradiction_candidates ?? []),
          ].find((c) => c.id === candidateId);
          if (hit) {
            provisional.requirement_id = item.requirement_id;
            provisional.document_id = hit.document_id;
            provisional.source_page = hit.source_page;
            provisional.supporting_quote = hit.supporting_quote;
            provisional.source_document_name = hit.source_document_name;
            provisional.nli = hit.nli;
            provisional.model_status = hit.model_status;
            break;
          }
        }
        syncEvaluation(
          applyCandidateOverrideLocally(previous, provisional, status),
        );
      }

      const updated = await updateCandidateStatus(
        patientId,
        candidateId,
        status,
      );
      if (previousEvaluationRef.current) {
        syncEvaluation(
          applyCandidateOverrideLocally(
            previousEvaluationRef.current,
            updated,
            status,
          ),
        );
      }

      // Background sync with cached-NLI evaluation (no loading overlay).
      void getPolicyEvaluation(patientId, policyIdRef.current)
        .then((nextEvaluation) => {
          syncEvaluation(nextEvaluation);
        })
        .catch(() => {
          /* keep optimistic UI */
        });
    } catch (err) {
      if (previous) {
        previousEvaluationRef.current = previous;
        setEvaluation(previous);
        syncPacketSelection(previous);
      }
      setError(
        err instanceof Error ? err.message : "Failed to update citation status",
      );
    }
  }

  function handleTogglePacketSelection(
    requirementId: string,
    documentId: string,
    selected: boolean,
  ) {
    const key = packetSelectionKey(requirementId, documentId);
    setSelectedPacketKeys((previous) => {
      if (selected) {
        return previous.includes(key) ? previous : [...previous, key];
      }
      return previous.filter((item) => item !== key);
    });
  }

  async function handleExportPacket() {
    try {
      setError(null);
      await downloadEvidencePacketPdf(
        patientId,
        documentIdsFromPacketSelections(selectedPacketKeys),
        policyId,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Packet export failed");
    }
  }

  async function handleUpload(file: File) {
    try {
      setUploading(true);
      setError(null);
      const created = await uploadDocument(patientId, file);
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
        flushSync(() => {
          setSelectedId(null);
          setSelectedDoc(null);
          setFocusPage(null);
          setHighlightQuote(null);
        });
      }
      await deleteDocument(patientId, documentId);
      await refreshLibrary(selectedId === documentId ? null : selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleReseed() {
    const confirmed = window.confirm(
      "Reload Raymond Yao’s demo documents? That chart’s uploaded PDFs will be removed. Other patients are left alone.",
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
      {patient && (
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-y border-line/80 py-4">
          <div>
            <p className="font-display text-2xl text-ink">
              {patient.display_name}
            </p>
            <p className="text-sm text-muted">
              DOB {patient.date_of_birth ?? "—"}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            {policies.length > 0 && (
              <label className="flex flex-col gap-1 text-sm text-ink-soft">
                <span className="text-xs uppercase tracking-[0.12em] text-muted">
                  Insurance
                </span>
                <select
                  className="w-auto appearance-none border border-line bg-white/70 bg-[length:12px] bg-[position:right_12px_center] bg-no-repeat py-2 pl-3 pr-9 text-sm text-ink [field-sizing:content] focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                  style={{
                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%23465c61' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
                  }}
                  value={policyId}
                  onChange={(event) => {
                    void handlePolicyChange(event.target.value);
                  }}
                >
                  {policies.map((policy) => (
                    <option key={policy.id} value={policy.id}>
                      {policy.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {patientId === DEFAULT_PATIENT_ID && (
              <button
                type="button"
                onClick={() => void handleReseed()}
                className="border border-line bg-white/50 px-4 py-2 text-sm text-ink-soft hover:border-ink/30 hover:bg-white focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
              >
                Reload demo documents
              </button>
            )}
          </div>
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
          {documentIdsFromPacketSelections(selectedPacketKeys).length > 0 && (
            <span className="ml-2 bg-mist px-2 py-0.5 text-xs text-ink-soft">
              {documentIdsFromPacketSelections(selectedPacketKeys).length}
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
                  patientId={patientId}
                  document={visibleDoc}
                  loading={docLoading}
                  focusPage={focusPage}
                  highlightQuote={highlightQuote}
                />
              </div>
            </div>
          </div>
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
            onUpdateCandidateStatus={(candidateId, status) =>
              handleUpdateCandidateStatus(candidateId, status)
            }
          />
        </div>
      ) : (
        <div role="tabpanel" id="packet-panel" aria-labelledby="packet-tab">
          <EvidencePacketPanel
            evaluation={evaluation}
            documents={documents}
            selectedKeys={selectedPacketKeys}
            onToggleSelection={handleTogglePacketSelection}
            onOpenDocument={(documentId) =>
              handleOpenEvidenceSource(documentId)
            }
            onExport={() => void handleExportPacket()}
          />
        </div>
      )}
    </div>
  );
}
