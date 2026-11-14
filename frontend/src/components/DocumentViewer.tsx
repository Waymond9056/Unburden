"use client";

import { useEffect, useRef } from "react";
import { documentFileUrl } from "@/lib/api";
import type { DocumentDetail } from "@/lib/types";

type DocumentViewerProps = {
  patientId: string;
  document: DocumentDetail | null;
  loading: boolean;
  focusPage?: number | null;
  highlightQuote?: string | null;
};

export function DocumentViewer({
  patientId,
  document,
  loading,
  focusPage = null,
  highlightQuote = null,
}: DocumentViewerProps) {
  const pageRefs = useRef<Map<number, HTMLElement>>(new Map());

  useEffect(() => {
    if (!document || !focusPage) return;
    const node = pageRefs.current.get(focusPage);
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [document?.id, focusPage, highlightQuote]);

  if (loading) {
    return (
      <section className="flex h-full items-center justify-center text-sm text-muted">
        Loading document…
      </section>
    );
  }

  if (!document) {
    return (
      <section className="flex h-full items-center justify-center px-6 text-center text-sm text-muted">
        Select a document to preview the PDF and extracted text.
      </section>
    );
  }

  const pdfSrc =
    focusPage && focusPage > 0
      ? `${documentFileUrl(patientId, document.id)}#page=${focusPage}`
      : documentFileUrl(patientId, document.id);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <div className="flex min-h-[320px] flex-col border border-line bg-white/60">
          <iframe
            key={`${document.id}-${focusPage ?? "all"}`}
            title={`PDF preview ${document.original_filename}`}
            src={pdfSrc}
            className="min-h-0 flex-1 w-full bg-white"
          />
        </div>

        <div className="flex min-h-[320px] flex-col border border-line bg-white/60">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
            {document.pages.map((page) => {
              const focused = focusPage === page.page_number;
              const quote = highlightQuote?.trim();
              const showQuote =
                focused && quote && page.text.includes(quote) ? quote : null;
              return (
                <article
                  key={page.page_number}
                  ref={(node) => {
                    if (node) pageRefs.current.set(page.page_number, node);
                    else pageRefs.current.delete(page.page_number);
                  }}
                  className={
                    focused
                      ? "rounded-sm border border-accent/50 bg-[#e7f6f2]/70 p-3"
                      : ""
                  }
                >
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent-deep">
                    Page {page.page_number}
                    {focused ? " · citation" : ""}
                  </h3>
                  {showQuote ? (
                    <p className="mb-3 border-l-2 border-accent pl-3 text-sm leading-6 text-ink">
                      “{showQuote}”
                    </p>
                  ) : null}
                  <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-ink-soft">
                    {page.text || "(No extractable text on this page)"}
                  </pre>
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
