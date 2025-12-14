from blockLayout import BlockLayout

HSTEP, VSTEP = 13, 18

class DocumentLayout:
  def __init__(self, node, width, rtl, bold: bool = False, tag_color: str = None):
    self.node = node
    self.parent = None
    self.children = []
    self.rtl = rtl
    self.bold = bold
    self.width = width
    self.tag_color = tag_color

    self.x = 0
    self.y = 0
    self.height = 0

  @property
  def content_height(self):
    return self.y + self.height + VSTEP

  def layout(self):
    self.children = []

    self.x = HSTEP
    self.y = VSTEP
    self.width = self.width - 2 * HSTEP

    child = BlockLayout(self.node, self, None, self.rtl, self.bold, self.tag_color)
    self.children.append(child)

    child.layout()
    self.height = child.height

  def paint(self):
    return []
