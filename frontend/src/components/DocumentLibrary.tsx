"use client";

import type { DocumentSummary } from "@/lib/types";

type DocumentLibraryProps = {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUpload: (file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  uploading: boolean;
  deletingId?: string | null;
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

function typeLabel(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "Uploaded";
  return trimmed.replaceAll("_", " ");
}

export function DocumentLibrary({
  documents,
  selectedId,
  onSelect,
  onUpload,
  onDelete,
  uploading,
  deletingId = null,
}: DocumentLibraryProps) {
  return (
    <section className="flex h-full min-h-0 flex-col">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl text-ink">Documents</h2>
         
        </div>
        <label
          className={`relative cursor-pointer border border-accent bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-deep focus-within:ring-2 focus-within:ring-ink focus-within:ring-offset-2 focus-within:ring-offset-paper ${
            uploading ? "uploading-pulse pointer-events-none opacity-70" : ""
          }`}
        >
          {uploading ? "Uploading…" : "Upload PDF"}
          <input
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
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
            const name = doc.source_label || doc.original_filename;
            const deleting = deletingId === doc.id;
            return (
              <li key={doc.id} className="flex items-stretch gap-1">
                <button
                  type="button"
                  title={name}
                  onClick={() => onSelect(doc.id)}
                  className={`min-w-0 flex-1 border-l-2 px-3 py-3 text-left ${
                    active
                      ? "border-accent bg-white/70"
                      : "border-transparent hover:border-line hover:bg-white/40"
                  }`}
                >
                  <div
                    className={`text-sm font-medium text-ink ${
                      active ? "whitespace-normal break-words" : "truncate"
                    }`}
                  >
                    {name}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="capitalize">{typeLabel(doc.document_type)}</span>
                    <span>
                      {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
                    </span>
                    <span>{formatDate(doc.uploaded_at)}</span>
                  </div>
                </button>
                <button
                  type="button"
                  disabled={deleting || uploading}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onDelete(doc.id);
                  }}
                  className="shrink-0 self-center px-2 py-1 text-xs text-[#8f3d3d] hover:bg-[#fbeaea] disabled:opacity-50"
                  aria-label={`Delete ${name}`}
                >
                  {deleting ? "…" : "Delete"}
                </button>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
