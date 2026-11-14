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

export type RequirementEvaluation = {
  requirement_id: string;
  title: string;
  status: string;
  explanation: string;
  suggested_document_types: string[];
  accepted_candidate_ids: string[];
  review_candidate_ids: string[];
  rejected_candidate_ids: string[];
  supporting_candidates: EvidenceCandidate[];
  review_candidates: EvidenceCandidate[];
};

export type PolicyEvaluation = {
  patient_id: string;
  policy_id: string;
  policy_name: string;
  disclaimer: string;
  as_of_date: string;
  logic: string;
  overall_status: string;
  requirements: RequirementEvaluation[];
};

export type PacketDocument = {
  document_id: string;
  source_label: string;
  original_filename: string;
  document_type: string;
  page_count: number;
  covers_requirement_ids: string[];
  covers_requirement_titles: string[];
  strength_score: number;
};

export type MissingEvidenceItem = {
  requirement_id: string;
  title: string;
  status: string;
  explanation: string;
  suggested_document_types: string[];
};

export type EvidencePacket = {
  patient_id: string;
  policy_id: string;
  policy_name: string;
  disclaimer: string;
  covered_requirement_ids: string[];
  selected_documents: PacketDocument[];
  omitted_document_ids: string[];
  total_pages: number;
  packet_strength: number;
  missing_evidence: MissingEvidenceItem[];
  notes: string[];
};
