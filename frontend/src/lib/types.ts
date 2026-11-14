export type Patient = {
  id: string;
  display_name: string;
  date_of_birth: string | null;
  created_at: string;
};

export type DocumentSummary = {
  id: string;
  patient_id: string;
  filename: string;
  original_filename: string;
  document_type: string;
  page_count: number;
  uploaded_at: string;
  source_label: string | null;
  scenario_tag: string | null;
};

export type PageText = {
  page_number: number;
  text: string;
};

export type DocumentDetail = DocumentSummary & {
  pages: PageText[];
};

export type EvidenceCandidate = {
  id: string;
  patient_id: string;
  document_id: string;
  policy_id: string;
  requirement_id: string;
  requirement_title: string;
  source_page: number;
  supporting_quote: string;
  extracted_details: Record<string, unknown>;
  relevance_score: number;
  retrieval_method: string;
  verification_status: string;
  created_at: string;
  source_document_name: string | null;
  source_document_type: string | null;
};
