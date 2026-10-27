---
name: pdf_translator
description: High-precision chunked PDF academic translation into Traditional Chinese (Taiwan academic terminology) with LaTeX formula preservation.
---

# Skill: PDF Translator (`pdf_translator`)

This skill extracts text from academic PDF papers, segments them into manageable chunks, and performs concurrent academic translation into Traditional Chinese (Taiwan terminology).

## Execution Pipeline
1. **Load and Chunk**:
   - Reads the PDF file located at `state.top_paper.pdf_path` via `PyMuPDF` (`fitz`).
   - Aborts gracefully if paper path is missing or file does not exist.
   - Splits extracted text into chunks of 2,000 characters.
2. **Translate Chunks**:
   - Concurrently translates chunks with academic translation prompt.
   - Preserves mathematical formulas in LaTeX format ($E=mc^2$).
   - Retains proper nouns in English or parenthesized.
   - Preserves chunk ordering and writes markdown to `Papers/Translated_{file_name}.md`.
   - Stores output path in `state.final_translated_file`.
