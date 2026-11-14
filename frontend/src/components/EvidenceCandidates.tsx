import type { EvidenceCandidate } from "@/lib/types";

type EvidenceCandidatesProps = {
  candidates: EvidenceCandidate[];
  onOpenSource: (documentId: string) => void;
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

export function EvidenceCandidates({
  candidates,
  onOpenSource,
}: EvidenceCandidatesProps) {
  const groups = groupedCandidates(candidates);

  return (
    <section className="border border-line bg-white/55 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-accent-deep">
            Milestone 2 · policy-driven retrieval
          </p>
          <h2 className="mt-1 font-display text-2xl text-ink">
            Requirement evidence candidates
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Potentially relevant passages retrieved for the fictional active policy.
            Candidates are not accepted evidence until Milestone 3 verifies the policy
            constraints.
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
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-accent-deep">
                        Potential evidence
                      </p>
                      <span className="shrink-0 border border-warning/35 bg-[#fff8ef] px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-warning">
                        Unverified
                      </span>
                    </div>
                    <blockquote className="mt-3 flex-1 border-l-2 border-accent/45 pl-3 text-sm leading-6 text-ink-soft">
                      “{candidate.supporting_quote}”
                    </blockquote>
                    <button
                      type="button"
                      onClick={() => onOpenSource(candidate.document_id)}
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
