import sys, os, unittest, tempfile, shutil, csv
from datetime import datetime, timedelta

# Ensure the crm module in this directory is importable
sys.path.insert(0, os.path.dirname(__file__))
from crm import (
    parse_frontmatter,
    render_contact_file,
    add_contact,
    load_contact,
    list_contacts,
    log_interaction,
    load_interactions,
    get_interactions_for,
    list_followups,
    generate_briefing,
)

class TestParseFrontmatter(unittest.TestCase):
    def test_no_frontmatter(self):
        text = "Just a body without frontmatter"
        fields, body = parse_frontmatter(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_basic_frontmatter(self):
        fm = "---\nname: Alice\nemail: alice@example.com\ntags: friend, colleague\nfollow_up: 2023-12-01\n---\nBody text"
        fields, body = parse_frontmatter(fm)
        expected = {
            'name': 'Alice',
            'email': 'alice@example.com',
            'tags': 'friend, colleague',
            'follow_up': '2023-12-01',
        }
        self.assertEqual(fields, expected)
        self.assertEqual(body, "Body text")

    def test_empty_follow_up(self):
        fm = "---\nname: Bob\nemail: bob@example.com\ntags: client\nfollow_up:\n---\nNotes"
        fields, _ = parse_frontmatter(fm)
        self.assertIn('follow_up', fields)
        self.assertEqual(fields['follow_up'], '')

    def test_body_preserved(self):
        fm = "---\nname: Carol\n---\n   Indented body line   \nSecond line"
        _, body = parse_frontmatter(fm)
        self.assertEqual(body, "   Indented body line   \nSecond line")

class TestRenderContact(unittest.TestCase):
    def test_roundtrip(self):
        fields = {'name': 'Dave', 'email': 'dave@example.com', 'tags': 'partner', 'follow_up': '2024-01-01'}
        body = "Meeting notes"
        rendered = render_contact_file(fields, body)
        parsed_fields, parsed_body = parse_frontmatter(rendered)
        self.assertEqual(parsed_fields, fields)
        self.assertEqual(parsed_body, body)

class TestContactIO(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.contacts_dir = os.path.join(self.tempdir.name, 'contacts')
        os.makedirs(self.contacts_dir, exist_ok=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_add_and_load(self):
        slug = add_contact(self.contacts_dir, 'Eve Adams', 'eve@example.com', 'investor', '2024-02-20', 'Met at summit')
        self.assertEqual(slug, 'eve-adams')
        contact = load_contact(self.contacts_dir, slug)
        self.assertEqual(contact['name'], 'Eve Adams')
        self.assertEqual(contact['email'], 'eve@example.com')
        self.assertEqual(contact['tags'], 'investor')
        self.assertEqual(contact['follow_up'], '2024-02-20')
        self.assertEqual(contact['notes'], 'Met at summit')
        self.assertEqual(contact['slug'], slug)

    def test_slug_derivation(self):
        slug = add_contact(self.contacts_dir, 'Jane Doe', 'jane@example.com', '', '', '')
        self.assertEqual(slug, 'jane-doe')

    def test_list_contacts_sorted(self):
        add_contact(self.contacts_dir, 'Charlie', '', '', '', '')
        add_contact(self.contacts_dir, 'Alice', '', '', '', '')
        add_contact(self.contacts_dir, 'Bob', '', '', '', '')
        contacts = list_contacts(self.contacts_dir)
        names = [c['name'] for c in contacts]
        self.assertEqual(names, ['Alice', 'Bob', 'Charlie'])

    def test_load_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_contact(self.contacts_dir, 'nonexistent')

class TestInteractions(unittest.TestCase):
    def setUp(self):
        fd, self.csv_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        os.remove(self.csv_path)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def test_create_with_header(self):
        log_interaction(self.csv_path, 'slug1', 'First', 'tag1')
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            header = f.readline().strip()
        self.assertEqual(header, 'slug,timestamp,summary,tags')

    def test_append_rows(self):
        log_interaction(self.csv_path, 's1', 'First', 't1')
        log_interaction(self.csv_path, 's2', 'Second', 't2')
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['slug'], 's1')
        self.assertEqual(rows[1]['slug'], 's2')
    def test_load_empty(self):
        interactions = load_interactions(self.csv_path)
        self.assertEqual(interactions, [])

    def test_filter_by_slug(self):
        log_interaction(self.csv_path, 'a', 'A1', 'x')
        log_interaction(self.csv_path, 'b', 'B1', 'y')
        log_interaction(self.csv_path, 'a', 'A2', 'z')
        ints = get_interactions_for(self.csv_path, 'a')
        self.assertEqual(len(ints), 2)
        self.assertEqual([i['summary'] for i in ints], ['A1', 'A2'])

    def test_explicit_timestamp(self):
        ts = '2024-01-01T09:00:00'
        log_interaction(self.csv_path, 'slugX', 'Exact time', 'tagX', timestamp=ts)
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]['timestamp'], ts)

