import type {
  DocumentDetail,
  DocumentSummary,
  EvidenceCandidate,
  EvidencePacket,
  Patient,
  PolicyEvaluation,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getApiBase() {
  return API_BASE;
}

export function listPatients() {
  return request<Patient[]>("/api/patients");
}

export function getPatient(patientId: string) {
  return request<Patient>(`/api/patients/${patientId}`);
}

export function listDocuments(patientId: string) {
  return request<DocumentSummary[]>(`/api/patients/${patientId}/documents`);
}

export function getDocument(patientId: string, documentId: string) {
  return request<DocumentDetail>(
    `/api/patients/${patientId}/documents/${documentId}`,
  );
}

export function listEvidenceCandidates(patientId: string) {
  return request<EvidenceCandidate[]>(
    `/api/patients/${patientId}/evidence-candidates`,
  );
}

export function getPolicyEvaluation(patientId: string) {
  return request<PolicyEvaluation>(
    `/api/patients/${patientId}/policy-evaluation`,
  );
}

export function evaluatePolicy(patientId: string) {
  return request<PolicyEvaluation>(`/api/patients/${patientId}/evaluate`, {
    method: "POST",
  });
}

export function getEvidencePacket(patientId: string) {
  return request<EvidencePacket>(
    `/api/patients/${patientId}/evidence-packet`,
  );
}

export function evidencePacketExportUrl(patientId: string) {
  return `${API_BASE}/api/patients/${patientId}/evidence-packet/export`;
}

export async function downloadEvidencePacketPdf(patientId: string) {
  const response = await fetch(evidencePacketExportUrl(patientId));
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] || `unburden-pa-evidence-packet-${patientId}.pdf`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function documentFileUrl(patientId: string, documentId: string) {
  return `${API_BASE}/api/patients/${patientId}/documents/${documentId}/file`;
}

export async function uploadDocument(
  patientId: string,
  file: File,
  documentType?: string,
) {
  const body = new FormData();
  body.append("file", file);
  const trimmedType = documentType?.trim();
  if (trimmedType) body.append("document_type", trimmedType);
  body.append("source_label", file.name);
  return request<DocumentSummary>(`/api/patients/${patientId}/documents`, {
    method: "POST",
    body,
  });
}

export async function reseedDemo() {
  return request<{
    patient_id: string;
    documents_created: number;
    document_ids: string[];
  }>("/api/demo/seed", { method: "POST" });
}
