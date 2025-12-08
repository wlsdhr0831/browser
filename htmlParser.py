from urllib.request import urlopen

from text import Text
from tag import Tag

SELF_CLOSING_TAGS = [
  "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"
]

HEAD_TAGS = ["base", "basefont", "bgsound", "noscript", "link", "meta", "title", "style", "script"]

class HTMLParser:
  def __init__(self, body):
    self.body = body
    self.unfinished = []

  def parse(self):
    text = ""
    in_tag = False

    for c in self.body:
      if c == "<":
        in_tag = True
        if text: self.add_text(text)
        text = ""
      elif c == ">":
        in_tag = False
        self.add_tag(text)
        text = ""
      else:
        text += c

    if not in_tag and text:
      self.add_text(text)

    return self.finish()

  def add_text(self, text):
    if text.isspace(): return
    
    if self.unfinished and self.unfinished[-1].tag == "script":
      return

    self.implicit_tags(None)

    parent = self.unfinished[-1]
    node = Text(text, parent)
    parent.children.append(node)

  def add_tag(self, tag):
    tag, attributes = self.get_attributes(tag)

    if tag.startswith("!"): return

    self.implicit_tags(tag)

    if tag.startswith("/"):
      if len(self.unfinished) == 1: return
      node = self.unfinished.pop()
      parent = self.unfinished[-1]
      parent.children.append(node)
    elif tag in SELF_CLOSING_TAGS:
      parent = self.unfinished[-1]
      node = Tag(tag, attributes, parent)
      parent.children.append(node)
    else:
      parent = self.unfinished[-1] if self.unfinished else None
      node = Tag(tag,attributes,  parent)
      self.unfinished.append(node)
  
  def get_attributes(self, text):
    parts = text.split()
    tag = parts[0].casefold()

    attributes = {}
    for attrpair in parts[1:]:
      if "=" in attrpair:
        key, value = attrpair.split("=", 1)
        
        if len(value) > 2 and value[0] in ["'", "\""]:
          value = value[1:-1]

        attributes[key.casefold()] = value
      else:
       attributes[attrpair.casefold()] = True
    
    return tag, attributes

  def finish(self):
    if not self.unfinished:
      self.implicit_tags(None)
    while len(self.unfinished) > 1:
      node = self.unfinished.pop()
      parent = self.unfinished[-1]
      parent.children.append(node)
    return self.unfinished.pop()
  
  def implicit_tags(self, tag):
    while True:
      open_tags = [node.tag for node in self.unfinished]

      if open_tags == [] and tag != "html":
        self.add_tag("html")
      elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
        if tag in HEAD_TAGS:
          self.add_tag("head")
        else:
          self.add_tag('body')
      elif open_tags == ["html", "body"] and tag not in ["/head"] + HEAD_TAGS:
        self.add_tag("/head")
      else:
        break