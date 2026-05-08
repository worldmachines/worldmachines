# Kickoff / repo architecture meeting summary

Source: https://gist.github.com/vgururao/ee85a27434446b17599b9161a4e26b19

## Project direction

World Machines is evolving from collective essay writing into a structured knowledge system. The group discussed a layered architecture:

1. Raw chaotic reading and writing.
2. Rough notes and research dumps as connective tissue between ideas.
3. Structured analysis using embeddings, statistical models, and time-aware simulation.
4. A future predictive “psychohistory” core with falsifiable claims.

## Technical decisions

- Use GitHub as the shared content-management substrate.
- Keep Markdown / Obsidian-style working material separate from the public website.
- Use AI agents to organize raw material into wiki entries and propose pull requests.
- Require human review and approval for AI-generated organization changes.
- Keep notification and comment systems attached to repo/content changes rather than external publishing platforms.

## Repo implications

- `raw-notes/`: one directory per participant; contributors can push their own rough notes.
- `wiki/`: curated shared knowledge layer; AI-generated PRs from raw notes; admin/maintainer approval required.
- `website/`: public Cloudflare Pages site; changes by PR only; Venkat approval required.
