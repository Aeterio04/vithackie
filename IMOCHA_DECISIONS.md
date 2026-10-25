# IMOCHA Decisions and Assumptions

1. **Spec has 46 TCs, not about 45.** All 46 are used. Gates compare against the parsed count, not a hard-coded 45.
2. **Single-step "loop" TCs pass the lint.** TC-NAV-005, PAGE-001, PAGE-002, PAGE-006 and RESP-001 have one unnumbered step of the form "For each ... / Open each ...". The lint rule "fewer than 2 steps" is waived only when that one step contains an iteration phrase (`for each`, `open each`, `each of`), because it implies open, act and verify per item. The step text is stored verbatim.
3. **Expected results split.** Bullet lists become one expected item per bullet. Inline text is split on `;` outside parentheses and backticks. Items are kept verbatim, with no rewriting.
4. **Measurable check in the lint** is a keyword heuristic (digits, equals, contains, ends, status, href, at least, below, naturalWidth, aria-, "fails to load", "served from", ...). TC-HOME-005 needed "fails to load" and "served from" added: its only measurable clause is "Record any image that fails to load or is served from a third-party host", which is observable in the browser.
5. **Priority mapping:** P0 -> critical, P1 -> high, P2 -> medium. Original P-level is kept in the spec; the catalog keeps the mapped value.
6. **Alignment strictness:** a catalog test whose title, steps or expected results differ from the spec counts as `changed` and blocks execution. This also blocks human edits at the review gate. Revisit if reviewers need to edit tests.
7. **Legacy parser:** if a spec contains TC blocks, `parse_spec_text` returns the REQ table as spec items, so existing consumers (coverage matrix, `RunInput.spec`) see the 17 REQs instead of junk. Bullet-style specs go through the old code path unchanged.
8. **Pre-existing test failures** (alembic/DB hardening tests, `test_validation_errors_reported_together`, scaffolding) were seen both with and without my changes and were left alone.
