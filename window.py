import tkinter

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

    self.window.bind("<Up>", self.scrollup)
    self.window.bind("<Down>", self.scrolldown)
    self.window.bind("<MouseWheel>", self.mousewheel)
    self.window.bind("<Configure>", self.configure)

    self.text = ""

  def show(self):
    self.canvas.create_rectangle(10, 20, 400, 300, outline="red")
  
  def layout(self):
    display_list = []

    cursor_x = HSTEP
    cursor_y = VSTEP

    for c in self.text:
      if c == "\n":
        cursor_y += VSTEP * 1
        cursor_x = HSTEP
        continue

      if cursor_x >= self.width - HSTEP:
        cursor_y += VSTEP
        cursor_x = HSTEP

      display_list.append((cursor_x, cursor_y, c))

      cursor_x += HSTEP  
    
    self.content_height = max(self.height, cursor_y + VSTEP)

    return display_list

  def draw(self, text):
    self.text = text

    display_list = self.layout()

    self.canvas.delete("all")

    for x, y, text in display_list:
      if y > self.scroll + self.height: 
        continue
      if y + VSTEP < self.scroll: 
        continue
      self.canvas.create_text(x, y - self.scroll, text=text)
    
    self.update_scrollbar()

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