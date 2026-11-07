import { fileExtension, formatFileSize, MAX_GUIDELINE_BYTES, validateGuidelineFile } from "./guidelineFile";

test.each(["a.txt", "a.md", "A.DOCX", "brand guide.PDF", "x.y.pdf"])("accepts %s", (name) => {
  expect(validateGuidelineFile({ name, size: 10 })).toEqual({ ok: true });
});

test.each(["a.doc", "a.exe", "archive.tar.gz", "noext", ".pdf", "trailing.", "a.pdf.exe"])("rejects %s by type", (name) => {
  const r = validateGuidelineFile({ name, size: 10 });
  expect(r.ok).toBe(false);
  if (!r.ok) expect(r.error).toContain("not a supported file type");
});

test("rejects empty files and names the file", () => {
  const r = validateGuidelineFile({ name: "a.txt", size: 0 });
  expect(r).toMatchObject({ ok: false });
  if (!r.ok) expect(r.error).toContain("a.txt");
});

test("rejects files over the limit but accepts exactly the limit", () => {
  expect(validateGuidelineFile({ name: "a.pdf", size: MAX_GUIDELINE_BYTES }).ok).toBe(true);
  expect(validateGuidelineFile({ name: "a.pdf", size: MAX_GUIDELINE_BYTES + 1 }).ok).toBe(false);
});

test("helpers", () => {
  expect(fileExtension("a.TXT")).toBe("txt");
  expect(fileExtension(".hidden")).toBeNull();
  expect(formatFileSize(512)).toBe("512 B");
  expect(formatFileSize(2048)).toBe("2.0 KB");
  expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
});
