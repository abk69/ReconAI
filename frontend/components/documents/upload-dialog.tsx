"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { uploadDocument } from "@/lib/api/documents";
import { resourceError } from "@/components/procurement/use-resource";
import {
  UPLOAD_ACCEPT,
  fileExtension,
  formatFileSize,
  validateSelectedFile,
} from "@/lib/documents/upload-rules";

type Outcome =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "uploaded"; id: string }
  | { kind: "duplicate"; id: string }
  | { kind: "error"; message: string };

export function UploadDialog({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const inputId = useId();
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [clientMessage, setClientMessage] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });
  const dragDepth = useRef(0);
  const busy = outcome.kind === "uploading";

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (open) return;
    setDragging(false);
    setFile(null);
    setClientMessage(null);
    setOutcome({ kind: "idle" });
    dragDepth.current = 0;
    if (inputRef.current) inputRef.current.value = "";
  }, [open]);

  function choose(next: File | null, extra?: string) {
    if (busy) return;
    setOutcome({ kind: "idle" });
    if (!next) {
      setFile(null);
      setClientMessage(extra ?? null);
      return;
    }
    setFile(next);
    setClientMessage(validateSelectedFile(next));
  }

  function takeFiles(list: FileList | null) {
    if (!list || list.length === 0) {
      choose(null);
      return;
    }
    if (list.length > 1) {
      choose(null, "Choose one file.");
      return;
    }
    choose(list[0]);
  }

  async function submit() {
    if (busy) return;
    if (!file) {
      setClientMessage("Choose a file before uploading.");
      return;
    }
    const problem = validateSelectedFile(file);
    if (problem) {
      setClientMessage(problem);
      setFile(null);
      return;
    }
    setClientMessage(null);
    setOutcome({ kind: "uploading" });
    try {
      const result = await uploadDocument(file);
      onUploaded();
      setOutcome(result.isDuplicate ? { kind: "duplicate", id: result.id } : { kind: "uploaded", id: result.id });
    } catch (error) {
      setOutcome({ kind: "error", message: resourceError(error, "Upload") });
    }
  }

  const message =
    clientMessage ??
    (outcome.kind === "error"
      ? outcome.message
      : outcome.kind === "uploaded"
        ? "Document uploaded successfully."
        : outcome.kind === "duplicate"
          ? "This document already exists."
          : outcome.kind === "uploading"
            ? "Uploading."
            : null);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={`${titleId}-description`}
      className="w-[min(32rem,calc(100vw-2rem))] max-h-[calc(100vh-2rem)] overflow-y-auto rounded-md border border-line bg-surface p-5 text-ink shadow-card backdrop:bg-ink/40"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <h2 id={titleId} className="text-lg font-semibold">
        Upload document
      </h2>
      <p id={`${titleId}-description`} className="mt-2 text-sm leading-6 text-ink-muted">
        Upload a procurement document for reconciliation.
      </p>
      <p className="mt-1 text-sm text-ink-muted">PDF, JPG, JPEG, PNG, XLSX · Max 10 MB</p>

      <div
        className={`mt-4 rounded-md border border-dashed px-4 py-6 text-center ${
          dragging ? "border-brand bg-white/[0.04]" : "border-white/15"
        }`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (busy) return;
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
        }}
        onDragLeave={() => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (!busy) takeFiles(event.dataTransfer.files);
        }}
      >
        <p className="text-sm text-ink">{dragging ? "Release to select this file." : "Drop a file here, or browse."}</p>
        <label htmlFor={inputId} className="sr-only">
          Procurement document
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={UPLOAD_ACCEPT}
          className="sr-only"
          disabled={busy}
          onChange={(event) => takeFiles(event.target.files)}
        />
        <button
          type="button"
          className="mt-3 min-h-10 rounded-md border border-line px-3 py-2 text-sm"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          Browse
        </button>
      </div>

      {file ? (
        <div className="mt-4 text-sm">
          <p className="break-all font-medium">{file.name}</p>
          <p className="mt-1 text-ink-muted">
            {formatFileSize(file.size)} · {file.type || fileExtension(file.name) || "Unknown type"}
          </p>
          <button
            type="button"
            className="mt-2 min-h-10 text-sm text-brand underline"
            disabled={busy}
            onClick={() => {
              choose(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            Remove file
          </button>
        </div>
      ) : null}

      {message ? (
        <p role={outcome.kind === "error" || clientMessage ? "alert" : "status"} className="mt-4 text-sm leading-6">
          {message}
        </p>
      ) : null}

      {outcome.kind === "uploaded" || outcome.kind === "duplicate" ? (
        <Link className="mt-3 inline-flex min-h-10 items-center text-sm text-brand underline" href={`/documents/${outcome.id}`}>
          {outcome.kind === "duplicate" ? "View existing document" : "View document"}
        </Link>
      ) : null}

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          className="min-h-10 rounded-md border border-line px-3 py-2 text-sm"
          disabled={busy}
          onClick={onClose}
        >
          {outcome.kind === "uploaded" || outcome.kind === "duplicate" ? "Close" : "Cancel"}
        </button>
        {outcome.kind === "uploaded" || outcome.kind === "duplicate" ? null : (
          <button
            type="button"
            className="min-h-10 rounded-lg bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
            disabled={busy || !file || Boolean(clientMessage)}
            onClick={() => void submit()}
          >
            {busy ? "Uploading" : "Upload"}
          </button>
        )}
      </div>
    </dialog>
  );
}
