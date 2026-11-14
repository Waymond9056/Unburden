"use client";

import { useEffect, useState } from "react";
import { listPatients } from "@/lib/api";
import {
  DEFAULT_PATIENT_ID,
  type AppView,
} from "@/lib/constants";
import type { Patient } from "@/lib/types";
import { Dashboard } from "./Dashboard";
import { PatientUploadView } from "./PatientUploadView";

function readViewFromUrl(): AppView {
  if (typeof window === "undefined") return "provider";
  const value = new URLSearchParams(window.location.search).get("view");
  return value === "patient" ? "patient" : "provider";
}

function readPatientFromUrl(): string {
  if (typeof window === "undefined") return DEFAULT_PATIENT_ID;
  return (
    new URLSearchParams(window.location.search).get("patient") ||
    DEFAULT_PATIENT_ID
  );
}

export function AppShell() {
  const [view, setView] = useState<AppView>("provider");
  const [patientId, setPatientId] = useState(DEFAULT_PATIENT_ID);
  const [patients, setPatients] = useState<Patient[]>([]);

  useEffect(() => {
    setView(readViewFromUrl());
    setPatientId(readPatientFromUrl());
    void listPatients()
      .then(setPatients)
      .catch(() => setPatients([]));
  }, []);

  function updateUrl(nextView: AppView, nextPatientId: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("view", nextView);
    url.searchParams.set("patient", nextPatientId);
    window.history.replaceState({}, "", url.toString());
  }

  function switchView(next: AppView) {
    setView(next);
    updateUrl(next, patientId);
  }

  function switchPatient(nextPatientId: string) {
    setPatientId(nextPatientId);
    updateUrl(view, nextPatientId);
  }

  const activePatient =
    patients.find((patient) => patient.id === patientId) ?? null;

  return (
    <div className="relative z-10 min-h-screen">
      <div className="border-b border-line/80 bg-white/40">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <h1 className="font-display text-3xl text-ink">Unburden</h1>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-ink-soft">
              <span className="text-xs uppercase tracking-[0.14em] text-muted">
                Patient
              </span>
              <select
                value={patientId}
                onChange={(event) => switchPatient(event.target.value)}
                className="border border-line bg-white/80 px-2 py-1.5 text-sm text-ink"
              >
                {patients.length === 0 ? (
                  <option value={patientId}>{patientId}</option>
                ) : (
                  patients.map((patient) => (
                    <option key={patient.id} value={patient.id}>
                      {patient.display_name}
                    </option>
                  ))
                )}
              </select>
            </label>
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
      </div>

      {view === "patient" ? (
        <PatientUploadView
          patientId={patientId}
          patientName={activePatient?.display_name ?? patientId}
        />
      ) : (
        <Dashboard key={patientId} patientId={patientId} />
      )}
    </div>
  );
}
