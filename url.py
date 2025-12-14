import gzip
import html as _html
import re
import urllib.parse

from cache import get_cache_key, load_from_cache, store_in_cache
from connection import get_connection, close_connection

DEFAULT_LOCAL_FILE = "file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html"

def remove_html_comments(text: str) -> str:
  return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

def decode_html_entities(text: str) -> str:
  return _html.unescape(text)

def lex(body: str) -> str:
  body = remove_html_comments(body)
  return decode_html_entities(body)

class URL:
  def __init__(self, url: str):
    if url == "":
      url = DEFAULT_LOCAL_FILE

    self.original_url = url
    self.scheme, rest = url.split(":", 1)
    self.scheme = self.scheme.lower()
    assert self.scheme in ["http", "https", "file", "data", "view-source"]

    self.host = ""
    self.port = None
    self.path = ""
    self.data_body = ""
    self.mimetype = "text/plain"
    self.inner_url = None

    self.connection = "keep-alive"
    self.user_agent = "KAKAOPAY/25.9.0"
    self.accept_encoding = "gzip"

    if self.scheme == "view-source":
      self.inner_url = rest
      return

    if self.scheme == "file":
      p = rest[2:] 
      if not p.startswith("/"):
        p = "/" + p
      self.path = p
      return

    if self.scheme == "data":
      if "," in rest:
        metadata, data_part = rest.split(",", 1)
      else:
        metadata, data_part = "", rest
      self.mimetype = metadata if metadata else "text/plain"
      self.data_body = urllib.parse.unquote(data_part)
      return

    rest = rest[2:] 
    self.port = 80 if self.scheme == "http" else 443
    if "/" not in rest:
      rest += "/"
    hostpart, pathpart = rest.split("/", 1)
    self.path = "/" + pathpart

    if ":" in hostpart:
      hostpart, port = hostpart.split(":", 1)
      self.port = int(port)
    self.host = hostpart

  def _read_chunked_body(self, response) -> bytes:
    body = bytearray()
    while True:
      line = response.readline().decode("iso-8859-1")
      if not line:
        break

      line = line.strip()
      if line == "":
        continue

      size_str = line.split(";", 1)[0]
      try:
        chunk_size = int(size_str, 16)
      except ValueError:
        break

      if chunk_size == 0:
        while True:
          trailer = response.readline().decode("iso-8859-1")
          if trailer in ("\r\n", ""):
            break
        break

      chunk = response.read(chunk_size)
      if not chunk:
        break
      body.extend(chunk)

      _ = response.read(2)  
    return bytes(body)

  def request(self, redirect_count=0, max_redirects=10) -> str:
    if redirect_count > max_redirects:
      return f"[Redirect error] Exceeded {max_redirects} redirects"

    if self.scheme == "view-source":
      inner = URL(self.inner_url)
      return inner.request(redirect_count=redirect_count + 1, max_redirects=max_redirects)

    if self.scheme == "data":
      return self.data_body

    if self.scheme == "file":
      try:
        with open(self.path, "r", encoding="utf-8") as f:
          return f.read()
      except FileNotFoundError:
        return f"[File error] File not found: {self.path}"
      except OSError as e:
        return f"[File error] {e}"

    cache_key = get_cache_key(self.scheme, self.host, self.port, self.path)
    cached = load_from_cache(cache_key)
    if cached is not None:
      return cached

    key = None
    try:
      s, key = get_connection(self.scheme, self.host, self.port)

      req = f"GET {self.path} HTTP/1.1\r\n"
      req += f"Host: {self.host}\r\n"
      req += f"Connection: {self.connection}\r\n"
      req += f"User-Agent: {self.user_agent}\r\n"
      req += f"Accept-Encoding: {self.accept_encoding}\r\n"
      req += "\r\n"
      s.send(req.encode("utf-8"))

      response = s.makefile("rb")
      statusline = response.readline().decode("iso-8859-1")
      if not statusline:
        close_connection(key)
        return "[Network error] Empty status line"

      _version, status, _explanation = statusline.split(" ", 2)

      headers = {}
      while True:
        line = response.readline().decode("iso-8859-1")
        if line == "\r\n":
          break
        h, v = line.split(":", 1)
        headers[h.casefold()] = v.strip()

      if status.startswith("3"):
        location = headers.get("location")
        response.close()
        if key is not None:
          close_connection(key)

        if not location:
          return f"[HTTP redirect {status}] (no Location header)"

        if location.startswith("/"):
          location = f"{self.scheme}://{self.host}{location}"

        return URL(location).request(
          redirect_count=redirect_count + 1,
          max_redirects=max_redirects,
        )

      transfer_encoding = headers.get("transfer-encoding", "").lower()
      content_length = headers.get("content-length")
      connection_hdr = headers.get("connection", "").lower()

      if "chunked" in transfer_encoding:
        body_bytes = self._read_chunked_body(response)
      else:
        if content_length is not None:
          body_bytes = response.read(int(content_length))
        else:
          body_bytes = response.read()
          if key is not None:
            close_connection(key)

      response.close()
      if "close" in connection_hdr and key is not None:
        close_connection(key)

      content_encoding = headers.get("content-encoding", "").lower()
      if "gzip" in content_encoding:
        try:
          body_bytes = gzip.decompress(body_bytes)
        except OSError:
          pass

      body = body_bytes.decode("utf-8", errors="replace")
      store_in_cache(cache_key, headers, body)
      return body

    except OSError as e:
      if key is not None:
        close_connection(key)
      return f"[Network error] {e}"
