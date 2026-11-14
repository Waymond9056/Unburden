import type { EvidenceCandidate } from "@/lib/types";

type EvidenceCandidatesProps = {
  candidates: EvidenceCandidate[];
  onOpenSource: (documentId: string, page: number, quote?: string) => void;
};

function groupedCandidates(candidates: EvidenceCandidate[]) {
  const groups = new Map<string, EvidenceCandidate[]>();
  for (const candidate of candidates) {
    const existing = groups.get(candidate.requirement_id) ?? [];
    existing.push(candidate);
    groups.set(candidate.requirement_id, existing);
  }
  return [...groups.values()];
}

function statusLabel(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "unverified_candidate") return "Unverified";
  return trimmed.replaceAll("_", " ");
}

function statusStyles(status: string) {
  switch (status) {
    case "accepted":
      return "border-[#1b7a6d]/50 bg-[#e7f6f2] text-[#0f5a51]";
    case "needs_review":
      return "border-[#c48a2e]/45 bg-[#fff6e8] text-[#8a6230]";
    case "rejected":
      return "border-[#b45656]/40 bg-[#fbeaea] text-[#8f3d3d]";
    default:
      return "border-line bg-mist/60 text-ink-soft";
  }
}

export function EvidenceCandidates({
  candidates,
  onOpenSource,
}: EvidenceCandidatesProps) {
  const groups = groupedCandidates(candidates);

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Requirement evidence</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Passages retrieved for the fictional policy, labeled with their
            verification status.
          </p>
        </div>
        <div className="text-sm text-muted">
          {candidates.length} candidate{candidates.length === 1 ? "" : "s"}
        </div>
      </div>

      {groups.length === 0 ? (
        <p className="mt-5 border-t border-line pt-5 text-sm text-muted">
          No passages matched the active policy requirements.
        </p>
      ) : (
        <div className="mt-5 space-y-5">
          {groups.map((group) => (
            <section key={group[0].requirement_id}>
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-2">
                <h3 className="font-display text-lg text-ink">
                  {group[0].requirement_title}
                </h3>
                <span className="text-xs uppercase tracking-[0.1em] text-muted">
                  {group.length} retrieved
                </span>
              </div>
              <ul className="mt-3 grid gap-3 lg:grid-cols-2">
                {group.map((candidate) => (
                  <li
                    key={candidate.id}
                    className="flex min-w-0 flex-col border border-line bg-paper/55 p-4"
                  >
                    <span
                      className={`self-start border px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${statusStyles(candidate.verification_status)}`}
                    >
                      {statusLabel(candidate.verification_status)}
                    </span>
                    <blockquote className="mt-3 flex-1 border-l-2 border-accent/45 pl-3 text-sm leading-6 text-ink-soft">
                      “{candidate.supporting_quote}”
                    </blockquote>
                    <button
                      type="button"
                      onClick={() =>
                        onOpenSource(
                          candidate.document_id,
                          candidate.source_page,
                          candidate.supporting_quote,
                        )
                      }
                      className="mt-4 self-start text-left text-xs font-medium text-accent-deep underline decoration-accent/35 underline-offset-4 hover:decoration-accent-deep focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                    >
                      {candidate.source_document_name || "Source document"} · page{" "}
                      {candidate.source_page}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
