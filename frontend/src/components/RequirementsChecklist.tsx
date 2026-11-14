"use client";

import type { PolicyEvaluation, RequirementEvaluation } from "@/lib/types";

export type RequirementStatusChange = {
  requirement_id: string;
  title: string;
  from: string;
  to: string;
};

type RequirementsChecklistProps = {
  evaluation: PolicyEvaluation | null;
  loading?: boolean;
  statusChanges?: RequirementStatusChange[];
  onOpenCandidate: (
    documentId: string,
    page: number,
    quote?: string,
  ) => void;
  onReevaluate: () => void;
};

function statusStyles(status: string) {
  switch (status) {
    case "SUPPORTED":
    case "accepted":
      return "border-[#1b7a6d]/50 bg-[#e7f6f2] text-[#0f5a51]";
    case "NEEDS_REVIEW":
    case "needs_review":
      return "border-[#c48a2e]/45 bg-[#fff6e8] text-[#8a6230]";
    case "NOT_ESTABLISHED":
    case "rejected":
      return "border-[#b45656]/40 bg-[#fbeaea] text-[#8f3d3d]";
    default:
      return "border-line bg-mist/60 text-ink-soft";
  }
}

function RequirementBlock({
  item,
  change,
  onOpenCandidate,
}: {
  item: RequirementEvaluation;
  change?: RequirementStatusChange;
  onOpenCandidate: (
    documentId: string,
    page: number,
    quote?: string,
  ) => void;
}) {
  const citations = [...item.supporting_candidates, ...item.review_candidates];
  return (
    <article
      className={`border-t border-line/70 py-4 ${
        change ? "bg-[#fff8ef]/70 ring-1 ring-[#c48a2e]/35" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-xl text-ink">{item.title}</h3>
          {change && (
            <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#8a6230]">
              Changed · {change.from.replaceAll("_", " ")} →{" "}
              {change.to.replaceAll("_", " ")}
            </p>
          )}
          <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-soft">
            {item.explanation}
          </p>
        </div>
        <span
          className={`border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${statusStyles(item.status)}`}
        >
          {item.status.replaceAll("_", " ")}
        </span>
      </div>

      {citations.length > 0 && (
        <ul className="mt-3 space-y-2">
          {citations.map((candidate) => (
            <li key={candidate.id}>
              <button
                type="button"
                onClick={() =>
                  onOpenCandidate(
                    candidate.document_id,
                    candidate.source_page,
                    candidate.supporting_quote,
                  )
                }
                className={`w-full border px-3 py-2 text-left hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 ${statusStyles(candidate.verification_status)}`}
              >
                <div className="text-xs uppercase tracking-[0.12em]">
                  {candidate.verification_status.replaceAll("_", " ")} · page{" "}
                  {candidate.source_page} ·{" "}
                  {candidate.source_document_name || candidate.document_id}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {item.status === "NOT_ESTABLISHED" &&
        item.suggested_document_types.length > 0 && (
          <p className="mt-3 text-sm text-muted">
            Suggested documentation:{" "}
            {item.suggested_document_types.join("; ")}.
          </p>
        )}
    </article>
  );
}

export function RequirementsChecklist({
  evaluation,
  loading,
  statusChanges = [],
  onOpenCandidate,
  onReevaluate,
}: RequirementsChecklistProps) {
  if (loading) {
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
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Insurance requirements</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-ink-soft">
            {evaluation.policy_name}
          </p>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-muted">
            {evaluation.disclaimer}
          </p>
        </div>
        <div className="text-right">
          <div
            className={`inline-block border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${statusStyles(evaluation.overall_status)}`}
          >
            {evaluation.overall_status.replaceAll("_", " ")}
          </div>
          <button
            type="button"
            onClick={onReevaluate}
            className="mt-2 block border border-line bg-white/50 px-3 py-1.5 text-xs text-ink-soft hover:bg-white focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
          >
            Re-evaluate
          </button>
        </div>
      </div>

      {statusChanges.length > 0 && (
        <div className="mb-4 border border-[#c48a2e]/40 bg-[#fff8ef] px-3 py-2 text-sm text-[#8a6230]">
          {statusChanges.length} requirement
          {statusChanges.length === 1 ? "" : "s"} changed since the last
          evaluation.
        </div>
      )}

      <p className="text-xs uppercase tracking-[0.14em] text-muted">
        Logic {evaluation.logic} · as of {evaluation.as_of_date}
      </p>

      <div className="mt-2">
        {evaluation.requirements.map((item) => (
          <RequirementBlock
            key={item.requirement_id}
            item={item}
            change={changeById.get(item.requirement_id)}
            onOpenCandidate={onOpenCandidate}
          />
        ))}
      </div>
    </section>
  );
}
