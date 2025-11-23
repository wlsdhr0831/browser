import socket
import ssl
from typing import Optional

# key: (scheme, host, port) -> socket
_CONNECTIONS = {}

def get_connection(scheme: str, host: str, port: Optional[int]):
  key = (scheme, host, port)

  sock = _CONNECTIONS.get(key)
  if sock is not None:
    return sock, key

  sock = socket.socket(
    family=socket.AF_INET,
    type=socket.SOCK_STREAM,
    proto=socket.IPPROTO_TCP,
  )
  sock.connect((host, port))

  if scheme == "https":
    ctx = ssl.create_default_context()
    sock = ctx.wrap_socket(sock, server_hostname=host)

  _CONNECTIONS[key] = sock
  return sock, key

def close_connection(key):
  sock = _CONNECTIONS.pop(key, None)
  if sock is not None:
    try:
      sock.close()
    except OSError:
      pass

def close_all():
  for key, sock in list(_CONNECTIONS.items()):
    try:
      sock.close()
    except OSError:
      pass
  _CONNECTIONS.clear()
