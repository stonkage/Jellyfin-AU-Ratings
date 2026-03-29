# Test Coverage

**203 tests, 95 subtests — all passing.**

Run with:

```bash
pip install pytest
pytest test_jellyfin_au_ratings.py -v
```

No network connection required. All Jellyfin API calls are mocked using `unittest.mock`.

---

## Coverage by class

| Class | Tests | What's covered |
|---|---|---|
| `TestExtractAge` | 13 | Regex parsing of bare age strings — integers, `+` suffix, whitespace, unicode minus, rejection of 3-digit and alphanumeric |
| `TestAgeToAu` | 12 | Age bucket boundaries: every transition point in the G / PG / M / MA 15+ / R 18+ ladder |
| `TestNormaliseAu` | 15 | Spacing variants (MA15+, R18+), AU- prefix stripping, case insensitivity, non-AU returns None |
| `TestMapRating` | 45 | Core mapping waterfall — empty/None input, all canonical AU pass-throughs, MPAA, TV, BBFC, FSK, French, Dutch, case-insensitive fallback, skip entries, unmapped strings |
| `TestMapRatingAdditional` | 11 | Canadian, Brazilian, and remaining Dutch ratings |
| `TestCleanPayload` | 7 | Null-field sanitiser that prevents Jellyfin NullReferenceException crashes |
| `TestItemDisplayName` | 6 | Movie, episode (series only), episode (series + season), missing name fallback, empty/None series |
| `TestAuthHeader` | 6 | MediaBrowser header format, token inclusion, trailing slash stripping |
| `TestAuthenticateWithApiKey` | 5 | Admin user selection, fallback to first user, missing Policy key |
| `TestAuthenticateWithPassword` | 5 | User ID from response, token header update, correct endpoint, request body |
| `TestGetAllItems` | 5 | Single-page, two-page, three-page pagination, empty library, StartIndex increments |
| `TestDoUpdate` | 10 | Strategy 1 success, in-memory update, correct ID, fallback to strategy 2 on HTTP error, both strategies fail, null-field cleaning |
| `TestDoUpdateAdditional` | 3 | get_item_full failure on strategy 1, error string format, total failure |
| `TestCredentialStore` | 23 | load/save/forget/has_saved — file creation, chmod 600, host persistence, overwrite, missing section, double-forget safety |
| `TestColourHelpers` | 8 | ANSI code presence, green/red/dim assignment for success and error counts |
| `TestRatingTag` | 5 | Breakdown view annotations — green ✓, cyan →, red ⚠, dim skip, empty string |
| `TestMapRatingRoundTrip` | 1 (×11 subtests) | Every canonical AU rating fed back in returns `already_au` |
| `TestRatingMapCompleteness` | 2 (×84 subtests) | Every non-null RATING_MAP entry produces a valid AU rating; every null entry is a known skip |
| `TestPrintDone` | 5 | Bulk operation summary output — green zero errors, red non-zero, error samples, success count |

---

## Design notes

**Rating logic** is the most critical area — `map_rating` has six possible return statuses and a multi-stage lookup waterfall (exact match → case-insensitive → normalise → prefix strip → age extraction). Tests cover every branch and each foreign rating system independently.

**`_do_update`** has a two-strategy fallback (full payload first, minimal payload second). Tests verify each strategy succeeds and fails independently, that in-memory item state is only updated on success, and that both-fail returns a combined error string rather than raising.

**Credential store** tests redirect `_CONFIG_PATH` to a temp directory so they never touch `~/.config`. The chmod 600 assertion verifies the actual file permission bits.

**Integration sweeps** use `subTest` to run every AU rating and every RATING_MAP entry as independent sub-cases, so a single bad entry produces a named failure rather than an early exit.

---

← Back to [README.md](README.md)
