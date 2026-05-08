# Contributing

**Read this file before contributing anything to this repository.**

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

## Zone ownership

| Zone | Rule |
|------|------|
| `raw-notes/yourname/` | Push directly; you own your directory. |
| `wiki/` | PR required; any repo admin may approve. |
| `website/` | PR required; Venkat must approve. |

See `.github/CODEOWNERS` for the full ownership map.
