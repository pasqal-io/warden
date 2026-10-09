import importlib.metadata

try:
    __version__ = importlib.metadata.version("warden")
except importlib.metadata.PackageNotFoundError:
    # Checkout upgraded without re-running `make install`.
    __version__ = ""
