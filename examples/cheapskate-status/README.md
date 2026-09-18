# CheapskateStatus

CheapskateStatus is a zero-cost serverless micro-status page generator that monitors endpoint latency, HTTP status, and SSL certificate expiry.

## Features

- **CLI-based checking**: Probes endpoints from a configuration file.
- **Badge generation**: Produces SVG status badges.
- **Static page generation**: Produces a responsive HTML status page.
- **Serverless-ready**: Output is self-contained JSON/HTML, deployable to GitHub Pages, Cloudflare Pages, etc.

## Installation

CheapskateStatus requires Python 3.9+ and uses only the Python standard library. No additional dependencies are required.

## Usage

### CLI Reference

The `status.py` script provides the following subcommands:

- `probe <config>`: Probes configured endpoints and outputs telemetry JSON to stdout.
- `badge <results>`: Generates an SVG badge based on the probes results JSON.
- `page <results>`: Generates a static HTML status page based on the probes results JSON.

```bash
# Probe endpoints
python3 examples/cheapskate-status/status.py probe examples/cheapskate-status/endpoints.json > results.json

# Generate badge
python3 examples/cheapskate-status/status.py badge results.json > status.svg

# Generate status page
python3 examples/cheapskate-status/status.py page results.json > index.html
```

## Configuration

`endpoints.json` is a JSON file containing a top-level `endpoints` array:

```json
{
  "endpoints": [
    {
      "name": "Google",
      "url": "https://google.com",
      "enabled": true,
      "weight": 1
    }
  ]
}
```

## Telemetry JSON Schema

The `probe` command outputs a JSON list of objects. Each object contains:

- `url`: The endpoint URL probed.
- `name`: Human-readable name of the endpoint.
- `ok`: Boolean indicating if the probe succeeded.
- `status`: HTTP status code (if ok is true) or error message.
- `latency`: Response latency in seconds (if ok is true).
- `ssl_expiry`: SSL certificate expiration date string (if ok is true).

## Deployment

Since the output is just static `index.html` and `status.svg` files, you can deploy the generated content to any static hosting provider like **GitHub Pages** or **Cloudflare Pages**.

## Tests

The example includes deterministic unit tests with mocked network/socket calls.

```bash
python3 -m unittest examples/cheapskate-status/test_status.py
```

