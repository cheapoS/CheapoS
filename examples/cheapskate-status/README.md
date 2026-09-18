# CheapskateStatus

CheapskateStatus is a zero-cost serverless micro-status page generator that monitors endpoint latency, HTTP status, and SSL certificate expiry.

## Features

- **CLI-based checking**: Uses `status.py` to probe endpoints.
- **Badge generation**: Produces SVG status badges.
- **Static page generation**: Produces a responsive HTML status page.

## Usage

```bash
# Probe endpoints
python3 examples/cheapskate-status/status.py probe examples/cheapskate-status/endpoints.json > results.json

# Generate badge
python3 examples/cheapskate-status/status.py badge results.json

# Generate status page
python3 examples/cheapskate-status/status.py page results.json > index.html
```

## Configuration

`endpoints.json` is a JSON file containing a list of endpoints:

```json
[
  {
    "url": "https://google.com",
    "name": "Google"
  }
]
```
