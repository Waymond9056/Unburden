"use client";

import type {
  DocumentSummary,
  EvidenceCandidate,
  PolicyEvaluation,
  RequirementEvaluation,
} from "@/lib/types";

/** Selection key scoped to one requirement so checkboxes don't cross-link. */
export function packetSelectionKey(
  requirementId: string,
  documentId: string,
): string {
  return `${requirementId}::${documentId}`;
}

export function documentIdsFromPacketSelections(keys: string[]): string[] {
  const ids = new Set<string>();
  for (const key of keys) {
    const sep = key.indexOf("::");
    if (sep < 0) continue;
    const documentId = key.slice(sep + 2);
    if (documentId) ids.add(documentId);
  }
  return [...ids];
}

type EvidencePacketPanelProps = {
  evaluation: PolicyEvaluation | null;
  documents: DocumentSummary[];
  /** Per-requirement selections: `${requirementId}::${documentId}` */
  selectedKeys: string[];
  onToggleSelection: (
    requirementId: string,
    documentId: string,
    selected: boolean,
  ) => void;
  onOpenDocument: (documentId: string) => void;
  onExport: () => void;
};

function typeLabel(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "Uploaded";
  return trimmed.replaceAll("_", " ");
}

function citationIsSupport(candidate: EvidenceCandidate) {
  const status =
    candidate.display_status ||
    candidate.clinician_override ||
    candidate.model_status ||
    candidate.verification_status;
  return status === "support" || status === "accepted" || status === "SUPPORTED";
}

/** Same formula as requirements checklist: up with support, down with contradiction. */
function nliMatchScore(nli: {
  entailment?: number | null;
  support?: number | null;
  support_probability?: number | null;
  contradiction: number;
}): number {
  const entailment =
    nli.entailment ?? nli.support ?? nli.support_probability ?? 0;
  return 0.5 + 0.5 * (entailment - nli.contradiction);
}

function candidateNli(candidate: EvidenceCandidate) {
  if (candidate.nli != null) return candidate.nli;
  const raw = candidate.extracted_details?.nli;
  if (!raw || typeof raw !== "object") return null;
  const nli = raw as Record<string, unknown>;
  try {
    const support = Number(
      nli.support ?? nli.entailment ?? nli.support_probability,
    );
    const contradiction = Number(nli.contradiction);
    if (!Number.isFinite(support) || !Number.isFinite(contradiction)) {
      return null;
    }
    return {
      support,
      insufficient: Number(nli.insufficient ?? nli.neutral ?? 0),
      contradiction,
      support_probability: support,
      entailment: support,
      neutral: Number(nli.neutral ?? nli.insufficient ?? 0),
      predicted_label: String(nli.predicted_label ?? ""),
      model_name: String(nli.model_name ?? ""),
    };
  } catch {
    return null;
  }
}

function candidateMatchScore(candidate: EvidenceCandidate): number {
  const nli = candidateNli(candidate);
  return nli != null ? nliMatchScore(nli) : -1;
}

function supportCandidatesFor(item: RequirementEvaluation) {
  const all = [
    ...(item.support_candidates ?? item.supporting_candidates ?? []),
    ...(item.insufficient_candidates ?? item.review_candidates ?? []),
    ...(item.contradiction_candidates ?? []),
  ];
  // Prefer the highest-%-match citation when the same document appears twice.
  const bestByDoc = new Map<string, EvidenceCandidate>();
  for (const candidate of all) {
    if (!citationIsSupport(candidate)) continue;
    const existing = bestByDoc.get(candidate.document_id);
    if (
      !existing ||
      candidateMatchScore(candidate) > candidateMatchScore(existing)
    ) {
      bestByDoc.set(candidate.document_id, candidate);
    }
  }
  return [...bestByDoc.values()].sort((a, b) => {
    const scoreDiff = candidateMatchScore(b) - candidateMatchScore(a);
    if (scoreDiff !== 0) return scoreDiff;
    if (a.source_page !== b.source_page) return a.source_page - b.source_page;
    return a.id.localeCompare(b.id);
  });
}

