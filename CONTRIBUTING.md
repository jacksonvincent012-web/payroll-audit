# Contributing

## Branch model

`main` is protected. Direct commits to `main` are not allowed.

1. Branch from `main`:
   ```
   git checkout -b feat/short-description
   ```
2. Commit in small, reviewable slices (2–4 commits per pull request).
3. Push the branch and open a pull request against `main`.
4. **One approving review is required** from a contributor who did not author the PR.
5. Squash-merge into `main`.

## Commit message format

```
<type>: <summary in imperative mood>
```

Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`.

Examples:
- `feat: add approver escalation after 48h delay`
- `test: cover HMAC chain truncation detection`
- `security: rate-limit login attempts per IP`

## Pull request checklist

- [ ] Tests added or updated for the change
- [ ] No secrets, API keys, tokens, or credentials in the diff
- [ ] No generated files, lockfile-only changes, or vendored third-party code
- [ ] No auto-generated boilerplate committed as "new code"
- [ ] Security controls (HMAC chain, append-only triggers, auth, RBAC) are
      **not weakened** unless this PR is explicitly about changing them
- [ ] Migrations included and reversible where applicable
- [ ] Documentation updated if behaviour or configuration changed

## What not to commit

- `.env` files, `db.sqlite3`, uploaded media, or any local credentials
- `node_modules/`, `__pycache__/`, virtual environments
- Third-party libraries copied into the tree

## Review standard

A reviewer should be able to answer, from the PR description alone:

1. What problem does this solve?
2. How was it verified?
3. What could break?
