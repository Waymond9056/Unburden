"use client";

import { documentFileUrl } from "@/lib/api";
import type { DocumentDetail } from "@/lib/types";

type DocumentViewerProps = {
  patientId: string;
  document: DocumentDetail | null;
  loading: boolean;
};

export function DocumentViewer({
  patientId,
  document,
  loading,
}: DocumentViewerProps) {
  if (loading) {
    return (
      <section className="animate-fade flex h-full items-center justify-center text-sm text-muted">
        Loading document…
      </section>
    );
  }

  if (!document) {
    return (
      <section className="animate-fade flex h-full items-center justify-center px-6 text-center text-sm text-muted">
        Select a document to preview the PDF and extracted text.
      </section>
    );
  }

  return (
    <section className="animate-rise stagger-3 flex h-full min-h-0 flex-col gap-4">
      <header>
        <h2 className="font-display text-2xl text-ink">
          {document.source_label || document.original_filename}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {document.original_filename} · {document.page_count} page
          {document.page_count === 1 ? "" : "s"} · extracted with page
          boundaries preserved
        </p>
      </header>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <div className="flex min-h-[320px] flex-col border border-line bg-white/60">
          <div className="border-b border-line px-3 py-2 text-xs uppercase tracking-[0.14em] text-muted">
            PDF preview
          </div>
          <iframe
            title={`PDF preview ${document.original_filename}`}
            src={documentFileUrl(patientId, document.id)}
            className="min-h-0 flex-1 w-full bg-white"
          />
        </div>

        <div className="flex min-h-[320px] flex-col border border-line bg-white/60">
          <div className="border-b border-line px-3 py-2 text-xs uppercase tracking-[0.14em] text-muted">
            Extracted text
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
            {document.pages.map((page) => (
              <article key={page.page_number}>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent-deep">
                  Page {page.page_number}
                </h3>
                <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-ink-soft">
                  {page.text || "(No extractable text on this page)"}
                </pre>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
