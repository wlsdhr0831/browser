import tkinter.font as tkfont

from text import Text
from tag import Tag

from cache import get_font

HSTEP, VSTEP = 13, 18

class Layout:
  def __init__(self, tokens, width, rtl):
    self.display_list = []

    self.rtl = rtl
    self.width = width  
    if rtl:
      self.cursor_x =  width - HSTEP
    else:
      self.cursor_x = HSTEP
    self.cursor_y = VSTEP

    self.size = 12
    self.weight = "normal"
    self.style = "roman"

    self.display_list = []
    self.line = []

    self.align_center = False
  
    self.is_sup = False
    self.is_abbr = False
    self.abbr_size_stack = []

    self.is_pre = False
    self.font_family = None

    for tok in tokens:
      self.token(tok)

    self.flush()
    self.content_height = self.cursor_y + VSTEP

  def token(self, tok):
    if isinstance(tok, Tag):
      raw = tok.tag.strip()

      if raw.startswith("h1") and "class=\"title\"" in raw:
        self.flush()
        self.align_center = True
      elif raw == "/h1":
        self.flush()
        self.align_center = False
      if tok.tag == "i":
        self.style = "italic"
      elif tok.tag == "/i":
        self.style = "roman"
      elif tok.tag == "b":
        self.weight = "bold"
      elif tok.tag == "/b":
        self.weight = "normal"
      elif tok.tag == "small":
        self.size -= 2
      elif tok.tag == "/small":
        self.size += 2
      elif tok.tag == "big":
        self.size += 4
      elif tok.tag == "/big":
        self.size -= 4
      elif tok.tag == "br":
        self.flush()
      elif tok.tag == "/p":
        self.flush()
        self.cursor_y += VSTEP
      elif tok.tag == "sup":
        self.size -= 4
        self.is_sup = True
      elif tok.tag == "/sup":
        self.size += 4
        self.is_sup = False
      elif tok.tag == "abbr":
        self.abbr_size_stack.append(self.size)
        self.size -= 2
        self.is_abbr = True
      elif tok.tag == "/abbr":
        if self.abbr_size_stack:
          self.size = self.abbr_size_stack.pop()
        self.is_abbr = False
      elif raw == "pre":
        self.flush()
        self.is_pre = True
        self.font_family = "SF Mono"   
      elif raw == "/pre":
        self.flush()
        self.is_pre = False
        self.font_family = None

    if isinstance(tok, Text):
      self.word(tok.text)

  def word(self, text):
    if self.is_pre:
      font = get_font(self.size, self.weight, self.style, family="SF Mono")
    else:
      font = get_font(self.size, self.weight, self.style)

    if self.is_pre:
      text = text.replace("\r\n", "\n").replace("\r", "\n")

      for ch in text:
        if ch == "\n":
          self.flush()
          self.cursor_x = self.width - HSTEP if self.rtl else HSTEP
          continue

        w = font.measure(ch)

        if self.rtl:
          if self.cursor_x - w <= HSTEP:
            self.flush()
          x = self.cursor_x - w
          self.line.append((x, self.cursor_y, ch, font, self.is_sup, self.is_abbr))
          self.cursor_x -= w   
        else:
          if self.cursor_x + w >= self.width - HSTEP:
            self.flush()
          x = self.cursor_x
          self.line.append((x, self.cursor_y, ch, font, self.is_sup, self.is_abbr))
          self.cursor_x += w
      return 
    
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\n", " \n ")
    text = text.replace("\n", " \n ")

    for word in text.split(" "):
      if not word:
        continue

      if word == "\n":
        self.flush()
        self.cursor_x = self.width - HSTEP if self.rtl else HSTEP
        continue

      w = font.measure(word)

      if self.rtl:
        if self.cursor_x - w <= HSTEP:
          self.flush()

        x = self.cursor_x - w

        text_word = word.upper() if self.is_abbr else word
        self.line.append((x, self.cursor_y, text_word, font, self.is_sup, self.is_abbr))

        self.cursor_x -= w + font.measure(" ")   
      else:
        if self.cursor_x + w >= self.width - HSTEP:
          self.flush()

        text_word = word.upper() if self.is_abbr else word
        self.line.append((self.cursor_x, self.cursor_y, text_word, font, self.is_sup, self.is_abbr))

        self.cursor_x += w + font.measure(" ")

  def flush(self):
    if not self.line: return

    metrics = [font.metrics() for x, y, word, font, is_sup, is_abbr in self.line]
    
    max_ascent = max([metric["ascent"] for metric in metrics])
    max_descent = max([metric["descent"] for metric in metrics])

    baseline = self.cursor_y + max_ascent

    if self.align_center:
      total_width = 0
      for x, y, word, font, is_sup in self.line:
        total_width += font.measure(word) + font.measure(" ")

      start_x = (self.width - total_width) / 2   

      ascent = font.metrics("ascent")
      top_y = baseline - ascent

      if is_sup:
        top_y -= ascent * 0.4

      cur = start_x
      for x, y, word, font, is_sup, is_abbr in self.line:
        w = font.measure(word)
        self.display_list.append((cur, top_y, word, font))
        cur += w + font.measure(" ")
    else:
      for x, y, word, font, is_sup, is_abbr in self.line:
        ascent = font.metrics("ascent")
        top_y = baseline - ascent

        if is_sup:
          top_y -= ascent * 0.4
          
        self.display_list.append((x, top_y, word, font))

    line_height = max_ascent + max_descent
    self.cursor_y = baseline + line_height * 0.25 + max_descent

    if self.rtl:
      self.cursor_x = self.width - HSTEP
    else:
      self.cursor_x = HSTEP
    self.line = []


