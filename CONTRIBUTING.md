# Contributing

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
