const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-start justify-center gap-4 px-8 py-16 font-sans">
      <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">
        Hackathon MVP
      </p>
      <h1 className="text-5xl font-semibold tracking-tight text-zinc-950">
        Unburden
      </h1>
      <p className="max-w-xl text-lg leading-7 text-zinc-600">
        Evidence engine shell. Milestone 1 backend is live for PDF upload and
        page-bounded text extraction. Clinician dashboard arrives in Milestone 5.
      </p>
      <p className="text-sm text-zinc-500">
        API:{" "}
        <a className="underline" href={`${API_BASE}/health`}>
          {API_BASE}/health
        </a>
      </p>
    </main>
  );
}
