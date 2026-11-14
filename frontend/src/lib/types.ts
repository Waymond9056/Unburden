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
