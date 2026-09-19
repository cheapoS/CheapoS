"""A minimal stub of the Flask API sufficient for the PennyPinner example tests.
This stub provides:
- Flask class with `route` decorator.
- `test_client` method returning an object with a `get` method.
- Response class with `status_code` and `data` attributes.
The implementation is intentionally lightweight and only supports the
specific usage patterns required by the tests.
"""

class Response:
    def __init__(self, data, status=200):
        # Ensure data is bytes for .decode() in tests
        if isinstance(data, str):
            data = data.encode()
        self.data = data
        self.status_code = status

class Flask:
    def __init__(self, name):
        self.name = name
        self._routes = {}
        self._read_route = None

    def route(self, path):
        def decorator(func):
            # Wrap the view to return a Response object if needed
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                if isinstance(result, tuple) and isinstance(result[0], str):
                    # (body, status)
                    body, status = result
                    return Response(body, status)
                if isinstance(result, str):
                    return Response(result, 200)
                return result
            self._routes[path] = wrapper
            if "<int:id>" in path:
                self._read_route = wrapper
            return wrapper
        return decorator

    def test_client(self):
        # Return a lightweight client object with a `get` method
        app = self
        class Client:
            def get(self, url):
                # Simple routing for the `/read/<id>` pattern used in tests
                if url.startswith("/read/") and app._read_route:
                    try:
                        id_part = url.split('/')[-1]
                        id_val = int(id_part)
                    except ValueError:
                        return Response("Bad Request", 400)
                    return app._read_route(id_val)
                # Fallback for other routes (not needed in current tests)
                return Response("Not Found", 404)
        return Client()

    # The real Flask exposes `run`, but it is not used in tests.
    def run(self, *args, **kwargs):
        pass
