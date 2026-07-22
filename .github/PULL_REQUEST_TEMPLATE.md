<!--
PR titles must follow Conventional Commits (enforced by the Semantic PR workflow),
e.g. `feat(catalog): …`, `fix(sync): …`, `chore(deps): …`. The title becomes the
squash-merge commit subject and drives release-please.
-->

## Summary

<!-- What does this change and why? -->

## Related issues

<!-- e.g. Closes #123 -->

## Checklist

- [ ] PR title follows Conventional Commits
- [ ] Tests added/updated for the change (every defect fixed in review lands with a regression test)
- [ ] `ruff check` / `mypy` / `pytest` pass for backend changes
- [ ] `npm run lint` / `npm run build` / `npm test` pass for frontend changes
- [ ] OpenAPI contract updated and `npm run gen:api` re-run if the API surface changed
- [ ] Docs (`README.md` / `prd.md` / specs) updated if behavior or setup changed
