import sys
import tkinter

from url import URL, lex
from htmlParser import HTMLParser
from element import Element
from text import Text
from documentLayout import DocumentLayout

INIT_WIDTH, INIT_HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100


def paint_tree(layout_object, display_list):
  display_list.extend(layout_object.paint())
  for child in layout_object.children:
    paint_tree(child, display_list)
  return display_list


class Browser:
  def __init__(self, rtl=False):
    self.rtl = rtl
    self.scroll = 0
    self.content_height = INIT_HEIGHT
    self.display_list = []
    self.text = ""
    self.is_source = False

    self.window = tkinter.Tk()
    self.window.title("Marsh Browser")

    self.frame = tkinter.Frame(self.window)
    self.frame.pack(fill=tkinter.BOTH, expand=True)

    self.canvas = tkinter.Canvas(self.frame, width=INIT_WIDTH, height=INIT_HEIGHT)
    self.canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)

    self.scrollbar = tkinter.Scrollbar(self.frame, orient=tkinter.VERTICAL, command=self.on_scrollbar)
    self.scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)

    self.width = INIT_WIDTH
    self.height = INIT_HEIGHT

    self.window.bind("<Up>", self.scrollup)
    self.window.bind("<Down>", self.scrolldown)
    self.window.bind("<MouseWheel>", self.mousewheel)
    self.canvas.bind("<Configure>", self.configure)

  def load(self, url_str: str):
    url = URL(url_str)
    body = url.request()

    if url.scheme == "view-source":
      self.is_source = True
      self.text = body
      self.render_source(body)
    else:
      self.is_source = False
      self.text = lex(body)
      self.render_html(self.text)

    self.draw()

  def render_html(self, text: str):
    node = HTMLParser(text).parse()
    self.document = DocumentLayout(node, width=self.width, rtl=self.rtl)
    self.document.layout()

    self.display_list = []
    paint_tree(self.document, self.display_list)

    self.content_height = max(self.height, self.document.content_height)
    self.clamp_scroll()

  def render_source(self, source_text: str):
    root = Element("pre", {}, None)
    root.children.append(Text(source_text, root))

    self.document = DocumentLayout(root, width=self.width, rtl=self.rtl, bold=True, tag_color="#881280")
    self.document.layout()

    self.display_list = []
    paint_tree(self.document, self.display_list)

    self.content_height = max(self.height, self.document.content_height)
    self.clamp_scroll()

  def draw(self):
    self.canvas.delete("all")

    for cmd in self.display_list:
      if cmd.top > self.scroll + self.height:
        continue
      if cmd.bottom < self.scroll:
        continue
      cmd.execute(self.scroll, self.canvas)

    self.update_scrollbar()

  def scrollup(self, e=None):
    self.scroll -= SCROLL_STEP
    self.clamp_scroll()
    self.draw()

  def scrolldown(self, e=None):
    self.scroll += SCROLL_STEP
    self.clamp_scroll()
    self.draw()

  def mousewheel(self, e):
    step = SCROLL_STEP * (abs(e.delta) or 1)
    if e.delta < 0:
      self.scroll += step
    else:
      self.scroll -= step
    self.clamp_scroll()
    self.draw()

  def configure(self, e):
    self.width = e.width
    self.height = e.height
    if self.text:
      if self.is_source:
        self.render_source(self.text)
      else:
        self.render_html(self.text)
    self.draw()

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

    if not self.scrollbar.winfo_ismapped():
      self.scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)

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
        self.scroll += amount * SCROLL_STEP
      elif what == "pages":
        self.scroll += amount * self.height

    self.clamp_scroll()
    self.draw()


if __name__ == "__main__":
  rtl = False
  url_arg_index = 1

  if len(sys.argv) >= 2 and sys.argv[1] == "--rtl":
    rtl = True
    url_arg_index = 2

  b = Browser(rtl=rtl)

  if len(sys.argv) < url_arg_index + 1:
    b.load("")
  else:
    b.load(sys.argv[url_arg_index])

  tkinter.mainloop()


# python3 browser.py http://browser.engineering/examples/example1-simple.html
# python3 browser.py https://browser.engineering/examples/example1-simple.html
# python3 browser.py file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html
# python3 browser.py "data:text/html,<h1>Hello</h1>"
# python3 browser.py view-source:http://browser.engineering/examples/example1-simple.html
# python3 browser.py http://browser.engineering/redirect
# python3 browser.py http://browser.engineering/redirect3
# /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 browser.py view-source:file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html
# /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 browser.py file:///Users/jinokseong/Documents/진옥/스터디/browser/default.html
# /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 browser.py http://browser.engineering/examples/xiyouji.html
# /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 browser.py --rtl http://browser.engineering/examples/example2-rtl.html
# /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 browser.py http://browser.engineering/index.html
