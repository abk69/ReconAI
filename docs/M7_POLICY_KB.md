# M7.1 — Policy Knowledge Base Foundation

M7 will eventually add RAG/policy grounding for exception explanations.
**M7.1 implements only the versioned policy storage foundation.**

## What this stage is

```
Policy source
    ↓
PolicyDocument (logical identity)
    ↓
PolicyVersion (versioned content + lifecycle)
    ↓
PolicyChunk (ordered sections with citation provenance)
```

## What this stage is NOT

- No embeddings
- No pgvector / vector indexes
- No retrieval / similarity search
- No LangChain / LlamaIndex
- No Gemini policy generation

Those belong to later M7 stages:

```
Policy chunks
    ↓
Embeddings
    ↓
Vector retrieval
    ↓
Grounded Gemini
    ↓
Cited explanation
```

## Design rules

1. **Separate from procurement transactions** — policy text is knowledge, not PO/GRN/Invoice financial facts (M2).
2. **Versions are first-class** — policies change; citations must pin a specific `version_label` / `PolicyVersion.id`.
3. **Chunks preserve provenance** — `section_id`, `section_title`, `chunk_index`, `source_filename`, `page_number`, `content_hash` support future citations without relying on similarity scores alone.
4. **Deferred retrieval** — store retrievable text now; wire vectors later without rewriting the model.

## Lifecycle

`PolicyVersionStatus`: `DRAFT` → `ACTIVE` → `RETIRED`
