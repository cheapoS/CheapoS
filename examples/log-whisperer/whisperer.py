import sys
import argparse
import re
import json
from collections import Counter
import math

# Tokenization patterns
PATTERNS = [
    (r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '<IP>'),  # IPv4
    (r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '<UUID>'), # UUID
    (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '<TIMESTAMP>'), # ISO-8601
    (r'\d+', '<NUM>'), # Numbers
]

def tokenize(line):
    for pattern, placeholder in PATTERNS:
        line = re.sub(pattern, placeholder, line)
    return line.strip()

def parse_log_line(line):
    # Simplistic parsing based on expectations
    if line.startswith('{'):
        try:
            data = json.loads(line)
            return data.get('message', line)
        except json.JSONDecodeError:
            pass
    return line

def process_file(path, action):
    with open(path, 'r') as f:
        lines = [parse_log_line(line.strip()) for line in f]
    
    templates = [tokenize(line) for line in lines]
    
    if action == 'parse':
        for t in templates:
            print(t)
    elif action == 'cluster':
        counts = Counter(templates)
        for t, count in counts.most_common():
            print(f"{count}: {t}")
    elif action == 'detect':
        counts = Counter(templates)
        total = len(templates)
        if total == 0: return
        
        freqs = [c for c in counts.values()]
        mean = sum(freqs) / len(freqs)
        stdev = math.sqrt(sum((x - mean) ** 2 for x in freqs) / len(freqs))
        
        threshold = 2.0
        for t, count in counts.items():
            z_score = (count - mean) / stdev if stdev > 0 else 0
            if abs(z_score) > threshold:
                print(f"ANOMALY ({z_score:.2f} sigma): {count} occurrences: {t}")

def main():
    parser = argparse.ArgumentParser(description="LogWhisperer: Simple log clustering")
    parser.add_argument('action', choices=['parse', 'cluster', 'detect'])
    parser.add_argument('file', help="Path to log file")
    args = parser.parse_args()
    
    process_file(args.file, args.action)

if __name__ == '__main__':
    main()
