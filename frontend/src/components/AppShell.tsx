"use client";

import { useEffect, useState } from "react";
import type { AppView } from "@/lib/constants";
import { Dashboard } from "./Dashboard";
import { PatientUploadView } from "./PatientUploadView";

function readViewFromUrl(): AppView {
  if (typeof window === "undefined") return "provider";
  const value = new URLSearchParams(window.location.search).get("view");
  return value === "patient" ? "patient" : "provider";
}

export function AppShell() {
  const [view, setView] = useState<AppView>("provider");

  useEffect(() => {
    setView(readViewFromUrl());
  }, []);

  function switchView(next: AppView) {
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState({}, "", url.toString());
  }

  return (
    <div className="relative z-10 min-h-screen">
      <div className="border-b border-line/80 bg-white/40">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <p className="text-xs uppercase tracking-[0.18em] text-muted">
            Unburden workspace
          </p>
          <div
            role="tablist"
            aria-label="Workspace role"
            className="flex border border-line bg-white/70"
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === "patient"}
              onClick={() => switchView("patient")}
              className={`px-4 py-2 text-sm font-medium transition ${
                view === "patient"
                  ? "bg-ink text-white"
                  : "text-ink-soft hover:bg-mist/60"
              }`}
            >
              Patient
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "provider"}
              onClick={() => switchView("provider")}
              className={`px-4 py-2 text-sm font-medium transition ${
                view === "provider"
                  ? "bg-ink text-white"
                  : "text-ink-soft hover:bg-mist/60"
              }`}
            >
              Care provider
            </button>
          </div>
        </div>
      </div>

      {view === "patient" ? <PatientUploadView /> : <Dashboard />}
    </div>
  );
}
