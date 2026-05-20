# Contributing

**Read this file before contributing anything to this repository.**

For a full technical overview of the website stack, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Proposals and decisions

Use **GitHub Issues** (labeled `proposal`) for anything that needs group input before work begins — technical plans, feature proposals, infrastructure changes, policy questions.

Structure a proposal issue with:
- A summary of what is being proposed and why
- The key design decisions and tradeoffs
- Explicit questions you want contributors to answer

Once a decision is reached, close the issue with a resolution summary and record the decision in `wiki/decisions/` as a short ADR (Architecture Decision Record) — one file per decision, linked from the closing comment.

**Do not put in-progress planning artifacts in the repo tree.** Issues are the deliberation space; the wiki is the durable record of what was decided and why.

## Devlog rule

Every non-trivial commit or PR to this repository should include an update to `website/devlog.md`. Prepend a new entry:

```
## YYYY-MM-DD · yourhandle
One to three sentences: what changed and why it matters for the project.
```

For trivial changes (typo fixes, formatting, config tweaks), add `[trivial]` to your commit message instead. The `devlog-check` workflow will flag violations with a red ✗ — it will not block your merge, but please follow the rule.

## Security

**Never commit API keys, tokens, or credentials to this repository.**

- Store credentials in `.env` or `.env.keys` at the repo root — both are gitignored and will not be committed.
- Do not hardcode credentials in scripts, raw notes, or any other tracked file.
- Before pushing, run `git diff --staged` and check that no secrets appear in staged content.
- If you accidentally commit a credential, treat it as compromised immediately: rotate the key and notify Venkat. Do not assume that deleting the file in a follow-up commit is sufficient — the credential is in git history and should be considered public.

The `.gitignore` covers `.env` and `.env.keys` by name. If you create a credentials file with a different name, add it to `.gitignore` yourself before staging anything.

## Zone ownership

| Zone | Rule |
|------|------|
| `raw-notes/yourname/` | Push directly; you own your directory. |
| `wiki/` | PR required; any repo admin may approve. |
| `website/` | PR required; Venkat must approve. |

See `.github/CODEOWNERS` for the full ownership map.
