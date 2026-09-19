# M7 — Policy Knowledge Base

M7 will eventually add RAG/policy grounding for exception explanations.

## M7.1 — Storage foundation

```
Policy source
    ↓
PolicyDocument (logical identity)
    ↓
PolicyVersion (versioned content + lifecycle)
    ↓
PolicyChunk (ordered sections with citation provenance)
```

## M7.2 — Ingestion & deterministic chunking

Transforms a policy **file** into M7.1 rows:

```
.md / .pdf upload
    ↓
SHA-256 source hash
    ↓
Markdown or PDF parse (PDF via M4 PyMuPDF)
    ↓
Section-aware chunking (POLICY_CHUNK_MAX_CHARS)
    ↓
PolicyChunk rows + provenance
```

### Supported formats

| Format | Notes |
| --- | --- |
| Markdown (`.md`, `.markdown`) | ATATX headings; lists/paragraphs kept as blocks |
| PDF (`.pdf`) | Text via existing `PDFExtractor`; page provenance |

Unsupported types → `422`. Empty/unextractable PDF → `422`.

### Chunking algorithm

1. Parse into heading-scoped **sections** with paragraph/list **blocks**.
2. Pack blocks into chunks while `len <= POLICY_CHUNK_MAX_CHARS` (default 2000).
3. Oversized blocks split on whitespace (never mid-word when possible).
4. Contiguous `chunk_index` from 0; SHA-256 per chunk body.

Same bytes + same max ⇒ identical chunks/hashes (ready for M7.3 embeddings).

### Idempotency

- Source SHA-256 stored on `PolicyVersion.content_hash`.
- Re-ingest identical source → `ALREADY_INGESTED` (no duplicate chunks).
- Different source on a version that already has chunks → `409` (create a new version).

### Provenance retained

`section_id`, `section_title`, `chunk_index`, `source_filename`, `page_number` (PDF), `content_hash`.

### Deferred to M7.3+

Embeddings, pgvector, retrieval, grounded Gemini answers.

## Design rules

1. Policy text is knowledge — separate from PO/GRN/Invoice (M2).
2. Versions are first-class for citations.
3. Chunks preserve provenance without relying on similarity scores.
4. No LLM / vector DB in M7.1–M7.2.

## Lifecycle

`PolicyVersionStatus`: `DRAFT` → `ACTIVE` → `RETIRED`

## API (ingestion)

```bash
POST /policies/{policy_id}/versions/{version_id}/ingest
```
