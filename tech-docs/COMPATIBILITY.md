# Compatibility

## Target

| Layer | Version |
|-------|---------|
| DatoriumDB | **v0.0.4** |
| HTTP API | `/datoriumdb/v1` |
| Client package | 0.1.x |

## Fixture provenance

Golden envelopes in [`testdata/contract/golden/`](../testdata/contract/golden/) were copied from `datoriumdb/test/contract/golden` at the v0.0.4 line.

Update procedure is documented in that directory’s README.

## Drift checks

1. Diff golden fixtures against a tagged DatoriumDB checkout.
2. Run unit + contract tests.
3. Optionally run Docker integration against that tag.
