# References

Datorium documents may store references as strings:

| Kind | Format | Meaning |
|------|--------|---------|
| Direct | `@__Collection__id` | Live reference to another document |
| Cached | `@@__Collection__id` | Front-page / summary reference |

```python
from datorium_client import format_direct, format_cached, parse_ref

print(format_direct("Users", "u1"))
ref, ok = parse_ref("@__Users__u1")
```

Read with `cache_summaries=True` to receive summary objects for cached refs. Helpers such as `summaries_for_array_field` extract those summaries for a SOT array field.
