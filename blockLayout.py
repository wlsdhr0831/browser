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

HIDDEN_TAGS = ["head", "title", "meta", "link", "style", "script"]

RUN_IN_TAG = "h6"

class BlockLayout:
  def __init__(self, nodes, parent, previous, rtl, bold: bool = False, tag_color: str = None, runin_prefix=None):
    self.nodes = nodes if isinstance(nodes, list) else [nodes]
    self.parent = parent
    self.previous = previous
    self.children = []
    self.rtl = rtl

    self.bold = bold
    self.tag_color = tag_color

    self.runin_prefix = runin_prefix if runin_prefix else []

    self.x = 0
    self.y = 0
    self.width = 0
    self.height = 0

    self.cursor_x = 0
    self.cursor_y = 0

    self.size = 12
    self.weight = "bold" if bold else "normal"
    self.style = "roman"

    self._h6_stack = []

    self.display_list = []
    self.line = []

    self.align_center = False
    self.is_sup = False
    self.is_abbr = False
    self.abbr_size_stack = []

    self.is_pre = False
    self.font_family = None

  def open_tag(self, tag):
    if tag in BLOCK_TAGS and tag != RUN_IN_TAG:
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
    elif tag == RUN_IN_TAG:
      self._h6_stack.append((self.size, self.weight, self.style))
      self.size = max(self.size, 14)
      self.weight = "bold"
      self.style = "roman"

  def close_tag(self, tag):
    if tag == "i":
      self.style = "roman"
    elif tag == "b":
      self.weight = "bold" if self.bold else "normal"
    elif tag == "small":
      self.size += 2
    elif tag == "big":
      self.size -= 4
    elif tag == RUN_IN_TAG:
      if self._h6_stack:
        self.size, self.weight, self.style = self._h6_stack.pop()
      self._add_space()
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
  
  def _add_space(self):
    font = get_font(self.size, self.weight, self.style) if not self.is_pre else get_font(self.size, self.weight, self.style, family="SF Mono")
    space = font.measure(" ")
    if self.rtl:
      self.cursor_x -= space
      if self.cursor_x < 0:
        self.flush()
    else:
      self.cursor_x += space
      if self.cursor_x >= self.width:
        self.flush()

  def recurse(self, tree):
    if isinstance(tree, Text):
      if self.is_pre:
        self.word(tree.text)
      else:
        for w in tree.text.split():
          self.word(w)
    elif isinstance(tree, Element) and tree.tag in HIDDEN_TAGS:
      return
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
        color = None  

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
    for n in self.nodes:
      if isinstance(n, Element):
        if n.tag == "pre":
          return "inline"
        if n.tag == "__toc_title__":
          return "block"
        if n.tag in BLOCK_TAGS and n.tag != RUN_IN_TAG:
          return "block"
    return "inline"

  def layout(self):
    self.x = self.parent.x
    self.width = self.parent.width
    self.y = (self.previous.y + self.previous.height) if self.previous else self.parent.y

    mode = self.layout_mode()

    if mode == "block":
      self.children = []
      self.display_list = []
      self.line = []

      root = self.nodes[0] if self.nodes else None

      if isinstance(root, Element):
        children = list(root.children)
      else:
        children = list(self.nodes)

      if self.runin_prefix:
        children = list(self.runin_prefix) + children

      if isinstance(root, Element) and root.tag == "nav":
        nav_id = root.attributes.get("id", "")
        if isinstance(nav_id, str) and nav_id == "toc":
          title_el = Element("__toc_title__", {}, root)
          title_el.children.append(Text("목차", title_el))
          children = [title_el] + children

      def is_inline_node(n):
        if isinstance(n, Text):
          return True
        if isinstance(n, Element):
          if n.tag in HIDDEN_TAGS:
            return None
          if n.tag == "__toc_title__":
            return False
          if n.tag == RUN_IN_TAG:
            return True
          if n.tag in BLOCK_TAGS:
            return False
        return True

      inline_run = []
      previous = None
      pending_runin = None

      def flush_inline_run():
        nonlocal inline_run, previous
        if not inline_run:
          return
        nxt = BlockLayout(
          inline_run,
          self,
          previous,
          self.rtl,
          bold=self.bold,
          tag_color=self.tag_color,
        )
        self.children.append(nxt)
        previous = nxt
        inline_run = []

      i = 0
      while i < len(children):
        child = children[i]

        if isinstance(child, Element) and child.tag == RUN_IN_TAG:
          pending_runin = child
          i += 1
          continue

        flag = is_inline_node(child)
        if flag is None:
          i += 1
          continue

        if pending_runin is not None:
          if flag:
            inline_run.append(pending_runin)
            pending_runin = None
            inline_run.append(child)
            i += 1
            continue
          else:
            flush_inline_run()
            nxt = BlockLayout(
              [child],
              self,
              previous,
              self.rtl,
              bold=self.bold,
              tag_color=self.tag_color,
              runin_prefix=[pending_runin],
            )
            self.children.append(nxt)
            previous = nxt
            pending_runin = None
            i += 1
            continue

        if flag:
          inline_run.append(child)
        else:
          flush_inline_run()
          force_bold = isinstance(child, Element) and child.tag == "__toc_title__"
          nxt = BlockLayout(
            [child],
            self,
            previous,
            self.rtl,
            bold=(True if force_bold else self.bold),
            tag_color=self.tag_color,
          )
          self.children.append(nxt)
          previous = nxt

        i += 1

      if pending_runin is not None:
        inline_run.append(pending_runin)
        pending_runin = None

      flush_inline_run()

      for child in self.children:
        child.layout()

      self.height = (
        (self.children[-1].y + self.children[-1].height) - self.y
        if self.children
        else VSTEP
      )
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

    for n in self.nodes:
      self.recurse(n)

    self.flush()
    self.height = self.cursor_y

  def paint(self):
    cmds = []

    if len(self.nodes) == 1 and isinstance(self.nodes[0], Element) and self.nodes[0].tag == "__toc_title__":
      x2, y2 = self.x + self.width, self.y + self.height
      cmds.append(DrawRect(self.x, self.y, x2, y2, "#e6e6e6"))

    if len(self.nodes) == 1 and isinstance(self.nodes[0], Element) and self.nodes[0].tag == "pre":
      x2, y2 = self.x + self.width, self.y + self.height
      cmds.append(DrawRect(self.x, self.y, x2, y2, "gray"))

    if self.layout_mode() == "inline":
      for x, y, word, font, color in self.display_list:
        cmds.append(DrawText(self.x + x, self.y + y, word, font))

    if len(self.nodes) == 1 and isinstance(self.nodes[0], Element) and self.nodes[0].tag == "nav":
      nav = self.nodes[0]
      original_class = nav.attributes.get("class", "")
      classes = original_class.split() if isinstance(original_class, str) else []
      if "links" in classes:
        x2, y2 = self.x + self.width, self.y + self.height
        cmds.append(DrawRect(self.x, self.y, x2, y2, "#ffdc6b"))

    return cmds
