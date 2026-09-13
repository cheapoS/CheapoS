import unittest
from cheapos.titles import automatic_title


class TitleTests(unittest.TestCase):
    def test_first_substantive_request_is_stable(self):
        self.assertEqual(automatic_title({'requests':['hi', 'Create a CSV converter with tests', 'Change it']}), 'Create a CSV converter with tests')
        self.assertEqual(automatic_title({'requests':['Why?']}), 'Why?')
        self.assertEqual(automatic_title({'requests':['Hello!', 'hi gemma']}), 'New chat')

    def test_normalization_and_safe_plain_text(self):
        for value, expected in [('\n  Fix   this\nThen test', 'Fix this'), ('Fix it. Then test.', 'Fix it.'), ('🌱 <b>"hello"</b>', '🌱 <b>"hello"</b>')]:
            self.assertEqual(automatic_title({'prompt':value}), expected)
        self.assertLessEqual(len(automatic_title({'prompt':'long words '*30})), 72)
        self.assertEqual(automatic_title({'prompt':''}), 'New chat')
