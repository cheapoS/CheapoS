"""Wrapper module to expose FeedCurator functionality at top-level examples package.
This allows tests that import 'curator' (after adding the 'examples' directory to sys.path)
to access the same implementation located in examples/feed-curator/curator.py.
"""

from pathlib import Path
import importlib.util

_impl_path = Path(__file__).parent / "feed-curator" / "curator.py"
_spec = importlib.util.spec_from_file_location("_feed_curator_impl", _impl_path)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# Export the symbols defined in the implementation module.
__all__ = [name for name in dir(_module) if not name.startswith("_")]
for name in __all__:
    globals()[name] = getattr(_module, name)