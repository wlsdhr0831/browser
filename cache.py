import time
from typing import Optional

# key: (scheme, host, port, path) -> {"expires_at": float 또는 None, "body": str}
_CACHE = {}

def get_cache_key(scheme: str, host: str, port: Optional[int], path: str):
  if scheme in ["http", "https"]:
    return (scheme, host, port, path)
  return None

def load_from_cache(cache_key):
  if cache_key is None:
    return None

  entry = _CACHE.get(cache_key)
  if entry is None:
    return None

  now = time.time()
  expires_at = entry["expires_at"]

  if expires_at is not None and expires_at >= now:
    return entry["body"]

  _CACHE.pop(cache_key, None)
  return None

def store_in_cache(cache_key, response_headers: dict, body: str):
  if cache_key is None:
    return

  cache_control = response_headers.get("cache-control", "")
  if not cache_control:
    return

  directives = [d.strip().lower() for d in cache_control.split(",")]

  if "no-store" in directives:
    return

  expires_at = None
  for d in directives:
    if d.startswith("max-age="):
      try:
        seconds = int(d.split("=", 1)[1])
        expires_at = time.time() + seconds
      except ValueError:
        pass
      break 

  if expires_at is not None:
    _CACHE[cache_key] = {
      "expires_at": expires_at,
      "body": body,
    }
