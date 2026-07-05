# GitHub Backend Notes

Use this reference only when the user asks to upgrade parsing, reading, or graph construction beyond the local `paper_digest.py` workflow.

## Parsing Backends

- Docling: https://github.com/docling-project/docling
  - Good fit for future PDF-to-Markdown/JSON parsing in Python-first workflows.
  - Prefer as the first heavy backend to test on Windows.
- GROBID: https://github.com/grobidOrg/grobid
  - Strong scientific-paper parser for metadata, sections, references, and citations.
  - Usually requires a Java service or Docker; treat as a later service-backed upgrade.
- Unstructured: https://github.com/Unstructured-IO/unstructured
  - General document ETL for LLM/RAG pipelines.
  - Useful if the project broadens beyond papers.
- S2ORC doc2json: https://github.com/allenai/s2orc-doc2json
  - Useful reference for scientific PDF/LaTeX/JATS JSON schemas.
- Nougat: https://github.com/facebookresearch/nougat
  - Useful for OCR-like paper-to-Markdown extraction, but may need heavier model dependencies.

## Reading And Zotero Tools

- Zotero Better Notes: https://github.com/windingwind/zotero-better-notes
  - Strong Zotero-native note workflow. Consider user-side installation, not project automation.
- llm-for-zotero: https://github.com/yilewang/llm-for-zotero
  - Zotero-centered research agent. Evaluate separately before mixing with this project.
- Zotero GPT: https://github.com/MuiseDestiny/zotero-gpt
  - Useful reference for interactive paper Q&A inside Zotero.
- Zotero PDF Translate: https://github.com/windingwind/zotero-pdf-translate
  - Useful if bilingual reading and annotation translation become a priority.

## Graph/RAG Backends

- Microsoft GraphRAG: https://github.com/microsoft/graphrag
  - Consider after the local `paper_graph.json` has enough clean entities.
- SciAtlas: https://github.com/zjunlp/SciAtlas
  - Reference for scientific knowledge graph design.
- OpenAlex: https://github.com/ourresearch/OpenAlex
  - Continue using OpenAlex APIs for paper, venue, author, and citation metadata.
