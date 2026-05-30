# ADR 0002 — Book ingestion: separate vs. merged Oracle index

**Status:** proposed — seeking input from @aneeshsathe before implementation
**Date:** 2026-05-30
**Authors:** vgr
**Relates to:** [ADR 0001](0001-notes-oracle-architecture.md)

## Context

We now have a `worldmachines-library` R2 bucket hosting full PDFs — starting with Darnton's *The Business of Enlightenment* (CC BY). More books will follow, a mix of public domain, Creative Commons, and team-only.

The Oracle currently searches raw notes via a single `notes.parquet` file embedded with Workers AI vectors and queried by DuckDB-WASM in the browser. Books are fundamentally different from notes:

| | Notes | Books |
|---|---|---|
| Length | Short (markdown files, ~500–2000 words each) | Long (100–700 pages) |
| Origin | Native worldmachines thinking | Third-party authored texts |
| Structure | Flat / linked | Chapters → sections → paragraphs |
| Semantic density | Conceptually dense, compressed | Narrative/argumentative, more context needed |
| Volume | ~750 files currently | A 500-page book → ~1500–3000 chunks |

Ingesting one book adds more text than the entire notes corpus. Mixing them naively risks drowning the notes signal.

## Options considered

### Option A: Merge books into the notes index

Chunk books and add rows directly to `worldmachines-notes.parquet` alongside note rows.

**Pros:**
- Oracle works with zero UI changes
- Cross-source retrieval happens automatically (a query about the Encyclopédie finds both Aneesh's note on it and the relevant Darnton chapter)

**Cons:**
- Book volume dwarfs notes — retrieval may become dominated by book chunks
- Chunk size mismatch: notes are whole files (~1000 tokens), books need ~400–800 token chunks with overlap
- Notes pipeline would need refactoring to handle variable-length chunking

### Option B: Separate book index, separate UI

New `books-index.parquet` stored in LIBRARY R2. A new "Library" tab on `oracle.html` (or separate `library-oracle.html`) queries only this file.

**Pros:**
- Notes Oracle is completely unaffected — no regression risk
- Book index can be optimized independently (chunk size, metadata schema)
- Clean conceptual separation: notes = our thinking, library = source texts

**Cons:**
- Users must consciously choose which corpus to search
- Cross-source connections (Aneesh's note references Darnton) not surfaced automatically

### Option C: Separate index, unified query (preferred starting point)

Book chunks in a separate Parquet (`books-index.parquet`), but DuckDB-WASM queries both files in a single Oracle search. Results are merged and labelled by source (note vs. book title + chapter).

**Pros:**
- Single search box, no context-switching
- Source labels let users understand result provenance
- Notes and books indexed independently, can tune each separately
- Reveals cross-corpus connections (query → finds both a note and the book chapter it references)

**Cons:**
- Slightly more complex DuckDB query (union or ranked merge)
- Need a strategy for weighting/blending notes vs. book chunks in ranking

## Proposed technical plan (pending Option C confirmation)

### Ingest pipeline
New script `tools/ingest_pdf.py`:
1. Extract text via `pdfplumber` (page by page, preserving page numbers)
2. Detect chapter/section headings from font size or text patterns
3. Chunk into ~600-token segments with ~150-token overlap (proposed — see questions)
4. Embed each chunk via Workers AI (`@cf/baai/bge-base-en-v1.5`)
5. Write to `books-index.parquet` with columns:

```
book_slug, title, author, chapter, section, page_start, page_end,
body, word_count, embedding float[768]
```

6. Upload to `worldmachines-library/books-index.parquet`

### Article JSON update
Add `indexed: true/false` to track which PDFs have been ingested (avoids double-indexing on re-run).

### Oracle query update (`oracle.html`)
Modify the DuckDB-WASM query to optionally load `books-index.parquet` from R2 and union with notes results, tagging each row with `source = 'note'` or `source = 'book'`. Add a source badge to result cards.

## Questions for @aneeshsathe

1. **Retrieval quality with mixed corpus:** Does mixing book chunks (~600 tokens of dense academic prose) with note chunks hurt embedding-based retrieval? Or does the semantic overlap (notes that reference books, books that ground abstract concepts) make the merged index more useful? Have you seen this pattern work well or badly in practice?

2. **Chunk size:** For dense academic history prose (Darnton, Ibn Khaldun, Braudel), what chunk size gives the best retrieval quality with `bge-base-en-v1.5`? My instinct is 600 tokens / 150 overlap but I'd defer to your experimentation.

3. **Ranking in Option C:** If we union notes and book chunks, pure cosine similarity may always favour long book chunks (more context = better embedding match). Should we apply a note/book weight factor, or let similarity score stand alone and see what happens empirically?

4. **Is Option B actually better for V1?** If Option C complexity isn't worth it yet, Option B (separate UI) is faster to ship. Happy to do B now and merge later. Your call.
