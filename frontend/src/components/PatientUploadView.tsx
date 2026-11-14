"use client";

import { useState } from "react";
import { uploadDocument } from "@/lib/api";

export function PatientUploadView({
  patientId,
  patientName,
}: {
  patientId: string;
  patientName: string;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<string | null>(null);

  async function handleUpload(file: File) {
    try {
      setUploading(true);
      setError(null);
      const created = await uploadDocument(patientId, file);
      setLastUploaded(created.source_label || created.original_filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] w-full max-w-3xl flex-col justify-center px-5 py-16 sm:px-8">
      <p className="max-w-xl text-lg leading-7 text-ink-soft">
        Upload medical PDFs for your care team. Your clinician reviews them in
        the care provider workspace.
      </p>

      <div className="mt-10 border-y border-line/80 py-8">
        <h2 className="font-display text-2xl text-ink">Document upload</h2>
        <p className="mt-2 text-sm text-muted">
          PDF only. Files are stored for {patientName}’s chart and appear
          immediately in the care provider view.
        </p>

        <label
          className={`relative mt-6 inline-flex cursor-pointer border border-accent bg-accent px-5 py-3 text-sm font-medium text-white hover:bg-accent-deep focus-within:ring-2 focus-within:ring-ink focus-within:ring-offset-2 focus-within:ring-offset-paper ${
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
              if (file) await handleUpload(file);
            }}
          />
        </label>

        {lastUploaded && !error && (
          <p className="mt-4 text-sm text-[#0f5a51]">
            Uploaded “{lastUploaded}”. Your care provider can review it now.
          </p>
        )}
        {error && (
          <p className="mt-4 text-sm text-warning">{error}</p>
        )}
      </div>
    </div>
  );
}
