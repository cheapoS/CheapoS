# LogWhisperer

LogWhisperer is a lightweight, zero-dependency server log clustering and anomaly isolation CLI in pure Python stdlib. It helps to extract log event templates, cluster repetitive lines, and detect anomaly spikes.

## Features
- Scans server logs (Common Log Format, Combined Log Format, and JSON lines).
- Strips variable tokens (IPs, UUIDs, timestamps, numbers) to extract log event templates.
- Clusters repetitive lines/stack traces.
- Detects anomaly spikes based on frequency deviation.

## Installation
This example requires only Python 3.9+ and has zero external dependencies.

## Usage

### CLI
```bash
- `parse`: Tokenizes and prints each log line.
- `cluster`: Clusters templates and prints frequency of each.
- `detect`: Detects anomalies based on frequency deviation (Z-score).

## Testing
Run unit tests with:
```bash
python3 -m unittest examples/log-whisperer/test_whisperer.py
```
