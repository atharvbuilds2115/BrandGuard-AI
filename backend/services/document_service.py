from __future__ import annotations

import csv
from pathlib import Path

import fitz
from docx import Document


SUPPORTED_EXTENSIONS = {'.txt', '.csv', '.pdf', '.docx', '.png', '.jpg', '.jpeg', '.webp'}


def extract_text_from_file(file_path: str, mime_type: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in {'.txt', '.csv'}:
        try:
            with path.open('r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            with path.open('r', encoding='latin-1') as file:
                return file.read()

    if suffix == '.pdf':
        text_chunks: list[str] = []
        doc = fitz.open(path)
        for page in doc:
            text_chunks.append(page.get_text())
        doc.close()
        return '\n'.join(text_chunks).strip()

    if suffix == '.docx':
        document = Document(path)
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return '\n'.join(paragraphs)

    if suffix in {'.csv'}:
        rows: list[str] = []
        with path.open('r', encoding='utf-8', newline='') as file:
            reader = csv.reader(file)
            for row in reader:
                rows.append(', '.join(row))
        return '\n'.join(rows)

    if suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
        return 'OCR is not implemented for image uploads. Asset stored for later review.'

    return ''
