"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with sensible local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="reconai", description="Service name")
    app_env: str = Field(default="local", description="Environment name")
    debug: bool = Field(default=True, description="Enable debug mode")
    api_prefix: str = Field(default="", description="Optional API path prefix")

    # Local default targets PostgreSQL. Override via DATABASE_URL; never commit secrets.
    database_url: str = Field(
        default="postgresql+psycopg://reconai:reconai@localhost:5432/reconai",
        description="SQLAlchemy database URL (PostgreSQL in production/local)",
    )

    # Reconciliation tolerances (Decimal-compatible strings in env).
    quantity_tolerance: str = Field(
        default="0",
        description="Absolute quantity tolerance (default 0)",
    )
    price_tolerance_percent: str = Field(
        default="0",
        description="Allowed unit-price variance as a percentage (default 0%)",
    )
    tax_rate_tolerance_percent: str = Field(
        default="0",
        description="Allowed tax-rate variance as a percentage (default 0%)",
    )

    # Anomaly detection thresholds (M9.1) — Decimal-compatible strings / ints.
    anomaly_price_low_pct: str = Field(default="5", description="PRICE_VARIANCE LOW ≥ %")
    anomaly_price_medium_pct: str = Field(
        default="10", description="PRICE_VARIANCE MEDIUM ≥ %"
    )
    anomaly_price_high_pct: str = Field(default="25", description="PRICE_VARIANCE HIGH ≥ %")
    anomaly_price_critical_pct: str = Field(
        default="50", description="PRICE_VARIANCE CRITICAL ≥ %"
    )
    anomaly_quantity_low_pct: str = Field(
        default="5", description="QUANTITY_VARIANCE LOW ≥ %"
    )
    anomaly_quantity_medium_pct: str = Field(
        default="10", description="QUANTITY_VARIANCE MEDIUM ≥ %"
    )
    anomaly_quantity_high_pct: str = Field(
        default="25", description="QUANTITY_VARIANCE HIGH ≥ %"
    )
    anomaly_quantity_critical_pct: str = Field(
        default="50", description="QUANTITY_VARIANCE CRITICAL ≥ %"
    )
    vendor_spike_min_history: int = Field(
        default=3, ge=1, description="Min prior invoices for VENDOR_SPIKE"
    )
    vendor_spike_medium_ratio: str = Field(default="2", description="VENDOR_SPIKE MEDIUM ≥")
    vendor_spike_high_ratio: str = Field(default="3", description="VENDOR_SPIKE HIGH ≥")
    vendor_spike_critical_ratio: str = Field(
        default="5", description="VENDOR_SPIKE CRITICAL ≥"
    )
    repeated_mismatch_min_history: int = Field(
        default=5, ge=1, description="Min invoices for REPEATED_MISMATCH"
    )
    repeated_mismatch_medium_rate: str = Field(
        default="0.30", description="REPEATED_MISMATCH MEDIUM ≥ rate"
    )
    repeated_mismatch_high_rate: str = Field(
        default="0.50", description="REPEATED_MISMATCH HIGH ≥ rate"
    )
    repeated_mismatch_critical_rate: str = Field(
        default="0.75", description="REPEATED_MISMATCH CRITICAL ≥ rate"
    )
    repeated_mismatch_window_days: int = Field(
        default=90, ge=1, description="Lookback window for REPEATED_MISMATCH"
    )
    timing_long_delay_days: int = Field(
        default=30, ge=1, description="PO→invoice delay days for TIMING_ANOMALY"
    )

    # Document intake (M3)
    storage_root: str = Field(
        default="storage/documents",
        description="Local filesystem root for uploaded document binaries",
    )
    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum upload size in bytes (default 10 MB)",
        ge=1,
    )

    # LLM-assisted extraction (M6) — real Gemini only; never hard-code secrets.
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key (GEMINI_API_KEY)",
    )
    llm_provider: str = Field(
        default="google",
        description="LLM provider identifier (google)",
    )
    llm_model: str = Field(
        default="gemini-3.1-flash-lite",
        description="Gemini model id for structured extraction",
    )
    llm_timeout_seconds: float = Field(
        default=45.0,
        description="Per-request timeout for Gemini calls",
        gt=0,
    )
    llm_max_input_chars: int = Field(
        default=24_000,
        description="Maximum document text characters sent to Gemini",
        ge=1000,
    )
    llm_max_output_tokens: int = Field(
        default=4096,
        description="Maximum output tokens for Gemini structured responses",
        ge=256,
    )
    llm_max_retries: int = Field(
        default=1,
        description="Bounded retries for transient Gemini failures (not schema retries)",
        ge=0,
        le=3,
    )
    llm_quality_threshold: str = Field(
        default="READY_FOR_RECONCILIATION",
        description="M4 outcome that skips Gemini (cost control)",
    )

    # Policy ingestion / chunking (M7.2)
    policy_chunk_max_chars: int = Field(
        default=2000,
        description="Maximum characters per policy chunk before deterministic split",
        ge=200,
        le=50_000,
    )
    max_policy_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum policy source upload size in bytes",
        ge=1,
    )

    # Policy embeddings / retrieval (M7.3)
    embedding_model: str = Field(
        default="gemini-embedding-001",
        description="Gemini embedding model id (EMBEDDING_MODEL)",
    )
    embedding_dimension: int = Field(
        default=768,
        description="Embedding vector size; must match pgvector column / output_dimensionality",
        ge=128,
        le=3072,
    )
    embedding_batch_size: int = Field(
        default=32,
        description="Max chunks per embed_content batch",
        ge=1,
        le=100,
    )
    policy_search_default_top_k: int = Field(
        default=5,
        description="Default top_k for policy vector search",
        ge=1,
        le=50,
    )

    # Policy grounded reasoning (M7.4)
    policy_grounding_top_k: int = Field(
        default=5,
        description="Top-K policy chunks retrieved for grounded explanation",
        ge=1,
        le=50,
    )
    policy_retrieval_min_similarity: float = Field(
        default=0.25,
        description=(
            "Minimum cosine similarity for a retrieved chunk to count as evidence. "
            "Below this, Gemini is not called (INSUFFICIENT_EVIDENCE)."
        ),
        ge=0.0,
        le=1.0,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
