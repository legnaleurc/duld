import unittest

from duld.dfd import _to_pattern, _to_regex_list, should_exclude


class TestToPattern(unittest.TestCase):
    def test_valid_pattern_returns_compiled_regex(self):
        result = _to_pattern(r"\d+")
        self.assertIsNotNone(result)

    def test_compiled_pattern_matches(self):
        result = _to_pattern(r"\d+")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.match("123"))

    def test_invalid_pattern_returns_none(self):
        result = _to_pattern("(invalid")
        self.assertIsNone(result)

    def test_pattern_is_case_insensitive(self):
        result = _to_pattern("abc")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.match("ABC"))
        self.assertIsNotNone(result.match("abc"))


class TestToRegexList(unittest.TestCase):
    def test_filters_out_empty_strings(self):
        result = _to_regex_list(["", "abc", ""])
        self.assertEqual(len(result), 1)

    def test_filters_out_invalid_patterns(self):
        result = _to_regex_list(["valid", "(invalid"])
        self.assertEqual(len(result), 1)

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(_to_regex_list([]), [])

    def test_all_valid_patterns_are_included(self):
        result = _to_regex_list(["abc", r"\d+", "xyz"])
        self.assertEqual(len(result), 3)

    def test_generator_input_is_accepted(self):
        result = _to_regex_list(s for s in ["a", "b"])
        self.assertEqual(len(result), 2)


class TestShouldExclude(unittest.TestCase):
    def setUp(self):
        self.filters = _to_regex_list(["sample", r"^\[.*\]"])

    def test_matching_name_is_excluded(self):
        self.assertTrue(should_exclude("sample_file", self.filters))

    def test_non_matching_name_is_not_excluded(self):
        self.assertFalse(should_exclude("clean_file", self.filters))

    def test_bracket_prefix_pattern_matches(self):
        self.assertTrue(should_exclude("[Fansub] Anime", self.filters))

    def test_empty_filter_list_never_excludes(self):
        self.assertFalse(should_exclude("anything", []))

    def test_match_is_case_insensitive(self):
        self.assertTrue(should_exclude("SAMPLE_FILE", self.filters))