class TestFollowups(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.contacts_dir = os.path.join(self.tempdir.name, 'contacts')
        os.makedirs(self.contacts_dir, exist_ok=True)
        self.now = datetime.utcnow()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_within_window(self):
        past = (self.now - timedelta(days=5)).strftime('%Y-%m-%d')
        future = (self.now + timedelta(days=5)).strftime('%Y-%m-%d')
        add_contact(self.contacts_dir, 'Past', 'p@example.com', '', past, '')
        add_contact(self.contacts_dir, 'Future', 'f@example.com', '', future, '')
        followups = list_followups(self.contacts_dir, within_days=30, now=self.now)
        slugs = {c['slug'] for c in followups}
        self.assertIn('past', slugs)
        self.assertIn('future', slugs)

    def test_outside_window(self):
        far = (self.now + timedelta(days=60)).strftime('%Y-%m-%d')
        add_contact(self.contacts_dir, 'Far', 'far@example.com', '', far, '')
        followups = list_followups(self.contacts_dir, within_days=30, now=self.now)
        self.assertEqual(followups, [])

    def test_empty_follow_up_excluded(self):
        add_contact(self.contacts_dir, 'NoFU', 'n@example.com', '', '', '')
        followups = list_followups(self.contacts_dir, within_days=30, now=self.now)
        self.assertEqual(followups, [])

    def test_sorted_by_date(self):
        d1 = (self.now + timedelta(days=2)).strftime('%Y-%m-%d')
        d2 = (self.now + timedelta(days=1)).strftime('%Y-%m-%d')
        add_contact(self.contacts_dir, 'Later', 'l@example.com', '', d1, '')
        add_contact(self.contacts_dir, 'Sooner', 's@example.com', '', d2, '')
        followups = list_followups(self.contacts_dir, within_days=30, now=self.now)
        dates = [c['follow_up'] for c in followups]
        self.assertEqual(dates, sorted(dates))

class TestBriefing(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.contacts_dir = os.path.join(self.tempdir.name, 'contacts')
        os.makedirs(self.contacts_dir, exist_ok=True)
        fd, self.csv_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        os.remove(self.csv_path)

    def tearDown(self):
        self.tempdir.cleanup()
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)
    def test_briefing_contains_name(self):
        slug = add_contact(self.contacts_dir, 'Grace', 'grace@example.com', 'client', '', 'Key client')
        brief = generate_briefing(self.contacts_dir, self.csv_path, slug)
        self.assertIn('Grace', brief)

    def test_briefing_contains_email(self):
        slug = add_contact(self.contacts_dir, 'Grace', 'grace@example.com', 'client', '', 'Key client')
        brief = generate_briefing(self.contacts_dir, self.csv_path, slug)
        self.assertIn('grace@example.com', brief)

    def test_briefing_contains_interaction_summary(self):
        slug = add_contact(self.contacts_dir, 'Heidi', 'heidi@example.com', '', '', '')
        log_interaction(self.csv_path, slug, 'Call intro', 'call')
        log_interaction(self.csv_path, slug, 'Sent quote', 'email')
        brief = generate_briefing(self.contacts_dir, self.csv_path, slug)
        self.assertIn('Call intro', brief)
        self.assertIn('Sent quote', brief)

    def test_briefing_no_interactions(self):
        slug = add_contact(self.contacts_dir, 'Ivan', 'ivan@example.com', '', '', '')
        brief = generate_briefing(self.contacts_dir, self.csv_path, slug)
        self.assertIn('No interactions recorded.', brief)

if __name__ == '__main__':
    unittest.main()
