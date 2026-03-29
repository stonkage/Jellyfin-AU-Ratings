# Jellyfin Australian Rating Manager

> ⚠️ **Vibe coded.** This entire project — script, tests, and documentation — was written through a conversational session with Claude. No code was written by hand. See [PROMPTS.md](PROMPTS.md) for the full prompt sequence used to build it.

An interactive terminal tool for browsing, converting, and managing parental ratings in a Jellyfin media library using Australian Classification Board (ACB) classifications.

---

## What it does

- **Rating Breakdown** — browse your library by type (Movies, Series, Seasons, Episodes) and see every rating in use, colour-coded by AU status
- **Auto-Convert All** — maps foreign rating systems (US MPAA/TV, UK BBFC, German FSK, French, Dutch, Brazilian, Canadian) to their closest AU equivalent in one shot
- **Inherit Series** — pushes a series' rating down to all mismatched episodes and seasons
- **Search** — find items by name and change ratings individually
- **Credential store** — saves your Jellyfin host URL + API key or username/password to `~/.config/jellyfin_au_ratings.cfg` (chmod 600) so you don't re-enter them on every run

---

## Requirements

```
python3
pip install requests
```

No other dependencies. The credential store uses the standard library (`configparser`, `pathlib`, `stat`).

---

## Usage

```bash
python3 jellyfin_au_ratings.py
```

On first run you'll be prompted for:
1. Jellyfin host URL (e.g. `https://jellyfin.example.com`)
2. Auth method — API key or username/password

After a successful login you'll be asked whether to save the config for next time.

**Environment variable overrides** (useful for automation):

```bash
JELLYFIN_URL=https://jellyfin.example.com \
JELLYFIN_API_KEY=your-key-here \
python3 jellyfin_au_ratings.py
```

Or with username/password:

```bash
JELLYFIN_URL=https://jellyfin.example.com \
JELLYFIN_USERNAME=admin \
JELLYFIN_PASSWORD=secret \
python3 jellyfin_au_ratings.py
```

**Quit from anywhere:** `Ctrl+C` at any prompt exits cleanly.

---

## Supported rating systems

| System | Examples | Maps to |
|---|---|---|
| US MPAA | G, PG, PG-13, R, NC-17 | G, PG, M, MA 15+, R 18+ |
| US TV | TV-Y, TV-Y7, TV-G, TV-PG, TV-14, TV-MA | P, C, G, PG, M, MA 15+ |
| UK BBFC | U, PG, 12, 12A, 15, 18, R18 | G, PG, M, M, MA 15+, R 18+, R 18+ |
| UK prefixed | GB-U, GB-PG, GB-12, GB-15, GB-18 | as above |
| German FSK | FSK-0/6/12/16/18, de/0–18 | G, PG, M, MA 15+, R 18+ |
| French | FR-U, FR-10, FR-12, FR-16, FR-18 | G, PG, M, MA 15+, R 18+ |
| Canadian | 14A, 14+, 18A, A | M, M, MA 15+, R 18+ |
| Dutch | AL, nl/6, nl/9, nl/12, nl/16 | G, PG, PG, M, MA 15+ |
| Brazilian | L, 10, 14, 16 | G, PG, M, MA 15+ |
| AU variants | MA15+, R18+, AU-G, AU-MA 15+, etc. | normalised to canonical form |
| Bare ages | 6, 15+, -18 | mapped via age buckets |

Ratings marked NR, Unrated, Not Rated, or Approved are skipped (left unchanged).

---

## Saved config

```ini
# ~/.config/jellyfin_au_ratings.cfg  (chmod 600)
[credentials]
host = https://jellyfin.example.com
api_key = your-key-here
username =
password =
```

Use **Forget Saved Credentials** from the main menu to wipe it.

---

## Tests

**203 tests, 95 subtests — all passing.** No network connection required. All Jellyfin API calls are mocked.

```bash
pip install pytest
pytest test_jellyfin_au_ratings.py -v
```

Full test coverage details: [TESTS.md](TESTS.md)

---

## How this was built

Full prompt-by-prompt session log: [PROMPTS.md](PROMPTS.md)
