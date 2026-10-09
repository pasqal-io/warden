import importlib.metadata

try:
    __version__ = importlib.metadata.version("warden")
except importlib.metadata.PackageNotFoundError:
    # Failsafe if Warden was upgraded maunally without re-running `make install`.
    __version__ = ""
