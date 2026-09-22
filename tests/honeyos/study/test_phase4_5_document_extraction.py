
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from honeyos.tools.read_extract import ExtractionError, extract_document_text


def _zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return path


def _text_pdf_bytes(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode())
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(data)


def test_docx_extracts_text(tmp_path: Path):
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>Intro paragraph</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '</w:body></w:document>'
    )
    path = _zip(tmp_path / "notes.docx", {"word/document.xml": xml})
    text = extract_document_text(str(path))
    assert "Intro paragraph" in text
    assert "Table cell" in text


def test_xlsx_extracts_sheet_and_values(tmp_path: Path):
    path = _zip(
        tmp_path / "study.xlsx",
        {
            "xl/workbook.xml": (
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Pathology" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
            ),
            "xl/worksheets/sheet1.xml": (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Topic</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>Melanoma</t></is></c></row></sheetData></worksheet>'
            ),
        },
    )
    text = extract_document_text(str(path))
    assert "Sheet: Pathology" in text
    assert "Melanoma" in text


def test_pptx_extracts_slide_order_and_text(tmp_path: Path):
    path = _zip(
        tmp_path / "lecture.pptx",
        {
            "ppt/presentation.xml": (
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<p:sldIdLst><p:sldId id="256" r:id="rId1"/><p:sldId id="257" r:id="rId2"/></p:sldIdLst>'
                '</p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="slides/slide1.xml"/>'
                '<Relationship Id="rId2" Target="slides/slide2.xml"/></Relationships>'
            ),
            "ppt/slides/slide1.xml": (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide One</a:t></a:r></a:p>'
                '</p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
            ),
            "ppt/slides/slide2.xml": (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                '<p:cSld><p:spTree><p:graphicFrame><a:graphic><a:graphicData>'
                '<a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Table Value</a:t></a:r></a:p>'
                '</a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic>'
                '</p:graphicFrame></p:spTree></p:cSld></p:sld>'
            ),
        },
    )
    text = extract_document_text(str(path))
    assert text.index("[Slide 1]") < text.index("[Slide 2]")
    assert "Slide One" in text
    assert "Table Value" in text


def test_pdf_extracts_text_layer(tmp_path: Path):
    path = tmp_path / "text-layer.pdf"
    path.write_bytes(_text_pdf_bytes("HoneyOS Study PDF"))

    text = extract_document_text(str(path))

    assert "[Page 1]" in text
    assert "HoneyOS Study PDF" in text


def test_empty_pdf_is_rejected(tmp_path: Path):
    from pypdf import PdfWriter

    path = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)

    with pytest.raises(ExtractionError, match="no extractable text"):
        extract_document_text(str(path))
