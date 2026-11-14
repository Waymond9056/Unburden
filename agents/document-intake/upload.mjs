/**
 * Upload a captured PDF into Unburden's document API.
 * @param {Uint8Array} pdfBytes
 * @param {{
 *   apiBase?: string,
 *   patientId?: string,
 *   sessionId?: string | null,
 *   sourceLabel?: string,
 * }} [options]
 */
export async function uploadCapturedPdf(pdfBytes, options = {}) {
  const apiBase = (options.apiBase || process.env.UNBURDEN_API_BASE || 'http://localhost:8000').replace(/\/$/, '');
  const patientId = options.patientId || process.env.UNBURDEN_PATIENT_ID || 'patient-raymond-yao';
  const sourceLabel =
    options.sourceLabel ||
    `FaceTime capture — ${new Date().toISOString().replace('T', ' ').slice(0, 19)}`;

  const form = new FormData();
  form.append(
    'file',
    new Blob([pdfBytes], { type: 'application/pdf' }),
    'facetime-capture.pdf',
  );
  form.append('source_label', sourceLabel);
  form.append('document_type', 'clinical_note');

  const response = await fetch(`${apiBase}/api/patients/${patientId}/documents`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Unburden upload failed (${response.status}): ${detail}`);
  }
  const document = await response.json();

  if (options.sessionId) {
    try {
      await fetch(`${apiBase}/api/patients/${patientId}/chert/sessions/${options.sessionId}/uploaded`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          document_id: document.id,
          source_label: document.source_label || sourceLabel,
        }),
      });
    } catch (error) {
      console.warn('[upload] session callback failed', error);
    }
  }

  return document;
}

export function patientIdFromMetadata(raw) {
  try {
    const parsed = JSON.parse(raw || '{}');
    if (typeof parsed.patient_id === 'string' && parsed.patient_id) return parsed.patient_id;
    if (typeof parsed.unburden_patient_id === 'string' && parsed.unburden_patient_id) {
      return parsed.unburden_patient_id;
    }
  } catch {
    /* ignore */
  }
  return process.env.UNBURDEN_PATIENT_ID || 'patient-raymond-yao';
}

export function sessionIdFromMetadata(raw) {
  try {
    const parsed = JSON.parse(raw || '{}');
    if (typeof parsed.session_id === 'string' && parsed.session_id) return parsed.session_id;
    if (typeof parsed.unburden_session_id === 'string' && parsed.unburden_session_id) {
      return parsed.unburden_session_id;
    }
  } catch {
    /* ignore */
  }
  return null;
}
