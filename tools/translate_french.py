#!/usr/bin/env python3
"""
Extract and translate French passages from a PDF using the Claude API.
Outputs a Markdown document with page number and chapter/section context
for each translated passage.

Usage:
    ANTHROPIC_API_KEY=sk-... python3 translate_french.py <pdf_path> [options]

Options:
    --output, -o   Output Markdown file (default: <pdf_stem>-translations.md)
    --start-page   First page to process (1-indexed, default: 1)
    --end-page     Last page to process (inclusive, default: last page)
    --batch        Pages per API call (default: 12)

Requires:
    pip install pdfplumber anthropic
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pdfplumber
import anthropic

MODEL = 'claude-sonnet-4-6'
DEFAULT_BATCH = 12

SYSTEM_PROMPT = """\
You are a specialist in 18th-century French history reading Robert Darnton's
"The Business of Enlightenment: A Publishing History of the Encyclopédie, 1775–1800".
The book is written in English but contains many French passages: quotations from
correspondence, manuscripts, business documents, and the Encyclopédie itself.

Your task: find every French passage in the supplied page extracts and translate it.
Include passages of any length — a single French phrase embedded in an English sentence
counts. Exclude proper nouns and book/article titles that appear only as citations.

For each passage output a JSON object. Return ONLY a JSON array, no markdown fences,
no explanation text. If a batch has no French text, return [].

