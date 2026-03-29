"""
Test suite for jellyfin_au_ratings.py
======================================
Covers all pure functions and mocked I/O paths.
Run with:  pytest test_jellyfin_au_ratings.py -v
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ── Stub out `requests` before importing the module so tests don't need
#    a real network and the module-level `import requests` succeeds.
requests_stub = types.ModuleType("requests")
requests_stub.Session = MagicMock
class _FakeHTTPError(Exception):
    """Module-level HTTPError stub with .response for _do_update compatibility."""
    def __init__(self, msg="error", status=500):
        super().__init__(msg)
        self.response = type("R", (), {"status_code": status, "text": str(msg)})()

requests_stub.exceptions = types.SimpleNamespace(HTTPError=_FakeHTTPError)
sys.modules.setdefault("requests", requests_stub)

import importlib
import os
sys.path.insert(0, os.path.dirname(__file__))
import jellyfin_au_ratings as jfr


# ══════════════════════════════════════════════════════════════════════
# _extract_age
# ══════════════════════════════════════════════════════════════════════

class TestExtractAge(unittest.TestCase):

    # ── Happy path ────────────────────────────────────────────────────

    def test_plain_integer(self):
        self.assertEqual(jfr._extract_age("12"), 12)

    def test_with_plus_suffix(self):
        self.assertEqual(jfr._extract_age("15+"), 15)

    def test_single_digit(self):
        self.assertEqual(jfr._extract_age("6"), 6)

    def test_zero(self):
        self.assertEqual(jfr._extract_age("0"), 0)

    def test_padded_whitespace(self):
        self.assertEqual(jfr._extract_age(" 18 "), 18)

    def test_ascii_minus_prefix(self):
        """Some sources emit "-16" as a rating."""
        self.assertEqual(jfr._extract_age("-16"), 16)

    def test_unicode_minus_prefix(self):
        """Unicode minus sign (−) also appears in the wild."""
        self.assertEqual(jfr._extract_age("−18"), 18)

    def test_two_digit_boundary(self):
        self.assertEqual(jfr._extract_age("99"), 99)

    # ── Edge / reject cases ───────────────────────────────────────────

    def test_three_digit_number_rejected(self):
        """Only 1–2 digit numbers are valid age ratings."""
        self.assertIsNone(jfr._extract_age("100"))

    def test_alpha_string_rejected(self):
        self.assertIsNone(jfr._extract_age("PG"))

    def test_empty_string_rejected(self):
        self.assertIsNone(jfr._extract_age(""))

    def test_mixed_alphanumeric_rejected(self):
        self.assertIsNone(jfr._extract_age("12A"))

    def test_rating_with_embedded_plus_rejected(self):
        """'MA 15+' has non-numeric prefix, should not match."""
        self.assertIsNone(jfr._extract_age("MA 15+"))


# ══════════════════════════════════════════════════════════════════════
# _age_to_au
# ══════════════════════════════════════════════════════════════════════

class TestAgeToAu(unittest.TestCase):
    """
    AGE_TO_AU buckets: ≤0 G, ≤7 PG, ≤12 M, ≤14 M, ≤15 MA15+, ≤17 MA15+, ≤99 R18+
    Ages above 99 fall through to the hardcoded "R 18+" return.
    """

    def test_age_0_is_G(self):
        self.assertEqual(jfr._age_to_au(0), "G")

    def test_age_1_is_PG(self):
        """Age 1 is above 0 so falls into the PG (≤7) bucket."""
        self.assertEqual(jfr._age_to_au(1), "PG")

    def test_age_7_is_PG(self):
        self.assertEqual(jfr._age_to_au(7), "PG")

    def test_age_8_is_M(self):
        self.assertEqual(jfr._age_to_au(8), "M")

    def test_age_12_is_M(self):
        self.assertEqual(jfr._age_to_au(12), "M")

    def test_age_13_is_M(self):
        """13 falls into the ≤14 M bucket."""
        self.assertEqual(jfr._age_to_au(13), "M")

    def test_age_14_is_M(self):
        self.assertEqual(jfr._age_to_au(14), "M")

    def test_age_15_is_MA15(self):
        self.assertEqual(jfr._age_to_au(15), "MA 15+")

    def test_age_17_is_MA15(self):
        self.assertEqual(jfr._age_to_au(17), "MA 15+")

    def test_age_18_is_R18(self):
        self.assertEqual(jfr._age_to_au(18), "R 18+")

    def test_age_99_is_R18(self):
        self.assertEqual(jfr._age_to_au(99), "R 18+")

    def test_age_above_99_fallback(self):
        """Nothing in AGE_TO_AU covers >99; the hardcoded fallback applies."""
        self.assertEqual(jfr._age_to_au(150), "R 18+")


# ══════════════════════════════════════════════════════════════════════
# _normalise_au
# ══════════════════════════════════════════════════════════════════════

class TestNormaliseAu(unittest.TestCase):

    # ── Spacing-variant canonicalisation ──────────────────────────────

    def test_MA15_nospace(self):
        self.assertEqual(jfr._normalise_au("MA15+"), "MA 15+")

    def test_MA_with_extra_space(self):
        """Double space between MA and 15+ should still canonicalise."""
        self.assertEqual(jfr._normalise_au("MA  15+"), "MA 15+")

    def test_R18_nospace(self):
        self.assertEqual(jfr._normalise_au("R18+"), "R 18+")

    def test_X18_nospace(self):
        self.assertEqual(jfr._normalise_au("X18+"), "X 18+")

    def test_AV15_nospace(self):
        self.assertEqual(jfr._normalise_au("AV15+"), "AV 15+")

    def test_case_insensitive_ma(self):
        self.assertEqual(jfr._normalise_au("ma15+"), "MA 15+")

    def test_case_insensitive_r(self):
        self.assertEqual(jfr._normalise_au("r18+"), "R 18+")

    # ── AU- prefix stripping ──────────────────────────────────────────

    def test_AU_prefix_G(self):
        self.assertEqual(jfr._normalise_au("AU-G"), "G")

    def test_AU_prefix_MA15(self):
        self.assertEqual(jfr._normalise_au("AU-MA15+"), "MA 15+")

    def test_AU_space_prefix(self):
        """'AU G' (space separator) should also strip."""
        self.assertEqual(jfr._normalise_au("AU G"), "G")

    def test_AU_prefix_lowercase(self):
        self.assertEqual(jfr._normalise_au("au-pg"), "PG")

    # ── Simple pass-throughs ──────────────────────────────────────────

    def test_G_passthrough(self):
        self.assertEqual(jfr._normalise_au("G"), "G")

    def test_PG_passthrough(self):
        self.assertEqual(jfr._normalise_au("PG"), "PG")

    def test_M_passthrough(self):
        self.assertEqual(jfr._normalise_au("M"), "M")

    def test_lowercase_simple(self):
        self.assertEqual(jfr._normalise_au("g"), "G")

    def test_mixed_case_simple(self):
        self.assertEqual(jfr._normalise_au("Pg"), "PG")

    # ── Strings that should not normalise ─────────────────────────────

    def test_non_au_rating_returns_None(self):
        self.assertIsNone(jfr._normalise_au("PG-13"))

    def test_gibberish_returns_None(self):
        self.assertIsNone(jfr._normalise_au("XYZ"))

    def test_whitespace_only_returns_None(self):
        self.assertIsNone(jfr._normalise_au("   "))


# ══════════════════════════════════════════════════════════════════════
# map_rating  (the main logic function)
# ══════════════════════════════════════════════════════════════════════

class TestMapRating(unittest.TestCase):

    # ── Empty / None input ────────────────────────────────────────────

    def test_none_input(self):
        self.assertEqual(jfr.map_rating(None), (None, "empty"))

    def test_empty_string(self):
        self.assertEqual(jfr.map_rating(""), (None, "empty"))

    def test_whitespace_only(self):
        self.assertEqual(jfr.map_rating("   "), (None, "empty"))

    # ── Already canonical AU ratings ──────────────────────────────────

    def test_G_already_au(self):
        self.assertEqual(jfr.map_rating("G"), ("G", "already_au"))

    def test_PG_already_au(self):
        self.assertEqual(jfr.map_rating("PG"), ("PG", "already_au"))

    def test_M_already_au(self):
        self.assertEqual(jfr.map_rating("M"), ("M", "already_au"))

    def test_MA15_already_au(self):
        self.assertEqual(jfr.map_rating("MA 15+"), ("MA 15+", "already_au"))

    def test_R18_already_au(self):
        self.assertEqual(jfr.map_rating("R 18+"), ("R 18+", "already_au"))

    def test_X18_already_au(self):
        self.assertEqual(jfr.map_rating("X 18+"), ("X 18+", "already_au"))

    def test_E_already_au(self):
        self.assertEqual(jfr.map_rating("E"), ("E", "already_au"))

    def test_RC_already_au(self):
        self.assertEqual(jfr.map_rating("RC"), ("RC", "already_au"))

    # ── US MPAA ratings ───────────────────────────────────────────────

    def test_PG13_maps_to_M(self):
        self.assertEqual(jfr.map_rating("PG-13"), ("M", "mapped"))

    def test_R_maps_to_MA15(self):
        self.assertEqual(jfr.map_rating("R"), ("MA 15+", "mapped"))

    def test_NC17_maps_to_R18(self):
        self.assertEqual(jfr.map_rating("NC-17"), ("R 18+", "mapped"))

    def test_NR_skipped(self):
        self.assertEqual(jfr.map_rating("NR"), (None, "skip"))

    def test_Unrated_skipped(self):
        self.assertEqual(jfr.map_rating("Unrated"), (None, "skip"))

    def test_Not_Rated_skipped(self):
        self.assertEqual(jfr.map_rating("Not Rated"), (None, "skip"))

    def test_Approved_skipped(self):
        self.assertEqual(jfr.map_rating("Approved"), (None, "skip"))

    # ── US TV ratings ─────────────────────────────────────────────────

    def test_TV_Y_maps_to_P(self):
        self.assertEqual(jfr.map_rating("TV-Y"), ("P", "mapped"))

    def test_TV_Y7_maps_to_C(self):
        self.assertEqual(jfr.map_rating("TV-Y7"), ("C", "mapped"))

    def test_TV_Y7FV_maps_to_C(self):
        self.assertEqual(jfr.map_rating("TV-Y7-FV"), ("C", "mapped"))

    def test_TV_G_maps_to_G(self):
        self.assertEqual(jfr.map_rating("TV-G"), ("G", "mapped"))

    def test_TV_PG_maps_to_PG(self):
        self.assertEqual(jfr.map_rating("TV-PG"), ("PG", "mapped"))

    def test_TV_14_maps_to_M(self):
        self.assertEqual(jfr.map_rating("TV-14"), ("M", "mapped"))

    def test_TV_MA_maps_to_MA15(self):
        self.assertEqual(jfr.map_rating("TV-MA"), ("MA 15+", "mapped"))

    # ── UK BBFC ratings ───────────────────────────────────────────────

    def test_U_maps_to_G(self):
        self.assertEqual(jfr.map_rating("U"), ("G", "mapped"))

    def test_12A_maps_to_M(self):
        self.assertEqual(jfr.map_rating("12A"), ("M", "mapped"))

    def test_15_maps_to_MA15(self):
        self.assertEqual(jfr.map_rating("15"), ("MA 15+", "mapped"))

    def test_18_maps_to_R18(self):
        self.assertEqual(jfr.map_rating("18"), ("R 18+", "mapped"))

    def test_R18_nospace_maps(self):
        self.assertEqual(jfr.map_rating("R18"), ("R 18+", "mapped"))

    def test_GB_prefix_U(self):
        self.assertEqual(jfr.map_rating("GB-U"), ("G", "mapped"))

    def test_GB_prefix_15(self):
        self.assertEqual(jfr.map_rating("GB-15"), ("MA 15+", "mapped"))

    # ── German FSK ────────────────────────────────────────────────────

    def test_FSK_0(self):
        self.assertEqual(jfr.map_rating("FSK-0"), ("G", "mapped"))

    def test_FSK_16(self):
        self.assertEqual(jfr.map_rating("FSK-16"), ("MA 15+", "mapped"))

    def test_FSK_18(self):
        self.assertEqual(jfr.map_rating("FSK-18"), ("R 18+", "mapped"))

    def test_de_slash_12(self):
        self.assertEqual(jfr.map_rating("de/12"), ("M", "mapped"))

    def test_de_slash_18(self):
        self.assertEqual(jfr.map_rating("de/18"), ("R 18+", "mapped"))

    # ── French ────────────────────────────────────────────────────────

    def test_FR_U(self):
        self.assertEqual(jfr.map_rating("FR-U"), ("G", "mapped"))

    def test_FR_16(self):
        self.assertEqual(jfr.map_rating("FR-16"), ("MA 15+", "mapped"))

    # ── Dutch ─────────────────────────────────────────────────────────

    def test_nl_slash_16(self):
        self.assertEqual(jfr.map_rating("nl/16"), ("MA 15+", "mapped"))

    def test_AL_maps_to_G(self):
        self.assertEqual(jfr.map_rating("AL"), ("G", "mapped"))

    # ── Case-insensitive lookup ───────────────────────────────────────

    def test_lowercase_pg13(self):
        self.assertEqual(jfr.map_rating("pg-13"), ("M", "mapped"))

    def test_lowercase_tv_ma(self):
        self.assertEqual(jfr.map_rating("tv-ma"), ("MA 15+", "mapped"))

    def test_lowercase_unrated(self):
        self.assertEqual(jfr.map_rating("unrated"), (None, "skip"))

    def test_mixed_case_nr(self):
        self.assertEqual(jfr.map_rating("nR"), (None, "skip"))

    # ── AU spacing/prefix variants (normalised path) ──────────────────

    def test_MA15_nospace_normalised(self):
        """'MA15+' is in RATING_MAP directly, so status is 'mapped'."""
        rating, status = jfr.map_rating("MA15+")
        self.assertEqual(rating, "MA 15+")
        self.assertIn(status, ("mapped", "normalised"))

    def test_R18_nospace_variant(self):
        rating, status = jfr.map_rating("R18+")
        self.assertEqual(rating, "R 18+")
        self.assertIn(status, ("mapped", "normalised"))

    def test_AU_prefix_G_mapped(self):
        self.assertEqual(jfr.map_rating("AU-G"), ("G", "mapped"))

    def test_AU_prefix_MA15(self):
        rating, status = jfr.map_rating("AU-MA 15+")
        self.assertEqual(rating, "MA 15+")
        self.assertIn(status, ("mapped", "normalised", "already_au"))

    def test_whitespace_stripped_before_lookup(self):
        """Leading/trailing whitespace is stripped; 'M' should be already_au."""
        self.assertEqual(jfr.map_rating("  M  "), ("M", "already_au"))

    # ── Two-letter prefix + age stripping ────────────────────────────

    def test_two_letter_prefix_with_age(self):
        """'xx/16' → stripped '16' → _extract_age → 16 → MA 15+."""
        rating, status = jfr.map_rating("xx/16")
        self.assertEqual(rating, "MA 15+")
        self.assertEqual(status, "mapped")

    def test_two_letter_prefix_with_plus_age(self):
        """'zz/18+' → stripped '18+' → age 18 → R 18+."""
        rating, status = jfr.map_rating("zz/18+")
        self.assertEqual(rating, "R 18+")
        self.assertEqual(status, "mapped")

    # ── Bare numeric age at top level ─────────────────────────────────

    def test_bare_age_25(self):
        """A bare age not in RATING_MAP falls through to age extraction."""
        rating, status = jfr.map_rating("25")
        self.assertEqual(rating, "R 18+")
        self.assertEqual(status, "mapped")

    def test_bare_age_7(self):
        rating, status = jfr.map_rating("7")
        self.assertEqual(rating, "PG")
        self.assertEqual(status, "mapped")

    # ── Unmapped / unknown ────────────────────────────────────────────

    def test_gibberish_unmapped(self):
        self.assertEqual(jfr.map_rating("Troll"), (None, "unmapped"))

    def test_three_letter_prefix_not_treated_as_prefix(self):
        """'BBC-U' has 3 letters; prefix regex requires exactly 2."""
        self.assertEqual(jfr.map_rating("BBC-U"), (None, "unmapped"))

    def test_unknown_two_letter_prefix_non_numeric_suffix(self):
        """'zz/abc' → stripped 'abc' → not a known rating, not an age."""
        self.assertEqual(jfr.map_rating("zz/abc"), (None, "unmapped"))

    def test_R_rated_not_matched(self):
        """'R-rated' doesn't parse as just 'R' — it's unmapped."""
        self.assertEqual(jfr.map_rating("R-rated"), (None, "unmapped"))


# ══════════════════════════════════════════════════════════════════════
# _clean_payload
# ══════════════════════════════════════════════════════════════════════

class TestCleanPayload(unittest.TestCase):

    def _all_null(self):
        """Return a payload where every nullable field is None."""
        return {
            "Id": "abc", "Name": "Test",
            "Genres": None, "Tags": None, "Studios": None,
            "People": None, "LockedFields": None, "GenreItems": None,
            "TagItems": None, "RemoteTrailers": None,
            "ProductionLocations": None, "ArtistItems": None,
            "AlbumArtists": None, "ProviderIds": None,
        }

    def test_null_list_fields_become_empty_lists(self):
        payload = self._all_null()
        result = jfr._clean_payload(payload)
        for field in ["Genres", "Tags", "Studios", "People", "LockedFields",
                      "GenreItems", "TagItems", "RemoteTrailers",
                      "ProductionLocations", "ArtistItems", "AlbumArtists"]:
            self.assertEqual(result[field], [], f"{field} should be []")

    def test_null_provider_ids_becomes_empty_dict(self):
        payload = self._all_null()
        result = jfr._clean_payload(payload)
        self.assertEqual(result["ProviderIds"], {})

    def test_existing_list_not_overwritten(self):
        payload = self._all_null()
        payload["Genres"] = ["Action", "Drama"]
        result = jfr._clean_payload(payload)
        self.assertEqual(result["Genres"], ["Action", "Drama"])

    def test_missing_field_not_added(self):
        """Fields absent from the payload should not be injected."""
        payload = {"Id": "abc", "Name": "Test"}
        result = jfr._clean_payload(payload)
        self.assertNotIn("Genres", result)

    def test_provider_ids_existing_not_overwritten(self):
        payload = self._all_null()
        payload["ProviderIds"] = {"Tmdb": "12345"}
        result = jfr._clean_payload(payload)
        self.assertEqual(result["ProviderIds"], {"Tmdb": "12345"})

    def test_returns_same_dict_object(self):
        """_clean_payload mutates and returns the same dict."""
        payload = self._all_null()
        result = jfr._clean_payload(payload)
        self.assertIs(result, payload)

    def test_already_clean_payload_unchanged(self):
        payload = {
            "Genres": ["Comedy"], "Tags": [], "Studios": [],
            "People": [], "LockedFields": [], "ProviderIds": {"Imdb": "tt0"},
        }
        result = jfr._clean_payload(payload)
        self.assertEqual(result["Genres"], ["Comedy"])
        self.assertEqual(result["ProviderIds"], {"Imdb": "tt0"})


# ══════════════════════════════════════════════════════════════════════
# item_display_name
# ══════════════════════════════════════════════════════════════════════

class TestItemDisplayName(unittest.TestCase):

    def test_movie_just_name(self):
        item = {"Name": "Inception"}
        self.assertEqual(jfr.item_display_name(item), "Inception")

    def test_episode_with_series_only(self):
        item = {"SeriesName": "Breaking Bad", "Name": "Pilot"}
        self.assertEqual(jfr.item_display_name(item), "Breaking Bad > Pilot")

    def test_episode_with_series_and_season(self):
        item = {"SeriesName": "Breaking Bad", "SeasonName": "Season 1", "Name": "Pilot"}
        self.assertEqual(jfr.item_display_name(item), "Breaking Bad > Season 1 > Pilot")

    def test_missing_name_falls_back_to_Unknown(self):
        item = {}
        self.assertEqual(jfr.item_display_name(item), "Unknown")

    def test_empty_series_name_not_included(self):
        """An empty string SeriesName should be treated as falsy."""
        item = {"SeriesName": "", "Name": "Some Episode"}
        self.assertEqual(jfr.item_display_name(item), "Some Episode")

    def test_none_series_name_not_included(self):
        item = {"SeriesName": None, "Name": "Solo Movie"}
        self.assertEqual(jfr.item_display_name(item), "Solo Movie")


# ══════════════════════════════════════════════════════════════════════
# JellyfinClient._auth_header
# ══════════════════════════════════════════════════════════════════════

class TestAuthHeader(unittest.TestCase):

    def setUp(self):
        self.client = jfr.JellyfinClient("https://example.com")

    def test_header_without_token_has_required_fields(self):
        h = self.client._auth_header()
        self.assertIn('Client="JellyfinAURatings"', h)
        self.assertIn('Device="PythonScript"', h)
        self.assertIn('Version="2.0.0"', h)
        self.assertIn("MediaBrowser ", h)

    def test_header_without_token_has_no_token_field(self):
        h = self.client._auth_header()
        self.assertNotIn("Token=", h)

    def test_header_with_token_includes_token(self):
        h = self.client._auth_header("mysecretkey")
        self.assertIn('Token="mysecretkey"', h)

    def test_header_starts_with_mediabrowser(self):
        h = self.client._auth_header()
        self.assertTrue(h.startswith("MediaBrowser "))

    def test_device_id_is_present(self):
        h = self.client._auth_header()
        self.assertIn("DeviceId=", h)

    def test_base_url_trailing_slash_stripped(self):
        c = jfr.JellyfinClient("https://example.com/")
        self.assertEqual(c.base_url, "https://example.com")


# ══════════════════════════════════════════════════════════════════════
# _do_update  (mocked API)
# ══════════════════════════════════════════════════════════════════════

class TestDoUpdate(unittest.TestCase):
    """
    _do_update uses the module-level `client` global. We patch it with a
    mock and validate the fallback/retry strategy.
    """

    class _FakeHTTPError(Exception):
        """Minimal stand-in for requests.exceptions.HTTPError."""
        def __init__(self, msg, status=500):
            super().__init__(msg)
            self.response = type("R", (), {"status_code": status, "text": msg})()

    def _make_item(self, item_id="item-1", rating="PG-13"):
        return {"Id": item_id, "OfficialRating": rating, "Name": "Test Item"}

    def _full_payload(self, item):
        """Minimal but valid full-item response from get_item_full."""
        return {
            "Id": item["Id"], "Name": item["Name"],
            "OfficialRating": item["OfficialRating"],
            "Genres": [], "Tags": [], "Studios": [], "People": [],
            "LockedFields": [], "ProviderIds": {}, "LockData": False,
        }

    def setUp(self):
        self.mock_client = MagicMock()
        self._orig_client = jfr.client
        jfr.client = self.mock_client

    def tearDown(self):
        jfr.client = self._orig_client

    # ── Strategy 1 success ────────────────────────────────────────────

    def test_returns_True_on_success(self):
        item = self._make_item()
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        self.mock_client.update_item.return_value = None

        result = jfr._do_update(item, "MA 15+")

        self.assertTrue(result)

    def test_updates_item_dict_in_memory_on_success(self):
        item = self._make_item()
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        jfr._do_update(item, "MA 15+")
        self.assertEqual(item["OfficialRating"], "MA 15+")

    def test_calls_update_item_with_correct_id(self):
        item = self._make_item(item_id="xyz-99")
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        jfr._do_update(item, "G")
        args = self.mock_client.update_item.call_args
        self.assertEqual(args[0][0], "xyz-99")

    def test_new_rating_is_in_payload_sent_to_api(self):
        item = self._make_item()
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        jfr._do_update(item, "R 18+")
        sent_payload = self.mock_client.update_item.call_args[0][1]
        self.assertEqual(sent_payload["OfficialRating"], "R 18+")

    # ── Strategy 1 fails → Strategy 2 succeeds ───────────────────────

    def test_falls_back_to_minimal_payload_on_http_error(self):
        item = self._make_item()
        full = self._full_payload(item)

        http_err = _FakeHTTPError("500 Server Error")
        # First call (get_item_full for strategy 1) → succeeds
        # update_item for strategy 1 → raises
        # Second call (get_item_full for strategy 2) → succeeds
        self.mock_client.get_item_full.return_value = full
        self.mock_client.update_item.side_effect = [http_err, None]

        result = jfr._do_update(item, "G")
        self.assertTrue(result)
        self.assertEqual(self.mock_client.update_item.call_count, 2)

    def test_item_updated_in_memory_even_via_fallback(self):
        item = self._make_item()
        full = self._full_payload(item)
        self.mock_client.get_item_full.return_value = full
        self.mock_client.update_item.side_effect = [_FakeHTTPError("fail"), None]

        jfr._do_update(item, "G")
        self.assertEqual(item["OfficialRating"], "G")

    # ── Both strategies fail ──────────────────────────────────────────

    def test_returns_error_string_when_both_strategies_fail(self):
        item = self._make_item()
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        self.mock_client.update_item.side_effect = _FakeHTTPError("always fails")

        result = jfr._do_update(item, "G")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, True)

    def test_item_not_modified_in_memory_when_both_fail(self):
        item = self._make_item(rating="PG-13")
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        self.mock_client.update_item.side_effect = Exception("always fails")

        jfr._do_update(item, "M")
        self.assertEqual(item["OfficialRating"], "PG-13")

    # ── Null-field cleaning applied before first attempt ─────────────

    def test_null_genres_are_cleaned_before_update(self):
        item = self._make_item()
        full = self._full_payload(item)
        full["Genres"] = None      # would crash Jellyfin if sent as-is
        self.mock_client.get_item_full.return_value = full
        jfr._do_update(item, "G")

        sent = self.mock_client.update_item.call_args[0][1]
        self.assertEqual(sent["Genres"], [])

    def test_null_provider_ids_cleaned_before_update(self):
        item = self._make_item()
        full = self._full_payload(item)
        full["ProviderIds"] = None
        self.mock_client.get_item_full.return_value = full
        jfr._do_update(item, "G")

        sent = self.mock_client.update_item.call_args[0][1]
        self.assertEqual(sent["ProviderIds"], {})


# ══════════════════════════════════════════════════════════════════════
# Colour helpers
# ══════════════════════════════════════════════════════════════════════

class TestColourHelpers(unittest.TestCase):

    def test_ok_zero_is_dim(self):
        result = jfr.ok(0)
        self.assertIn(jfr.C.DIM, result)
        self.assertIn("0", result)

    def test_ok_nonzero_is_green(self):
        result = jfr.ok(42)
        self.assertIn(jfr.C.GREEN, result)
        self.assertIn("42", result)

    def test_err_colour_zero_is_green(self):
        result = jfr.err_colour(0)
        self.assertIn(jfr.C.GREEN, result)

    def test_err_colour_nonzero_is_red(self):
        result = jfr.err_colour(3)
        self.assertIn(jfr.C.RED, result)

    def test_green_wraps_with_reset(self):
        result = jfr.green("hello")
        self.assertTrue(result.startswith(jfr.C.GREEN))
        self.assertTrue(result.endswith(jfr.C.RESET))

    def test_red_wraps_with_reset(self):
        result = jfr.red("error")
        self.assertTrue(result.startswith(jfr.C.RED))
        self.assertTrue(result.endswith(jfr.C.RESET))

    def test_orange_uses_yellow_code(self):
        """'Orange' is rendered via ANSI yellow (033[33m)."""
        result = jfr.orange("warn")
        self.assertIn(jfr.C.YELLOW, result)

    def test_dim_wraps_with_reset(self):
        result = jfr.dim("quiet")
        self.assertIn(jfr.C.DIM, result)
        self.assertIn(jfr.C.RESET, result)


# ══════════════════════════════════════════════════════════════════════
# _rating_tag  (visual annotation in breakdown view)
# ══════════════════════════════════════════════════════════════════════

class TestRatingTag(unittest.TestCase):

    def test_au_rating_gets_green_checkmark(self):
        tag = jfr._rating_tag("MA 15+")
        self.assertIn(jfr.C.GREEN, tag)
        self.assertIn("✓", tag)

    def test_mappable_rating_gets_cyan_arrow(self):
        tag = jfr._rating_tag("PG-13")
        self.assertIn(jfr.C.CYAN, tag)
        self.assertIn("→", tag)

    def test_unmapped_rating_gets_red_warning(self):
        tag = jfr._rating_tag("Troll")
        self.assertIn(jfr.C.RED, tag)
        self.assertIn("⚠", tag)

    def test_no_rating_returns_empty_string(self):
        tag = jfr._rating_tag("(No Rating)")
        self.assertEqual(tag, "")

    def test_skipped_rating_is_dim(self):
        tag = jfr._rating_tag("NR")
        self.assertIn(jfr.C.DIM, tag)


# ══════════════════════════════════════════════════════════════════════
# Integration-style: map_rating round-trips for every AU rating
# ══════════════════════════════════════════════════════════════════════

class TestMapRatingRoundTrip(unittest.TestCase):
    """Every canonical AU rating fed back in should come out already_au."""

    def test_all_au_ratings_are_idempotent(self):
        for r in jfr.AU_RATINGS:
            with self.subTest(rating=r):
                result, status = jfr.map_rating(r)
                self.assertEqual(result, r)
                self.assertEqual(status, "already_au")


# ══════════════════════════════════════════════════════════════════════
# Integration-style: every entry in RATING_MAP produces a valid AU output
# ══════════════════════════════════════════════════════════════════════

class TestRatingMapCompleteness(unittest.TestCase):

    def test_every_non_null_map_entry_produces_valid_au_rating(self):
        for source, expected in jfr.RATING_MAP.items():
            if expected is None:
                continue
            with self.subTest(source=source):
                self.assertIn(
                    expected, jfr.AU_RATINGS_SET,
                    f"RATING_MAP['{source}'] = '{expected}' is not a valid AU rating"
                )

    def test_every_null_map_entry_is_intentional_skip(self):
        """Null-mapped entries represent ratings we deliberately don't convert."""
        null_entries = [k for k, v in jfr.RATING_MAP.items() if v is None]
        known_skips = {"NR", "Unrated", "Not Rated", "Approved"}
        for entry in null_entries:
            with self.subTest(entry=entry):
                self.assertIn(entry, known_skips,
                              f"'{entry}' maps to None but is not a known skip entry")




# ══════════════════════════════════════════════════════════════════════
# Credential store
# ══════════════════════════════════════════════════════════════════════

import tempfile
import stat as _stat
from pathlib import Path


class TestCredentialStore(unittest.TestCase):
    """
    All tests redirect _CONFIG_PATH to a temp file so they never
    touch the real ~/.config/jellyfin_au_ratings.cfg.
    """

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp_dir) / "test.cfg"
        self._orig_path = jfr._CONFIG_PATH
        jfr._CONFIG_PATH = self._tmp_path

    def tearDown(self):
        jfr._CONFIG_PATH = self._orig_path
        # Clean up any files left behind
        if self._tmp_path.exists():
            self._tmp_path.unlink()

    # ── _load_credentials ─────────────────────────────────────────────

    def test_load_returns_empty_tuple_when_no_file(self):
        self.assertEqual(jfr._load_credentials(), ("", "", "", ""))

    def test_load_returns_api_key(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="abc123")
        h, k, u, p = jfr._load_credentials()
        self.assertEqual(h, "https://jf.example.com")
        self.assertEqual(k, "abc123")
        self.assertEqual(u, "")
        self.assertEqual(p, "")

    def test_load_returns_username_and_password(self):
        jfr._save_credentials(host="https://jf.example.com", username="rob", password="s3cr3t")
        h, k, u, p = jfr._load_credentials()
        self.assertEqual(h, "https://jf.example.com")
        self.assertEqual(k, "")
        self.assertEqual(u, "rob")
        self.assertEqual(p, "s3cr3t")

    def test_load_returns_all_fields(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key", username="rob", password="pw")
        h, k, u, p = jfr._load_credentials()
        self.assertEqual((h, k, u, p), ("https://jf.example.com", "key", "rob", "pw"))

    def test_load_handles_missing_credentials_section(self):
        """A config file without a [credentials] section returns empty strings."""
        self._tmp_path.write_text("[other_section]\nfoo = bar\n")
        self.assertEqual(jfr._load_credentials(), ("", "", "", ""))

    # ── _save_credentials ─────────────────────────────────────────────

    def test_save_creates_file(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        self.assertTrue(self._tmp_path.exists())

    def test_save_sets_chmod_600(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        perms = _stat.S_IMODE(self._tmp_path.stat().st_mode)
        self.assertEqual(perms, 0o600)

    def test_save_overwrites_existing(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="old_key")
        jfr._save_credentials(host="https://jf.example.com", api_key="new_key")
        _, k, _, _ = jfr._load_credentials()
        self.assertEqual(k, "new_key")

    def test_save_creates_parent_directory(self):
        deep = Path(self._tmp_dir) / "subdir" / "deep.cfg"
        jfr._CONFIG_PATH = deep
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        self.assertTrue(deep.exists())
        deep.unlink()

    def test_save_empty_values_still_writes_file(self):
        jfr._save_credentials()
        self.assertTrue(self._tmp_path.exists())
        h, k, u, p = jfr._load_credentials()
        self.assertEqual((h, k, u, p), ("", "", "", ""))

    # ── _forget_credentials ───────────────────────────────────────────

    def test_forget_returns_True_and_removes_file(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        result = jfr._forget_credentials()
        self.assertTrue(result)
        self.assertFalse(self._tmp_path.exists())

    def test_forget_returns_False_when_no_file(self):
        result = jfr._forget_credentials()
        self.assertFalse(result)

    def test_forget_twice_is_safe(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        jfr._forget_credentials()
        result = jfr._forget_credentials()  # second call
        self.assertFalse(result)

    def test_load_after_forget_returns_empty(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        jfr._forget_credentials()
        self.assertEqual(jfr._load_credentials(), ("", "", "", ""))

    # ── _has_saved_credentials ────────────────────────────────────────

    def test_has_saved_False_when_no_file(self):
        self.assertFalse(jfr._has_saved_credentials())

    def test_has_saved_True_with_api_key(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        self.assertTrue(jfr._has_saved_credentials())

    def test_has_saved_True_with_username(self):
        jfr._save_credentials(host="https://jf.example.com", username="rob")
        self.assertTrue(jfr._has_saved_credentials())

    def test_has_saved_False_when_only_password_saved(self):
        """Password alone without key or username should not count."""
        jfr._save_credentials(password="pw")  # no host, key, or username
        self.assertFalse(jfr._has_saved_credentials())

    def test_has_saved_False_after_forget(self):
        jfr._save_credentials(host="https://jf.example.com", api_key="key")
        jfr._forget_credentials()
        self.assertFalse(jfr._has_saved_credentials())


    def test_load_returns_host(self):
        jfr._save_credentials(host="https://jf.example.com")
        h, k, u, p = jfr._load_credentials()
        self.assertEqual(h, "https://jf.example.com")
        self.assertEqual(k, "")

    def test_has_saved_True_with_host_only(self):
        """A saved host alone is enough to consider credentials present."""
        jfr._save_credentials(host="https://jf.example.com")
        self.assertTrue(jfr._has_saved_credentials())

    def test_save_host_persists_across_load(self):
        jfr._save_credentials(host="https://myjellyfin.local", api_key="k")
        h, k, _, _ = jfr._load_credentials()
        self.assertEqual(h, "https://myjellyfin.local")
        self.assertEqual(k, "k")


# ══════════════════════════════════════════════════════════════════════
# map_rating — additional rating systems not previously covered
# ══════════════════════════════════════════════════════════════════════

class TestMapRatingAdditional(unittest.TestCase):

    # ── Canadian ratings ──────────────────────────────────────────────

    def test_14A_maps_to_M(self):
        self.assertEqual(jfr.map_rating("14A"), ("M", "mapped"))

    def test_14plus_maps_to_M(self):
        self.assertEqual(jfr.map_rating("14+"), ("M", "mapped"))

    def test_18A_maps_to_MA15(self):
        self.assertEqual(jfr.map_rating("18A"), ("MA 15+", "mapped"))

    def test_A_maps_to_R18(self):
        """Canadian 'A' (Adults Only) → R 18+."""
        self.assertEqual(jfr.map_rating("A"), ("R 18+", "mapped"))

    # ── Brazilian ratings ─────────────────────────────────────────────

    def test_L_maps_to_G(self):
        """Brazilian 'L' (Livre) → G."""
        self.assertEqual(jfr.map_rating("L"), ("G", "mapped"))

    def test_10_maps_to_PG(self):
        """Brazilian '10' is in RATING_MAP directly → PG."""
        self.assertEqual(jfr.map_rating("10"), ("PG", "mapped"))

    def test_14_maps_to_M(self):
        """Brazilian '14' → M (also consistent with age extraction)."""
        rating, status = jfr.map_rating("14")
        self.assertEqual(rating, "M")

    def test_16_maps_to_MA15(self):
        """Brazilian '16' → MA 15+ (also consistent with age extraction)."""
        rating, status = jfr.map_rating("16")
        self.assertEqual(rating, "MA 15+")

    # ── Dutch additional ──────────────────────────────────────────────

    def test_nl_6_maps_to_PG(self):
        self.assertEqual(jfr.map_rating("nl/6"), ("PG", "mapped"))

    def test_nl_9_maps_to_PG(self):
        self.assertEqual(jfr.map_rating("nl/9"), ("PG", "mapped"))

    def test_nl_12_maps_to_M(self):
        self.assertEqual(jfr.map_rating("nl/12"), ("M", "mapped"))


# ══════════════════════════════════════════════════════════════════════
# JellyfinClient — authenticate_with_api_key
# ══════════════════════════════════════════════════════════════════════

class TestAuthenticateWithApiKey(unittest.TestCase):

    def _make_client(self):
        c = jfr.JellyfinClient("https://example.com")
        c.session = MagicMock()
        return c

    def _mock_resp(self, users):
        resp = MagicMock()
        resp.json.return_value = users
        resp.raise_for_status.return_value = None
        return resp

    def test_sets_user_id_to_admin(self):
        c = self._make_client()
        users = [
            {"Id": "u1", "Name": "Bob", "Policy": {"IsAdministrator": False}},
            {"Id": "u2", "Name": "Admin", "Policy": {"IsAdministrator": True}},
        ]
        c.session.get.return_value = self._mock_resp(users)
        c.authenticate_with_api_key("mykey")
        self.assertEqual(c.user_id, "u2")

    def test_falls_back_to_first_user_when_no_admin(self):
        c = self._make_client()
        users = [
            {"Id": "u1", "Name": "Alice", "Policy": {"IsAdministrator": False}},
            {"Id": "u2", "Name": "Bob",   "Policy": {"IsAdministrator": False}},
        ]
        c.session.get.return_value = self._mock_resp(users)
        c.authenticate_with_api_key("mykey")
        self.assertEqual(c.user_id, "u1")

    def test_returns_chosen_user(self):
        c = self._make_client()
        users = [{"Id": "u1", "Name": "Admin", "Policy": {"IsAdministrator": True}}]
        c.session.get.return_value = self._mock_resp(users)
        user = c.authenticate_with_api_key("mykey")
        self.assertEqual(user["Id"], "u1")

    def test_authorization_header_includes_token(self):
        c = self._make_client()
        users = [{"Id": "u1", "Policy": {"IsAdministrator": True}}]
        c.session.get.return_value = self._mock_resp(users)
        c.authenticate_with_api_key("secret-key")
        update_call = c.session.headers.update.call_args[0][0]
        self.assertIn("secret-key", update_call["Authorization"])

    def test_handles_user_without_policy_key(self):
        """Users dict without 'Policy' key should not raise."""
        c = self._make_client()
        users = [{"Id": "u1", "Name": "NoPolicy"}]
        c.session.get.return_value = self._mock_resp(users)
        c.authenticate_with_api_key("key")
        self.assertEqual(c.user_id, "u1")


# ══════════════════════════════════════════════════════════════════════
# JellyfinClient — authenticate_with_password
# ══════════════════════════════════════════════════════════════════════

class TestAuthenticateWithPassword(unittest.TestCase):

    def _make_client(self):
        c = jfr.JellyfinClient("https://example.com")
        c.session = MagicMock()
        return c

    def _mock_resp(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def test_sets_user_id_from_response(self):
        c = self._make_client()
        c.session.post.return_value = self._mock_resp({
            "User": {"Id": "user-99", "Name": "Rob"},
            "AccessToken": "tok123",
        })
        c.authenticate_with_password("rob", "password")
        self.assertEqual(c.user_id, "user-99")

    def test_returns_user_dict(self):
        c = self._make_client()
        c.session.post.return_value = self._mock_resp({
            "User": {"Id": "u1", "Name": "Rob"},
            "AccessToken": "tok",
        })
        user = c.authenticate_with_password("rob", "password")
        self.assertEqual(user["Name"], "Rob")

    def test_authorization_header_updated_with_token(self):
        c = self._make_client()
        c.session.post.return_value = self._mock_resp({
            "User": {"Id": "u1", "Name": "Rob"},
            "AccessToken": "my-access-token",
        })
        c.authenticate_with_password("rob", "pw")
        # The code does: session.headers["Authorization"] = _auth_header(token)
        # which calls __setitem__ on the MagicMock headers object.
        set_calls = c.session.headers.__setitem__.call_args_list
        auth_values = [v for k, v in (call[0] for call in set_calls) if k == "Authorization"]
        self.assertTrue(any("my-access-token" in v for v in auth_values),
                        f"Token not found in header assignments: {auth_values}")

    def test_posts_to_correct_endpoint(self):
        c = self._make_client()
        c.session.post.return_value = self._mock_resp({
            "User": {"Id": "u1"}, "AccessToken": "tok",
        })
        c.authenticate_with_password("rob", "pw")
        url = c.session.post.call_args[0][0]
        self.assertIn("/Users/AuthenticateByName", url)

    def test_sends_username_and_password_in_body(self):
        c = self._make_client()
        c.session.post.return_value = self._mock_resp({
            "User": {"Id": "u1"}, "AccessToken": "tok",
        })
        c.authenticate_with_password("rob", "mysecret")
        body = c.session.post.call_args[1]["json"]
        self.assertEqual(body["Username"], "rob")
        self.assertEqual(body["Pw"], "mysecret")


# ══════════════════════════════════════════════════════════════════════
# JellyfinClient — get_all_items pagination
# ══════════════════════════════════════════════════════════════════════

class TestGetAllItems(unittest.TestCase):

    def _make_client(self):
        c = jfr.JellyfinClient("https://example.com")
        c.session = MagicMock()
        c.user_id = "user-1"
        return c

    def _page(self, items, total):
        resp = MagicMock()
        resp.json.return_value = {"Items": items, "TotalRecordCount": total}
        resp.raise_for_status.return_value = None
        return resp

    def test_single_page_returns_all_items(self):
        c = self._make_client()
        items = [{"Id": str(i)} for i in range(5)]
        c.session.get.return_value = self._page(items, 5)
        result = c.get_all_items()
        self.assertEqual(len(result), 5)
        self.assertEqual(c.session.get.call_count, 1)

    def test_pagination_fetches_all_pages(self):
        c = self._make_client()
        page1 = [{"Id": str(i)} for i in range(200)]
        page2 = [{"Id": str(i)} for i in range(200, 250)]
        c.session.get.side_effect = [
            self._page(page1, 250),
            self._page(page2, 250),
        ]
        result = c.get_all_items()
        self.assertEqual(len(result), 250)
        self.assertEqual(c.session.get.call_count, 2)

    def test_pagination_three_pages(self):
        c = self._make_client()
        def make_page(n):
            return self._page([{"Id": str(i)} for i in range(n)], 500)
        c.session.get.side_effect = [make_page(200), make_page(200), make_page(100)]
        result = c.get_all_items()
        self.assertEqual(len(result), 500)
        self.assertEqual(c.session.get.call_count, 3)

    def test_empty_library_returns_empty_list(self):
        c = self._make_client()
        c.session.get.return_value = self._page([], 0)
        result = c.get_all_items()
        self.assertEqual(result, [])

    def test_start_index_increments_correctly(self):
        c = self._make_client()
        page1 = [{"Id": str(i)} for i in range(200)]
        page2 = [{"Id": str(i)} for i in range(200, 210)]
        c.session.get.side_effect = [
            self._page(page1, 210),
            self._page(page2, 210),
        ]
        c.get_all_items()
        calls = c.session.get.call_args_list
        self.assertEqual(calls[0][1]["params"]["StartIndex"], 0)
        self.assertEqual(calls[1][1]["params"]["StartIndex"], 200)


# ══════════════════════════════════════════════════════════════════════
# _print_done output
# ══════════════════════════════════════════════════════════════════════

class TestPrintDone(unittest.TestCase):

    def _capture(self, success, errors, samples):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            jfr._print_done(success, errors, samples)
        return buf.getvalue()

    def test_zero_errors_shows_green_zero(self):
        out = self._capture(10, 0, [])
        self.assertIn(jfr.C.GREEN, out)
        # The error count (0) should be green, not red
        self.assertNotIn(jfr.C.RED, out)

    def test_nonzero_errors_shows_red_count(self):
        out = self._capture(5, 2, [("Item A", "500 error")])
        self.assertIn(jfr.C.RED, out)

    def test_error_samples_are_printed(self):
        out = self._capture(0, 1, [("Breaking Bad S01E01", "404 not found")])
        self.assertIn("Breaking Bad", out)
        self.assertIn("404 not found", out)

    def test_no_samples_printed_when_list_empty(self):
        out = self._capture(5, 0, [])
        self.assertNotIn("Error details", out)

    def test_success_count_in_output(self):
        out = self._capture(42, 0, [])
        self.assertIn("42", out)


# ══════════════════════════════════════════════════════════════════════
# _do_update — additional failure modes
# ══════════════════════════════════════════════════════════════════════

class TestDoUpdateAdditional(unittest.TestCase):

    def _make_item(self, item_id="item-1", rating="PG-13"):
        return {"Id": item_id, "OfficialRating": rating, "Name": "Test"}

    def _full_payload(self, item):
        return {
            "Id": item["Id"], "Name": item["Name"],
            "OfficialRating": item["OfficialRating"],
            "Genres": [], "Tags": [], "Studios": [], "People": [],
            "LockedFields": [], "ProviderIds": {}, "LockData": False,
        }

    def setUp(self):
        self.mock_client = MagicMock()
        self._orig = jfr.client
        jfr.client = self.mock_client

    def tearDown(self):
        jfr.client = self._orig

    def test_get_item_full_failure_on_strategy1_falls_back(self):
        """If get_item_full itself raises on strategy 1, strategy 2 should run."""
        item = self._make_item()
        # Strategy 1: get_item_full raises
        # Strategy 2: get_item_full succeeds, update_item succeeds
        self.mock_client.get_item_full.side_effect = [
            Exception("timeout"),        # strategy 1 fetch fails
            self._full_payload(item),    # strategy 2 fetch succeeds
        ]
        self.mock_client.update_item.return_value = None
        result = jfr._do_update(item, "G")
        self.assertTrue(result)

    def test_error_string_references_both_strategies(self):
        """When both strategies fail the returned string mentions both."""
        item = self._make_item()
        self.mock_client.get_item_full.return_value = self._full_payload(item)
        self.mock_client.update_item.side_effect = _FakeHTTPError("bad request", 400)
        result = jfr._do_update(item, "G")
        self.assertIsInstance(result, str)
        self.assertIn("Full:", result)
        self.assertIn("Minimal:", result)

    def test_get_item_full_fails_both_strategies_returns_error_string(self):
        """get_item_full failing on both strategies should still return a string."""
        item = self._make_item()
        self.mock_client.get_item_full.side_effect = Exception("network error")
        result = jfr._do_update(item, "G")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, True)

if __name__ == "__main__":
    unittest.main(verbosity=2)
