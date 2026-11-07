"""Document content and section parsing engine."""
import io
import re
from defusedxml import ElementTree as ET
import zipfile
from dataclasses import dataclass

from app.core.errors import ProblemException


@dataclass
class ParsedSection:
    section_number: int
    heading: str | None
    content: str
    page_number: int | None = None


def parse_text_sections(text: str) -> list[ParsedSection]:
    """Parse text into sections using markdown headings or paragraph blocks."""
    lines = text.splitlines()
    sections: list[ParsedSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    sec_num = 1

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(
                        ParsedSection(
                            section_number=sec_num,
                            heading=current_heading,
                            content=content,
                        )
                    )
                    sec_num += 1
                current_lines = []
            current_heading = stripped.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(
                ParsedSection(
                    section_number=sec_num,
                    heading=current_heading,
                    content=content,
                )
            )

    if not sections and text.strip():
        sections.append(
            ParsedSection(
                section_number=1,
                heading=None,
                content=text.strip(),
            )
        )

    return sections


def parse_docx_content(content: bytes) -> list[ParsedSection]:
    """Extract paragraphs and headings from DOCX word/document.xml with XML size limit (M-13)."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        if "word/document.xml" not in zf.namelist():
            raise ProblemException(
                status=422,
                code="INVALID_DOCX_STRUCTURE",
                title="Unprocessable Entity",
                detail="DOCX archive missing required 'word/document.xml' component.",
            )
        info = zf.getinfo("word/document.xml")
        if info.file_size > 20 * 1024 * 1024:
            raise ProblemException(
                status=422,
                code="DOCX_XML_TOO_LARGE",
                title="Unprocessable Entity",
                detail="DOCX word/document.xml exceeds safe uncompressed threshold of 20 MB.",
            )
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)

        # XML namespace for WordML
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for p in root.findall(".//w:p", ns):
            texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
            p_text = "".join(texts).strip()
            if p_text:
                paragraphs.append(p_text)

        full_text = "\n\n".join(paragraphs)
        return parse_text_sections(full_text)


def parse_pdf_content(content: bytes) -> list[ParsedSection]:
    """Extract text from PDF pages with 100 page resource limit (M-13)."""
    text_content = ""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        if len(reader.pages) > 100:
            raise ProblemException(
                status=422,
                code="PDF_PAGE_LIMIT_EXCEEDED",
                title="Unprocessable Entity",
                detail=f"PDF document contains {len(reader.pages)} pages, exceeding maximum limit of 100 pages.",
            )

        sections: list[ParsedSection] = []
        for idx, page in enumerate(reader.pages):
            p_text = page.extract_text() or ""
            if p_text.strip():
                sections.append(
                    ParsedSection(
                        section_number=idx + 1,
                        heading=f"Page {idx + 1}",
                        content=p_text.strip(),
                        page_number=idx + 1,
                    )
                )
        if sections:
            return sections
    except ProblemException:
        raise
    except (pypdf.errors.PyPdfError, ValueError, KeyError):
        # Fallback to simple stream text extraction
        decoded = content.decode("latin-1", errors="ignore")
        matches = re.findall(r"\((.*?)\)Tj", decoded)
        text_content = " ".join(matches)

    if not text_content.strip():
        raise ProblemException(
            status=422,
            code="PDF_TEXT_NOT_EXTRACTABLE",
            title="Unprocessable Entity",
            detail="No extractable text was found. Scanned or image-only PDFs are not supported; upload a text-based PDF or TXT/DOCX file.",
        )
    return parse_text_sections(text_content)


def parse_document(file_format: str, content: bytes) -> list[ParsedSection]:
    if file_format in ("TXT", "MD"):
        decoded = content.decode("utf-8", errors="replace")
        return parse_text_sections(decoded)
    if file_format == "DOCX":
        return parse_docx_content(content)
    if file_format == "PDF":
        return parse_pdf_content(content)
    return []
