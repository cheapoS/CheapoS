import os
import csv
import re
import argparse
from datetime import datetime, timedelta
from pathlib import Path

def parse_frontmatter(text):
    """
    Split on first pair of '---' lines.
    Return (fields_dict, stripped_body).
    """
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip() == '---':
        try:
            end_idx = lines.index('---', 1)
            fm_text = "\n".join(lines[1:end_idx])
            body = "\n".join(lines[end_idx + 1:])
            fields = {}
            for line in fm_text.splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    fields[k.strip()] = v.strip()
            return fields, body
        except ValueError:
            pass
    return {}, text

def render_contact_file(fields, body):
    """
    Render frontmatter and body.
    """
    fm_lines = [f"{k}: {v}" for k, v in fields.items()]
    return "---\n" + "\n".join(fm_lines) + "\n---\n" + body

def load_contact(contacts_dir, slug):
    """
    Load contact from <dir>/<slug>.md.
    """
    path = Path(contacts_dir) / f"{slug}.md"
    if not path.exists():
        raise FileNotFoundError(f"Contact {slug} not found")
    
    text = path.read_text(encoding='utf-8')
    fields, notes = parse_frontmatter(text)
    data = fields.copy()
    data['slug'] = slug
    data['notes'] = notes
    return data

def save_contact(contacts_dir, slug, fields, notes):
    """
    Save contact to <dir>/<slug>.md.
    """
    os.makedirs(contacts_dir, exist_ok=True)
    path = Path(contacts_dir) / f"{slug}.md"
    text = render_contact_file(fields, notes)
    path.write_text(text, encoding='utf-8')

def list_contacts(contacts_dir):
    """
    List all .md files in contacts_dir sorted by name.
    """
    os.makedirs(contacts_dir, exist_ok=True)
    files = sorted([f for f in os.listdir(contacts_dir) if f.endswith('.md')])
    results = []
    for f in files:
        slug = f[:-3]
        results.append(load_contact(contacts_dir, slug))
    return results

def add_contact(contacts_dir, name, email, tags, follow_up, notes):
    """
    Derive slug, save contact, and return slug.
    """
    slug = re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))
    fields = {
        'name': name,
        'email': email,
        'tags': tags,
        'follow_up': follow_up,
    }
    save_contact(contacts_dir, slug, fields, notes)
    return slug

def log_interaction(csv_path, slug, summary, tags, timestamp=None):
    """
    Append interaction to CSV.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['slug', 'timestamp', 'summary', 'tags'])
        writer.writerow([slug, timestamp, summary, tags])

def load_interactions(csv_path):
    """
    Load all interactions from CSV.
    """
    if not os.path.exists(csv_path):
        return []
    
    interactions = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            interactions.append(row)
    return interactions

def get_interactions_for(csv_path, slug):
    """
    Filter interactions by slug and sort ascending.
    """
    all_ints = load_interactions(csv_path)
    filtered = [i for i in all_ints if i['slug'] == slug]
    return sorted(filtered, key=lambda x: x['timestamp'])

def list_followups(contacts_dir, within_days=30, now=None):
    """
    List contacts with follow_up within window.
    """
    contacts = list_contacts(contacts_dir)
    followups = []
    if now is None:
        now = datetime.utcnow()
    for c in contacts:
        fu_str = c.get('follow_up', '').strip()
        if not fu_str:
            continue
        try:
            fu_date = datetime.strptime(fu_str, '%Y-%m-%d')
            if now - timedelta(days=within_days) <= fu_date <= now + timedelta(days=within_days):
                followups.append(c)
        except ValueError:
            continue
    return sorted(followups, key=lambda x: x['follow_up'])

def generate_briefing(contacts_dir, csv_path, slug):
    """
    Generate meeting briefing sheet.
    """
    contact = load_contact(contacts_dir, slug)
    ints = get_interactions_for(csv_path, slug)
    last_5 = sorted(ints, key=lambda x: x['timestamp'], reverse=True)[:5]
    
    lines = [
        f"BRIEFING: {contact.get('name', slug)}",
        f"Email: {contact.get('email', 'N/A')}",
        f"Tags: {contact.get('tags', 'N/A')}",
        f"Follow-up: {contact.get('follow_up', 'N/A')}",
        f"\nNOTES:\n{contact.get('notes', '')}",
        f"\nRECENT INTERACTIONS:"
    ]
    if not last_5:
        lines.append("No interactions recorded.")
    for i in last_5:
        lines.append(f"- {i['timestamp']} [{i['tags']}]: {i['summary']}")
    
    return "\n".join(lines)

def main():
    base_dir = os.path.dirname(__file__)
    contacts_dir = os.path.join(base_dir, 'contacts')
    csv_path = os.path.join(base_dir, 'interactions.csv')
    
    parser = argparse.ArgumentParser(description="MicroCRM CLI")
    subparsers = parser.add_subparsers(dest='command')
    
    # add-contact
    p_add = subparsers.add_parser('add-contact')
    p_add.add_argument('--name', required=True)
    p_add.add_argument('--email', required=True)
    p_add.add_argument('--tags', default='')
    p_add.add_argument('--follow-up', default='')
    p_add.add_argument('--notes', default='')
    
    # log
    p_log = subparsers.add_parser('log')
    p_log.add_argument('--slug', required=True)
    p_log.add_argument('--summary', required=True)
    p_log.add_argument('--tags', default='')
    
    # followups
    p_fu = subparsers.add_parser('followups')
    p_fu.add_argument('--days', type=int, default=30)
    
    # briefing
    p_br = subparsers.add_parser('briefing')
    p_br.add_argument('--slug', required=True)
    
    # list
    p_list = subparsers.add_parser('list')
    
    args = parser.parse_args()
    
    if args.command == 'add-contact':
        slug = add_contact(contacts_dir, args.name, args.email, args.tags, args.follow_up, args.notes)
        print(f"Added contact with slug: {slug}")
    elif args.command == 'log':
        log_interaction(csv_path, args.slug, args.summary, args.tags)
        print("Interaction logged.")
    elif args.command == 'followups':
        fus = list_followups(contacts_dir, args.days)
        for f in fus:
            print(f"{f['follow_up']} - {f['name']} ({f['slug']})")
    elif args.command == 'briefing':
        print(generate_briefing(contacts_dir, csv_path, args.slug))
    elif args.command == 'list':
        for c in list_contacts(contacts_dir):
            print(f"{c['slug']} - {c['name']}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
