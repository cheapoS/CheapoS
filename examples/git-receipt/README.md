# GitReceipt

GitReceipt is a zero-cost cryptographic contribution proof generator. It allows contributors to generate verifiable proofs of their work in a Git repository without requiring a central authority.

## Overview

GitReceipt inspects the Git commit history to identify contributions by a specific author. It then computes a deterministic SHA-256 hash (the "receipt") based on the contribution's state, creating a verifiable claim of work.

## Features

- **Proof Generation**: Generates JSON receipts containing the commit hashes, author identity, and a cryptographic summary.
- **Verification**: Includes a CLI command to verify a receipt against the current state of the repository.
- **Badges**: Generates Markdown-compatible SVG badges for showcasing contribution proofs.
- **Zero-Cost**: Requires no external infrastructure other than the Git repository itself.

## Usage

### Generating a Receipt
To generate a receipt for a specific author:
```bash
python examples/git-receipt/receipt.py generate --author "Your Name"
```
This will create a `receipt.json` file.

### Verifying a Receipt
To verify a `receipt.json` file against the current repository:
```bash
python examples/git-receipt/receipt.py verify --file receipt.json
```

### Generating Badges
To generate an SVG badge from a receipt:
```bash
python examples/git-receipt/receipt.py badge --file receipt.json
```

## How it Works

### Cryptographic Computation
The receipt is computed as follows:
1. **Commit Discovery**: The tool finds all commits authored by the specified identity.
2. **Canonical Ordering**: Commit hashes are sorted lexicographically to ensure determinism.
3. **Hashing**: The sorted list of commit hashes, combined with the author's identity, is hashed using SHA-256.
4. **Receipt Structure**: The resulting hash, the list of commits, and a timestamp are stored in a JSON object.

### Verification Process
Verification re-runs the discovery and hashing process on the current repository state. If the computed hash matches the hash in the receipt, the proof is considered valid.

## Testing

The project includes deterministic unit tests to ensure correctness.
```bash
python3 -m unittest examples/git-receipt/test_receipt.py
```