export function EvidencePacketPanel({
  evaluation,
  documents,
  selectedKeys,
  onToggleSelection,
  onOpenDocument,
  onExport,
}: EvidencePacketPanelProps) {
  const docById = new Map(documents.map((doc) => [doc.id, doc]));
  const selected = new Set(selectedKeys);

  if (!evaluation) {
    return (
      <section className="border-t border-line/70 pt-5">
        <h2 className="font-display text-2xl text-ink">Evidence packet</h2>
        <p className="mt-2 text-sm text-muted">
          Evaluate insurance requirements first, then choose which supporting
          documents to include in the packet.
        </p>
      </section>
    );
  }

  const exportDocCount = documentIdsFromPacketSelections(selectedKeys).length;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-2xl text-ink">Evidence packet</h1>
        <button
          type="button"
          onClick={onExport}
          disabled={exportDocCount === 0}
          className="border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-deep disabled:cursor-not-allowed disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
        >
          Download packet PDF
          {exportDocCount > 0 ? ` (${exportDocCount})` : ""}
        </button>
      </div>

      <div className="space-y-6">
        {evaluation.requirements.map((item) => {
          const options = supportCandidatesFor(item);
          return (
            <div key={item.requirement_id} className="border-t border-line/70 pt-4">
              <h3 className="font-display text-xl text-ink">{item.title}</h3>

              {options.length === 0 ? (
                <p className="mt-3 text-sm text-muted">
                  No supporting documents for this requirement yet.
                </p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {options.map((candidate) => {
                    const doc = docById.get(candidate.document_id);
                    const label =
                      candidate.source_document_name ||
                      doc?.source_label ||
                      doc?.original_filename ||
                      candidate.document_id;
                    const docType =
                      candidate.source_document_type ||
                      doc?.document_type ||
                      "";
                    const pages = doc?.page_count;
                    const key = packetSelectionKey(
                      item.requirement_id,
                      candidate.document_id,
                    );
                    const checked = selected.has(key);
                    const nli = candidateNli(candidate);
                    const matchPct =
                      nli != null ? Math.round(nliMatchScore(nli) * 100) : null;
                    return (
                      <li key={key}>
                        <label
                          className={`flex cursor-pointer items-start gap-3 border px-3 py-3 ${
                            checked
                              ? "border-[#1b7a6d]/40 bg-[#e7f6f2] text-[#0f5a51]"
                              : "border-line bg-white/50 text-ink-soft"
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={checked}
                            onChange={(event) =>
                              onToggleSelection(
                                item.requirement_id,
                                candidate.document_id,
                                event.target.checked,
                              )
                            }
                          />
                          <span className="min-w-0 flex-1">
                            <span className="flex flex-wrap items-baseline justify-between gap-2">
                              <button
                                type="button"
                                className="text-left font-medium hover:underline focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                                onClick={(event) => {
                                  event.preventDefault();
                                  onOpenDocument(candidate.document_id);
                                }}
                              >
                                {label}
                              </button>
                              {matchPct != null && (
                                <span className="shrink-0 text-xs font-semibold tabular-nums">
                                  {matchPct}% match
                                </span>
                              )}
                            </span>
                            <div className="mt-1 text-xs uppercase tracking-[0.12em]">
                              {typeLabel(docType)}
                              {pages != null
                                ? ` · ${pages} page${pages === 1 ? "" : "s"}`
                                : ""}
                              {` · page ${candidate.source_page}`}
                            </div>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Per-requirement selection keys currently eligible (display_status = support). */
export function eligiblePacketSelectionKeys(
  evaluation: PolicyEvaluation | null,
): string[] {
  if (!evaluation) return [];
  const keys: string[] = [];
  for (const item of evaluation.requirements) {
    for (const candidate of supportCandidatesFor(item)) {
      keys.push(
        packetSelectionKey(item.requirement_id, candidate.document_id),
      );
    }
  }
  return keys;
}
