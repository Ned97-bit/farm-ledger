---
description: List the active year's quests (read-only helper before editing)
---

Read `<YEAR>/_quests.json` for the active year and show the user a terse summary:

```
Active quests for <YEAR>:
  1. (id) Label  [required|optional]  @Category  — match: tok1, tok2
  ...
Removed (status=removed): <count>
```

Use this before `/add-quest` to avoid duplicates and before `/remove-quest` to confirm the id. No writes.
