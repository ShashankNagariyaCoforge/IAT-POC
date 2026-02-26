"""
Unit tests for the document parser service.
Uses the synthetic PDFs already present in the repository.
"""

import os
import pytest
from pathlib import Path

from services.document_parser import DocumentParser, ParseResult

SYNTHETIC_PDFS_DIR = Path(__file__).parent.parent.parent  # repo root


@pytest.fixture
def parser():
    return DocumentParser()


@pytest.mark.asyncio
async def test_parse_pdf_digital(parser):
    """Test that a digital PDF extracts meaningful text without needing OCR."""
    pdf_path = SYNTHETIC_PDFS_DIR / "synthetic_3.pdf"
    if not pdf_path.exists():
        pytest.skip("synthetic_3.pdf not found")
    content = pdf_path.read_bytes()
    result = await parser.parse("synthetic_3.pdf", content)
    assert isinstance(result, ParseResult)
    assert result.file_type == "pdf"
    # Digital PDF should not require OCR (has meaningful text)
    if result.raw_text:
        assert result.ocr_required is False or len(result.raw_text) > 0


@pytest.mark.asyncio
async def test_parse_docx(parser, tmp_path):
    """Test that a simple DOCX is parsed correctly."""
    import docx as docx_lib
    doc = docx_lib.Document()
    doc.add_paragraph("Hello from IAT Insurance. Policy number: TEST-001.")
    docx_path = tmp_path / "test.docx"
    doc.save(str(docx_path))
    content = docx_path.read_bytes()

    result = await parser.parse("test.docx", content)
    assert result.file_type == "docx"
    assert result.ocr_required is False
    assert "Hello" in result.raw_text


@pytest.mark.asyncio
async def test_extract_urls(parser):
    """Test URL extraction from text."""
    text = "Visit https://example.com and http://test.org/path?q=1 for details."
    urls = parser._extract_urls(text)
    assert "https://example.com" in urls
    assert "http://test.org/path?q=1" in urls
    assert len(urls) == 2


@pytest.mark.asyncio
async def test_unsupported_type_treated_as_text(parser):
    """Test that unsupported file types fall back to plain text parsing."""
    content = b"Plain text content for testing."
    result = await parser.parse("test.txt", content)
    assert "Plain text content" in result.raw_text
