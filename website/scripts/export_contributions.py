#!/usr/bin/env python3
"""
Mirror contribution essays into raw-notes/commons/contributions/ so the
knowledge lake (and therefore the Oracle) can retrieve them.

    cd website && python scripts/export_contributions.py

The lake indexes raw-notes/ only, and embeds just the first `max_doc_chars`
(6000) of a note. So each essay is split at paragraph boundaries into parts
of at most PART_CHARS, one note per part:

    raw-notes/commons/contributions/<slug>/<slug>-p01.md, -p02.md, …

Note ids are file stems and must be unique repo-wide, hence the slug prefix.
Frontmatter `author:` overrides the folder-derived author, so each part is
credited to the member who wrote the essay, not to `commons`.

This is a deliberate exception to "no source text in raw-notes"
(wm-encyclopedia-kb/docs/RAG-SUBMISSIONS.md). These are members' own essays,
already public in content/articles/. Team-only articles and resources are
never exported.

Idempotent: it rewrites a slug's directory only when the parts change, and
removes directories whose article is gone or no longer qualifies.
"""
import json
import re
import shutil
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent
ARTICLES = WEBSITE / 'content' / 'articles'
OUT = WEBSITE.parent / 'raw-notes' / 'commons' / 'contributions'

PART_CHARS = 5000


def qualifies(article):
    return (article.get('type') == 'contribution'
            and article.get('extraction_success')
            and (article.get('extracted_text') or '').strip()
            and article.get('license') != 'team_only')


def split_parts(text, limit=PART_CHARS):
    """Pack paragraphs (one per line, as trafilatura emits them) into parts ≤ limit."""
    paras = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
    pieces = []
    for p in paras:
        while len(p) > limit:  # a single giant paragraph: cut at a sentence end
            cut = max(p.rfind('. ', 0, limit), p.rfind('? ', 0, limit), p.rfind('! ', 0, limit))
            cut = cut + 1 if cut > limit // 2 else limit
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)

    parts, cur = [], ''
    for piece in pieces:
        if cur and len(cur) + 2 + len(piece) > limit:
            parts.append(cur)
            cur = piece
        else:
            cur = f'{cur}\n\n{piece}' if cur else piece
    if cur:
        parts.append(cur)
    return parts


def _q(value):
    return json.dumps(value, ensure_ascii=False)  # a JSON string is valid YAML


def author_of(article):
    # A few early entries predate handles and record `submitted_by` instead.
    return article.get('handle') or article.get('submitted_by') or 'commons'


def render(article, body, n, total):
    title = article.get('title') or article['slug']
    heading = title if total == 1 else f'{title} (part {n} of {total})'
    summary = article.get('description') or f'Contribution essay by {author_of(article)}, submitted to World Machines.'
    lines = [
        '---',
        f'author: {_q(author_of(article))}',
        'type: contribution',
        f'resource: {_q(article["url"])}',
        f'source: {_q(article["slug"])}',
        f'summary: {_q(summary)}',
        'tags:',
        '- contribution',
        f'- {_q(article.get("format") or "essay")}',
    ]
    date = (article.get('published_at') or article.get('submitted_at') or '')[:10]
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        lines.append(f'last_updated: {date}')
    lines += [f'part: {n}', f'parts: {total}', '---', '', f'# {heading}', '', body, '']
    return '\n'.join(lines)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = set()
    written = unchanged = 0
    for path in sorted(ARTICLES.glob('*.json')):
        article = json.loads(path.read_text(encoding='utf-8'))
        if not qualifies(article):
            continue
        slug = article['slug']
        wanted.add(slug)
        parts = split_parts(article['extracted_text'])
        files = {f'{slug}-p{n:02d}.md': render(article, body, n, len(parts))
                 for n, body in enumerate(parts, 1)}
        d = OUT / slug
        current = {p.name: p.read_text(encoding='utf-8') for p in d.glob('*.md')} if d.is_dir() else {}
        if current == files:
            unchanged += 1
            continue
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for name, content in files.items():
            (d / name).write_text(content, encoding='utf-8')
        written += 1
        print(f'  {slug}: {len(parts)} part(s)')

    removed = 0
    for d in OUT.iterdir():
        if d.is_dir() and d.name not in wanted:
            shutil.rmtree(d)
            removed += 1
            print(f'  removed {d.name}')
    print(f'{written} written, {unchanged} unchanged, {removed} removed')


if __name__ == '__main__':
    main()
