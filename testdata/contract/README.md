# Contract fixtures

## `golden/`

Copied from DatoriumDB **v0.0.5** (`datoriumdb/test/contract/golden/`).

These fixtures are the authoritative response shapes for envelope decoding tests.

## Updating fixtures

1. Check out DatoriumDB at the tagged release matching [tech-docs/COMPATIBILITY.md](../../tech-docs/COMPATIBILITY.md).
2. Copy `test/contract/golden/*.json` into `golden/`.
3. Note the source tag/commit in the changelog and COMPATIBILITY.md.
4. Run `pytest tests/contract`.
