# Docs: Markdown is canonical. DOCX + PDF are rendered locally (no LLM).

from pathlib import Path
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# Placeholders supported inside a user-uploaded .docx template.
PLACEHOLDERS = [
    "project_name", "overview", "tech_stack", "architecture",
    "api_endpoints", "data_models", "file_tree", "setup", "limitations",
    "full_spec",
]


def split_sections(md: str) -> dict:
    """Split Markdown by ## headings so we can fill per-section placeholders."""
    sections: dict[str, str] = {}
    current = "full_spec"
    buf: list[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower().replace(" ", "_")
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    sections["full_spec"] = md
    return sections


def _replace_in_paragraph(para, mapping: dict):
    # Simple approach: replace on the whole paragraph text.
    # (Loses per-run bold formatting, but keeps code explainable.)
    text = para.text
    for key, val in mapping.items():
        tag = "{{" + key + "}}"
        if tag in text:
            text = text.replace(tag, val)
    if text != para.text:
        para.text = text


def markdown_to_docx(md: str, template_path: Path | None, out_path: Path):
    sections = split_sections(md)
    if template_path and template_path.exists():
        doc = Document(str(template_path))
        for para in doc.paragraphs:
            _replace_in_paragraph(para, sections)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        _replace_in_paragraph(para, sections)
    else:
        # No template: build a clean doc from the Markdown.
        doc = Document()
        doc.add_heading("Design Specification", 0)
        for line in md.splitlines():
            if line.startswith("## "):
                doc.add_heading(line[3:], level=1)
            elif line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.strip() == "":
                continue
            else:
                doc.add_paragraph(line)
    doc.save(str(out_path))


def markdown_to_pdf(md: str, out_path: Path):
    doc = SimpleDocTemplate(str(out_path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    for line in md.splitlines():
        s = line.replace("<", "&lt;").replace(">", "&gt;") or " "
        if line.startswith("## "):
            story.append(Paragraph(line[3:], styles["Heading1"]))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], styles["Heading1"]))
        else:
            story.append(Paragraph(s, styles["Normal"]))
        story.append(Spacer(1, 4))
    doc.build(story)
