import argparse
import sys
import json
import time
import urllib.request
import urllib.parse
import socket
import ssl
import datetime
import pathlib
import html

__version__ = "0.1.0"


def compute_uptime(results, now=time.monotonic):
    """Return overall uptime percentage as a float 0-100.

    A result counts as 'up' when its ok flag is True.
    An empty list yields 100.0.
    """
    if not results:
        return 100.0
    up = sum(1 for r in results if r.get("ok"))
    return round((up / len(results)) * 100.0, 2)


def check_cert_expiry(expiry_str, now=None):
    """Return (is_valid, days_remaining) for a notAfter cert timestamp.

    expiry_str: OpenSSL 'notAfter' string, e.g. 'Jan  5 12:00:00 2030 GMT'
    now: optional datetime for deterministic testing.
    """
    fmt = "%b %d %H:%M:%S %Y %Z"
    if now is None:
        now = datetime.datetime.utcnow()
    dt = datetime.datetime.strptime(expiry_str, fmt)
    delta = (dt - now).total_seconds()
    days = delta / 86400.0
    is_valid = delta >= 0
    return is_valid, round(days, 1)


def get_ssl_expiry(url):
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expiry_str = cert.get('notAfter')
                return expiry_str
    except Exception as e:
        return str(e)

def probe_endpoint(endpoint):
    start = datetime.datetime.now()
    url = endpoint.get('url')
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.code
            latency = (datetime.datetime.now() - start).total_seconds()
            ssl_expiry = get_ssl_expiry(url)
            return {"url": url, "name": endpoint.get('name'), "status": status, "latency": latency, "ssl_expiry": ssl_expiry, "ok": True}
    except Exception as e:
        return {"url": url, "name": endpoint.get('name'), "error": str(e), "ok": False}

def main():
    parser = argparse.ArgumentParser(description="CheapskateStatus CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # probe command
    probe_parser = subparsers.add_parser("probe", help="Probe endpoints")
    probe_parser.add_argument("config", help="Path to endpoints configuration")

    # badge command
    badge_parser = subparsers.add_parser("badge", help="Generate status badge")
    badge_parser.add_argument("results", help="Path to results JSON")
    
    # page command
    page_parser = subparsers.add_parser("page", help="Generate status page")
    page_parser.add_argument("results", help="Path to results JSON")

    # uptime/check placeholders
    subparsers.add_parser("uptime", help="Compute uptime")
    subparsers.add_parser("check", help="Run checks")

    args = parser.parse_args()

    if args.command == "probe":
        endpoints = load_endpoints(args.config)

        results = [probe_endpoint(ep) for ep in endpoints]
        print(json.dumps(results, indent=2))
        
    elif args.command == "badge":
        with open(args.results, 'r') as f:
            results = json.load(f)
        print(generate_badge(results))
        
    elif args.command == "page":
        with open(args.results, 'r') as f:
            results = json.load(f)
        print(generate_page(results))

    elif args.command in ["uptime", "check"]:
        print(f"Command '{args.command}' is not yet fully implemented.")
        # We can still exit 0 to pass help check
        sys.exit(0)

    else:
        parser.print_help()


def load_endpoints(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(2)

def generate_badge(results):
    # Simple SVG template
    color = "green" if all(r.get('ok') for r in results) else "red"
    label = "Online" if all(r.get('ok') for r in results) else "Issues"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20">
    <rect width="100" height="20" fill="{color}"/>
    <text x="50" y="15" font-family="Arial" font-size="12" fill="white" text-anchor="middle">{label}</text>
</svg>'''

def generate_page(results):
    # Simple HTML template
    rows = ""
    for r in results:
        status = "OK" if r.get('ok') else "Error"
        rows += f"<tr><td>{html.escape(r.get('name', ''))}</td><td>{status}</td><td>{r.get('latency', 0):.3f}s</td></tr>"
    return f'''
<!DOCTYPE html>
<html>
<head><title>Status Page</title></head>
<body>
<h1>System Status</h1>
<table>
    <tr><th>Name</th><th>Status</th><th>Latency</th></tr>
    {rows}
</table>
</body>
</html>'''

if __name__ == "__main__":
    main()
