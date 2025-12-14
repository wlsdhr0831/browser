from text import Text
from element import Element

from draw import DrawText, DrawRect
from cache import get_font

HSTEP, VSTEP = 13, 18

BLOCK_TAGS = [
  "html", "body", "article", "section", "nav", "aside",
  "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
  "footer", "address", "p", "hr", "pre", "blockquote",
  "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
  "figcaption", "main", "div", "table", "form", "fieldset",
  "legend", "details", "summary",
]

class BlockLayout:
  def __init__(self, node, parent, previous, rtl, bold: bool = False, tag_color: str = None):
    self.node = node
    self.parent = parent
    self.previous = previous
    self.children = []
    self.rtl = rtl

    self.bold = bold
    self.tag_color = tag_color

    self.x = 0
    self.y = 0
    self.width = 0
    self.height = 0

    self.cursor_x = 0
    self.cursor_y = 0

    self.size = 12
    self.weight = "bold" if bold else "normal"
    self.style = "roman"

    self.display_list = []
    self.line = []

    self.align_center = False
    self.is_sup = False
    self.is_abbr = False
    self.abbr_size_stack = []

    self.is_pre = False
    self.font_family = None

  def open_tag(self, tag):
    if tag in BLOCK_TAGS:
      self.flush()

    if tag == "i":
      self.style = "italic"
    elif tag == "b":
      self.weight = "bold"
    elif tag == "small":
      self.size -= 2
    elif tag == "big":
      self.size += 4
    elif tag == "br":
      self.flush()
    elif tag == "sup":
      self.size -= 4
      self.is_sup = True
    elif tag == "abbr":
      self.abbr_size_stack.append(self.size)
      self.size -= 2
      self.is_abbr = True
    elif tag == "pre":
      self.flush()
      self.is_pre = True
      self.font_family = "SF Mono"

  def close_tag(self, tag):
    if tag == "i":
      self.style = "roman"
    elif tag == "b":
      self.weight = "bold" if self.bold else "normal"
    elif tag == "small":
      self.size += 2
    elif tag == "big":
      self.size -= 4
    elif tag in BLOCK_TAGS:
      self.flush()
    elif tag == "sup":
      self.size += 4
      self.is_sup = False
    elif tag == "abbr":
      if self.abbr_size_stack:
        self.size = self.abbr_size_stack.pop()
      self.is_abbr = False
    elif tag == "pre":
      self.flush()
      self.is_pre = False
      self.font_family = None

  def recurse(self, tree):
    if isinstance(tree, Text):
      if self.is_pre:
        self.word(tree.text)
      else:
        for w in tree.text.split():
          self.word(w)
    else:
      self.open_tag(tree.tag)
      for child in tree.children:
        self.recurse(child)
      self.close_tag(tree.tag)

  def word(self, text):
    if self.is_pre:
      font = get_font(self.size, self.weight, self.style, family="SF Mono")
    else:
      font = get_font(self.size, self.weight, self.style)

    if self.is_pre:
      text = text.replace("\r\n", "\n").replace("\r", "\n")

      inside_tag = False
      in_tag_name = False
      expect_tag_name = False

      for ch in text:
        if ch == "\n":
          self.flush()
          self.cursor_x = (self.width - HSTEP) if self.rtl else 0
          continue

        color = None
        if self.tag_color:
          if ch == "<":
            inside_tag = True
            in_tag_name = False
            expect_tag_name = True
            color = self.tag_color
          elif ch == ">":
            inside_tag = False
            in_tag_name = False
            expect_tag_name = False
            color = self.tag_color
          elif inside_tag:
            if expect_tag_name:
              if ch == "/":
                color = self.tag_color
                expect_tag_name = True
              elif ch.isalpha():
                in_tag_name = True
                expect_tag_name = False
                color = self.tag_color
              else:
                expect_tag_name = False
                color = None
            elif in_tag_name:
              if ch.isalnum() or ch in "-:":
                color = self.tag_color
              else:
                in_tag_name = False
                color = None

        w = font.measure(ch)

        if self.rtl:
          if self.cursor_x - w < 0:
            self.flush()
          x = self.cursor_x - w
          self.line.append((x, self.cursor_y, ch, font, color))
          self.cursor_x -= w
        else:
          if self.cursor_x + w >= self.width:
            self.flush()
          x = self.cursor_x
          self.line.append((x, self.cursor_y, ch, font, color))
          self.cursor_x += w
      return

    out = text.upper() if self.is_abbr else text
    w = font.measure(out)
    space = font.measure(" ")

    if self.rtl:
      if self.cursor_x - w < 0:
        self.flush()
      x = self.cursor_x - w
      self.line.append((x, self.cursor_y, out, font, None))
      self.cursor_x -= (w + space)
    else:
      if self.cursor_x + w > self.width:
        self.flush()
      self.line.append((self.cursor_x, self.cursor_y, out, font, None))
      self.cursor_x += (w + space)

  def flush(self):
    if not self.line:
      return

    metrics = [font.metrics() for x, y, word, font, color in self.line]
    max_ascent = max(m["ascent"] for m in metrics)
    max_descent = max(m["descent"] for m in metrics)

    baseline = self.cursor_y + max_ascent

    for x, y, text, font, color in self.line:
      top = baseline - font.metrics("ascent")
      if self.is_sup:
        top -= font.metrics("ascent") * 0.4
      self.display_list.append((x, top, text, font, color))

    line_height = max_ascent + max_descent
    self.cursor_y = baseline + line_height * 0.25 + max_descent
    self.cursor_x = (self.width - HSTEP) if self.rtl else 0
    self.line = []

  def layout_mode(self):
    if isinstance(self.node, Text):
      return "inline"
    if isinstance(self.node, Element) and self.node.tag == "pre":
      return "inline"
    if isinstance(self.node, Element) and self.node.tag in BLOCK_TAGS:
      return "block"
    if any(isinstance(child, Element) and child.tag in BLOCK_TAGS for child in self.node.children):
      return "block"
    if self.node.children:
      return "inline"
    return "block"


  def layout(self):
    self.x = self.parent.x
    self.width = self.parent.width
    self.y = (self.previous.y + self.previous.height) if self.previous else self.parent.y

    mode = self.layout_mode()

    if mode == "block":
      self.children = []
      self.display_list = []
      self.line = []

      def is_inline_node(n):
        if isinstance(n, Text):
          return True
        if isinstance(n, Element) and n.tag in BLOCK_TAGS:
          return False
        return True 

      inline_run = []
      previous = None

      def flush_inline_run():
        nonlocal inline_run, previous
        if not inline_run:
          return
        wrapper = Element("__anon__", {}, self.node)
        wrapper.children = inline_run
        for c in inline_run:
          c.parent = wrapper
        inline_run = []
        nxt = BlockLayout(wrapper, self, previous, self.rtl, bold=self.bold, tag_color=self.tag_color)
        self.children.append(nxt)
        previous = nxt

      for child in self.node.children:
        if is_inline_node(child):
          inline_run.append(child)
        else:
          flush_inline_run()
          nxt = BlockLayout(child, self, previous, self.rtl, bold=self.bold, tag_color=self.tag_color)
          self.children.append(nxt)
          previous = nxt

      flush_inline_run()

      for child in self.children:
        child.layout()

      self.height = ((self.children[-1].y + self.children[-1].height) - self.y) if self.children else VSTEP
      return

    self.children = []
    self.display_list = []
    self.line = []

    self.cursor_x = (self.width - HSTEP) if self.rtl else 0
    self.cursor_y = 0

    self.weight = "bold" if self.bold else "normal"
    self.style = "roman"
    self.size = 12

    self.is_sup = False
    self.is_abbr = False
    self.abbr_size_stack = []
    self.is_pre = False
    self.font_family = None

    self.recurse(self.node)
    self.flush()
    self.height = self.cursor_y

  def paint(self):
    cmds = []

    if isinstance(self.node, Element) and self.node.tag == "pre":
      x2, y2 = self.x + self.width, self.y + self.height
      cmds.append(DrawRect(self.x, self.y, x2, y2, "gray"))

    if self.layout_mode() == "inline":
      for x, y, word, font, color in self.display_list:
        cmds.append(DrawText(self.x + x, self.y + y, word, font))

    return cmds