Schema:
[
  {
    "page": <integer>,
    "chapter": "<nearest chapter heading>",
    "section": "<nearest section heading, or null>",
    "french": "<exact French text as it appears, preserving original spelling>",
    "english": "<your English translation, in brackets if inserting implied words>"
  }
]"""


def extract_pages(pdf_path: Path) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            if i % 100 == 0:
                print(f'  Extracting... {i+1}/{total}', file=sys.stderr)
            text = page.extract_text(layout=False) or ''
            pages.append({'num': i + 1, 'text': text})
    return pages


# Patterns for chapter/section headings common in academic books
CHAPTER_PAT = re.compile(
    r'^(CHAPTER\s+\w+|PART\s+(?:ONE|TWO|THREE|FOUR|FIVE|\w+)|'
    r'EPILOGUE|PROLOGUE|INTRODUCTION|CONCLUSION|APPENDIX\b)',
    re.IGNORECASE,
)
SECTION_PAT = re.compile(r'^[IVX]+\.\s+.{5,60}$|^\d+\.\s+[A-Z].{5,55}$')


def annotate_headings(pages: list[dict]) -> list[dict]:
    current_chapter = 'Front matter'
    current_section = None
    for page in pages:
        lines = [l.strip() for l in page['text'].split('\n') if l.strip()]
        for line in lines:
            if CHAPTER_PAT.match(line) and len(line) < 90:
                current_chapter = line
                current_section = None
            elif SECTION_PAT.match(line):
                current_section = line
        page['chapter'] = current_chapter
        page['section'] = current_section
    return pages


def format_batch(pages: list[dict]) -> str:
    chunks = []
    for page in pages:
        header = f'[Page {page["num"]} | {page["chapter"]}'
        if page.get('section'):
            header += f' / {page["section"]}'
        header += ']'
        chunks.append(header)
        chunks.append(page['text'])
    return '\n\n'.join(chunks)


def call_claude(client: anthropic.Anthropic, batch_text: str) -> list[dict]:
    # Stream the response to avoid read timeouts on large outputs
    with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': batch_text}],
    ) as stream:
        raw = stream.get_final_text().strip()
    # Strip accidental markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f'  ⚠ JSON parse error: {e}', file=sys.stderr)
        print(f'  Response preview: {raw[:300]}', file=sys.stderr)
        return []


def group_by_chapter(results: list[dict]) -> dict[str, list[dict]]:
    chapters: dict[str, list[dict]] = {}
    for r in results:
        ch = r.get('chapter') or 'Unidentified'
        chapters.setdefault(ch, []).append(r)
    return chapters


def render_markdown(results: list[dict], title: str, author: str) -> str:
    lines = [
        f'# French Passages: *{title}*',
        f'*{author}*',
        '',
        (
            f'Translated by Claude ({MODEL}). '
            'Original French preserved verbatim. '
            'Bracketed words in translations indicate implied meaning. '
            'For research use.'
        ),
        '',
        '---',
        '',
    ]

    for chapter, items in group_by_chapter(results).items():
        lines.append(f'## {chapter}')
        lines.append('')
        for item in sorted(items, key=lambda x: x.get('page', 0)):
            page = item.get('page', '?')
            section = item.get('section')
            label_parts = [f'**p. {page}**']
            if section:
                label_parts.append(f'*{section}*')
            lines.append(' — '.join(label_parts))
            lines.append('')
            # Block-quote the French, then translation below
            for line in item['french'].split('\n'):
                lines.append(f'> {line}')
            lines.append('')
            lines.append(f'*{item["english"]}*')
            lines.append('')
        lines.append('---')
        lines.append('')

    lines.append(f'*{len(results)} passages translated.*')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pdf', help='Path to PDF file')
    parser.add_argument('--output', '-o', help='Output Markdown path')
    parser.add_argument('--start-page', type=int, default=1)
    parser.add_argument('--end-page', type=int, default=None)
    parser.add_argument('--batch', type=int, default=DEFAULT_BATCH, help='Pages per API call')
    args = parser.parse_args()

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        sys.exit('Error: ANTHROPIC_API_KEY environment variable not set.')

    client = anthropic.Anthropic(api_key=api_key)
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f'Error: {pdf_path} not found.')

    output_path = Path(args.output) if args.output else pdf_path.with_suffix('.translations.md')

    print(f'Extracting text from {pdf_path.name}…', file=sys.stderr)
    pages = extract_pages(pdf_path)
    pages = annotate_headings(pages)

    start = args.start_page - 1
    end = args.end_page if args.end_page else len(pages)
    pages = pages[start:end]
    print(f'Processing {len(pages)} pages ({start+1}–{start + len(pages)}) in batches of {args.batch}…', file=sys.stderr)

    # Incremental JSONL cache: survives crashes, enables resume
    cache_path = output_path.with_suffix('.cache.jsonl')
    done_pages: set[int] = set()
    all_results: list[dict] = []

    if cache_path.exists():
        print(f'Resuming from cache {cache_path.name}…', file=sys.stderr)
        with open(cache_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('_batch_pages'):
                        done_pages.update(entry['_batch_pages'])
                    else:
                        all_results.append(entry)
                except json.JSONDecodeError:
                    pass
        print(f'  Loaded {len(all_results)} passages, {len(done_pages)} pages already processed.', file=sys.stderr)

    cache_fh = open(cache_path, 'a', encoding='utf-8')
    n_batches = (len(pages) + args.batch - 1) // args.batch

    try:
        for i in range(0, len(pages), args.batch):
            batch = pages[i:i + args.batch]
            batch_page_nums = {p['num'] for p in batch}

            # Skip if all pages in this batch were already processed
            if batch_page_nums.issubset(done_pages):
                batch_num = i // args.batch + 1
                print(f'  [{batch_num}/{n_batches}] pages {batch[0]["num"]}–{batch[-1]["num"]}… skipped (cached)', file=sys.stderr)
                continue

            label = f'{batch[0]["num"]}–{batch[-1]["num"]}'
            batch_num = i // args.batch + 1
            print(f'  [{batch_num}/{n_batches}] pages {label}…', file=sys.stderr, end=' ', flush=True)

            batch_text = format_batch(batch)
            results = call_claude(client, batch_text)
            all_results.extend(results)

            # Write results + sentinel to cache immediately
            for r in results:
                cache_fh.write(json.dumps(r, ensure_ascii=False) + '\n')
            cache_fh.write(json.dumps({'_batch_pages': list(batch_page_nums)}) + '\n')
            cache_fh.flush()

            print(f'{len(results)} passage(s)', file=sys.stderr)

            if i + args.batch < len(pages):
                time.sleep(0.3)
    finally:
        cache_fh.close()

    print(f'\nTotal: {len(all_results)} French passages found.', file=sys.stderr)
    print(f'Writing to {output_path}…', file=sys.stderr)

    md = render_markdown(
        all_results,
        title='The Business of Enlightenment: A Publishing History of the Encyclopédie, 1775–1800',
        author='Robert Darnton',
    )
    output_path.write_text(md, encoding='utf-8')
    print(f'Done. Cache retained at {cache_path.name} — delete it to force a full re-run.', file=sys.stderr)


if __name__ == '__main__':
    main()
