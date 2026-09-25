/** Matches app/services/document_service.py ALLOWED_EXTENSIONS and the 10 MB default. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export const UPLOAD_ACCEPT = ".pdf,.jpg,.jpeg,.png,.xlsx";

const MIME_BY_EXTENSION: Record<string, readonly string[]> = {
  ".pdf": ["application/pdf"],
  ".jpg": ["image/jpeg"],
  ".jpeg": ["image/jpeg"],
  ".png": ["image/png"],
  ".xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
};

export function fileExtension(name: string): string {
  const base = name.split(/[/\\]/).pop() ?? name;
  const dot = base.lastIndexOf(".");
  if (dot <= 0) return "";
  return base.slice(dot).toLowerCase();
}

export function validateSelectedFile(file: File): string | null {
  if (file.size === 0) {
    return "This file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "This file is larger than 10 MB.";
  }
  const extension = fileExtension(file.name);
  const allowed = MIME_BY_EXTENSION[extension];
  if (!allowed) {
    return "This file type is not supported. Use PDF, JPG, JPEG, PNG, or XLSX.";
  }
  const mime = file.type.split(";")[0].trim().toLowerCase();
  if (mime && !allowed.includes(mime)) {
    return "This file type is not supported. Use PDF, JPG, JPEG, PNG, or XLSX.";
  }
  return null;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
