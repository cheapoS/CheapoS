import argparse
import json
import subprocess
import sys
import hashlib

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

def main():
    parser = argparse.ArgumentParser(description="GitReceipt Verification CLI")
    parser.add_argument("--file", required=True, help="Path to receipt.json")
    
    args = parser.parse_args()
    
    verify_receipt(args.file)

if __name__ == "__main__":
    main()
