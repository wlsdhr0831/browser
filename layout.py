import tkinter.font as tkfont

from text import Text
from tag import Tag


HSTEP, VSTEP = 13, 18

class Layout:
  def __init__(self, tokens, width, rtl):
    self.display_list = []

    self.width = width  
    self.cursor_x = HSTEP
    self.cursor_y = VSTEP

    self.size = 12
    self.weight = "normal"
    self.style = "roman"

    self.display_list = []

    for tok in tokens:
      self.token(tok, rtl)

    self.content_height = self.cursor_y + VSTEP

  def token(self, tok, rtl):
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
        self.size -= 2
      elif tok.tag == "big":
        self.size += 4
      elif tok.tag == "/big":
        self.size -= 4

    if isinstance(tok, Text):
      self.word(tok.text, rtl)
  
  def word(self, text, rtl):
    font = tkfont.Font(size=self.size, weight=self.weight, slant=self.style)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\n", " \n ")
    text = text.replace("\n", " \n ")

    for word in text.split(" "):
      if not word:
        continue

      if word == "\n":
        self.cursor_y += font.metrics("linespace") * 1.25
        self.cursor_x = self.width - HSTEP if rtl else HSTEP
        continue

      w = font.measure(word)

      if rtl:
        if self.cursor_x - w <= HSTEP:
          self.cursor_y += font.metrics("linespace") * 1.25
          self.cursor_x = self.width - HSTEP

        x = self.cursor_x
        self.display_list.append((x, self.cursor_y, word, font))

        self.cursor_x -= w + font.measure(" ")   
      else:
        if self.cursor_x + w >= self.width - HSTEP:
          self.cursor_y += font.metrics("linespace") * 1.25
          self.cursor_x = HSTEP

        self.display_list.append((self.cursor_x, self.cursor_y, word, font))
        self.cursor_x += w + font.measure(" ")

     
