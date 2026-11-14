"use client";

import type { DocumentSummary } from "@/lib/types";

type DocumentLibraryProps = {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUpload: (file: File) => Promise<void>;
  uploading: boolean;
};

function formatDate(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function prettyType(value: string) {
  return value.replaceAll("_", " ");
}

export function DocumentLibrary({
  documents,
  selectedId,
  onSelect,
  onUpload,
  uploading,
}: DocumentLibraryProps) {
  return (
    <section className="animate-rise stagger-2 flex h-full min-h-0 flex-col">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Document library</h2>
          <p className="mt-1 text-sm text-muted">
            Upload PDFs and inspect extracted page text.
          </p>
        </div>
        <label
          className={`cursor-pointer border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-deep ${
            uploading ? "uploading-pulse pointer-events-none opacity-70" : ""
          }`}
        >
          {uploading ? "Uploading…" : "Upload PDF"}
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            disabled={uploading}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) await onUpload(file);
            }}
          />
        </label>
      </div>

      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto border-y border-line/80 py-2">
        {documents.length === 0 ? (
          <li className="px-1 py-8 text-sm text-muted">
            No documents yet. Upload a PDF or reload the demo set.
          </li>
        ) : (
          documents.map((doc) => {
            const active = doc.id === selectedId;
            return (
              <li key={doc.id}>
                <button
                  type="button"
                  onClick={() => onSelect(doc.id)}
                  className={`w-full border-l-2 px-3 py-3 text-left transition ${
                    active
                      ? "border-accent bg-white/70"
                      : "border-transparent hover:border-line hover:bg-white/40"
                  }`}
                >
                  <div className="truncate text-sm font-medium text-ink">
                    {doc.source_label || doc.original_filename}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="capitalize">{prettyType(doc.document_type)}</span>
                    <span>
                      {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
                    </span>
                    <span>{formatDate(doc.uploaded_at)}</span>
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
