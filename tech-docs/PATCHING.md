# Patching design

The internal `_json`, `_schema`, and `_patch` packages implement the ojson-compatible subset required by typed collections:

- Ordered objects and exact number lexemes
- Void vs Null
- Datorium schema compile / apply / normalize
- RFC 6901 pointers and RFC 6902 ops
- Schema-aware diff/apply validation
- Custom formats `DatoriumDirectRef` / `DatoriumCachedRef`

Public typed APIs: `create_patch_from_changes`, `create_patch`, `patch_doc`.

Raw APIs accept detail dicts with `$`, `#`, and `RFC6902`.
