import subprocess
import hashlib
import json
import argparse
import sys
from datetime import datetime

def get_commits(author):
    """Returns a sorted list of commit hashes for a given author."""
    try:
        # Get all commit hashes for the author
        result = subprocess.run(
            ["git", "log", "--author", author, "--format=%H"],
            capture_output=True, text=True, check=True
        )
        commits = result.stdout.strip().split("\n")
        return sorted([c for c in commits if c])
    except subprocess.CalledProcessError as e:
        print(f"Error fetching git logs: {e}", file=sys.stderr)
        return []

def compute_receipt_hash(author, commits):
    """Computes a deterministic SHA-256 hash for the contribution."""
    payload = f"{author}:{','.join(commits)}"
    return hashlib.sha256(payload.encode()).hexdigest()

def generate_receipt(author):
    commits = get_commits(author)
    if not commits:
        print(f"No commits found for author: {author}")
        return None
    
    receipt_hash = compute_receipt_hash(author, commits)
    receipt = {
        "author": author,
        "commits": commits,
        "receipt_hash": receipt_hash,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    with open("receipt.json", "w") as f:
        json.dump(receipt, f, indent=2)
    
    print(f"Receipt generated: receipt.json")
    print(f"Hash: {receipt_hash}")
    return receipt

def verify_receipt(receipt_file):
    try:
        with open(receipt_file, "r") as f:
            receipt = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading receipt file: {e}")
        return False

    author = receipt["author"]
    commits = receipt["commits"]
    stored_hash = receipt["receipt_hash"]
    
    current_commits = get_commits(author)
    if current_commits != commits:
        print("Verification failed: Commit history mismatch.")
        return False
    
    current_hash = compute_receipt_hash(author, current_commits)
    if current_hash != stored_hash:
        print("Verification failed: Hash mismatch.")
        return False
    
    print("Verification successful: Receipt is valid.")
    return True

def generate_badge(receipt_file):
    try:
        with open(receipt_file, "r") as f:
            receipt = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading receipt file: {e}")
        return

    author = receipt["author"]
    r_hash = receipt["receipt_hash"][:8]
    
    # Simplified SVG badge generator
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="30">
  <rect width="200" height="30" rx="15" fill="#4CAF50" />
  <text x="100" y="20" font-family="Arial" font-size="14" fill="white" text-anchor="middle">
    Verified: {author} ({r_hash})
  </text>
</svg>'''
    
    with open("badge.svg", "w") as f:
        f.write(svg)
    print("Badge generated: badge.svg")

def main():
    parser = argparse.ArgumentParser(description="GitReceipt - Cryptographic Contribution Proofs")
    subparsers = parser.add_subparsers(dest="command")

    gen_parser = subparsers.add_parser("generate")
    gen_parser.add_argument("--author", required=True, help="Author name or email")

    ver_parser = subparsers.add_parser("verify")
    ver_parser.add_argument("--file", required=True, help="Path to receipt.json")

    badge_parser = subparsers.add_parser("badge")
    badge_parser.add_argument("--file", required=True, help="Path to receipt.json")

    args = parser.parse_args()

    if args.command == "generate":
        generate_receipt(args.author)
    elif args.command == "verify":
        verify_receipt(args.file)
    elif args.command == "badge":
        generate_badge(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
