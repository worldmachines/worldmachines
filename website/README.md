# Website

Cloudflare Pages website for World Machines.

Website changes must go through pull requests and must be approved by Venkat before merge. Configure GitHub branch protection to require CODEOWNERS review for `website/**`.

## Local build

```bash
cd website
python3 scripts/build.py
```

## Deploy

GitHub Actions deploys `website/` after article ingestion. Manual deploys, when necessary:

```bash
cd website
wrangler pages deploy . --project-name worldmachines --commit-dirty=true
```
