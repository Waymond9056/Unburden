"use client";

import type { EvidencePacket } from "@/lib/types";

type EvidencePacketPanelProps = {
  packet: EvidencePacket | null;
  loading?: boolean;
  onOpenDocument: (documentId: string) => void;
  onRefresh: () => void;
  onExport: () => void;
};

function typeLabel(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "Uploaded";
  return trimmed.replaceAll("_", " ");
}

function statusStyles(status: string) {
  switch (status) {
    case "NEEDS_REVIEW":
      return "border-[#c48a2e]/45 bg-[#fff6e8] text-[#8a6230]";
    case "NOT_ESTABLISHED":
      return "border-[#b45656]/40 bg-[#fbeaea] text-[#8f3d3d]";
    default:
      return "border-line bg-mist/60 text-ink-soft";
  }
}

export function EvidencePacketPanel({
  packet,
  loading,
  onOpenDocument,
  onRefresh,
  onExport,
}: EvidencePacketPanelProps) {
  if (loading) {
    return (
      <section className="text-sm text-muted">Building evidence packet…</section>
    );
  }

  if (!packet) {
    return (
      <section className="border-t border-line/70 pt-5">
        <h2 className="font-display text-2xl text-ink">Evidence packet</h2>
        <p className="mt-2 text-sm text-muted">
          No packet yet. Evaluate requirements first, then build the review
          packet.
        </p>
        <button
          type="button"
          onClick={onRefresh}
          className="mt-4 border border-accent bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-deep focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
        >
          Build packet
        </button>
      </section>
    );
  }

  return (
    <section className="space-y-10">
      <div>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-2xl text-ink">Evidence packet</h2>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:items-end">
            <button
              type="button"
              onClick={onExport}
              className="border border-accent bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-deep focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
            >
              Download packet PDF
            </button>
            <button
              type="button"
              onClick={onRefresh}
              className="border border-line bg-white/50 px-3 py-1.5 text-xs text-ink-soft hover:bg-white focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
            >
              Rebuild packet
            </button>
          </div>
        </div>

        <p className="text-xs uppercase tracking-[0.14em] text-muted">
          {packet.selected_documents.length} document
          {packet.selected_documents.length === 1 ? "" : "s"} ·{" "}
          {packet.total_pages} page{packet.total_pages === 1 ? "" : "s"} ·{" "}
          {packet.covered_requirement_ids.length} requirement
          {packet.covered_requirement_ids.length === 1 ? "" : "s"} covered
        </p>

        {packet.selected_documents.length === 0 ? (
          <p className="mt-4 text-sm text-muted">
            No accepted evidence is available to include yet.
          </p>
        ) : (
          <ul className="mt-4 space-y-2">
            {packet.selected_documents.map((doc) => (
              <li key={doc.document_id}>
                <button
                  type="button"
                  onClick={() => onOpenDocument(doc.document_id)}
                  className="w-full border border-[#1b7a6d]/40 bg-[#e7f6f2] px-3 py-3 text-left text-[#0f5a51] hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
                >
                  <div className="font-medium">{doc.source_label}</div>
                  <div className="mt-1 text-xs uppercase tracking-[0.12em]">
                    {typeLabel(doc.document_type)} ·{" "}
                    {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
                  </div>
                  <div className="mt-2 text-sm">
                    Covers: {doc.covers_requirement_titles.join("; ")}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h2 className="font-display text-2xl text-ink">Still needed</h2>
        

        {packet.missing_evidence.length === 0 ? (
          <p className="mt-4 text-sm text-muted">
            No missing documentation items for the current evaluation.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {packet.missing_evidence.map((item) => (
              <li
                key={item.requirement_id}
                className={`border px-3 py-3 ${statusStyles(item.status)}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="font-medium">{item.title}</h3>
                  <span className="text-xs font-semibold uppercase tracking-[0.12em]">
                    {item.status.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6">{item.explanation}</p>
                {item.suggested_document_types.length > 0 && (
                  <p className="mt-2 text-xs uppercase tracking-[0.12em]">
                    Suggested: {item.suggested_document_types.join("; ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
