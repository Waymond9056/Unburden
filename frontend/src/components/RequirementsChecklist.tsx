"use client";

import { useEffect, useRef, useState } from "react";
import { getChertSession, ringDocumentAssistant } from "@/lib/api";
import { DEFAULT_PATIENT_ID } from "@/lib/constants";
import type {
  CandidateStatus,
  ChertSession,
  EvidenceCandidate,
  PolicyEvaluation,
  RequirementEvaluation,
} from "@/lib/types";

export type RequirementStatusChange = {
  requirement_id: string;
  title: string;
  from: string;
  to: string;
};

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
  if (
    status === "ringing" ||
    status === "queued" ||
    status === "dialing" ||
    status === "allocated"
  ) {
    return "ringing";
  }
  if (status === "preparing") return "preparing";
  return "ringing";
}

function ringStatusLabel(phase: RingPhase): string {
  switch (phase) {
    case "preparing":
      return "Preparing FaceTime…";
    case "ringing":
      return "Ringing patient…";
    case "active":
      return "On the call…";
    case "uploaded":
      return "Document uploaded";
    case "failed":
      return "Request failed";
    default:
      return "";
  }
}

type RequirementsChecklistProps = {
  evaluation: PolicyEvaluation | null;
  loading?: boolean;
  statusChanges?: RequirementStatusChange[];
  patientId?: string;
  onOpenCandidate: (
    documentId: string,
    page: number,
    quote?: string,
  ) => void;
  onReevaluate: () => void;
  onUpdateCandidateStatus?: (
    candidateId: string,
    status: CandidateStatus,
  ) => Promise<void> | void;
};

const STATUS_OPTIONS: CandidateStatus[] = [
  "support",
  "insufficient",
  "contradiction",
];

function statusStyles(status: string) {
  switch (status) {
    case "READY":
    case "APPROVED":
    case "support":
    case "SUPPORTED":
    case "accepted":
      return "border-[#1b7a6d]/50 bg-[#e7f6f2] text-[#0f5a51]";
    case "NEEDS_REVIEW":
    case "needs_review":
      return "border-line bg-mist/70 text-muted";
    case "insufficient":
      return "border-[#c48a2e]/45 bg-[#fff6e8] text-[#8a6230]";
    case "contradiction":
    case "NOT_ESTABLISHED":
    case "rejected":
      return "border-[#b45656]/40 bg-[#fbeaea] text-[#8f3d3d]";
    default:
      return "border-line bg-mist/60 text-ink-soft";
  }
}

function citationStatus(candidate: EvidenceCandidate) {
  return (
    candidate.display_status ||
    candidate.clinician_override ||
    candidate.model_status ||
    candidate.verification_status
  );
}

/** Explainable NLI match in [0, 1]: up with entailment, down with contradiction. */
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

function requirementCitations(item: RequirementEvaluation) {
  const merged = [
    ...(item.support_candidates ?? item.supporting_candidates ?? []),
    ...(item.insufficient_candidates ?? item.review_candidates ?? []),
    ...(item.contradiction_candidates ?? []),
  ];
  const seen = new Set<string>();
  const unique: typeof merged = [];
  for (const candidate of merged) {
    if (seen.has(candidate.id)) continue;
    seen.add(candidate.id);
    unique.push(candidate);
  }
  // Highest % match first (stable ties by page / id).
  return unique.sort((a, b) => {
    const scoreDiff = candidateMatchScore(b) - candidateMatchScore(a);
    if (scoreDiff !== 0) return scoreDiff;
    if (a.source_page !== b.source_page) return a.source_page - b.source_page;
    return a.id.localeCompare(b.id);
  });
}

