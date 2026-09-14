#!/usr/bin/env python3
"""Generate 100 bounded, test-driven micro-tasks for cheapoS stress testing."""

import json
from pathlib import Path

TASKS = []

def add_task(task_id, category, title, module_name, prompt, test_code):
    test_name = f"test_{module_name}"
    TASKS.append({
        "id": task_id,
        "category": category,
        "title": title,
        "module_name": module_name,
        "test_name": test_name,
        "prompt": f"{prompt}\nVerification check: python3 -m unittest -v {test_name}",
        "verification_command": f"python3 -m unittest -v {test_name}",
        "test_code": test_code.strip() + "\n"
    })

# ==========================================
# 1. String Manipulation & Text Processing (ST-001 to ST-010)
# ==========================================

add_task(
    "ST-001", "Text Processing", "URL Slug Generator", "slugify.py",
    "Create slugify.py implementing slugify(text, separator='-', lowercase=True). Converts accents/symbols, removes non-alphanumeric chars, replaces spaces with separator, strips repeated and boundary separators.",
    """import unittest
from slugify import slugify

class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")
    def test_custom_sep(self):
        self.assertEqual(slugify("Hello World!", separator="_"), "hello_world")
    def test_special_chars(self):
        self.assertEqual(slugify("  CheapOS -- Unattended Mode -- v0.2!  "), "cheapos-unattended-mode-v0-2")
    def test_case_sensitive(self):
        self.assertEqual(slugify("Fast Track", lowercase=False), "Fast-Track")
    def test_empty(self):
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify("   ---   "), "")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-002", "Text Processing", "Semantic Version Comparator", "semver.py",
    "Create semver.py implementing parse_semver(version_str) returning a tuple (major, minor, patch, prerelease) and compare_semver(v1, v2) returning -1 if v1 < v2, 0 if v1 == v2, and 1 if v1 > v2. Handle optional 'v' prefix and prerelease tags like '-alpha.1'.",
    """import unittest
from semver import parse_semver, compare_semver

class TestSemver(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_semver("v1.2.3"), (1, 2, 3, None))
        self.assertEqual(parse_semver("2.0.0-beta.1"), (2, 0, 0, "beta.1"))
    def test_compare_equal(self):
        self.assertEqual(compare_semver("1.0.0", "v1.0.0"), 0)
    def test_compare_patch(self):
        self.assertEqual(compare_semver("1.0.1", "1.0.0"), 1)
        self.assertEqual(compare_semver("1.0.0", "1.0.1"), -1)
    def test_compare_minor_major(self):
        self.assertEqual(compare_semver("1.2.0", "1.1.9"), 1)
        self.assertEqual(compare_semver("2.0.0", "1.9.9"), 1)
    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_semver("invalid.version")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-003", "Text Processing", "Markdown Inline Formatter", "md_inline.py",
    "Create md_inline.py implementing parse_inline_markdown(text) converting **bold** to <strong>bold</strong>, *italic* to <em>italic</em>, `code` to <code>code</code>, and [text](url) to <a href=\"url\">text</a>.",
    """import unittest
from md_inline import parse_inline_markdown

class TestMdInline(unittest.TestCase):
    def test_bold(self):
        self.assertEqual(parse_inline_markdown("This is **bold** text"), "This is <strong>bold</strong> text")
    def test_italic(self):
        self.assertEqual(parse_inline_markdown("This is *italic* text"), "This is <em>italic</em> text")
    def test_code(self):
        self.assertEqual(parse_inline_markdown("Run `git status` here"), "Run <code>git status</code> here")
    def test_link(self):
        self.assertEqual(parse_inline_markdown("Visit [Google](https://google.com)"), "Visit <a href=\\"https://google.com\\">Google</a>")
    def test_combined(self):
        self.assertEqual(parse_inline_markdown("**Bold** and *italic* with `code`"), "<strong>Bold</strong> and <em>italic</em> with <code>code</code>")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-004", "Text Processing", "Nested Template String Interpolator", "template.py",
    "Create template.py implementing render_template(template_str, context_dict). Replaces {{ key }} and nested {{ user.name }} placeholders with values from context_dict. Supports default empty string for missing keys.",
    """import unittest
from template import render_template

class TestTemplate(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(render_template("Hello {{ name }}!", {"name": "Alice"}), "Hello Alice!")
    def test_nested(self):
        ctx = {"user": {"profile": {"city": "New York"}}}
        self.assertEqual(render_template("From {{ user.profile.city }}", ctx), "From New York")
    def test_missing_key(self):
        self.assertEqual(render_template("Hello {{ missing }}!", {}), "Hello !")
    def test_whitespace_tolerance(self):
        self.assertEqual(render_template("{{a}} {{  b  }}", {"a": 1, "b": 2}), "1 2")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-005", "Text Processing", "Identifier Case Converter", "case_conv.py",
    "Create case_conv.py implementing to_snake_case(s), to_camel_case(s), to_kebab_case(s), and to_pascal_case(s) handling transitions between camelCase, PascalCase, snake_case, and kebab-case.",
    """import unittest
from case_conv import to_snake_case, to_camel_case, to_kebab_case, to_pascal_case

class TestCaseConv(unittest.TestCase):
    def test_to_snake(self):
        self.assertEqual(to_snake_case("camelCaseVar"), "camel_case_var")
        self.assertEqual(to_snake_case("PascalCaseVar"), "pascal_case_var")
        self.assertEqual(to_snake_case("kebab-case-var"), "kebab_case_var")
    def test_to_camel(self):
        self.assertEqual(to_camel_case("snake_case_var"), "snakeCaseVar")
        self.assertEqual(to_camel_case("kebab-case-var"), "kebabCaseVar")
    def test_to_kebab(self):
        self.assertEqual(to_kebab_case("camelCaseVar"), "camel-case-var")
    def test_to_pascal(self):
        self.assertEqual(to_pascal_case("snake_case_var"), "SnakeCaseVar")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-006", "Text Processing", "Word Wrap Text Column Formatter", "word_wrap.py",
    "Create word_wrap.py implementing wrap_text(text, width=80, break_long_words=False). Wraps paragraphs at whitespace so no line exceeds width characters, preserving existing newline paragraphs.",
    """import unittest
from word_wrap import wrap_text

class TestWordWrap(unittest.TestCase):
    def test_simple_wrap(self):
        text = "The quick brown fox jumps over the lazy dog"
        lines = wrap_text(text, width=15).splitlines()
        for line in lines:
            self.assertLessEqual(len(line), 15)
        self.assertEqual(" ".join(lines), text)
    def test_preserves_paragraphs(self):
        text = "First paragraph.\\n\\nSecond paragraph is longer and wraps nicely."
        res = wrap_text(text, width=20)
        self.assertIn("\\n\\n", res)
    def test_exact_width(self):
        self.assertEqual(wrap_text("12345 67890", width=5), "12345\\n67890")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-007", "Text Processing", "Smart Text Truncator", "smart_truncate.py",
    "Create smart_truncate.py implementing truncate_words(text, max_chars, suffix='...'). Truncates text so the total length including suffix does not exceed max_chars, breaking only on word boundaries without leaving trailing spaces before the suffix.",
    """import unittest
from smart_truncate import truncate_words

class TestSmartTruncate(unittest.TestCase):
    def test_no_truncate_needed(self):
        self.assertEqual(truncate_words("Short text", 20), "Short text")
    def test_word_boundary(self):
        self.assertEqual(truncate_words("The quick brown fox", 15), "The quick...")
    def test_exact_boundary(self):
        self.assertEqual(truncate_words("Hello world", 11), "Hello world")
    def test_very_short_limit(self):
        self.assertEqual(truncate_words("Hello world", 4, suffix="."), "H.")
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-008", "Text Processing", "Levenshtein String Similarity", "similarity.py",
    "Create similarity.py implementing levenshtein_distance(s1, s2) returning integer edit distance and similarity_ratio(s1, s2) returning float score from 0.0 to 1.0 (1.0 for identical strings).",
    """import unittest
from similarity import levenshtein_distance, similarity_ratio

class TestSimilarity(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(levenshtein_distance("kitten", "kitten"), 0)
        self.assertEqual(similarity_ratio("kitten", "kitten"), 1.0)
    def test_classic_kitten_sitting(self):
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)
    def test_empty(self):
        self.assertEqual(levenshtein_distance("", "test"), 4)
        self.assertEqual(similarity_ratio("", ""), 1.0)
        self.assertEqual(similarity_ratio("", "abc"), 0.0)
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-009", "Text Processing", "ANSI Color Code Cleaner", "ansi_cleaner.py",
    "Create ansi_cleaner.py implementing strip_ansi(text) which removes ANSI escape sequences (like \\x1b[31m) and visible_length(text) returning the visible character count.",
    """import unittest
from ansi_cleaner import strip_ansi, visible_length

class TestAnsiCleaner(unittest.TestCase):
    def test_strip_color(self):
        raw = "\\x1b[31mRed Text\\x1b[0m"
        self.assertEqual(strip_ansi(raw), "Red Text")
        self.assertEqual(visible_length(raw), 8)
    def test_strip_styles(self):
        raw = "\\x1b[1;32;40mBold Green\\x1b[0m"
        self.assertEqual(strip_ansi(raw), "Bold Green")
        self.assertEqual(visible_length(raw), 10)
    def test_no_ansi(self):
        self.assertEqual(strip_ansi("Plain"), "Plain")
        self.assertEqual(visible_length("Plain"), 5)
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-010", "Text Processing", "Query String Parser & Formatter", "query_string.py",
    "Create query_string.py implementing parse_qs_custom(qs_string) returning a dict with list values, and format_qs_custom(params_dict) returning an escaped query string sorted by key name.",
    """import unittest
from query_string import parse_qs_custom, format_qs_custom

class TestQueryString(unittest.TestCase):
    def test_parse(self):
        res = parse_qs_custom("name=John+Doe&tag=python&tag=cheapos&count=5")
        self.assertEqual(res["name"], ["John Doe"])
        self.assertEqual(res["tag"], ["python", "cheapos"])
        self.assertEqual(res["count"], ["5"])
    def test_format(self):
        data = {"b": [2], "a": [1, 3]}
        self.assertEqual(format_qs_custom(data), "a=1&a=3&b=2")
    def test_empty(self):
        self.assertEqual(parse_qs_custom(""), {})
        self.assertEqual(format_qs_custom({}), "")
if __name__ == '__main__': unittest.main()"""
)

# ==========================================
# 2. Data Structures & Collections (ST-011 to ST-020)
# ==========================================

add_task(
    "ST-011", "Data Structures", "Capacity-Limited LRU Cache", "lru_cache.py",
    "Create lru_cache.py implementing LRUCache(capacity). Supports get(key, default=None), put(key, value), size(), and items(). When capacity is exceeded, evicts the least recently accessed item.",
    """import unittest
from lru_cache import LRUCache

class TestLRUCache(unittest.TestCase):
    def test_eviction(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("c"), 3)
    def test_overwrite(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("a", 10)
        self.assertEqual(cache.get("a"), 10)
        self.assertEqual(cache.size(), 1)
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-012", "Data Structures", "Priority Queue with FIFO Tie-Breaking", "priority_queue.py",
    "Create priority_queue.py implementing PriorityQueue(). Supports push(item, priority), pop(), peek(), is_empty(), and len(pq). Smaller priority values come first; ties break in FIFO order.",
    """import unittest
from priority_queue import PriorityQueue

class TestPriorityQueue(unittest.TestCase):
    def test_ordering(self):
        pq = PriorityQueue()
        pq.push("low", 10)
        pq.push("high", 1)
        pq.push("medium", 5)
        self.assertEqual(pq.pop(), "high")
        self.assertEqual(pq.pop(), "medium")
        self.assertEqual(pq.pop(), "low")
    def test_fifo_ties(self):
        pq = PriorityQueue()
        pq.push("first", 5)
        pq.push("second", 5)
        self.assertEqual(pq.pop(), "first")
        self.assertEqual(pq.pop(), "second")
    def test_empty(self):
        pq = PriorityQueue()
        self.assertTrue(pq.is_empty())
        with self.assertRaises(IndexError):
            pq.pop()
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-013", "Data Structures", "Deep Dictionary Merger", "dict_merge.py",
    "Create dict_merge.py implementing deep_merge(base, override, list_strategy='replace'). Recursively merges nested dictionaries. If list_strategy is 'replace', overrides list; if 'concat', concatenates lists; if 'union', preserves unique items in order.",
    """import unittest
from dict_merge import deep_merge

class TestDictMerge(unittest.TestCase):
    def test_nested_merge(self):
        b = {"app": {"theme": "dark", "port": 5000}}
        o = {"app": {"port": 8080, "debug": True}}
        res = deep_merge(b, o)
        self.assertEqual(res, {"app": {"theme": "dark", "port": 8080, "debug": True}})
    def test_list_concat(self):
        b = {"tags": [1, 2]}
        o = {"tags": [2, 3]}
        self.assertEqual(deep_merge(b, o, list_strategy="concat")["tags"], [1, 2, 2, 3])
        self.assertEqual(deep_merge(b, o, list_strategy="union")["tags"], [1, 2, 3])
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-014", "Data Structures", "Flatten and Unflatten Dictionaries", "dict_flatten.py",
    "Create dict_flatten.py implementing flatten_dict(d, sep='.') and unflatten_dict(d, sep='.'). Converts nested dictionary to dot-delimited flat keys and reconstructs the nested structure from flat keys.",
    """import unittest
from dict_flatten import flatten_dict, unflatten_dict

class TestDictFlatten(unittest.TestCase):
    def test_flatten(self):
        d = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
        flat = flatten_dict(d)
        self.assertEqual(flat, {"a.b": 1, "a.c.d": 2, "e": 3})
    def test_unflatten(self):
        flat = {"user.name": "Carlos", "user.settings.theme": "dark"}
        nested = unflatten_dict(flat)
        self.assertEqual(nested, {"user": {"name": "Carlos", "settings": {"theme": "dark"}}})
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-015", "Data Structures", "Trie Prefix Tree for Autocomplete", "trie.py",
    "Create trie.py implementing Trie(). Supports insert(word), search(word) -> bool, starts_with(prefix) -> bool, and autocomplete(prefix) -> list[str] in alphabetical order.",
    """import unittest
from trie import Trie

class TestTrie(unittest.TestCase):
    def test_trie_operations(self):
        trie = Trie()
        for w in ["cheap", "cheapo", "cheapos", "check", "cat"]:
            trie.insert(w)
        self.assertTrue(trie.search("cheapo"))
        self.assertFalse(trie.search("cheaposs"))
        self.assertTrue(trie.starts_with("che"))
        self.assertEqual(trie.autocomplete("cheap"), ["cheap", "cheapo", "cheapos"])
        self.assertEqual(trie.autocomplete("z"), [])
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-016", "Data Structures", "Fixed-Size Circular Ring Buffer", "ring_buffer.py",
    "Create ring_buffer.py implementing RingBuffer(capacity). Supports append(item), to_list(), is_full(), is_empty(), and clear(). When capacity is exceeded, oldest items are overwritten.",
    """import unittest
from ring_buffer import RingBuffer

class TestRingBuffer(unittest.TestCase):
    def test_overflow(self):
        rb = RingBuffer(3)
        rb.append(1); rb.append(2); rb.append(3)
        self.assertTrue(rb.is_full())
        self.assertEqual(rb.to_list(), [1, 2, 3])
        rb.append(4)
        self.assertEqual(rb.to_list(), [2, 3, 4])
    def test_empty(self):
        rb = RingBuffer(3)
        self.assertTrue(rb.is_empty())
        rb.clear()
        self.assertEqual(rb.to_list(), [])
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-017", "Data Structures", "Disjoint Set Union-Find", "union_find.py",
    "Create union_find.py implementing UnionFind(elements). Supports find(x), union(x, y), connected(x, y), and count_components(). Uses path compression and union by rank.",
    """import unittest
from union_find import UnionFind

class TestUnionFind(unittest.TestCase):
    def test_connectivity(self):
        uf = UnionFind([1, 2, 3, 4, 5])
        self.assertEqual(uf.count_components(), 5)
        uf.union(1, 2)
        uf.union(2, 3)
        self.assertTrue(uf.connected(1, 3))
        self.assertFalse(uf.connected(1, 4))
        self.assertEqual(uf.count_components(), 3)
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-018", "Data Structures", "Bi-directional Mapping", "bimap.py",
    "Create bimap.py implementing BiMap(). Supports set(k, v), get_by_key(k), get_by_val(v), delete_by_key(k), delete_by_val(v), and len(). Keys and values must remain unique 1-to-1 mappings.",
    """import unittest
from bimap import BiMap

class TestBiMap(unittest.TestCase):
    def test_bidirectional(self):
        bm = BiMap()
        bm.set("us", "united_states")
        bm.set("fr", "france")
        self.assertEqual(bm.get_by_key("us"), "united_states")
        self.assertEqual(bm.get_by_val("france"), "fr")
    def test_delete(self):
        bm = BiMap()
        bm.set("a", 1)
        bm.delete_by_val(1)
        self.assertIsNone(bm.get_by_key("a"))
        self.assertEqual(len(bm), 0)
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-019", "Data Structures", "Interval Overlap Checker", "interval_tree.py",
    "Create interval_tree.py implementing IntervalSet(). Supports add(start, end), overlaps(start, end) -> bool, and all_overlapping(start, end) -> list[tuple[int, int]]. Intervals are inclusive [start, end].",
    """import unittest
from interval_tree import IntervalSet

class TestIntervalSet(unittest.TestCase):
    def test_overlaps(self):
        iset = IntervalSet()
        iset.add(10, 20)
        iset.add(30, 40)
        self.assertTrue(iset.overlaps(15, 25))
        self.assertFalse(iset.overlaps(21, 29))
        self.assertEqual(iset.all_overlapping(15, 35), [(10, 20), (30, 40)])
if __name__ == '__main__': unittest.main()"""
)

add_task(
    "ST-020", "Data Structures", "Sparse Vector with Cosine Similarity", "sparse_vector.py",
    "Create sparse_vector.py implementing SparseVector(dimensions, values_dict). Supports dot(other), norm(), and cosine_similarity(other). Efficiently computes without allocating full dense arrays.",
    """import unittest
from sparse_vector import SparseVector

class TestSparseVector(unittest.TestCase):
    def test_dot_product(self):
        v1 = SparseVector(1000, {0: 3, 500: 4})
        v2 = SparseVector(1000, {0: 1, 500: 2, 999: 10})
        self.assertEqual(v1.dot(v2), 3*1 + 4*2)
    def test_cosine_similarity(self):
        v1 = SparseVector(100, {1: 1, 2: 1})
        v2 = SparseVector(100, {1: 1, 2: 1})
        self.assertAlmostEqual(v1.cosine_similarity(v2), 1.0)
if __name__ == '__main__': unittest.main()"""
)

# ==========================================
# 3 to 10: Populate 80 more tasks across the remaining domains
# ==========================================

categories = [
    ("Validation", [
        ("ST-021", "Email Address Validator", "email_validator.py", "validate_email(email) -> bool checking syntax, domain, and quotes.",
         "from email_validator import validate_email\nclass Test(unittest.TestCase):\n def test_valid(self): self.assertTrue(validate_email('test@example.com'))\n def test_invalid(self): self.assertFalse(validate_email('plainaddress'))"),
        ("ST-022", "Credit Card Luhn Validator", "card_validator.py", "validate_card(num) -> bool and detect_brand(num) -> str (Visa, Mastercard, Amex).",
         "from card_validator import validate_card, detect_brand\nclass Test(unittest.TestCase):\n def test_visa(self): self.assertEqual(detect_brand('4000000000000'), 'Visa')"),
        ("ST-023", "IP Address & CIDR Checker", "ip_validator.py", "is_valid_ipv4(ip), is_valid_ipv6(ip), and ip_in_cidr(ip, cidr).",
         "from ip_validator import is_valid_ipv4, ip_in_cidr\nclass Test(unittest.TestCase):\n def test_ip(self): self.assertTrue(is_valid_ipv4('192.168.1.1'))\n self.assertTrue(ip_in_cidr('192.168.1.5', '192.168.1.0/24'))"),
        ("ST-024", "HTTP URL Validator", "url_validator.py", "validate_url(url, require_https=False) -> bool.",
         "from url_validator import validate_url\nclass Test(unittest.TestCase):\n def test_url(self): self.assertTrue(validate_url('https://cheapos.local:5173/path'))"),
        ("ST-025", "Schema Lite Validator", "schema_validator.py", "validate_schema(data, schema) -> list[str] of error messages.",
         "from schema_validator import validate_schema\nclass Test(unittest.TestCase):\n def test_schema(self): self.assertEqual(validate_schema({'a': 1}, {'a': {'type': 'int'}}), [])"),
        ("ST-026", "Password Strength Evaluator", "password_evaluator.py", "evaluate_password(pwd) -> dict(score=0..4, feedback=list).",
         "from password_evaluator import evaluate_password\nclass Test(unittest.TestCase):\n def test_pwd(self): self.assertGreaterEqual(evaluate_password('C0mpl3x!Pass#99')['score'], 3)"),
        ("ST-027", "Cron Expression Parser", "cron_validator.py", "parse_cron(expr) -> dict(minute, hour, dom, month, dow).",
         "from cron_validator import parse_cron\nclass Test(unittest.TestCase):\n def test_cron(self): self.assertEqual(len(parse_cron('*/5 * * * *')['minute']), 12)"),
        ("ST-028", "ISO 8601 Duration Parser", "iso_duration.py", "parse_duration(p_str) -> int total seconds (e.g. PT1H30M).",
         "from iso_duration import parse_duration\nclass Test(unittest.TestCase):\n def test_dur(self): self.assertEqual(parse_duration('PT1H30M'), 5400)"),
        ("ST-029", "Phone Number Normalizer", "phone_normalizer.py", "normalize_phone(phone_str, default_country='US') -> str E.164.",
         "from phone_normalizer import normalize_phone\nclass Test(unittest.TestCase):\n def test_phone(self): self.assertEqual(normalize_phone('(555) 123-4567'), '+15551234567')"),
        ("ST-030", "HTML Tag Sanitizer", "html_sanitizer.py", "sanitize_html(raw_html, allowed_tags=None) -> str safe text.",
         "from html_sanitizer import sanitize_html\nclass Test(unittest.TestCase):\n def test_html(self): self.assertEqual(sanitize_html('<script>bad()</script><b>Hi</b>', ['b']), '<b>Hi</b>')"),
    ]),
    ("Math & Numerical", [
        ("ST-031", "Precise Money Calculator", "money_calc.py", "Money(amount, currency) with add, sub, mul, and round_cents.",
         "from money_calc import Money\nclass Test(unittest.TestCase):\n def test_money(self): self.assertEqual((Money(10.50, 'USD') + Money(5.25, 'USD')).amount, 15.75)"),
        ("ST-032", "Running Stream Statistics", "running_stats.py", "RunningStats with push(val), mean(), variance(), std_dev().",
         "from running_stats import RunningStats\nclass Test(unittest.TestCase):\n def test_stats(self): s = RunningStats(); s.push(10); s.push(20); self.assertEqual(s.mean(), 15.0)"),
        ("ST-033", "Number to English Words", "num_to_words.py", "number_to_words(n: int) -> str (e.g. 1042 -> 'one thousand forty-two').",
         "from num_to_words import number_to_words\nclass Test(unittest.TestCase):\n def test_num(self): self.assertEqual(number_to_words(42), 'forty-two')"),
        ("ST-034", "Linear Regression Calculator", "linear_regression.py", "calc_regression(points: list[(x,y)]) -> (slope, intercept, r_squared).",
         "from linear_regression import calc_regression\nclass Test(unittest.TestCase):\n def test_reg(self): m, b, r = calc_regression([(1, 2), (2, 4), (3, 6)]); self.assertAlmostEqual(m, 2.0)"),
        ("ST-035", "Matrix Math Operations", "matrix_ops.py", "matrix_multiply(a, b) and matrix_transpose(m).",
         "from matrix_ops import matrix_multiply, matrix_transpose\nclass Test(unittest.TestCase):\n def test_mat(self): self.assertEqual(matrix_transpose([[1, 2], [3, 4]]), [[1, 3], [2, 4]])"),
        ("ST-036", "Fraction Arithmetic", "fraction_calc.py", "Fraction(num, denom) with simplify, add, multiply.",
         "from fraction_calc import Fraction\nclass Test(unittest.TestCase):\n def test_frac(self): self.assertEqual((Fraction(1, 2) + Fraction(1, 3)).to_tuple(), (5, 6))"),
        ("ST-037", "Compound Growth Calculator", "compound_calc.py", "calc_compound(principal, rate, years, periods=12).",
         "from compound_calc import calc_compound\nclass Test(unittest.TestCase):\n def test_compound(self): self.assertAlmostEqual(calc_compound(1000, 0.05, 1, 1), 1050.0)"),
        ("ST-038", "Haversine Distance Calculator", "haversine.py", "haversine_km(lat1, lon1, lat2, lon2) -> float km distance.",
         "from haversine import haversine_km\nclass Test(unittest.TestCase):\n def test_dist(self): self.assertGreater(haversine_km(40.7128, -74.0060, 51.5074, -0.1278), 5500)"),
        ("ST-039", "Moving Average Stream", "moving_average.py", "SimpleMovingAverage(window) and ExponentialMovingAverage(alpha).",
         "from moving_average import SimpleMovingAverage\nclass Test(unittest.TestCase):\n def test_sma(self): sma = SimpleMovingAverage(2); sma.push(10); self.assertEqual(sma.push(20), 15.0)"),
        ("ST-040", "Roman Numeral Converter", "roman_numerals.py", "to_roman(num: int) -> str and from_roman(s: str) -> int.",
         "from roman_numerals import to_roman, from_roman\nclass Test(unittest.TestCase):\n def test_roman(self): self.assertEqual(to_roman(1984), 'MCMLXXXIV'); self.assertEqual(from_roman('MCMLXXXIV'), 1984)"),
    ]),
    ("Serialization & IO", [
        ("ST-041", "CSV Dialect Detector", "csv_reader.py", "detect_delimiter(sample_text) -> str and parse_rows(text).",
         "from csv_reader import detect_delimiter\nclass Test(unittest.TestCase):\n def test_delim(self): self.assertEqual(detect_delimiter('a\\tb\\tc\\n1\\t2\\t3'), '\\t')"),
        ("ST-042", "Lightweight INI Parser", "ini_parser.py", "parse_ini(text) -> dict and serialize_ini(dict) -> str.",
         "from ini_parser import parse_ini\nclass Test(unittest.TestCase):\n def test_ini(self): self.assertEqual(parse_ini('[s]\\nk=v')['s']['k'], 'v')"),
        ("ST-043", "JSONL Batch Streamer", "jsonl_processor.py", "filter_jsonl(input_lines, predicate_fn) returning matched dicts.",
         "from jsonl_processor import filter_jsonl\nclass Test(unittest.TestCase):\n def test_jsonl(self): self.assertEqual(len(filter_jsonl(['{\"x\": 1}', '{\"x\": 2}'], lambda d: d['x'] > 1)), 1)"),
        ("ST-044", "File Glob Path Matcher", "glob_matcher.py", "glob_match(path, pattern) supporting * and **.",
         "from glob_matcher import glob_match\nclass Test(unittest.TestCase):\n def test_glob(self): self.assertTrue(glob_match('cheapos/core/app.py', '**/*.py'))"),
        ("ST-045", "Unified Diff Parser", "diff_parser.py", "parse_diff_hunks(diff_str) -> list of hunk dicts with old/new lines.",
         "from diff_parser import parse_diff_hunks\nclass Test(unittest.TestCase):\n def test_diff(self): self.assertTrue(callable(parse_diff_hunks))"),
        ("ST-046", "Properties File Parser", "props_reader.py", "parse_properties(text) -> dict with escape support.",
         "from props_reader import parse_properties\nclass Test(unittest.TestCase):\n def test_props(self): self.assertEqual(parse_properties('app.name=CheapOS\\nport=5173')['port'], '5173')"),
        ("ST-047", "Base64 Formatter", "base64_util.py", "safe_b64encode(data, line_wrap=0) and safe_b64decode(s).",
         "from base64_util import safe_b64encode, safe_b64decode\nclass Test(unittest.TestCase):\n def test_b64(self): self.assertEqual(safe_b64decode(safe_b64encode(b'hello')), b'hello')"),
        ("ST-048", "Byte Size Formatter", "byte_format.py", "format_bytes(n: int) -> str and parse_bytes(s: str) -> int.",
         "from byte_format import format_bytes, parse_bytes\nclass Test(unittest.TestCase):\n def test_bytes(self): self.assertEqual(format_bytes(1024), '1.0 KB'); self.assertEqual(parse_bytes('1KB'), 1024)"),
        ("ST-049", "Tar Header Reader", "tar_header.py", "parse_tar_header(header_512_bytes) -> dict(name, size, mode).",
         "from tar_header import parse_tar_header\nclass Test(unittest.TestCase):\n def test_tar(self): self.assertTrue(callable(parse_tar_header))"),
        ("ST-050", "JSON Deep Diff", "json_diff.py", "json_diff(obj1, obj2) -> list[dict(op, path, old, new)].",
         "from json_diff import json_diff\nclass Test(unittest.TestCase):\n def test_diff(self): self.assertEqual(json_diff({'a': 1}, {'a': 2})[0]['op'], 'replace')"),
    ]),
    ("Datetime & Time", [
        ("ST-051", "Date Range Generator", "date_range.py", "date_range(start_str, end_str, skip_weekends=False) -> list[str].",
         "from date_range import date_range\nclass Test(unittest.TestCase):\n def test_range(self): self.assertEqual(len(date_range('2026-09-01', '2026-09-05')), 5)"),
        ("ST-052", "Relative Time Formatter", "relative_time.py", "time_ago(epoch_seconds, now=None) -> str ('2 hours ago').",
         "from relative_time import time_ago\nclass Test(unittest.TestCase):\n def test_ago(self): self.assertEqual(time_ago(100, now=160), '1 minute ago')"),
        ("ST-053", "Interval Merger", "interval_merger.py", "merge_intervals(intervals: list[(s, e)]) -> list.",
         "from interval_merger import merge_intervals\nclass Test(unittest.TestCase):\n def test_merge(self): self.assertEqual(merge_intervals([(1, 3), (2, 6), (8, 10)]), [(1, 6), (8, 10)])"),
        ("ST-054", "Timezone Offset Parser", "tz_parser.py", "parse_tz_offset(tz_str) -> int seconds offset.",
         "from tz_parser import parse_tz_offset\nclass Test(unittest.TestCase):\n def test_tz(self): self.assertEqual(parse_tz_offset('-04:00'), -14400)"),
        ("ST-055", "Business Hours Calculator", "business_hours.py", "business_hours_between(start_dt, end_dt, workday_hours=(9, 17)).",
         "from business_hours import business_hours_between\nclass Test(unittest.TestCase):\n def test_bh(self): self.assertTrue(callable(business_hours_between))"),
        ("ST-056", "Month Calendar Grid", "calendar_grid.py", "generate_month_grid(year, month) -> 2D list of days.",
         "from calendar_grid import generate_month_grid\nclass Test(unittest.TestCase):\n def test_cal(self): grid = generate_month_grid(2026, 9); self.assertEqual(len(grid[0]), 7)"),
        ("ST-057", "Exponential Backoff Jitter", "backoff.py", "calc_backoff(attempt, base_sec=1.0, max_sec=60.0, jitter=True).",
         "from backoff import calc_backoff\nclass Test(unittest.TestCase):\n def test_bo(self): self.assertLessEqual(calc_backoff(3, jitter=False), 8.0)"),
        ("ST-058", "Token Bucket Rate Limiter", "token_bucket.py", "TokenBucket(rate, capacity) with consume(tokens=1) -> bool.",
         "from token_bucket import TokenBucket\nclass Test(unittest.TestCase):\n def test_tb(self): tb = TokenBucket(10, 10); self.assertTrue(tb.consume(5)); self.assertFalse(tb.consume(10))"),
        ("ST-059", "Leaky Bucket Rate Limiter", "leaky_bucket.py", "LeakyBucket(capacity, leak_rate) with add_drop().",
         "from leaky_bucket import LeakyBucket\nclass Test(unittest.TestCase):\n def test_lb(self): lb = LeakyBucket(5, 1); self.assertTrue(lb.add())"),
        ("ST-060", "Stopwatch Split Timer", "stopwatch.py", "Stopwatch with start(), lap(), stop(), elapsed().",
         "from stopwatch import Stopwatch\nclass Test(unittest.TestCase):\n def test_sw(self): sw = Stopwatch(); sw.start(); self.assertGreaterEqual(sw.elapsed(), 0)"),
    ]),
    ("Security & Encodings", [
        ("ST-061", "Base58 Encoder Decoder", "base58.py", "b58encode(data) -> str and b58decode(str) -> bytes.",
         "from base58 import b58encode, b58decode\nclass Test(unittest.TestCase):\n def test_b58(self): self.assertEqual(b58decode(b58encode(b'hello')), b'hello')"),
        ("ST-062", "HMAC Constant-Time Checker", "hmac_util.py", "compute_hmac(key, msg) and constant_time_compare(a, b).",
         "from hmac_util import compute_hmac, constant_time_compare\nclass Test(unittest.TestCase):\n def test_hmac(self): self.assertTrue(constant_time_compare('abc', 'abc'))"),
        ("ST-063", "UUID v4 Utilities", "uuid_util.py", "generate_uuid4() -> str and is_valid_uuid(uuid_str) -> bool.",
         "from uuid_util import generate_uuid4, is_valid_uuid\nclass Test(unittest.TestCase):\n def test_uuid(self): u = generate_uuid4(); self.assertTrue(is_valid_uuid(u))"),
        ("ST-064", "Hex Dump Formatter", "hexdump.py", "format_hexdump(data: bytes, width=16) -> str.",
         "from hexdump import format_hexdump\nclass Test(unittest.TestCase):\n def test_hex(self): self.assertIn('00000000', format_hexdump(b'test data'))"),
        ("ST-065", "URL Token Generator", "token_gen.py", "generate_token(length=32) and verify_token(token).",
         "from token_gen import generate_token, verify_token\nclass Test(unittest.TestCase):\n def test_tok(self): t = generate_token(); self.assertTrue(verify_token(t))"),
        ("ST-066", "Caesar & Vigenere Ciphers", "ciphers.py", "caesar_cipher(text, shift) and vigenere_cipher(text, key).",
         "from ciphers import caesar_cipher, vigenere_cipher\nclass Test(unittest.TestCase):\n def test_ciph(self): self.assertEqual(caesar_cipher('abc', 3), 'def')"),
        ("ST-067", "Bloom Filter Probabilistic Set", "bloom_filter.py", "BloomFilter(size, hash_count) with add and contains.",
         "from bloom_filter import BloomFilter\nclass Test(unittest.TestCase):\n def test_bloom(self): bf = BloomFilter(100, 3); bf.add('apple'); self.assertTrue(bf.contains('apple'))"),
        ("ST-068", "Bitwise Permission Flags", "permissions_flags.py", "PermissionFlags with grant, revoke, has_permission.",
         "from permissions_flags import PermissionFlags\nclass Test(unittest.TestCase):\n def test_perm(self): p = PermissionFlags(); p.grant('READ'); self.assertTrue(p.has_permission('READ'))"),
        ("ST-069", "CRC32 Checksum Calculator", "checksums.py", "calc_crc32(data: bytes) -> int.",
         "from checksums import calc_crc32\nclass Test(unittest.TestCase):\n def test_crc(self): self.assertIsInstance(calc_crc32(b'data'), int)"),
        ("ST-070", "Log Secret Redactor", "log_redactor.py", "redact_secrets(log_line) masking keys and bearer tokens.",
         "from log_redactor import redact_secrets\nclass Test(unittest.TestCase):\n def test_redact(self): self.assertNotIn('secret123', redact_secrets('Bearer secret123'))"),
    ]),
    ("Graph & Algorithms", [
        ("ST-071", "Topological Sorter", "topological_sort.py", "topological_sort(graph: dict[node, list]) -> list or raises cycle.",
         "from topological_sort import topological_sort\nclass Test(unittest.TestCase):\n def test_topo(self): self.assertEqual(topological_sort({'b': ['a'], 'a': []})[:2], ['a', 'b'])"),
        ("ST-072", "Graph Cycle Detector", "cycle_detector.py", "has_cycle(graph, directed=True) -> bool.",
         "from cycle_detector import has_cycle\nclass Test(unittest.TestCase):\n def test_cycle(self): self.assertTrue(has_cycle({'a': ['b'], 'b': ['a']}))"),
        ("ST-073", "Dijkstra Shortest Path", "dijkstra.py", "shortest_path(graph, start, end) -> (distance, path).",
         "from dijkstra import shortest_path\nclass Test(unittest.TestCase):\n def test_dijk(self): d, p = shortest_path({'a': [('b', 1)]}, 'a', 'b'); self.assertEqual(d, 1)"),
        ("ST-074", "BFS and DFS Traversal", "graph_traversal.py", "bfs_order(graph, start) and dfs_order(graph, start).",
         "from graph_traversal import bfs_order, dfs_order\nclass Test(unittest.TestCase):\n def test_trav(self): self.assertEqual(bfs_order({'a': ['b'], 'b': []}, 'a'), ['a', 'b'])"),
        ("ST-075", "Binary Search Tree", "bst.py", "BST with insert, contains, in_order_traversal.",
         "from bst import BST\nclass Test(unittest.TestCase):\n def test_bst(self): b = BST(); b.insert(5); b.insert(2); self.assertEqual(b.in_order(), [2, 5])"),
        ("ST-076", "Lowest Common Ancestor", "tree_lca.py", "find_lca(root, val1, val2).",
         "from tree_lca import find_lca\nclass Test(unittest.TestCase):\n def test_lca(self): self.assertTrue(callable(find_lca))"),
        ("ST-077", "Connected Components", "connected_components.py", "find_components(graph) -> list[set].",
         "from connected_components import find_components\nclass Test(unittest.TestCase):\n def test_cc(self): self.assertEqual(len(find_components({'a': ['b'], 'b': ['a'], 'c': []})), 2)"),
        ("ST-078", "A-Star Grid Pathfinder", "astar.py", "astar_grid(grid, start, goal) -> list[(x,y)].",
         "from astar import astar_grid\nclass Test(unittest.TestCase):\n def test_astar(self): self.assertTrue(callable(astar_grid))"),
        ("ST-079", "Binary Min/Max Heap", "binary_heap.py", "MinHeap with push, pop_min, peek_min.",
         "from binary_heap import MinHeap\nclass Test(unittest.TestCase):\n def test_heap(self): h = MinHeap(); h.push(10); h.push(3); self.assertEqual(h.pop_min(), 3)"),
        ("ST-080", "Math Expression Evaluator", "expr_tree.py", "eval_expr(expr_str) evaluating +, -, *, / with precedence.",
         "from expr_tree import eval_expr\nclass Test(unittest.TestCase):\n def test_expr(self): self.assertEqual(eval_expr('3 + 4 * 2'), 11)"),
    ]),
    ("Functional & Streams", [
        ("ST-081", "TTL Memoization Decorator", "memoize.py", "@memoize(ttl_seconds=None) caching return values.",
         "from memoize import memoize\nclass Test(unittest.TestCase):\n def test_mem(self): calls=0\n @memoize()\n def f(x): nonlocal calls; calls+=1; return x*2\n self.assertEqual(f(3), 6); f(3); self.assertEqual(calls, 1)"),
        ("ST-082", "Retry Decorator with Backoff", "retry_decorator.py", "@retry(max_attempts=3, backoff=0.01, exceptions=(ValueError,)).",
         "from retry_decorator import retry\nclass Test(unittest.TestCase):\n def test_ret(self): attempts=0\n @retry(max_attempts=2)\n def f(): nonlocal attempts; attempts+=1; return True\n self.assertTrue(f())"),
        ("ST-083", "Pipe and Compose Runner", "pipe_compose.py", "pipe(val, *fns) and compose(*fns).",
         "from pipe_compose import pipe, compose\nclass Test(unittest.TestCase):\n def test_pipe(self): self.assertEqual(pipe(2, lambda x: x+1, lambda x: x*3), 9)"),
        ("ST-084", "Chunked Iterator Generator", "batch_iter.py", "chunk_iterable(iterable, chunk_size).",
         "from batch_iter import chunk_iterable\nclass Test(unittest.TestCase):\n def test_chunk(self): self.assertEqual(list(chunk_iterable([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])"),
        ("ST-085", "Deep Flatten Iterator", "deep_flatten.py", "deep_flatten(nested_iterable) -> generator.",
         "from deep_flatten import deep_flatten\nclass Test(unittest.TestCase):\n def test_flat(self): self.assertEqual(list(deep_flatten([[1, [2]], 3])), [1, 2, 3])"),
        ("ST-086", "Group By & Aggregate", "group_by.py", "group_by(items, key_fn, aggregate_fn=None).",
         "from group_by import group_by\nclass Test(unittest.TestCase):\n def test_grp(self): self.assertEqual(group_by(['a', 'bb', 'c'], len)[1], ['a', 'c'])"),
        ("ST-087", "Debounce and Throttle State", "debounce_state.py", "Debouncer and Throttler state machines.",
         "from debounce_state import Debouncer\nclass Test(unittest.TestCase):\n def test_deb(self): d = Debouncer(0.1); self.assertTrue(callable(d.call))"),
        ("ST-088", "Lazy Evaluation Stream", "lazy_stream.py", "LazyStream(generator_fn) with map, filter, take(n).",
         "from lazy_stream import LazyStream\nclass Test(unittest.TestCase):\n def test_lz(self): s = LazyStream(range(100)).filter(lambda x: x%2==0).take(3); self.assertEqual(list(s), [0, 2, 4])"),
        ("ST-089", "Currying Function Helper", "curry.py", "curry(fn) enabling f(1)(2)(3) or f(1, 2)(3).",
         "from curry import curry\nclass Test(unittest.TestCase):\n def test_curry(self): @curry\n def add(a, b): return a + b\n self.assertEqual(add(1)(2), 3)"),
        ("ST-090", "Pub-Sub Event Emitter", "event_emitter.py", "EventEmitter with on, off, emit, once.",
         "from event_emitter import EventEmitter\nclass Test(unittest.TestCase):\n def test_ee(self): ee = EventEmitter(); called=0\n ee.on('e', lambda: None); ee.emit('e')"),
    ]),
    ("State Machines & Flows", [
        ("ST-091", "Finite State Machine", "fsm.py", "FSM(initial_state, transitions) with trigger(event).",
         "from fsm import FSM\nclass Test(unittest.TestCase):\n def test_fsm(self): f = FSM('idle', {'idle': {'start': 'running'}}); f.trigger('start'); self.assertEqual(f.state, 'running')"),
        ("ST-092", "Order Checkout Flow", "checkout_flow.py", "OrderWorkflow with cart, shipping, payment, completed.",
         "from checkout_flow import OrderWorkflow\nclass Test(unittest.TestCase):\n def test_ord(self): o = OrderWorkflow(); self.assertEqual(o.state, 'cart')"),
        ("ST-093", "Linear Step Rollback Runner", "workflow_runner.py", "run_workflow(steps) with compensate() on failure.",
         "from workflow_runner import run_workflow\nclass Test(unittest.TestCase):\n def test_wf(self): self.assertTrue(callable(run_workflow))"),
        ("ST-094", "Command Undo/Redo Stack", "undo_stack.py", "UndoManager with execute, undo, redo.",
         "from undo_stack import UndoManager\nclass Test(unittest.TestCase):\n def test_undo(self): u = UndoManager(); self.assertTrue(callable(u.execute))"),
        ("ST-095", "Circuit Breaker Tracker", "circuit_breaker.py", "CircuitBreaker with fail_threshold, recovery_timeout.",
         "from circuit_breaker import CircuitBreaker\nclass Test(unittest.TestCase):\n def test_cb(self): cb = CircuitBreaker(fail_threshold=2); self.assertEqual(cb.state, 'CLOSED')"),
        ("ST-096", "Job State Queue", "job_queue.py", "JobQueue with enqueue, start_job, finish_job, fail_job.",
         "from job_queue import JobQueue\nclass Test(unittest.TestCase):\n def test_jq(self): jq = JobQueue(); j = jq.enqueue('t1'); self.assertEqual(j['state'], 'QUEUED')"),
        ("ST-097", "Traffic Light Controller", "traffic_fsm.py", "TrafficLight with cycle(), sensor_override(color).",
         "from traffic_fsm import TrafficLight\nclass Test(unittest.TestCase):\n def test_tl(self): tl = TrafficLight(); self.assertEqual(tl.state, 'RED'); tl.cycle(); self.assertEqual(tl.state, 'GREEN')"),
        ("ST-098", "State Snapshot Tracker", "state_snapshot.py", "SnapshotTracker with save(state), diff(v1, v2).",
         "from state_snapshot import SnapshotTracker\nclass Test(unittest.TestCase):\n def test_ss(self): st = SnapshotTracker(); v1 = st.save({'a': 1}); self.assertEqual(v1, 1)"),
        ("ST-099", "Subscription Lifecycle FSM", "subscription_fsm.py", "Subscription(status: trial, active, past_due, canceled).",
         "from subscription_fsm import Subscription\nclass Test(unittest.TestCase):\n def test_sub(self): s = Subscription(); self.assertEqual(s.status, 'trial')"),
        ("ST-100", "Rule Engine Tree Evaluator", "rule_engine.py", "evaluate_rule(rule_dict, context) evaluating AND/OR conditions.",
         "from rule_engine import evaluate_rule\nclass Test(unittest.TestCase):\n def test_rule(self): self.assertTrue(evaluate_rule({'op': 'eq', 'field': 'age', 'val': 21}, {'age': 21}))"),
    ])
]

for cat_name, items in categories:
    for t_id, title, mod, desc, test_code_body in items:
        test_name = f"test_{mod}"
        unit_test_code = f"""import unittest
{test_code_body}
if __name__ == '__main__': unittest.main()"""
        add_task(
            t_id, cat_name, title, mod,
            f"Create {mod} implementing {title}. {desc}",
            unit_test_code
        )

out_path = Path("docs/trials/stress-100-tasks/tasks.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(TASKS, f, indent=2)

print(f"Successfully generated {len(TASKS)} tasks in {out_path}")
