# M7 — Policy Knowledge Base

M7 adds versioned policy storage, deterministic ingestion, and vector retrieval so
future grounded answers (M7.4) can cite evidence without inventing policy text.

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

Same bytes + same max ⇒ identical chunks/hashes.

### Idempotency

- Source SHA-256 stored on `PolicyVersion.content_hash`.
- Re-ingest identical source → `ALREADY_INGESTED` (no duplicate chunks).
- Different source on a version that already has chunks → `409` (create a new version).

## M7.3 — Embeddings + vector retrieval

```
PolicyChunk.content (source of truth)
    ↓
EmbeddingProvider (Gemini or test fake)
    ↓
pgvector column on PolicyChunk (derived)
    ↓
cosine-distance top-K retrieval + full provenance
```

### Why PostgreSQL + pgvector

- Reuses the existing ReconAI database (no second vector product).
- Local Docker uses `pgvector/pgvector:pg16` (same credentials/volume as before).
- Chunk text stays in relational tables; vectors are derived columns.

### Embedding model & dimension

| Setting | Default | Notes |
| --- | --- | --- |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | google-genai `embed_content` |
| `EMBEDDING_DIMENSION` | `768` | Requested via `output_dimensionality`; matches `vector(768)` |
| `EMBEDDING_BATCH_SIZE` | `32` | Bounded batches |

`gemini-embedding-001` defaults to **3072** dims. We request **768** (recommended MRL size per Google docs) and **L2-normalize** truncated vectors before storage/query (required for embedding-001 non-3072 dims). Changing dimension requires a new migration — do not diverge Settings from `vector(N)`.

### Similarity metric

**Cosine distance** (`1 - cosine_similarity`) on L2-normalized vectors.

- Write path and query path both normalize.
- Retrieval ranks by ascending distance (ties: `chunk_index`, then id).
- No HNSW/IVFFlat index at portfolio scale — exact scan is simpler and deterministic.

### Embedding lifecycle / staleness

A chunk needs (re)embedding when any of:

- `embedding` is null
- `embedding_content_hash != content_hash`
- `embedding_model` differs from the active provider model
- stored vector length ≠ configured dimension

Unchanged chunks are skipped. Embedding is an **explicit** `POST …/embed` — never on GET.

Provider failures roll back the current batch; chunks are not marked embedded.

### Retrieval flow

```
query text → query embedding → filter (policy_version_id / document)
  → score embedded non-stale chunks → top_k → provenance hits
```

Each hit includes chunk id, document/version ids, index, content, section fields,
page, filename, content hash, embedding model, distance, and similarity.

Retrieval never modifies policy rows.

### API

```bash
POST /policies/{policy_id}/versions/{version_id}/embed
POST /policies/{policy_id}/versions/{version_id}/search
# body: { "query": "...", "top_k": 5, "policy_version_id": optional }
```

### Deferred to M7.4

Grounded Gemini generation / RAG answers. M7.3 only retrieves evidence.

## Design rules

1. Policy text is knowledge — separate from PO/GRN/Invoice (M2).
2. Versions are first-class for citations.
3. Chunks preserve provenance without relying on similarity scores alone.
4. Embeddings are derived; Gemini must never rewrite policy text.
5. No LangChain / LlamaIndex.

## Lifecycle

`PolicyVersionStatus`: `DRAFT` → `ACTIVE` → `RETIRED`
