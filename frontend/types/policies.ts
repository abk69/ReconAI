export type PolicyDocument = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type PolicyLibraryItem = PolicyDocument & {
  version_count: number;
  active_version_count: number;
  active_version_id: string | null;
  active_version_label: string | null;
  active_status: string | null;
  effective_from: string | null;
  effective_to: string | null;
};

export type PolicyList = {
  items: PolicyLibraryItem[];
  count: number;
  total: number;
};

export type PolicyVersion = {
  id: string;
  policy_document_id: string;
  version_label: string;
  title: string | null;
  status: string;
  effective_from: string;
  effective_to: string | null;
  source_filename: string | null;
  source_reference: string | null;
  content_hash: string;
  created_at: string;
  updated_at: string;
  chunk_count?: number;
};

export type PolicyVersionList = {
  items: PolicyVersion[];
  count: number;
};

export type PolicyChunk = {
  id: string;
  policy_version_id: string;
  chunk_index: number;
  section_id: string | null;
  section_title: string | null;
  content: string;
  content_hash: string;
  source_filename: string | null;
  page_number: number | null;
  created_at: string;
  updated_at: string;
};

export type PolicyVersionDetail = PolicyVersion & {
  chunks: PolicyChunk[];
};

export type PolicySearchHit = {
  chunk_id: string;
  policy_document_id: string;
  policy_version_id: string;
  chunk_index: number;
  content: string;
  section_id: string | null;
  section_title: string | null;
  page_number: number | null;
  source_filename: string | null;
  content_hash: string;
  similarity: number;
};

export type PolicySearchResult = {
  query: string;
  top_k: number;
  items: PolicySearchHit[];
  count: number;
};
