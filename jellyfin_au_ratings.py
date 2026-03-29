#!/usr/bin/env python3
"""
Jellyfin Australian Rating Manager
====================================
Interactive tool to browse, convert, and manually manage parental
ratings in your Jellyfin library using Australian (ACB) classifications.

Usage:
    python jellyfin_au_ratings.py
"""

import os
import sys
import re
import stat
import time
import uuid
import configparser
from collections import Counter, defaultdict
from pathlib import Path

import requests

# ═════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════
# CREDENTIAL STORE
# ═════════════════════════════════════════════════════════════

_CONFIG_PATH = Path.home() / ".config" / "jellyfin_au_ratings.cfg"


def _load_credentials():
    """
    Return (host, api_key, username, password) from the config file, or
    ("", "", "", "") if none are saved.
    """
    if not _CONFIG_PATH.exists():
        return "", "", "", ""
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATH)
    sec = cfg["credentials"] if "credentials" in cfg else {}
    return (
        sec.get("host", ""),
        sec.get("api_key", ""),
        sec.get("username", ""),
        sec.get("password", ""),
    )


def _save_credentials(host="", api_key="", username="", password=""):
    """Write host + credentials to the config file with mode 600."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg["credentials"] = {
        "host":     host,
        "api_key":  api_key,
        "username": username,
        "password": password,
    }
    with open(_CONFIG_PATH, "w") as f:
        cfg.write(f)
    # Restrict to owner read/write only
    os.chmod(_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _forget_credentials():
    """Delete the saved config file if it exists."""
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
        return True
    return False


def _has_saved_credentials():
    host, api_key, username, _ = _load_credentials()
    return bool(host or api_key or username)


# ═════════════════════════════════════════════════════════════
# RATING DATA
# ═════════════════════════════════════════════════════════════

AU_RATINGS = ["G", "PG", "M", "MA 15+", "R 18+", "X 18+", "E", "RC", "P", "C", "AV 15+"]
AU_RATINGS_SET = set(AU_RATINGS)

_PROMPT_RATINGS = ["G", "PG", "M", "MA 15+", "R 18+"]

RATING_MAP = {
    # US MPAA
    "G": "G", "PG": "PG", "PG-13": "M", "R": "MA 15+", "NC-17": "R 18+",
    "NR": None, "Unrated": None,
    # US TV
    "TV-Y": "P", "TV-Y7": "C", "TV-Y7-FV": "C", "TV-G": "G",
    "TV-PG": "PG", "TV-14": "M", "TV-MA": "MA 15+",
    # UK BBFC
    "U": "G", "12": "M", "12A": "M", "15": "MA 15+", "18": "R 18+", "R18": "R 18+",
    # UK with prefix
    "GB-U": "G", "GB-PG": "PG", "GB-12": "M", "GB-12A": "M",
    "GB-15": "MA 15+", "GB-18": "R 18+",
    # German FSK
    "FSK-0": "G", "FSK-6": "PG", "FSK-12": "M", "FSK-16": "MA 15+", "FSK-18": "R 18+",
    "de/0": "G", "de/6": "PG", "de/12": "M", "de/16": "MA 15+", "de/18": "R 18+",
    # French
    "FR-U": "G", "FR-10": "PG", "FR-12": "M", "FR-16": "MA 15+", "FR-18": "R 18+",
    # Canadian
    "14A": "M", "14+": "M", "18A": "MA 15+", "A": "R 18+",
    # Dutch
    "AL": "G", "nl/6": "PG", "nl/9": "PG", "nl/12": "M", "nl/16": "MA 15+",
    # Brazilian
    "L": "G", "10": "PG", "14": "M", "16": "MA 15+",
    # AU canonical (pass-through)
    "E": "E", "M": "M", "MA 15+": "MA 15+", "R 18+": "R 18+",
    "X 18+": "X 18+", "RC": "RC", "P": "P", "C": "C", "AV 15+": "AV 15+",
    # AU spacing variants
    "MA15+": "MA 15+", "R18+": "R 18+", "X18+": "X 18+", "AV15+": "AV 15+",
    # AU prefixed
    "AU-G": "G", "AU-PG": "PG", "AU-M": "M",
    "AU-MA 15+": "MA 15+", "AU-MA15+": "MA 15+",
    "AU-R 18+": "R 18+", "AU-R18+": "R 18+",
    "AU-X 18+": "X 18+", "AU-X18+": "X 18+",
    "AU-E": "E", "AU-RC": "RC", "AU-P": "P", "AU-C": "C",
    "AU-AV 15+": "AV 15+", "AU-AV15+": "AV 15+",
    # Misc
    "Approved": None, "Not Rated": None,
}

AGE_TO_AU = [
    (0, "G"), (7, "PG"), (12, "M"), (14, "M"),
    (15, "MA 15+"), (17, "MA 15+"), (99, "R 18+"),
]

# ═════════════════════════════════════════════════════════════
# ANSI COLOURS
# ═════════════════════════════════════════════════════════════

class C:
    RESET  = "\033[0m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    RED    = "\033[31m"
    CYAN   = "\033[36m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"

def green(s):  return f"{C.GREEN}{s}{C.RESET}"
def orange(s): return f"{C.YELLOW}{s}{C.RESET}"
def red(s):    return f"{C.RED}{s}{C.RESET}"
def cyan(s):   return f"{C.CYAN}{s}{C.RESET}"
def dim(s):    return f"{C.DIM}{s}{C.RESET}"
def bold(s):   return f"{C.BOLD}{s}{C.RESET}"

def ok(n):
    """Green if non-zero successes, dim zero."""
    return green(str(n)) if n else dim("0")

def err_colour(n):
    """Red if non-zero errors, green zero."""
    return red(str(n)) if n else green("0")


# ═════════════════════════════════════════════════════════════
# RATING LOGIC
# ═════════════════════════════════════════════════════════════

def _extract_age(s):
    m = re.match(r'^[−\-]?\s*(\d{1,2})\s*\+?$', s)
    return int(m.group(1)) if m else None


def _age_to_au(age):
    for max_age, r in AGE_TO_AU:
        if age <= max_age:
            return r
    return "R 18+"


def _normalise_au(s):
    s = s.strip()
    if s.upper().startswith("AU-"):
        s = s[3:]
    elif s.upper().startswith("AU "):
        s = s[3:]
    for pattern, canonical in [
        (r'^MA\s*15\+$', "MA 15+"), (r'^R\s*18\+$', "R 18+"),
        (r'^X\s*18\+$', "X 18+"), (r'^AV\s*15\+$', "AV 15+"),
    ]:
        if re.match(pattern, s, re.IGNORECASE):
            return canonical
    simple = {"G": "G", "PG": "PG", "M": "M", "E": "E", "RC": "RC", "P": "P", "C": "C"}
    if s.upper() in simple:
        return simple[s.upper()]
    return None


def map_rating(current_rating):
    """
    Returns (new_rating, status).
    status: 'mapped', 'already_au', 'normalised', 'unmapped', 'skip', 'empty'
    """
    if not current_rating or not current_rating.strip():
        return None, "empty"
    rating = current_rating.strip()

    if rating in AU_RATINGS_SET:
        return rating, "already_au"

    if rating in RATING_MAP:
        mapped = RATING_MAP[rating]
        if mapped is None:
            return None, "skip"
        return (mapped, "already_au") if mapped == rating else (mapped, "mapped")

    for key, val in RATING_MAP.items():
        if key.lower() == rating.lower():
            if val is None:
                return None, "skip"
            return val, "mapped"

    normalised = _normalise_au(rating)
    if normalised:
        return (normalised, "already_au") if normalised == rating else (normalised, "normalised")

    prefix_match = re.match(r'^[A-Za-z]{2}[/\-](.+)$', rating)
    if prefix_match:
        stripped = prefix_match.group(1).strip()
        if stripped in RATING_MAP and RATING_MAP[stripped] is not None:
            return RATING_MAP[stripped], "mapped"
        for key, val in RATING_MAP.items():
            if key.lower() == stripped.lower() and val is not None:
                return val, "mapped"
        n = _normalise_au(stripped)
        if n:
            return n, "normalised"
        age = _extract_age(stripped)
        if age is not None:
            return _age_to_au(age), "mapped"

    age = _extract_age(rating)
    if age is not None:
        return _age_to_au(age), "mapped"

    return None, "unmapped"


# ═════════════════════════════════════════════════════════════
# JELLYFIN CLIENT
# ═════════════════════════════════════════════════════════════

DEVICE_ID = str(uuid.uuid4())


class JellyfinClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.user_id = None

    def _auth_header(self, token=""):
        parts = [
            'Client="JellyfinAURatings"', 'Device="PythonScript"',
            f'DeviceId="{DEVICE_ID}"', 'Version="2.0.0"',
        ]
        if token:
            parts.append(f'Token="{token}"')
        return "MediaBrowser " + ", ".join(parts)

    def authenticate_with_api_key(self, api_key):
        self.session.headers.update({
            "Authorization": self._auth_header(api_key),
            "Content-Type": "application/json",
        })
        resp = self.session.get(f"{self.base_url}/Users")
        resp.raise_for_status()
        users = resp.json()
        admin = next((u for u in users if u.get("Policy", {}).get("IsAdministrator")), None)
        chosen = admin or users[0]
        self.user_id = chosen["Id"]
        return chosen

    def authenticate_with_password(self, username, password):
        self.session.headers.update({
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        })
        resp = self.session.post(
            f"{self.base_url}/Users/AuthenticateByName",
            json={"Username": username, "Pw": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self.user_id = data["User"]["Id"]
        self.session.headers["Authorization"] = self._auth_header(data["AccessToken"])
        return data["User"]

    def get_all_items(self, item_types="Movie,Series,Episode,Season"):
        all_items = []
        start = 0
        while True:
            resp = self.session.get(
                f"{self.base_url}/Users/{self.user_id}/Items",
                params={
                    "Recursive": "true", "StartIndex": start, "Limit": 200,
                    "Fields": "OfficialRating,Name,Id,Type,Path,SeriesName,SeasonName,SeriesId,ParentId",
                    "IncludeItemTypes": item_types,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            all_items.extend(data.get("Items", []))
            total = data.get("TotalRecordCount", 0)
            start += 200
            if start >= total:
                break
            print(f"\r  Fetched {len(all_items)}/{total}...", end="", flush=True)
        if total > 200:
            print()
        return all_items

    def get_item_full(self, item_id):
        resp = self.session.get(f"{self.base_url}/Users/{self.user_id}/Items/{item_id}")
        resp.raise_for_status()
        return resp.json()

    def update_item(self, item_id, item_data):
        resp = self.session.post(f"{self.base_url}/Items/{item_id}", json=item_data)
        resp.raise_for_status()


# ═════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═════════════════════════════════════════════════════════════

# Set during login — shown in every header. (#12)
_logged_in_as = ""
_server_host = ""


def clear():
    os.system("cls" if os.name == "nt" else "clear")


_FRAME_W = 60

def header(title):
    """Framed header — title and logged-in user on one line."""
    clear()
    print("═" * _FRAME_W)
    if _logged_in_as:
        user_str = f"{_logged_in_as} @ {_server_host}"
        # Padding based on raw (non-ANSI) lengths; clamp to at least 1 space
        pad = max(1, _FRAME_W - 2 - len(title) - len(user_str))
        print(f"  {bold(title)}{' ' * pad}{dim(user_str)}")
    else:
        print(f"  {bold(title)}")
    print("═" * _FRAME_W)
    print()


def pause():
    input("\n  Press Enter to continue...")


def pick(prompt, options, allow_back=True):
    """Show numbered menu. Returns 0-based index or -1 for back."""
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    if allow_back:
        print(f"  0) ← Back")
    print()
    while True:
        try:
            choice = input(f"  {prompt}: ").strip()
            if choice == "0" and allow_back:
                return -1
            n = int(choice)
            if 1 <= n <= len(options):
                return n - 1
        except (ValueError, EOFError):
            pass
        print("  Invalid choice, try again.")


def item_display_name(item):
    """Build a readable name like 'Breaking Bad > S01 > Pilot'."""
    parts = []
    if item.get("SeriesName"):
        parts.append(item["SeriesName"])
    if item.get("SeasonName"):
        parts.append(item["SeasonName"])
    parts.append(item.get("Name", "Unknown"))
    return " > ".join(parts)


def _rating_tag(rating):
    """Coloured status annotation for a raw rating string used in Breakdown."""
    mapped, status = map_rating(rating if rating != "(No Rating)" else "")
    if status == "already_au":
        return green("  ✓ AU")
    elif status in ("mapped", "normalised"):
        return cyan(f"  → {mapped}")
    elif status == "empty":
        return ""
    elif status == "skip":
        return dim("  (skip)")
    else:
        return red("  ⚠ unmapped")


def _print_done(success, errors, error_samples):
    """Shared summary line for bulk operations with coloured counts."""
    print(f"\n  Done: {ok(success)} updated, {err_colour(errors)} errors.")
    if error_samples:
        print("\n  Error details (first 3):")
        for name, e in error_samples:
            print(f"    • {name[:50]}")
            print(f"      {e[:150]}")


# ═════════════════════════════════════════════════════════════
# MENU FUNCTIONS
# ═════════════════════════════════════════════════════════════

def menu_rating_breakdown(items_by_type):
    """Show rating counts broken down by type, then drill into a rating group."""
    while True:
        header("Rating Breakdown")
        type_options = [t for t in ["Movie", "Series", "Season", "Episode"] if t in items_by_type]
        type_options.append("All Types Combined")

        idx = pick("Select type", type_options)
        if idx == -1:
            return

        if type_options[idx] == "All Types Combined":
            pool = []
            for v in items_by_type.values():
                pool.extend(v)
            chosen_type = "All"
        else:
            chosen_type = type_options[idx]
            pool = items_by_type[chosen_type]

        # Fix #1: stay on the ratings list for this type; only 0 goes back to
        # the type selector, not back there automatically after viewing items.
        while True:
            rating_counts = Counter()
            for item in pool:
                r = item.get("OfficialRating", "") or "(No Rating)"
                rating_counts[r] += 1

            header(f"Rating Breakdown — {chosen_type} ({len(pool)} items)")
            sorted_ratings = sorted(rating_counts.items(), key=lambda x: -x[1])
            for i, (rating, count) in enumerate(sorted_ratings, 1):
                tag = _rating_tag(rating)
                print(f"  {i:>3}) {rating:<20} {count:>5} item(s){tag}")

            print()
            print(dim("  Enter a number to view items with that rating, or 0 to go back."))
            print()

            choice = input("  Choice: ").strip()
            if choice == "0":
                break  # back to type selection
            try:
                n = int(choice)
                if 1 <= n <= len(sorted_ratings):
                    chosen_rating = sorted_ratings[n - 1][0]
                    matching = [
                        item for item in pool
                        if (item.get("OfficialRating", "") or "(No Rating)") == chosen_rating
                    ]
                    menu_view_items(matching, chosen_rating, chosen_type)
                    # Loop back to ratings list, not type selector
                else:
                    print("  Invalid choice.")
            except ValueError:
                print("  Invalid choice.")


def menu_view_items(items, rating_label, type_label):
    """View items with a specific rating. Allow changing individual or all."""
    page = 0
    page_size = 20

    while True:
        header(f"{type_label} rated \"{rating_label}\" — {len(items)} item(s)")

        start = page * page_size
        end = min(start + page_size, len(items))
        total_pages = max(1, (len(items) + page_size - 1) // page_size)

        # Fix #10: show current rating alongside each item name
        for i, item in enumerate(items[start:end], start + 1):
            name = item_display_name(item)
            rating = item.get("OfficialRating") or "(none)"
            print(f"  {i:>4}) [{rating:<8}] {name[:50]}")

        print()
        print(f"  Page {page + 1}/{total_pages}")
        # Fix #11: single compact hint line
        print(dim("  [# change]  [all]  [n/p page]  [0 back]"))
        print()

        cmd = input("  Command: ").strip().lower()

        if cmd == "0":
            return
        elif cmd == "n":
            # Fix #4: explicit boundary message
            if end < len(items):
                page += 1
            else:
                print(dim("  Already on last page."))
        elif cmd == "p":
            if page > 0:
                page -= 1
            else:
                print(dim("  Already on first page."))
        elif cmd == "all":
            new_rating = prompt_au_rating()
            if new_rating:
                confirm = input(
                    f"\n  Change ALL {len(items)} items from \"{rating_label}\" → \"{new_rating}\"? (yes/no): "
                ).strip().lower()
                if confirm in ("yes", "y"):
                    bulk_update_rating(items, new_rating)
                    return  # ratings changed, go back
        else:
            try:
                n = int(cmd)
                if 1 <= n <= len(items):
                    menu_change_single(items[n - 1])
                else:
                    print("  Number out of range.")
            except ValueError:
                print("  Invalid command.")


def menu_change_single(item):
    """Change rating for a single item."""
    name = item_display_name(item)
    current = item.get("OfficialRating", "(none)")
    print(f"\n  Item:    {name}")
    print(f"  Current: {current}")
    new_rating = prompt_au_rating()
    if new_rating:
        confirm = input(f"  Set \"{name[:40]}\" to \"{new_rating}\"? (yes/no): ").strip().lower()
        if confirm in ("yes", "y"):
            update_single_rating(item, new_rating)


def menu_auto_convert(items_by_type):
    """Auto-convert all non-AU ratings using the mapping table."""
    header("Auto-Convert All Ratings to Australian")

    all_items = []
    for v in items_by_type.values():
        all_items.extend(v)

    to_update = []
    already_au = 0
    unmapped_items = []
    empty = 0
    skipped = 0

    for item in all_items:
        current = item.get("OfficialRating", "")
        mapped, status = map_rating(current)
        if status in ("mapped", "normalised"):
            to_update.append((item, mapped))
        elif status == "already_au":
            already_au += 1
        elif status == "unmapped":
            unmapped_items.append(item)
        elif status == "empty":
            empty += 1
        elif status == "skip":
            skipped += 1

    print(f"  Will convert:         {len(to_update)}")
    print(f"  Already Australian:   {already_au}")
    print(f"  No rating:            {empty}")
    print(f"  Skipped (NR/Unrated): {skipped}")
    print(f"  Unmapped:             {len(unmapped_items)}")
    print()

    if unmapped_items:
        unmapped_ratings = Counter(i.get("OfficialRating", "?") for i in unmapped_items)
        print(orange("  ⚠  Unmapped ratings (won't be changed):"))
        for r, c in unmapped_ratings.most_common():
            print(f"     • \"{r}\" — {c} item(s)")
        print()

    if to_update:
        conversion_counts = Counter(
            f"{item.get('OfficialRating', '?')} → {mapped}" for item, mapped in to_update
        )
        print("  Conversion preview:")
        for conv, count in conversion_counts.most_common(20):
            print(f"    {conv:<30} {count:>5} item(s)")
        if len(conversion_counts) > 20:
            print(f"    ... and {len(conversion_counts) - 20} more conversions")
        print()

        confirm = input(f"  Proceed with {len(to_update)} updates? (yes/no): ").strip().lower()
        if confirm in ("yes", "y"):
            bulk_update_list(to_update)
        else:
            print("  Aborted.")
    else:
        print("  Nothing to convert!")

    pause()


def menu_search(all_items):
    """Search for items by name and change their rating. Loops until user exits."""
    # Fix #3: loop so user can search again without going back to main menu
    while True:
        header("Search Items")
        query = input("  Search for (or Enter to go back): ").strip().lower()
        if not query:
            return

        results = [
            item for item in all_items
            if query in item_display_name(item).lower()
        ]

        if not results:
            print(f"\n  {orange('No items found matching')} \"{query}\".")
            pause()
            continue  # loop back to search prompt

        print(f"\n  Found {len(results)} item(s):\n")
        for i, item in enumerate(results[:50], 1):
            name = item_display_name(item)
            rating = item.get("OfficialRating", "(none)")
            print(f"  {i:>3}) [{rating:<10}] {name[:50]}")

        if len(results) > 50:
            print(f"\n  {dim('... showing first 50 of ' + str(len(results)))}")

        print()
        print(dim("  Enter # to change that item's rating, or 0 to search again."))
        cmd = input("  Choice: ").strip()
        if cmd == "0":
            continue  # search again
        try:
            n = int(cmd)
            if 1 <= n <= min(len(results), 50):
                menu_change_single(results[n - 1])
        except ValueError:
            pass
        # After acting (or invalid input), loop back to search prompt


def menu_inherit_series(all_items, items_by_type):
    """Apply each series' rating to all its episodes (and seasons)."""
    PAGE_SIZE = 25

    # Fix #2: outer loop so fixing one series brings you back to the list
    while True:
        header("Inherit Ratings from Series → Episodes")

        series_list = items_by_type.get("Series", [])
        if not series_list:
            print("  No series found in library.")
            pause()
            return

        series_by_id = {s["Id"]: s for s in series_list}

        children_by_series = defaultdict(list)
        for item in all_items:
            if item.get("Type") in ("Episode", "Season"):
                sid = item.get("SeriesId") or item.get("ParentId")
                if sid and sid in series_by_id:
                    children_by_series[sid].append(item)

        series_with_rating = []
        series_without_rating = []
        for s in series_list:
            rating = s.get("OfficialRating", "")
            children = children_by_series.get(s["Id"], [])
            if rating and rating.strip():
                mismatched = [
                    c for c in children
                    if (c.get("OfficialRating", "") or "") != rating
                ]
                series_with_rating.append((s, children, mismatched))
            else:
                series_without_rating.append((s, children))

        total_mismatched = sum(len(m) for _, _, m in series_with_rating)
        show_list = sorted(
            [(s, ch, mm) for s, ch, mm in series_with_rating if mm],
            key=lambda x: -len(x[2])
        )

        print(f"  Series with a rating:       {len(series_with_rating)}")
        print(f"  Series without a rating:    {len(series_without_rating)}")
        mismatch_str = orange(str(total_mismatched)) if total_mismatched else green("0")
        print(f"  Episodes/Seasons to update: {mismatch_str}")
        print()

        if total_mismatched == 0:
            print(f"  {green('All episodes already match their series rating!')}")
            pause()
            return

        # Fix #6: paginate — no longer capped at 30 with silent truncation
        page = 0
        total_pages = max(1, (len(show_list) + PAGE_SIZE - 1) // PAGE_SIZE)

        while True:
            header("Inherit Ratings from Series → Episodes")
            start = page * PAGE_SIZE
            end = min(start + PAGE_SIZE, len(show_list))

            print(f"  {orange(str(total_mismatched))} items need updating   "
                  f"{dim(f'Page {page+1}/{total_pages}')}\n")
            print(f"  {'#':>3}  {'Series':<37} {'Rating':<10} {'Fix':>4}  Children")
            print(f"  {'─'*3}  {'─'*37} {'─'*10} {'─'*4}  {'─'*20}")

            for i, (s, children, mismatched) in enumerate(show_list[start:end], start + 1):
                s_rating = s.get("OfficialRating", "?")
                child_ratings = Counter(
                    c.get("OfficialRating", "") or "(none)" for c in mismatched
                )
                child_str = ", ".join(f"{r}×{n}" for r, n in child_ratings.most_common(3))
                print(
                    f"  {i:>3}) {s['Name'][:35]:<37} "
                    f"[{s_rating:<8}] {len(mismatched):>4}  ({child_str})"
                )

            print()
            print(dim("  [# fix one series]  [all fix all]  [n/p page]  [0 back]"))
            print()

            cmd = input("  Choice: ").strip().lower()

            if cmd == "0":
                return
            elif cmd == "n":
                if end < len(show_list):
                    page += 1
                else:
                    print(dim("  Already on last page."))
            elif cmd == "p":
                if page > 0:
                    page -= 1
                else:
                    print(dim("  Already on first page."))
            elif cmd == "all":
                confirm = input(
                    f"\n  Apply series ratings to {total_mismatched} episodes/seasons? (yes/no): "
                ).strip().lower()
                if confirm not in ("yes", "y"):
                    print("  Aborted.")
                    continue

                print(f"\n  Updating {total_mismatched} items...")
                success = 0
                errors = 0
                error_samples = []
                count = 0
                for s, children, mismatched in show_list:
                    s_rating = s["OfficialRating"]
                    for item in mismatched:
                        count += 1
                        result = _do_update(item, s_rating)
                        if result is True:
                            success += 1
                        else:
                            errors += 1
                            if len(error_samples) < 3:
                                error_samples.append((item_display_name(item), result))
                        if count % 25 == 0 or count == total_mismatched:
                            print(f"    Progress: {count}/{total_mismatched} "
                                  f"({ok(success)} ok, {err_colour(errors)} errors)")
                        time.sleep(0.05)

                _print_done(success, errors, error_samples)
                pause()
                break  # re-analyse after bulk update

            else:
                try:
                    n = int(cmd)
                    # Fix #6: full range, not capped at 30
                    if 1 <= n <= len(show_list):
                        s, children, mismatched = show_list[n - 1]
                        s_rating = s["OfficialRating"]
                        print(f"\n  Series:     {s['Name']}")
                        print(f"  Rating:     {s_rating}")
                        print(f"  Mismatched: {len(mismatched)} episodes/seasons\n")

                        for j, c in enumerate(mismatched[:20], 1):
                            c_name = item_display_name(c)
                            c_rating = c.get("OfficialRating", "(none)")
                            print(f"    {j:>3}) [{c_rating:<10}] {c_name[:50]}")
                        if len(mismatched) > 20:
                            print(f"         {dim('... and ' + str(len(mismatched) - 20) + ' more')}")

                        confirm = input(
                            f"\n  Set all {len(mismatched)} to \"{s_rating}\"? (yes/no): "
                        ).strip().lower()
                        if confirm in ("yes", "y"):
                            bulk_update_rating(mismatched, s_rating)
                        # Fix #2: loop — stays on series list, not ejected to main menu
                    else:
                        print("  Number out of range.")
                except ValueError:
                    print("  Invalid choice.")


# ═════════════════════════════════════════════════════════════
# UPDATE FUNCTIONS
# ═════════════════════════════════════════════════════════════

client = None  # set during init


def prompt_au_rating():
    """Prompt user to pick an AU rating. Returns the rating string or None."""
    print("\n  Australian ratings:")
    for i, r in enumerate(_PROMPT_RATINGS, 1):
        print(f"    {i:>2}) {r}")
    print(f"     0) Cancel")
    print()
    while True:
        choice = input("  Pick rating: ").strip()
        if choice == "0":
            return None
        try:
            n = int(choice)
            if 1 <= n <= len(_PROMPT_RATINGS):
                return _PROMPT_RATINGS[n - 1]
        except ValueError:
            # Allow typing any valid AU rating directly
            if choice in AU_RATINGS_SET:
                return choice
        print("  Invalid choice.")


def _clean_payload(full):
    """
    Clean a full item payload to avoid Jellyfin UpdateItem crashes.
    The API throws NullReferenceException when list fields are null.
    """
    for field in [
        "Genres", "Tags", "Studios", "People", "LockedFields",
        "GenreItems", "TagItems", "RemoteTrailers",
        "ProductionLocations", "ArtistItems", "AlbumArtists",
    ]:
        if field in full and full[field] is None:
            full[field] = []
    if full.get("ProviderIds") is None:
        full["ProviderIds"] = {}
    return full


def _do_update(item, new_rating):
    """
    Try to update one item's OfficialRating.
    Returns True on success or an error string on failure.
    Tries full payload first, then minimal payload as fallback.
    """
    item_id = item["Id"]

    # Strategy 1: full payload with null-cleaning
    try:
        full = client.get_item_full(item_id)
        full = _clean_payload(full)
        full["OfficialRating"] = new_rating
        client.update_item(item_id, full)
        item["OfficialRating"] = new_rating
        return True
    except requests.exceptions.HTTPError as e:
        sc = e.response.status_code if e.response else "?"
        body = ""
        try:
            body = e.response.text[:200] if e.response else ""
        except Exception:
            pass
        err1 = f"[{sc}] {body}"
    except Exception as e:
        err1 = str(e)[:150]

    # Strategy 2: minimal payload
    try:
        full = client.get_item_full(item_id)
        minimal = {
            "Id": item_id,
            "Name": full.get("Name", ""),
            "OfficialRating": new_rating,
            "Genres": full.get("Genres") or [],
            "Tags": full.get("Tags") or [],
            "Studios": full.get("Studios") or [],
            "People": full.get("People") or [],
            "ProviderIds": full.get("ProviderIds") or {},
            "LockedFields": full.get("LockedFields") or [],
            "LockData": full.get("LockData", False),
        }
        client.update_item(item_id, minimal)
        item["OfficialRating"] = new_rating
        return True
    except requests.exceptions.HTTPError as e2:
        sc2 = e2.response.status_code if e2.response else "?"
        body2 = ""
        try:
            body2 = e2.response.text[:200] if e2.response else ""
        except Exception:
            pass
        return f"Full: {err1} | Minimal: [{sc2}] {body2}"
    except Exception as e2:
        return f"Full: {err1} | Minimal: {e2}"


def update_single_rating(item, new_rating):
    """Update a single item's OfficialRating via the API."""
    result = _do_update(item, new_rating)
    # Fix #8: coloured tick/cross
    if result is True:
        print(f"  {green('✓')} Updated to \"{new_rating}\"")
    else:
        print(f"  {red('✗')} Failed: {result}")


def bulk_update_rating(items, new_rating):
    """Update all items in a list to the same new rating."""
    print(f"\n  Updating {len(items)} items to \"{new_rating}\"...")
    success = 0
    errors = 0
    error_samples = []
    for i, item in enumerate(items, 1):
        result = _do_update(item, new_rating)
        if result is True:
            success += 1
        else:
            errors += 1
            if len(error_samples) < 3:
                error_samples.append((item_display_name(item), result))
        if i % 25 == 0 or i == len(items):
            # Fix #9: coloured progress counts
            print(f"    Progress: {i}/{len(items)} ({ok(success)} ok, {err_colour(errors)} errors)")
        time.sleep(0.05)

    _print_done(success, errors, error_samples)
    pause()


def bulk_update_list(update_pairs):
    """Update a list of (item, new_rating) pairs."""
    print(f"\n  Updating {len(update_pairs)} items...")
    success = 0
    errors = 0
    error_samples = []
    for i, (item, new_rating) in enumerate(update_pairs, 1):
        result = _do_update(item, new_rating)
        if result is True:
            success += 1
        else:
            errors += 1
            if len(error_samples) < 3:
                error_samples.append((item_display_name(item), result))
        if i % 25 == 0 or i == len(update_pairs):
            print(f"    Progress: {i}/{len(update_pairs)} ({ok(success)} ok, {err_colour(errors)} errors)")
        time.sleep(0.05)

    _print_done(success, errors, error_samples)


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

def main():
    global client, _logged_in_as, _server_host

    header("Jellyfin Australian Rating Manager")

    # ── Host ──
    # Priority: env var → saved config → interactive prompt
    jellyfin_url = os.environ.get("JELLYFIN_URL", "")

    # ── Auth ──
    # Priority: env vars → saved config → interactive prompt
    api_key = os.environ.get("JELLYFIN_API_KEY", "")
    username = os.environ.get("JELLYFIN_USERNAME", "")
    password = os.environ.get("JELLYFIN_PASSWORD", "")

    # Retry loop — allows re-entry on bad host or credentials
    _used_saved = False
    while True:
        if not jellyfin_url and not api_key and not username:
            saved_host, saved_key, saved_user, saved_pass = _load_credentials()
            if saved_host or saved_key or saved_user:
                who = saved_key[:6] + "\u2026" if saved_key else saved_user
                label = f"{who} @ {saved_host}" if saved_host else who
                use_saved = input(
                    f"  Saved config found ({label}). Use it? (yes/no): "
                ).strip().lower()
                if use_saved in ("yes", "y", ""):
                    jellyfin_url = saved_host
                    api_key, username, password = saved_key, saved_user, saved_pass
                    _used_saved = True

        if not jellyfin_url:
            jellyfin_url = input(
                f"  Jellyfin URL (e.g. https://jellyfin.example.com): "
            ).strip().rstrip("/")

        if not api_key and not username:
            print("  1) API Key")
            print("  2) Username & Password")
            choice = input("\n  Auth method: ").strip()
            if choice == "2":
                username = input("  Username: ").strip()
                password = input("  Password: ").strip()
            else:
                api_key = input("  API Key: ").strip()

        _server_host = jellyfin_url.replace("https://", "").replace("http://", "")
        client = JellyfinClient(jellyfin_url)
        print(f"\n  Server: {jellyfin_url}")
        print("  Authenticating...")
        try:
            if api_key:
                user = client.authenticate_with_api_key(api_key)
            else:
                user = client.authenticate_with_password(username, password)
            _logged_in_as = user["Name"]  # stored for all subsequent headers
            print(f"  {green('✓')} Logged in as: {user['Name']}\n")
            break  # success — exit the retry loop
        except Exception as e:
            print(f"  {red('✗')} Auth failed: {e}")
            if _used_saved:
                print(f"  {dim('Saved config may be stale.')}")
                _used_saved = False
            # Reset so the next iteration prompts fresh input
            jellyfin_url = api_key = username = password = ""
            retry = input("\n  Try again? (yes/no): ").strip().lower()
            if retry not in ("yes", "y"):
                sys.exit(1)
            print()

    # Offer to save if entered interactively
    if not _used_saved and jellyfin_url:
        save = input(
            f"  Save host + credentials for next time? (yes/no): "
        ).strip().lower()
        if save in ("yes", "y"):
            _save_credentials(
                host=jellyfin_url, api_key=api_key,
                username=username, password=password,
            )
            print(f"  {green('✓')} Saved to {_CONFIG_PATH}  {dim('(chmod 600)')}")
    print()

    # ── Load library ──
    print("  Loading library...")
    all_items = client.get_all_items()
    print(f"  {green('✓')} Loaded {len(all_items)} items.\n")

    items_by_type = defaultdict(list)
    for item in all_items:
        items_by_type[item.get("Type", "Unknown")].append(item)

    for t in ["Movie", "Series", "Season", "Episode"]:
        if t in items_by_type:
            print(f"    {t + 's':<12} {len(items_by_type[t]):>5}")
    print()
    pause()

    # ── Main menu loop ──
    while True:
        header("Main Menu")

        au_count = sum(1 for i in all_items if i.get("OfficialRating", "") in AU_RATINGS_SET)
        non_au = len(all_items) - au_count
        non_au_str = green(str(non_au)) if non_au == 0 else orange(str(non_au))
        print(f"  Library: {len(all_items)} items  |  AU: {au_count}  |  Non-AU/Empty: {non_au_str}\n")

        has_creds = _has_saved_credentials()
        cred_label = (
            f"Forget Saved Credentials  ({dim(_CONFIG_PATH.name)})"
            if has_creds
            else dim("Forget Saved Credentials  (none saved)")
        )
        options = [
            "Rating Breakdown  (browse by Movies / Series / Episodes)",
            "Auto-Convert All  (apply mapping table to entire library)",
            "Inherit Series    (apply series rating to all its episodes)",
            "Search Items      (find by name and change rating)",
            "Reload Library    (re-fetch from Jellyfin)",
            cred_label,
            "Exit",
        ]
        idx = pick("Select", options, allow_back=False)

        if idx == 0:
            menu_rating_breakdown(items_by_type)
        elif idx == 1:
            menu_auto_convert(items_by_type)
            items_by_type = defaultdict(list)
            for item in all_items:
                items_by_type[item.get("Type", "Unknown")].append(item)
        elif idx == 2:
            menu_inherit_series(all_items, items_by_type)
            items_by_type = defaultdict(list)
            for item in all_items:
                items_by_type[item.get("Type", "Unknown")].append(item)
        elif idx == 3:
            menu_search(all_items)
        elif idx == 4:
            header("Reloading...")
            all_items = client.get_all_items()
            items_by_type = defaultdict(list)
            for item in all_items:
                items_by_type[item.get("Type", "Unknown")].append(item)
            print(f"  {green('✓')} Reloaded {len(all_items)} items.")
            pause()
        elif idx == 5:
            if has_creds:
                confirm = input("\n  Delete saved credentials? (yes/no): ").strip().lower()
                if confirm in ("yes", "y"):
                    _forget_credentials()
                    print(f"  {green('✓')} Credentials removed.")
                    pause()
            else:
                print(f"  {dim('No saved credentials to remove.')}")
                pause()
        elif idx == 6:
            # Confirm before exiting
            confirm = input("\n  Really exit? (yes/no): ").strip().lower()
            if confirm in ("yes", "y"):
                print("\n  Bye!")
                sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted \u2014 bye!")
        sys.exit(0)

