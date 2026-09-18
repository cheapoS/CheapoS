import unittest
import os
import shutil
import tempfile
from datetime import datetime, timedelta

# Import the module under test
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('crm', pathlib.Path(__file__).parent / 'crm.py')
crm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crm)

class TestMicroCRM(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for contacts and a temp csv file
        self.tempdir = tempfile.TemporaryDirectory()
        self.contacts_dir = os.path.join(self.tempdir.name, 'contacts')
        os.makedirs(self.contacts_dir, exist_ok=True)
        self.csv_path = os.path.join(self.tempdir.name, 'interactions.csv')

    def tearDown(self):
        self.tempdir.cleanup()

    def test_parse_frontmatter_no_frontmatter(self):
        text = "Just a body without frontmatter"
        fields, body = crm.parse_frontmatter(text)
        self.assertEqual(fields, {})
        self.assertEqual(body, text)

    def test_parse_and_render_roundtrip(self):
        fields = {'name': 'Alice', 'email': 'alice@example.com', 'tags': 'friend', 'follow_up': '2023-12-01'}
        body = "Some notes here"
        rendered = crm.render_contact_file(fields, body)
        parsed_fields, parsed_body = crm.parse_frontmatter(rendered)
        self.assertEqual(parsed_fields, fields)
        self.assertEqual(parsed_body, body)

    def test_add_and_load_contact(self):        
        slug = crm.add_contact(self.contacts_dir, 'Bob Smith', 'bob@example.com', 'colleague', '2024-01-15', 'Met at conference')
        self.assertEqual(slug, 'bob-smith')
        contact = crm.load_contact(self.contacts_dir, slug)
        self.assertEqual(contact['name'], 'Bob Smith')
        self.assertEqual(contact['email'], 'bob@example.com')
        self.assertEqual(contact['tags'], 'colleague')
        self.assertEqual(contact['follow_up'], '2024-01-15')
        self.assertEqual(contact['notes'], 'Met at conference')
        self.assertEqual(contact['slug'], slug)

    def test_log_and_load_interactions(self):
        slug = 'testslug'
        crm.log_interaction(self.csv_path, slug, 'First interaction', 'meeting')
        crm.log_interaction(self.csv_path, slug, 'Second interaction', 'call')
        interactions = crm.load_interactions(self.csv_path)
        self.assertEqual(len(interactions), 2)
        # Ensure headers are not present in dict rows
        self.assertTrue(all('slug' in i for i in interactions))
        self.assertEqual(interactions[0]['slug'], slug)
        self.assertEqual(interactions[0]['summary'], 'First interaction')
        self.assertEqual(interactions[1]['summary'], 'Second interaction')

    def test_get_interactions_for(self):
        slug_a = 'a'
        slug_b = 'b'
        crm.log_interaction(self.csv_path, slug_a, 'A1', 'tag')
        crm.log_interaction(self.csv_path, slug_b, 'B1', 'tag')
        crm.log_interaction(self.csv_path, slug_a, 'A2', 'tag')
        ints_a = crm.get_interactions_for(self.csv_path, slug_a)
        self.assertEqual(len(ints_a), 2)
        self.assertEqual([i['summary'] for i in ints_a], ['A1', 'A2'])

    def test_list_followups(self):
        # Create contacts with various follow_up dates
        now = datetime.utcnow()
        past = (now - timedelta(days=10)).strftime('%Y-%m-%d')
        future = (now + timedelta(days=5)).strftime('%Y-%m-%d')
        crm.add_contact(self.contacts_dir, 'Past Person', 'past@example.com', '', past, '')
        crm.add_contact(self.contacts_dir, 'Future Person', 'future@example.com', '', future, '')
        crm.add_contact(self.contacts_dir, 'No Follow', 'nofollow@example.com', '', '', '')
        # Use the now injection to make test deterministic
        followups = crm.list_followups(self.contacts_dir, within_days=30, now=now)
        self.assertEqual(len(followups), 2)
        slugs = {c['slug'] for c in followups}
        self.assertIn('past-person', slugs)
        self.assertIn('future-person', slugs)
        self.assertNotIn('no-follow', slugs)

    def test_generate_briefing(self):
        slug = crm.add_contact(self.contacts_dir, 'Charlie', 'charlie@example.com', 'client', '', 'Important client')
        # Log three interactions
        crm.log_interaction(self.csv_path, slug, 'Intro call', 'call')
        crm.log_interaction(self.csv_path, slug, 'Sent proposal', 'email')
        crm.log_interaction(self.csv_path, slug, 'Follow-up meeting', 'meeting')
        brief = crm.generate_briefing(self.contacts_dir, self.csv_path, slug)
        self.assertIn('Charlie', brief)
        self.assertIn('charlie@example.com', brief)
        self.assertIn('Important client', brief)
        # All three interactions should appear
        self.assertIn('Intro call', brief)
        self.assertIn('Sent proposal', brief)
        self.assertIn('Follow-up meeting', brief)

if __name__ == '__main__':
    unittest.main()
