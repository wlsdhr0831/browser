import tkinter.font as tkfont

from text import Text
from tag import Tag


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

    for tok in tokens:
      self.token(tok)

    self.flush()
    self.content_height = self.cursor_y + VSTEP

  def token(self, tok):
    if isinstance(tok, Tag):
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

    if isinstance(tok, Text):
      self.word(tok.text)

  def word(self, text):
    font = tkfont.Font(size=self.size, weight=self.weight, slant=self.style)

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
        self.line.append((x, self.cursor_y, word, font))

        self.cursor_x -= w + font.measure(" ")   
      else:
        if self.cursor_x + w >= self.width - HSTEP:
          self.flush()

        self.line.append((self.cursor_x, self.cursor_y, word, font))
        self.cursor_x += w + font.measure(" ")

  def flush(self):
    if not self.line: return

    metrics = [font.metrics() for x, y, word, font in self.line]
    
    max_ascent = max([metric["ascent"] for metric in metrics])
    max_descent = max([metric["descent"] for metric in metrics])

    baseline = self.cursor_y + max_ascent

    for x, y, word, font in self.line:
      top_y = baseline - font.metrics("ascent")
      self.display_list.append((x, top_y, word, font))

    line_height = max_ascent + max_descent
    self.cursor_y = baseline + line_height * 0.25 + max_descent

    if self.rtl:
      self.cursor_x = self.width - HSTEP
    else:
      self.cursor_x = HSTEP
    self.line = []