function RequirementBlock({
  item,
  change,
  canRequest,
  requestDisabled,
  requestPhase,
  requestError,
  requestLabel,
  onRequestDocumentation,
  onOpenCandidate,
  onUpdateCandidateStatus,
}: {
  item: RequirementEvaluation;
  change?: RequirementStatusChange;
  canRequest: boolean;
  requestDisabled: boolean;
  requestPhase: RingPhase | null;
  requestError: string | null;
  requestLabel: string | null;
  onRequestDocumentation: () => void;
  onOpenCandidate: (
    documentId: string,
    page: number,
    quote?: string,
  ) => void;
  onUpdateCandidateStatus?: (
    candidateId: string,
    status: CandidateStatus,
  ) => Promise<void> | void;
}) {
  const citations = requirementCitations(item);
  const requestBusy =
    requestPhase === "preparing" ||
    requestPhase === "ringing" ||
    requestPhase === "active";
  return (
    <article
      className={`border-t border-line/70 py-4 ${
        change ? "bg-[#fff8ef]/70 ring-1 ring-[#c48a2e]/35" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-xl text-ink">{item.title}</h3>
          {change && (
            <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#8a6230]">
              Changed · {change.from.replaceAll("_", " ")} →{" "}
              {change.to.replaceAll("_", " ")}
            </p>
          )}
          {item.explanation.trim() && (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-soft">
              {item.explanation}
            </p>
          )}
          {canRequest && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={requestDisabled || requestBusy}
                onClick={onRequestDocumentation}
                className="border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-deep focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {requestBusy ? "Requesting…" : "Request Documentation"}
              </button>
              {requestPhase && requestPhase !== "idle" && (
                <p
                  className={`text-xs ${
                    requestPhase === "failed"
                      ? "text-[#8f3d3d]"
                      : requestPhase === "uploaded"
                        ? "text-[#0f5a51]"
                        : "text-muted"
                  }`}
                >
                  {requestError ||
                    (requestPhase === "uploaded" && requestLabel
                      ? `Uploaded · ${requestLabel}`
                      : ringStatusLabel(requestPhase))}
                </p>
              )}
            </div>
          )}
        </div>
        <span
          className={`border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${statusStyles(item.status)}`}
        >
          {item.status.replaceAll("_", " ")}
        </span>
      </div>

      {citations.length > 0 && (
        <ul className="mt-3 space-y-2">
          {citations.map((candidate) => {
            const colorStatus = citationStatus(candidate);
            const nli = candidateNli(candidate);
            const matchPctCard =
              nli != null ? Math.round(nliMatchScore(nli) * 100) : null;
            return (
              <li key={candidate.id}>
                <div
                  className={`w-full border px-3 py-2 ${statusStyles(colorStatus)}`}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        onOpenCandidate(
                          candidate.document_id,
                          candidate.source_page,
                          candidate.supporting_quote,
                        )
                      }
                      className="text-left text-xs uppercase tracking-[0.12em] hover:underline focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                    >
                      {colorStatus.replaceAll("_", " ")} · page{" "}
                      {candidate.source_page} ·{" "}
                      {candidate.source_document_name || candidate.document_id}
                      {candidate.clinician_override
                        ? " · clinician override"
                        : candidate.model_status
                          ? " · model"
                          : ""}
                    </button>
                    {matchPctCard != null && (
                      <span
                        className="shrink-0 text-xs font-semibold tabular-nums tracking-normal"
                        title="NLI match = ½ + ½×(entailment − contradiction). Color uses TREC cutoffs unless a clinician override is set."
                      >
                        {matchPctCard}% match
                      </span>
                    )}
                  </div>
                  {onUpdateCandidateStatus && (
                    <label className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <span className="uppercase tracking-[0.12em] opacity-80">
                        Set status
                      </span>
                      <select
                        aria-label={`Set status for page ${candidate.source_page}`}
                        className="appearance-none border border-current/30 bg-white/70 bg-[length:12px] bg-[position:right_10px_center] bg-no-repeat py-1 pl-2 pr-8 text-xs capitalize text-ink focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                        style={{
                          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%236b7280' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
                        }}
                        value={colorStatus}
                        onChange={(event) => {
                          void onUpdateCandidateStatus(
                            candidate.id,
                            event.target.value as CandidateStatus,
                          );
                        }}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {STATUS_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

    </article>
  );
}

export function RequirementsChecklist({
  evaluation,
  loading,
  statusChanges = [],
  patientId,
  onOpenCandidate,
  onReevaluate,
  onUpdateCandidateStatus,
}: RequirementsChecklistProps) {
  const canRequest = patientId === DEFAULT_PATIENT_ID;
  const [activeRequirementId, setActiveRequirementId] = useState<string | null>(
    null,
  );
  const [ringPhase, setRingPhase] = useState<RingPhase>("idle");
  const [ringError, setRingError] = useState<string | null>(null);
  const [ringLabel, setRingLabel] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const ringBusy =
    ringPhase === "preparing" ||
    ringPhase === "ringing" ||
    ringPhase === "active";

  useEffect(() => {
    if (!patientId || !canRequest) return;
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
      } catch (err) {
        if (!cancelled) {
          setRingError(
            err instanceof Error ? err.message : "Could not refresh call status",
          );
        }
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [ringPhase, patientId, canRequest]);

  async function handleRequestDocumentation(
    requirementId: string,
    title: string,
  ) {
    if (!patientId || !canRequest || ringBusy) return;
    try {
      setActiveRequirementId(requirementId);
      setRingError(null);
      setRingLabel(null);
      setRingPhase("preparing");
      const session = await ringDocumentAssistant(patientId, {
        requirement_title: title,
      });
      sessionIdRef.current = session.session_id;
      setRingPhase(phaseFromSession(session));
      if (session.error) setRingError(session.error);
    } catch (err) {
      setRingPhase("failed");
      setRingError(
        err instanceof Error ? err.message : "Could not start FaceTime call",
      );
    }
  }

  if (loading && !evaluation) {
    return (
      <section className="text-sm text-muted">
        Evaluating policy requirements…
      </section>
    );
  }

  if (!evaluation) {
    return (
      <section className="border-t border-line/70 pt-5">
        <h2 className="font-display text-2xl text-ink">Insurance requirements</h2>
        <p className="mt-2 text-sm text-muted">
          No evaluation yet. Run verification against the fictional example
          policy.
        </p>
        <button
          type="button"
          onClick={onReevaluate}
          className="mt-4 border border-accent bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-deep focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
        >
          Evaluate policy
        </button>
      </section>
    );
  }

  const changeById = new Map(
    statusChanges.map((change) => [change.requirement_id, change]),
  );

  return (
    <section>
      <div className="mb-4">
        <h2 className="font-display text-2xl text-ink">Insurance requirements</h2>
       
      </div>

      {statusChanges.length > 0 && (
        <div className="mb-4 border border-[#c48a2e]/40 bg-[#fff8ef] px-3 py-2 text-sm text-[#8a6230]">
          {statusChanges.length} requirement
          {statusChanges.length === 1 ? "" : "s"} changed since the last
          evaluation.
        </div>
      )}

      <div className="mt-2">
        {evaluation.requirements.map((item) => {
          const isActive = activeRequirementId === item.requirement_id;
          return (
            <RequirementBlock
              key={item.requirement_id}
              item={item}
              change={changeById.get(item.requirement_id)}
              canRequest={canRequest}
              requestDisabled={ringBusy}
              requestPhase={isActive ? ringPhase : null}
              requestError={isActive ? ringError : null}
              requestLabel={isActive ? ringLabel : null}
              onRequestDocumentation={() =>
                void handleRequestDocumentation(item.requirement_id, item.title)
              }
              onOpenCandidate={onOpenCandidate}
              onUpdateCandidateStatus={onUpdateCandidateStatus}
            />
          );
        })}
      </div>
    </section>
  );
}
