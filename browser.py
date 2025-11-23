import sys
import urllib.parse
import html
import gzip 

from cache import get_cache_key, load_from_cache, store_in_cache
from connection import get_connection, close_connection

DEFAULT_LOCAL_FILE = "file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html"

class URL:
  def __init__(self, url):
    if url == "":
      url = DEFAULT_LOCAL_FILE

    self.original_url = url

    self.scheme, url = url.split(":", 1)
    assert self.scheme in ["http", "https", "file", "data", "view-source"]

    if self.scheme == "view-source":
      self.inner_url = url
      return
    
    if self.scheme == "file":
      url = url[2:]
      if url.startswith("/"):
        self.path = url
      else:
        self.path = "/" + url
      self.host = ""
      self.port = None
      return
    
    elif self.scheme == "data":
      if "," in url:
        metadata, data_part = url.split(",", 1)
      else:
        metadata, data_part = "", url

      self.mimetype = metadata if metadata else "text/plain"
      self.data_body = urllib.parse.unquote(data_part)
      self.host = ""
      self.port = None
      self.path = ""
      return

    if self.scheme == "http":
      url = url[2:]
      self.port = 80
    elif self.scheme == "https":
      url = url[2:]
      self.port = 443    

    if "/" not in url:
      url = url + "/"

    self.host, url = url.split("/", 1)
    self.path = "/" + url

    self.connection = "keep-alive"
    self.userAgent = "KAKAOPAY/25.9.0"
    self.acceptEncoding = "gzip"

    if ":" in self.host:
      self.host, port = self.host.split(":", 1)
      self.port = int(port)

  def _read_chunked_body(self, response):
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
  
  def request(self, redirect_count=0, max_redirects=10):
    print(redirect_count, max_redirects, self.original_url)

    if redirect_count > max_redirects:
      return f"[Redirect error] Exceeded {max_redirects} redirects"
    
    if self.scheme == "view-source":
      inner = URL(self.inner_url)
      return inner.request(
        redirect_count=redirect_count + 1,
        max_redirects=max_redirects,
      )

    if self.scheme == "data":
      return self.data_body

    if self.scheme == "file":
      try:
        with open(self.path, "r", encoding="utf8") as f:
          body = f.read()
        return body
      except FileNotFoundError:
        return f"[File error] File not found: {self.path}"
      except OSError as e:
        return f"[File error] {e}"

    cache_key = get_cache_key(self.scheme, self.host, self.port, self.path)
    cached_body = load_from_cache(cache_key)
    if cached_body is not None:
      return cached_body

    s = None
    key = None

    try:
      s, key = get_connection(self.scheme, self.host, self.port)

      request = "GET {} HTTP/1.1\r\n".format(self.path)
      request += "Host: {}\r\n".format(self.host)
      request += "Connection: {}\r\n".format(self.connection)
      request += "User-Agent: {}\r\n".format(self.userAgent)
      request += "Accept-Encoding: {}\r\n".format(self.acceptEncoding)
      request += "\r\n"

      s.send(request.encode("utf8"))

      response = s.makefile("rb")
      statusline = response.readline().decode("iso-8859-1")

      if not statusline:
        close_connection(key)
        return "[Network error] Empty status line"

      version, status, explanation = statusline.split(" ", 2)

      response_headers = {}
      while True:
        line = response.readline().decode("iso-8859-1")
        if line == "\r\n":
          break
        header, value = line.split(":", 1)
        response_headers[header.casefold()] = value.strip()

      if status.startswith("3"):
        location = response_headers.get("location")

        if not location:
          response.close()
          if key is not None:
            close_connection(key)
          return f"[HTTP redirect {status}] (no Location header)"
        
        if location.startswith("/"):
          redirect_url = f"{self.scheme}://{self.host}{location}"
        else:
          redirect_url = location

        response.close()

        if key is not None:
          close_connection(key)

        return URL(redirect_url).request(
            redirect_count=redirect_count + 1,
            max_redirects=max_redirects,
          )

      transfer_encoding = response_headers.get("transfer-encoding", "").lower()
      content_length = response_headers.get("content-length")
      connection_hdr = response_headers.get("connection", "").lower()

      if "chunked" in transfer_encoding:
        body_bytes = self._read_chunked_body(response)
      else:
        if content_length is not None:
          length = int(content_length)
          body_bytes = response.read(length)
        else:
          body_bytes = response.read()
          close_connection(key)

      response.close()

      if "close" in connection_hdr:
        close_connection(key)

      content_encoding = response_headers.get("content-encoding", "").lower()
      if "gzip" in content_encoding:
        try:
          body_bytes = gzip.decompress(body_bytes)
        except OSError:
          pass

      body = body_bytes.decode("utf-8", errors="replace")

      store_in_cache(cache_key, response_headers, body)

      return body

    except OSError as e:
      if key is not None:
        close_connection(key)
      return f"[Network error] {e}"

def decode_html_entities(text):
  return html.unescape(text)

def show(body):
  decode = decode_html_entities(body)

  in_tag = False
  for c in decode:
    if c == "<":
      in_tag = True
    elif c == ">":
      in_tag = False
    elif not in_tag:
      print(c, end="")

def load(url):
  body = url.request()

  if url.scheme == "view-source":
    print(body)
  else:
    show(body)

if __name__ == "__main__":
  if len(sys.argv) < 2:
    load(URL(""))
  else:
    load(URL(sys.argv[1]))

# python3 browser.py http://browser.engineering/examples/example1-simple.html
# python3 browser.py https://browser.engineering/examples/example1-simple.html
# python3 browser.py file:///Users/jinokseong/Documents/진옥/스터디/default.html
# python3 browser.py "data:text/html,<h1>Hello</h1>"
# python3 browser.py view-source:http://browser.engineering/examples/example1-simple.html
# python3 browser.py http://browser.engineering/redirect
# python3 browser.py http://browser.engineering/redirect3
