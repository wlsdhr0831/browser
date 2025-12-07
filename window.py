import tkinter
import tkinter.font as tkfont

from text import Text
from tag import Tag

INIT_WIDTH, INIT_HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100

class Window:
  def __init__(self):
    self.window = tkinter.Tk()
    self.window.title("Marsh Browser")

    self.frame = tkinter.Frame(self.window)
    self.frame.pack(fill=tkinter.BOTH, expand=True)

    self.canvas = tkinter.Canvas(self.frame, width=INIT_WIDTH, height=INIT_HEIGHT)
    self.canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)

    self.width = INIT_WIDTH
    self.height = INIT_HEIGHT

    self.scroll = 0
    self.content_height = INIT_HEIGHT
    self.scrollbar = tkinter.Scrollbar(
      self.frame,
      orient=tkinter.VERTICAL,
      command=self.on_scrollbar
    )
    self.scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)

    self.rtl = False

    self.window.bind("<Up>", self.scrollup)
    self.window.bind("<Down>", self.scrolldown)
    self.window.bind("<MouseWheel>", self.mousewheel)
    self.canvas.bind("<Configure>", self.configure)

    self.text = []    
    self.tokens = []

  def show(self):
    self.canvas.create_rectangle(10, 20, 400, 300, outline="red")

  def layout(self):
    display_list = []

    cursor_x = HSTEP
    cursor_y = VSTEP

    weight = "normal"
    style = "roman"

    for tok in self.tokens:
      if isinstance(tok, Tag):
        if tok.tag == "i":
          style = "italic"
        elif tok.tag == "/i":
          style = "roman"
        elif tok.tag == "b":
          weight = "bold"
        elif tok.tag == "/b":
          weight = "normal"

      if isinstance(tok, Text):
        font = tkfont.Font(size=16, weight=weight, slant=style)

        text = tok.text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\n", " \n ")
        text = text.replace("\n", " \n ")

        for word in text.split(" "):
          if not word:
            continue

          if word == "\n":
            cursor_y += font.metrics("linespace") * 1.25
            cursor_x = self.width - HSTEP if self.rtl else HSTEP
            continue

          w = font.measure(word)

          if self.rtl:
            if cursor_x - w <= HSTEP:
              cursor_y += font.metrics("linespace") * 1.25
              cursor_x = self.width - HSTEP

            x = cursor_x
            display_list.append((x, cursor_y, word, font))

            cursor_x -= w + font.measure(" ")   
          else:
            if cursor_x + w >= self.width - HSTEP:
              cursor_y += font.metrics("linespace") * 1.25
              cursor_x = HSTEP

            display_list.append((cursor_x, cursor_y, word, font))
            cursor_x += w + font.measure(" ")

    self.content_height = max(self.height, cursor_y + VSTEP)
    
    return display_list

  def draw(self, text):
    self.tokens = text
    self.text = text

    display_list = self.layout()

    self.canvas.delete("all")

    for x, y, text, font in display_list:
      if y > self.scroll + self.height: 
        continue
      if y + VSTEP < self.scroll: 
        continue

      if self.rtl:
        self.canvas.create_text(x, y - self.scroll, text=text, font=font, anchor="e",)
      else:  
        self.canvas.create_text(x, y - self.scroll, text=text, font=font, anchor="w",)
    
    self.update_scrollbar()

  def set_direction(self, rtl: bool):
    self.rtl = rtl

  def scrollup(self, e):
    self.scroll -= SCROLL_STEP 
    self.clamp_scroll()
    self.draw(self.text)

  def scrolldown(self, e):
    self.scroll += SCROLL_STEP
    self.clamp_scroll()
    self.draw(self.text)
  
  def mousewheel(self, e):
    step = SCROLL_STEP * (abs(e.delta) or 1)

    if e.delta < 0:
      self.scroll += step
    elif e.delta > 0:
      self.scroll -= step

    self.clamp_scroll()
    self.draw(self.text)

  def configure(self, e):
    self.width = e.width
    self.height = e.height
    self.draw(self.text)

  def clamp_scroll(self):
    max_scroll = max(0, self.content_height - self.height)

    if self.scroll < 0:
      self.scroll = 0
    elif self.scroll > max_scroll:
      self.scroll = max_scroll

  def update_scrollbar(self):
    if self.content_height <= self.height:
      self.scrollbar.pack_forget()
      return

    first = self.scroll / self.content_height
    last = (self.scroll + self.height) / self.content_height
    first = max(0.0, min(1.0, first))
    last = max(0.0, min(1.0, last))
    self.scrollbar.set(first, last)

  def on_scrollbar(self, *args):
    if self.content_height <= self.height:
      return

    if args[0] == "moveto":
      fraction = float(args[1])
      self.scroll = int(fraction * self.content_height)
    elif args[0] == "scroll":
      amount = int(args[1])
      what = args[2] 
      if what == "units":
        delta = amount * SCROLL_STEP
      elif what == "pages":
        delta = amount * self.height
      else:
        delta = 0
      self.scroll += delta

    self.clamp_scroll()
    self.draw(self.text)