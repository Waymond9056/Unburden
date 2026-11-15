"use client";

import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";
import { listPatients } from "@/lib/api";
import {
  DEFAULT_PATIENT_ID,
  type AppView,
} from "@/lib/constants";
import type { Patient } from "@/lib/types";
import { Dashboard } from "./Dashboard";
import { PatientUploadView } from "./PatientUploadView";

const NAVIGATION_EVENT = "unburden-navigation";

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

function subscribeNavigation(onStoreChange: () => void) {
  window.addEventListener("popstate", onStoreChange);
  window.addEventListener(NAVIGATION_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("popstate", onStoreChange);
    window.removeEventListener(NAVIGATION_EVENT, onStoreChange);
  };
}

export function AppShell() {
  const view = useSyncExternalStore(
    subscribeNavigation,
    readViewFromUrl,
    () => "provider" as AppView,
  );
  const patientId = useSyncExternalStore(
    subscribeNavigation,
    readPatientFromUrl,
    () => DEFAULT_PATIENT_ID,
  );
  const [patients, setPatients] = useState<Patient[]>([]);

  useEffect(() => {
    let cancelled = false;
    void listPatients()
      .then((next) => {
        if (!cancelled) setPatients(next);
      })
      .catch(() => {
        if (!cancelled) setPatients([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function updateUrl(nextView: AppView, nextPatientId: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("view", nextView);
    url.searchParams.set("patient", nextPatientId);
    window.history.replaceState({}, "", url.toString());
    window.dispatchEvent(new Event(NAVIGATION_EVENT));
  }

  function switchView(next: AppView) {
    updateUrl(next, patientId);
  }

  function switchPatient(nextPatientId: string) {
    updateUrl(view, nextPatientId);
  }

  return (
    <div className="min-h-screen">
      <div className="border-b border-line/80 bg-white/40">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <h1 className="flex items-center">
            <Image
              src="/logo.png"
              alt="Unburden"
              width={188}
              height={58}
              className="h-10 w-auto"
              priority
            />
          </h1>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-ink-soft">
              <span className="text-xs uppercase tracking-[0.14em] text-muted">
                Patient
              </span>
              <select
                value={patientId}
                onChange={(event) => switchPatient(event.target.value)}
                className="w-auto appearance-none border border-line bg-white/80 bg-[length:12px] bg-[position:right_10px_center] bg-no-repeat py-1.5 pl-2 pr-8 text-sm text-ink [field-sizing:content] focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%23465c61' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
                }}
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
                className={`px-4 py-2 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper ${
                  view === "patient"
                    ? "bg-ink text-white"
                    : "text-ink-soft hover:bg-mist/60"
                }`}
              >
                Patient upload
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === "provider"}
                onClick={() => switchView("provider")}
                className={`px-4 py-2 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper ${
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
        <PatientUploadView patientId={patientId} />
      ) : (
        <Dashboard key={patientId} patientId={patientId} />
      )}
    </div>
  );
}
