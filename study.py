import socket
import sys
import ssl
import urllib.parse
import html
import time 
import gzip 

DEFAULT_LOCAL_FILE = "file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html"

# key: (scheme, host, port) -> socket
CONNECTIONS = {}  

# key: (scheme, host, port, path) -> {"expires_at": float, "body": str}
CACHE = {}

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
  
  def _get_connection(self):
    key = (self.scheme, self.host, self.port)

    s = CONNECTIONS.get(key)
    
    if s is not None:
      return s, key

    s = socket.socket(
      family=socket.AF_INET,
      type=socket.SOCK_STREAM,
      proto=socket.IPPROTO_TCP,
    )
    s.connect((self.host, self.port))

    if self.scheme == "https":
      ctx = ssl.create_default_context()
      s = ctx.wrap_socket(s, server_hostname=self.host)

    CONNECTIONS[key] = s
    return s, key
    

  def _close_connection(self, key):
    s = CONNECTIONS.pop(key, None)
    if s is not None:
      try:
        s.close()
      except OSError:
        pass    

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

    cache_key = None
    if self.scheme in ["http", "https"]:
      cache_key = (self.scheme, self.host, self.port, self.path)
      entry = CACHE.get(cache_key)

      if entry is not None:
        now = time.time()
        expires_at = entry["expires_at"]
        if expires_at is not None and expires_at >= now:
          return entry["body"]
        else:
          CACHE.pop(cache_key, None)

    s = None
    key = None

    try:
      s, key = self._get_connection()

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
        self._close_connection(key)
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
            self._close_connection(key)
          return f"[HTTP redirect {status}] (no Location header)"
        
        if location.startswith("/"):
          redirect_url = f"{self.scheme}://{self.host}{location}"
        else:
          redirect_url = location

        response.close()

        if key is not None:
          self._close_connection(key)

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
          self._close_connection(key)

      response.close()

      if "close" in connection_hdr:
        self._close_connection(key)

      content_encoding = response_headers.get("content-encoding", "").lower()
      if "gzip" in content_encoding:
        try:
          body_bytes = gzip.decompress(body_bytes)
        except OSError:
          pass

      body = body_bytes.decode("utf-8", errors="replace")

      if cache_key is not None:
        cache_control = response_headers.get("cache-control", "")
        expires_at = None

        if cache_control:
          directives = [d.strip().lower() for d in cache_control.split(",")]

          if "no-store" in directives:
            expires_at = None

          else:
            for d in directives:
              if d.startswith("max-age="):
                try:
                  seconds = int(d.split("=", 1)[1])
                  expires_at = time.time() + seconds
                except ValueError:
                  pass
                break 

          if expires_at is not None:
            CACHE[cache_key] = {
              "expires_at": expires_at,
              "body": body,
            }
      return body

    except OSError as e:
      if key is not None:
        self._close_connection(key)
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

# python3 study.py http://browser.engineering/examples/example1-simple.html
# python3 study.py https://browser.engineering/examples/example1-simple.html
# python3 study.py file:///Users/jinokseong/Documents/진옥/스터디/default.html
# python3 study.py "data:text/html,<h1>Hello</h1>"
# python3 study.py view-source:http://browser.engineering/examples/example1-simple.html
# python3 study.py http://browser.engineering/redirect
# python3 study.py http://browser.engineering/redirect3
