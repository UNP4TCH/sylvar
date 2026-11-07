export const ALLOWED_GUIDELINE_EXTENSIONS = ["txt", "md", "docx", "pdf"] as const;
/** Client-side guard only; the backend enforces its own limit. */
export const MAX_GUIDELINE_BYTES = 25 * 1024 * 1024;
/** Value for <input accept>. Extensions first (Windows/Linux pickers); MIME types help macOS/mobile pickers. */
export const GUIDELINE_ACCEPT = [
  ".txt",
  ".md",
  ".docx",
  ".pdf",
  "text/plain",
  "text/markdown",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
].join(",");

export type FileValidation = { ok: true } | { ok: false; error: string };

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileExtension(name: string): string | null {
  const i = name.lastIndexOf(".");
  if (i <= 0 || i === name.length - 1) return null; // no extension, dotfile, or trailing dot
  return name.slice(i + 1).toLowerCase();
}

export function validateGuidelineFile(file: Pick<File, "name" | "size">): FileValidation {
  const ext = fileExtension(file.name);
  if (!ext || !(ALLOWED_GUIDELINE_EXTENSIONS as readonly string[]).includes(ext)) {
    return {
      ok: false,
      error: `'${file.name}' is not a supported file type${ext ? ` (.${ext})` : ""}. Allowed: .txt, .md, .docx, .pdf.`,
    };
  }
  if (file.size === 0) {
    return { ok: false, error: `'${file.name}' is empty (0 bytes). Choose a document with content.` };
  }
  if (file.size > MAX_GUIDELINE_BYTES) {
    return {
      ok: false,
      error: `'${file.name}' is ${formatFileSize(file.size)}, over the ${formatFileSize(MAX_GUIDELINE_BYTES)} upload limit.`,
    };
  }
  return { ok: true };
}
