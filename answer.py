import math
import socket, ssl, sys
import ctypes
import sdl2
import skia
import threading
import time
import wbetools

import urllib.parse

import dukpy

EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"

REFRESH_RATE_SEC = .033

BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"
]

COOKIE_JAR = {}

class MeasureTime:
    def __init__(self):
        if not wbetools.OUTPUT_TRACE: return
        self.lock = threading.Lock()
        self.file = open("browser.trace", "w")
        self.file.write('{"traceEvents": [')
        ts = time.time() * 1000000
        self.file.write(
            '{ "name": "process_name",' +
            '"ph": "M",' +
            '"ts": ' + str(ts) + ',' +
            '"pid": 1, "cat": "__metadata",' +
            '"args": {"name": "Browser"}}')
        self.file.flush()

    def time(self, name):
        if not wbetools.OUTPUT_TRACE: return
        ts = time.time() * 1000000
        tid = threading.get_ident()
        self.lock.acquire(blocking=True)
        self.file.write(
            ', { "ph": "B", "cat": "_",' +
            '"name": "' + name + '",' +
            '"ts": ' + str(ts) + ',' +
            '"pid": 1, "tid": ' + str(tid) + '}')
        self.file.flush()
        self.lock.release()

    def stop(self, name):
        if not wbetools.OUTPUT_TRACE: return
        ts = time.time() * 1000000
        tid = threading.get_ident()
        self.lock.acquire(blocking=True)
        self.file.write(
            ', { "ph": "E", "cat": "_",' +
            '"name": "' + name + '",' +
            '"ts": ' + str(ts) + ',' +
            '"pid": 1, "tid": ' + str(tid) + '}')
        self.file.flush()
        self.lock.release()

    def finish(self):
        if not wbetools.OUTPUT_TRACE: return
        self.lock.acquire(blocking=True)
        for thread in threading.enumerate():
            self.file.write(
                ', { "ph": "M", "name": "thread_name",' +
                '"pid": 1, "tid": ' + str(thread.ident) + ',' +
                '"args": { "name": "' + thread.name + '"}}')
        self.file.write(']}')
        self.file.close()
        self.lock.release()

SETTIMEOUT_JS = "__runSetTimeout(dukpy.handle)"
XHR_ONLOAD_JS = "__runXHROnload(dukpy.out, dukpy.handle)"
RUNTIME_JS = open("runtime.js").read()

class SingleThreadedTaskRunner:
    def __init__(self, tab):
        self.tab = tab
        self.needs_quit = False
        self.tasks = []

    def schedule_task(self, callback):
        self.tasks.append(callback)
        self.tab.browser.needs_animation_frame = True

    def run_tasks(self):
        while self.tasks:
            task = self.tasks.pop(0)
            task.run()

    def clear_pending_tasks(self):
        self.tasks = []

    def start_thread(self):    
        pass

    def set_needs_quit(self):
        self.needs_quit = True
        pass

    def run(self):
        pass

class CommitData:
    def __init__(self, url, scroll, height, display_list):
        self.url = url
        self.scroll = scroll
        self.height = height
        self.display_list = display_list

class Task:
    def __init__(self, task_code, *args):
        self.task_code = task_code
        self.args = args

    def run(self):
        self.task_code(*self.args)
        self.task_code = None
        self.args = None


class TaskRunner:
    def __init__(self, tab):
        self.condition = threading.Condition()
        self.tab = tab
        self.tasks = []
        self.main_thread = threading.Thread(
            target=self.run,
            name="Main thread",
        )
        self.needs_quit = False

    def schedule_task(self, task):
        self.condition.acquire(blocking=True)
        self.tasks.append(task)
        self.condition.notify_all()
        self.condition.release()

    def set_needs_quit(self):
        self.condition.acquire(blocking=True)
        self.needs_quit = True
        self.condition.notify_all()
        self.condition.release()

    def clear_pending_tasks(self):
        self.condition.acquire(blocking=True)
        self.tasks.clear()
        self.condition.release()

    def start_thread(self):
        self.main_thread.start()

    def run(self):
        while True:
            self.condition.acquire(blocking=True)
            needs_quit = self.needs_quit
            self.condition.release()
            if needs_quit:
                self.handle_quit()
                return

            task = None
            self.condition.acquire(blocking=True)
            if len(self.tasks) > 0:
                task = self.tasks.pop(0)
            self.condition.release()
            if task:
                task.run()

            self.condition.acquire(blocking=True)
            if len(self.tasks) == 0 and not self.needs_quit:
                self.condition.wait()
            self.condition.release()

    def handle_quit(self):
        pass

class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def literal(self, literal):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("Parsing error")
        return self.s[start:self.i]

    def pair(self):
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()
        return prop.casefold(), val

    def ignore_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None

    def body(self):
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break
        return pairs

    def selector(self):
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    def parse(self):
        rules = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules
    
class JSContext:
    def __init__(self, tab):
        self.tab = tab
        self.discarded = False

        self.interp = dukpy.JSInterpreter()
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll",
            self.querySelectorAll)
        self.interp.export_function("createElement",
            self.createElement)
        self.interp.export_function("getAttribute",
            self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("children", self.children)
        self.interp.export_function("removeChild", self.removeChild)
        self.interp.export_function("setTimeout",
            self.setTimeout)
        self.interp.export_function("requestAnimationFrame",
            self.requestAnimationFrame)
        self.tab.browser.measure.time('script-runtime')
        self.interp.evaljs(RUNTIME_JS)
        self.tab.browser.measure.stop('script-runtime')

        self.node_to_handle = {}
        self.handle_to_node = {}

    def dispatch_xhr_onload(self, out, handle):
        if self.discarded: return
        self.tab.browser.measure.time('script-xhr')
        do_default = self.interp.evaljs(
            XHR_ONLOAD_JS, out=out, handle=handle)
        self.tab.browser.measure.stop('script-xhr')

    def XMLHttpRequest_send(
        self, method, url, body, isasync, handle):
        full_url = self.tab.url.resolve(url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        if full_url.origin() != self.tab.url.origin():
            raise Exception(
                "Cross-origin XHR request not allowed")

        def run_load():
            headers, response = full_url.request(self.tab.url, body)
            task = Task(self.dispatch_xhr_onload, response, handle)
            self.tab.task_runner.schedule_task(task)
            if not isasync:
                return response

        if not isasync:
            return run_load()
        else:
            threading.Thread(target=run_load).start()

    def run(self, script, code):
        try:
            return self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print("Script", script, "crashed", e)

    def dispatch_event(self, type, elt):
        handle = self.node_to_handle.get(elt, -1)
        do_default = self.interp.evaljs(
            EVENT_DISPATCH_JS, type=type, handle=handle)
        return not do_default

    def get_handle(self, elt):
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle

    def querySelectorAll(self, selector_text):
        selector = CSSParser(selector_text).selector()
        nodes = [node for node
                 in tree_to_list(self.tab.nodes, [])
                 if selector.matches(node)]
        return [self.get_handle(node) for node in nodes]

    def createElement(self, tag):
        elt = Element(tag, {}, None)  
        handle = self.get_handle(elt)
        return handle

    def getAttribute(self, handle, attr):
        elt = self.handle_to_node[handle]
        attr = elt.attributes.get(attr, None)
        return attr if attr else ""
    
    def children(self, handle):
        elt = self.handle_to_node[handle]
        result = []
        for child in elt.children:
            if child.tag is not None:  # Element node만
                result.append(self.get_handle(child))
        return result

    def removeChild(self, parent_handle, child_handle):
        parent = self.handle_to_node.get(parent_handle)
        child = self.handle_to_node.get(child_handle)

        if parent is None:
            raise Exception(f"Invalid parent handle: {parent_handle}")
        if child is None:
            raise Exception(f"Invalid child handle: {child_handle}")

        if child.parent is not parent:
            raise Exception("removeChild: node is not a child of this parent")

        try:
            parent.children.remove(child)
        except ValueError:
            raise Exception("removeChild: internal DOM state corrupted")

        child.parent = None

        return None

    def innerHTML_set(self, handle, s):
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        elt.children = new_nodes
        for child in elt.children:
            child.parent = elt
        self.tab.set_needs_render()

    def dispatch_settimeout(self, handle):
        if self.discarded: return
        self.tab.browser.measure.time('script-settimeout')
        self.interp.evaljs(SETTIMEOUT_JS, handle=handle)
        self.tab.browser.measure.stop('script-settimeout')

    def setTimeout(self, handle, time):
        def run_callback():
            task = Task(self.dispatch_settimeout, handle)
            self.tab.task_runner.schedule_task(task)
        threading.Timer(time / 1000.0, run_callback).start()

    def requestAnimationFrame(self):
        self.tab.browser.set_needs_animation_frame(self.tab)

class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self):
        return "TagSelector(tag={}, priority={})".format(
            self.tag, self.priority)

class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority
            
    def matches(self, node):
        if not self.descendant.matches(node): return False
        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent
        return False

    def __repr__(self):
        return ("DescendantSelector(ancestor={}, descendant={}, priority={})") \
            .format(self.ancestor, self.descendant, self.priority)
    
DEFAULT_STYLE_SHEET = CSSParser(open("answer.css").read()).parse()

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}

def style(node, rules):
    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            node.style[property] = value
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value
    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct = float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"
    for child in node.children:
        style(child, rules)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

def print_tree(node, indent=0):
    print(" " * indent + node)
    for child in node.children:
        print_tree(child, indent + 2)

def paint_tree(layout_object, display_list):
    cmds = []
    if layout_object.should_paint():
        cmds = layout_object.paint()
    for child in layout_object.children:
        paint_tree(child, cmds)

    if layout_object.should_paint():
        cmds = layout_object.paint_effects(cmds)
    display_list.extend(cmds)

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

def linespace(font):
    metrics = font.getMetrics()
    return metrics.fDescent - metrics.fAscent

def point_in_visual_rect(obj, x, y):
    # 1. 기본 사각형 범위 체크 (Bounding Box Check)
    # 이게 아니면 radius를 계산할 필요도 없이 False
    if not (obj.x <= x < obj.x + obj.width and obj.y <= y < obj.y + obj.height):
        return False

    # 2. border-radius 값 가져오기
    # 스타일이 없는 요소(예: 텍스트)는 안전하게 0으로 처리
    radius = 0
    if hasattr(obj.node, "style"):
        radius_str = obj.node.style.get("border-radius", "0px")
        try:
            radius = float(radius_str[:-2])
        except:
            radius = 0

    if radius == 0:
        return True

    # 3. 둥근 모서리 정밀 체크 (Corner Hit Testing)
    # 계산을 위해 클릭 좌표를 요소 내부의 상대 좌표(local coordinates)로 변환
    tx = x - obj.x
    ty = y - obj.y
    w = obj.width
    h = obj.height

    # (1) 왼쪽 위 모서리 (Top-Left)
    if tx < radius and ty < radius:
        # 원의 중심 (radius, radius)에서 클릭점까지의 거리가 반지름보다 작아야 함
        return (tx - radius)**2 + (ty - radius)**2 <= radius**2

    # (2) 오른쪽 위 모서리 (Top-Right)
    elif tx > w - radius and ty < radius:
        return (tx - (w - radius))**2 + (ty - radius)**2 <= radius**2

    # (3) 왼쪽 아래 모서리 (Bottom-Left)
    elif tx < radius and ty > h - radius:
        return (tx - radius)**2 + (ty - (h - radius))**2 <= radius**2

    # (4) 오른쪽 아래 모서리 (Bottom-Right)
    elif tx > w - radius and ty > h - radius:
        return (tx - (w - radius))**2 + (ty - (h - radius))**2 <= radius**2

    # 모서리 영역이 아닌 사각형 내부 (십자가 모양 안전 영역)
    return True

def paint_visual_effects(node, cmds, rect):
    opacity = float(node.style.get("opacity", "1.0"))
    blend_mode = node.style.get("mix-blend-mode")

    if node.style.get("overflow", "visible") == "clip":
        border_radius = float(node.style.get(
            "border-radius", "0px")[:-2])
        if not blend_mode:
            blend_mode = "source-over"
        cmds.append(Blend(1.0, "destination-in", [
            DrawRRect(rect, border_radius, "white")
        ]))

    return [Blend(opacity, blend_mode, cmds)]

def parse_blend_mode(blend_mode_str):
    if blend_mode_str == "multiply":
        return skia.BlendMode.kMultiply
    elif blend_mode_str == "difference":
        return skia.BlendMode.kDifference
    elif blend_mode_str == "destination-in":
        return skia.BlendMode.kDstIn
    elif blend_mode_str == "source-over":
        return skia.BlendMode.kSrcOver
    else:
        return skia.BlendMode.kSrcOver
    
class Blend:
    def __init__(self, opacity, blend_mode, children):
        self.opacity = opacity
        self.blend_mode = blend_mode
        self.should_save = self.blend_mode or self.opacity < 1

        self.children = children
        self.rect = skia.Rect.MakeEmpty()
        for cmd in self.children:
            self.rect.join(cmd.rect)

    def execute(self, canvas):
        paint = skia.Paint(
            Alphaf=self.opacity,
            BlendMode=parse_blend_mode(self.blend_mode),
        )
        if self.should_save:
            canvas.saveLayer(None, paint)
        for cmd in self.children:
            cmd.execute(canvas)
        if self.should_save:
            canvas.restore()

class DrawOutline:
    def __init__(self, rect, color, thickness):
        self.rect = rect
        self.color = color
        self.thickness = thickness

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawRect(self.rect, paint)

    def __repr__(self):
        return "DrawOutline({}, {}, {}, {}, color={}, thickness={})".format(
            self.left, self.top, self.right, self.bottom,
            self.color, self.thickness)
    
class DrawLine:
    def __init__(self, x1, y1, x2, y2, color, thickness):
        self.rect = skia.Rect.MakeLTRB(x1, y1, x2, y2)
        self.color = color
        self.thickness = thickness

    def execute(self, canvas):
        path = skia.Path().moveTo(
            self.rect.left(), self.rect.top()) \
                .lineTo(self.rect.right(),
                    self.rect.bottom())
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thickness,
            Style=skia.Paint.kStroke_Style,
        )
        canvas.drawPath(path, paint)

    def __repr__(self):
        return "DrawLine({}, {}, {}, {}, color={}, thickness={})".format(
            self.rect.left(), self.rect.top(), self.rect.right(), self.rect.bottom(),
            self.color, self.thickness)
    
class DrawRect:
    def __init__(self, rect, color):
        self.rect = rect
        self.color = color

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
        )
        canvas.drawRect(self.rect, paint)

    def __repr__(self):
        return "DrawRect(top={} left={} bottom={} right={} color={})".format(
            self.rect.top(), self.rect.left(), self.rect.bottom(),
            self.rect.right(), self.color)
    

class DrawRRect:
    def __init__(self, rect, radius, color):
        self.rect = rect
        self.rrect = skia.RRect.MakeRectXY(rect, radius, radius)
        self.color = color

    def execute(self, canvas):
        paint = skia.Paint(
            Color=parse_color(self.color),
        )
        canvas.drawRRect(self.rrect, paint)

class Chrome:
    def __init__(self, browser):
        self.browser = browser
        self.focus = None
        self.address_bar = ""
        self.cursor_idx = 0

        self.font = get_font(20, "normal", "roman")
        self.font_height = linespace(self.font)

        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2 * self.padding

        plus_width = self.font.measureText("+") + 2*self.padding
        self.newtab_rect = skia.Rect.MakeLTRB(
           self.padding,
           self.padding,
           self.padding + plus_width,
           self.padding + self.font_height)

        self.urlbar_top = self.tabbar_bottom + 1
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2 * self.padding
        
        back_width = self.font.measureText("<") + 2*self.padding
        self.back_rect = skia.Rect.MakeLTRB(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding)

        forward_width = self.font.measureText(">") + 2 * self.padding
        self.forward_rect = skia.Rect.MakeLTRB(
            self.back_rect.right() + self.padding,
            self.urlbar_top + self.padding,
            self.back_rect.right() + self.padding + forward_width,
            self.urlbar_bottom - self.padding)

        self.address_rect = skia.Rect.MakeLTRB(
            self.forward_rect.right() + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)
        
        self.bottom = self.urlbar_bottom

    def tab_rect(self, i):
        tabs_start = self.newtab_rect.right() + self.padding
        tab_width = self.font.measureText("Tab X") + 2 * self.padding
        return skia.Rect.MakeLTRB(
            tabs_start + tab_width * i, self.tabbar_top,
            tabs_start + tab_width * (i + 1), self.tabbar_bottom)

    def paint(self):
        cmds = []
        cmds.append(DrawLine(
            0, self.bottom, WIDTH,
            self.bottom, "black", 1))

        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left() + self.padding,
            self.newtab_rect.top(),
            "+", self.font, "black"))

        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left(), 0, bounds.left(), bounds.bottom(),
                "black", 1))
            cmds.append(DrawLine(
                bounds.right(), 0, bounds.right(), bounds.bottom(),
                "black", 1))
            cmds.append(DrawText(
                bounds.left() + self.padding, bounds.top() + self.padding,
                "Tab {}".format(i), self.font, "black"))

            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom(), bounds.left(), bounds.bottom(),
                    "black", 1))
                cmds.append(DrawLine(
                    bounds.right(), bounds.bottom(), WIDTH, bounds.bottom(),
                    "black", 1))

        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left() + self.padding,
            self.back_rect.top(),
            "<", self.font, "black"))

        cmds.append(DrawOutline(self.forward_rect, "black", 1))
        cmds.append(DrawText(
            self.forward_rect.left() + self.padding,
            self.forward_rect.top(),
            ">", self.font, "black"))

        cmds.append(DrawOutline(self.address_rect, "black", 1))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left() + self.padding,
                self.address_rect.top(),
                self.address_bar, self.font, "black"))
            w = self.font.measureText(self.address_bar[:self.cursor_idx])
            cmds.append(DrawLine(
                self.address_rect.left() + self.padding + w,
                self.address_rect.top(),
                self.address_rect.left() + self.padding + w,
                self.address_rect.bottom(),
                "red", 1))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left() + self.padding,
                self.address_rect.top(),
                url, self.font, "black"))

        return cmds

    def click(self, x, y):
        self.focus = None
        if self.newtab_rect.contains(x, y):
            self.browser.new_tab_internal(URL("http://browser.engineering/index.html"))
        elif self.back_rect.contains(x, y):
            task = Task(self.browser.active_tab.go_back)
            self.browser.active_tab.task_runner.schedule_task(task)
        elif self.forward_rect.contains(x, y):
            task = Task(self.browser.active_tab.go_forward)
            self.browser.active_tab.task_runner.schedule_task(task)
        elif self.address_rect.contains(x, y):
            self.focus = "address bar"
            self.address_bar = self.browser.active_tab.url.original_url
            self.cursor_idx = len(self.address_bar)
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains(x, y):
                    self.browser.set_active_tab(tab)
                    active_tab = self.browser.active_tab
                    task = Task(active_tab.set_needs_render)
                    active_tab.task_runner.schedule_task(task)
                    break

    def enter(self):
        if self.focus == "address bar":
            self.browser.schedule_load(URL(self.address_bar))
            self.focus = None
            return True
        return False

    def keypress(self, char):
        if self.focus == "address bar":
            self.address_bar = self.address_bar[:self.cursor_idx] + char + self.address_bar[self.cursor_idx:]
            self.cursor_idx = min(self.cursor_idx + 1, len(self.address_bar))
            return True
        return False

    def backspace(self):
        if self.focus == "address bar" and len(self.address_bar):
            self.address_bar  = self.address_bar[:self.cursor_idx - 1] + self.address_bar[self.cursor_idx:]
            self.cursor_idx = max(self.cursor_idx - 1, 0)
            return True
        return False
        
    def arrow(self, direction):
        if direction == "Left":
            self.cursor_idx = max(self.cursor_idx - 1, 0)
            return True
        elif direction == "Right":
            self.cursor_idx = min(self.cursor_idx + 1, len(self.address_bar))
            return True
        return False
    
    def blur(self):
        self.focus = None

########################################################################
# URL
########################################################################

class URL:
    def __init__(self, url):
        if "://" not in url:
            url = "http://google.com/search?q=" + url

        self.original_url = url

        self.scheme, url = url.split("://", 1)
        if "/" not in url:
            url += "/"
        self.host, self.path = url.split("/", 1)
        self.path = "/" + self.path
        self.port = 443 if self.scheme == "https" else 80
        if ":" in self.host:
            self.host, p = self.host.split(":", 1)
            self.port = int(p)

    def request(self, referrer, payload = None):
        s = socket.socket()
        s.connect((self.host, self.port))
        if self.scheme == "https":
            s = ssl.create_default_context().wrap_socket(
                s, server_hostname=self.host)
            
        method = "POST" if payload else "GET"
        request = "{} {} HTTP/1.0\r\n".format(method, self.path)
        request += "Host: {}\r\n".format(self.host)

        if self.host in COOKIE_JAR:
            cookie, params = COOKIE_JAR[self.host]
            allow_cookie = True
            if referrer and params.get("samesite", "none") == "lax":
                if method != "GET":
                    allow_cookie = self.host == referrer.host
            if allow_cookie:
                request += "Cookie: {}\r\n".format(cookie)

        if payload:
            content_length = len(payload.encode("utf8"))
            request += "Content-Length: {}\r\n".format(content_length)
        request += "\r\n"
        if payload: request += payload

        s.send(request.encode("utf8"))
        response = s.makefile("r", encoding="utf8", newline="\r\n")
    
        statusline = response.readline()
        # version, status, explanation = statusline.split(" ", 2)
    
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
    
        if "set-cookie" in response_headers:
            cookie = response_headers["set-cookie"]
            params = {}
            if ";" in cookie:
                cookie, rest = cookie.split(";", 1)
                for param in rest.split(";"):
                    if '=' in param:
                        param, value = param.split("=", 1)
                    else:
                        value = "true"
                    params[param.strip().casefold()] = value.casefold()
            COOKIE_JAR[self.host] = (cookie, params)

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
    
        content = response.read()
        s.close()

        return response_headers, content

    def resolve(self, url):
        if "://" in url:
            return URL(url)
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        if not url.startswith("/"):
            base, _ = self.path.rsplit("/", 1)
            url = base + "/" + url
        return URL(f"{self.scheme}://{self.host}:{self.port}{url}")

    def __str__(self):
        port = f":{self.port}"
        if (self.scheme, self.port) in [("http", 80), ("https", 443)]:
            port = ""
        return f"{self.scheme}://{self.host}{port}{self.path}"

    def origin(self):
        return self.scheme + "://" + self.host + ":" + str(self.port)

########################################################################
# DOM
########################################################################

class Text:
    def __init__(self, text, parent):
        self.text = text
        self.parent = parent
        self.children = []
        self.is_focused = False

class Element:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attributes = attrs
        self.parent = parent
        self.children = []
        self.is_focused = False

########################################################################
# HTML Parser
########################################################################

class HTMLParser:
    SELF_CLOSING_TAGS = ["br", "img", "meta", "link", "input", "hr"]
    
    HEAD_TAGS = ["base", "basefont", "bgsound", "noscript", "link", "meta", "title", "script", "style"]

    def __init__(self, body):
        self.body = body
        self.stack = []

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
                attributes[attrpair.casefold()] = ""
        return tag, attributes
    
    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.stack]

            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def parse(self):
        text = ""
        in_tag = False

        for c in self.body:
            if c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
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
        if text.isspace():
            return
        self.implicit_tags(None)
        parent = self.stack[-1]
        parent.children.append(Text(text, parent))

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        
        if tag.startswith("!"): return
        self.implicit_tags(tag)

        if tag.startswith("!"): return
        elif tag.startswith("/"): 
            if len(self.stack) == 1: return
            node = self.stack.pop()
            parent = self.stack[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.stack[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.stack[-1] if self.stack else None
            node = Element(tag, attributes, parent)
            self.stack.append(node)

    def finish(self):
        if not self.stack:
            self.implicit_tags(None)

        while len(self.stack) > 1:
            node = self.stack.pop()
            self.stack[-1].children.append(node)

        return self.stack.pop()

########################################################################
# Layout / Paint
########################################################################

WIDTH, HEIGHT = 800, 600
CHROME_PX = 80
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
FONTS = {}

def get_font(size, weight, style):
    key = (weight, style)
    if key not in FONTS:
        if weight == "bold":
            skia_weight = skia.FontStyle.kBold_Weight
        else:
            skia_weight = skia.FontStyle.kNormal_Weight
        if style == "italic":
            skia_style = skia.FontStyle.kItalic_Slant
        else:
            skia_style = skia.FontStyle.kUpright_Slant
        skia_width = skia.FontStyle.kNormal_Width
        style_info = \
            skia.FontStyle(skia_weight, skia_width, skia_style)
        font = skia.Typeface('Arial', style_info)
        FONTS[key] = font
    return skia.Font(FONTS[key], size)

NAMED_COLORS = {
    "black": "#000000",
    "gray":  "#808080",
    "white": "#ffffff",
    "red":   "#ff0000",
    "green": "#00ff00",
    "blue":  "#0000ff",
    "lightblue": "#add8e6",
    "lightgreen": "#90ee90",
    "orange": "#ffa500",
    "orangered": "#ff4500",
}

def parse_color(color):
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return skia.Color(r, g, b)
    elif color.startswith("#") and len(color) == 9:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        a = int(color[7:9], 16)
        return skia.Color(r, g, b, a)
    elif color in NAMED_COLORS:
        return parse_color(NAMED_COLORS[color])
    else:
        return skia.ColorBLACK
    
class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        if not self.children:
            self.height = 0
            return

        max_ascent = max([-word.font.getMetrics().fAscent 
                          for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline + word.font.getMetrics().fAscent
        max_descent = max([word.font.getMetrics().fDescent
                           for word in self.children])
        self.height = 1.25 * (max_ascent + max_descent)

    def paint(self):
        return []

    def paint_effects(self, cmds):
        return cmds

    def should_paint(self):
        return True
    
    def __repr__(self):
        return "LineLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        # Do not set self.y!!!
        self.width = self.font.measureText(self.word)

        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def paint(self):
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]

    def paint_effects(self, cmds):
        return cmds
    
    def should_paint(self):
        return True
    
    def __repr__(self):
        return ("TextLayout(x={}, y={}, width={}, height={}, word={})").format(
            self.x, self.y, self.width, self.height, self.word)

INPUT_WIDTH_PX = 100

class InputLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.children = []
        self.parent = parent
        self.previous = previous

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style)

        self.width = INPUT_WIDTH_PX

        if self.previous:
            space = self.previous.font.measureText(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = linespace(self.font)

    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x, self.y, self.x + self.width,
            self.y + self.height)
    
    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color","transparent")

        if bgcolor != "transparent":
            radius = float(self.node.style.get("border-radius", "0px")[:-2])
            cmds.append(DrawRRect(self.self_rect(), radius, bgcolor))

        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                print("Ignoring HTML contens inside button")
                text = ""

        color = self.node.style["color"]
        cmds.append(DrawText(self.x, self.y, text, self.font, color))
        
        if self.node.is_focused:
            cx = self.x + self.font.measureText(text)
            cmds.append(DrawLine(
                cx, self.y, cx, self.y + self.height, "black", 1))
            
        return cmds
    
    def should_paint(self):
        return True
    
    def __repr__(self):
        return ("InputLayout(x={}, y={}, width={}, height={})").format(
            self.x, self.y, self.width, self.height)

class BlockLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None

    def layout_intermdeiate(self):
        previous = None
        for child in self.node.children:
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
        else:
            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()

        self.height = sum([child.height for child in self.children])


    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and \
                  child.tag in BLOCK_ELEMENTS
                  for child in self.node.children]):
            return "block"
        elif self.node.children or self.node.tag == "input":
            return "inline"
        else:
            return "block"

    def recurse(self, node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            else:
                for child in node.children:
                    self.recurse(child)

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def word(self, node, word):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        font = get_font(size, weight, style)
        color = node.style["color"]

        w = font.measureText(word)

        self.cursor_x += w + font.measureText(" ")

        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)

        if self.cursor_x + w > self.width:
            self.new_line()

    def self_rect(self):
        return skia.Rect.MakeLTRB(
            self.x, self.y,
            self.x + self.width, self.y + self.height)

    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color",
                                      "transparent")

        if bgcolor != "transparent":
            radius = float(
                self.node.style.get(
                    "border-radius", "0px")[:-2])
            cmds.append(DrawRRect(
                self.self_rect(), radius, bgcolor))
            
        return cmds

    def paint_effects(self, cmds):
        cmds = paint_visual_effects(
            self.node, cmds, self.self_rect())
        return cmds
    
    def should_paint(self):
        return isinstance(self.node, Text) or (self.node.tag != "input" and self.node.tag != "button")

    def input(self, node):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous = line.children[-1] if line.children else None
        input = InputLayout(node, line, previous)
        line.children.append(input)

        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        font = get_font(size, weight, style)

        self.cursor_x += w + font.measureText(" ")

    def __repr__(self):
        return "BlockLayout[{}](x={}, y={}, width={}, height={})".format(
            self.layout_mode(), self.x, self.y, self.width, self.height)
    
class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.rect = skia.Rect.MakeLTRB(
            x1, y1,
            x1 + font.measureText(text),
            y1 - font.getMetrics().fAscent \
                + font.getMetrics().fDescent)
        self.text = text
        self.font = font
        self.color = color

    def execute(self, canvas):
        paint = skia.Paint(
            AntiAlias=True,
            Color=parse_color(self.color),
        )
        baseline = self.rect.top() \
            - self.font.getMetrics().fAscent
        canvas.drawString(self.text, float(self.rect.left()),
            baseline, self.font, paint)

    def __repr__(self):
        return "DrawText(text={})".format(self.text)

class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []

        self.x = None
        self.y = None
        self.width = None
        self.height = None

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)

        self.width = WIDTH - 2 * HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height

    def paint(self):
        return []
    
    def paint_effects(self, cmds):
        return cmds
    
    def should_paint(self):
        return True

    def __repr__(self):
        return "DocumentLayout()"

########################################################################
# Tab
########################################################################

class Tab:
    def __init__(self, browser, tab_height):
        self.scroll = 0
        self.url = None
        self.history = []
        self.future = []
        self.tab_height = tab_height
        self.focus = None
        self.js = None
        self.browser = browser
        self.loaded = False
        self.scroll_changed_in_tab = False
        self.needs_raf_callbacks = False
        self.needs_render = False
        if wbetools.USE_BROWSER_THREAD:
            self.task_runner = TaskRunner(self)
        else:
            self.task_runner = SingleThreadedTaskRunner(self)
        self.task_runner.start_thread()

    def load(self, url, payload=None):
        headers, body = url.request(self.url, payload)
        self.loaded = False
        self.scroll = 0
        self.scroll_changed_in_tab = True
        self.task_runner.clear_pending_tasks()
        self.url = url
        self.history.append(url)
        self.future = []

        self.allowed_origins = None
        if "content-security-policy" in headers:
           csp = headers["content-security-policy"].split()
           if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin).origin())

        self.nodes = HTMLParser(body).parse()

        self.rules = DEFAULT_STYLE_SHEET.copy()
        links = [node.attributes["href"]
                for node in tree_to_list(self.nodes, [])
                if isinstance(node, Element)
                and node.tag == "link"
                and node.attributes.get("rel") == "stylesheet"
                and "href" in node.attributes]

        for link in links:
            try:
                headers, body = url.resolve(link).request(url)
            except:
                continue
            self.rules.extend(CSSParser(body).parse())
        
        if self.js: self.js.discarded = True
        self.js = JSContext(self)
        scripts = [node.attributes["src"]
                   for node in tree_to_list(self.nodes, [])
                   if isinstance(node, Element) and node.tag == "script" and "src" in node.attributes]
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to CSP")
                continue
            try:
                header, body = script_url.request(url)
            except:
                continue
            task = Task(self.js.run, script_url, body)
            self.task_runner.schedule_task(task)
        self.set_needs_render()
        self.loaded = True

    def allowed_request(self, url):
        return self.allowed_origins == None or \
            url.origin() in self.allowed_origins
    
    def render(self):
        if not self.needs_render: return
        self.browser.measure.time('render')
        style(self.nodes, sorted(self.rules, key=cascade_priority))

        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.needs_render = False

        clamped_scroll = self.clamp_scroll(self.scroll)
        if clamped_scroll != self.scroll:
            self.scroll_changed_in_tab = True
        self.scroll = clamped_scroll

        self.browser.measure.stop('render')

    def raster(self, canvas):
        for cmd in self.display_list:
            cmd.execute(canvas)

    def scrollup(self):
        self.scroll = max(self.scroll - SCROLL_STEP, 0)

    def scrolldown(self):
        max_y = max(
            self.document.height + 2 * VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def set_needs_render(self):
        self.needs_render = True
        self.browser.set_needs_animation_frame(self)

    def clamp_scroll(self, scroll):
        height = math.ceil(self.document.height + 2*VSTEP)
        maxscroll = height - self.tab_height
        return max(0, min(scroll, maxscroll))
    
    def run_animation_frame(self, scroll):
        if not self.scroll_changed_in_tab:
            self.scroll = scroll
        self.browser.measure.time('script-runRAFHandlers')
        self.js.interp.evaljs("__runRAFHandlers()")
        self.browser.measure.stop('script-runRAFHandlers')

        self.render()

        scroll = None
        if self.scroll_changed_in_tab:
            scroll = self.scroll
        document_height = math.ceil(self.document.height + 2*VSTEP)
        commit_data = CommitData(
            self.url, scroll, document_height, \
            self.display_list)
        self.display_list = None
        self.browser.commit(self, commit_data)
        self.scroll_changed_in_tab = False

    def click(self, x, y):
        self.render()
        self.focus = None
        y += self.scroll

        objs = [obj for obj in tree_to_list(self.document, [])
                if point_in_visual_rect(obj, x, y)]
        
        if not objs: return
        elt = objs[-1].node

        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                if self.js.dispatch_event("click", elt): return
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elif elt.tag == "input":
                if self.js.dispatch_event("click", elt): return
                elt.attributes["value"] = ""
                if self.focus:
                    self.focus.is_focused = False
                self.focus = elt
                elt.is_focused = True
                return self.render()
            elif elt.tag == "button":
                if self.js.dispatch_event("click", elt): return
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                       return self.submit_form(elt)
                    elt = elt.parent
            elt = elt.parent
    
    def submit_form(self, elt):
        if self.js.dispatch_event("click", elt): return
        inputs = [node for node in tree_to_list(elt, [])
            if isinstance(node, Element) and node.tag == "input" and "name" in node.attributes]
        body = ""
        for input in inputs:
            name = urllib.parse.quote(input.attributes["name"])
            value = urllib.parse.quote(input.attributes.get("value", ""))
            body += "&" + name + "=" + value
        body = body[1:]
        url = self.url.resolve(elt.attributes["action"])
        self.load(url, body)

    def go_back(self):
        if len(self.history) > 1:
            self.future.append(self.history.pop())
            back = self.history.pop()
            self.load(back)
    
    def go_forward(self):
        if self.future:
            next = self.future.pop()
            self.load(next)

    def keypress(self, char):
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus): return
            self.focus.attributes["value"] += char
            self.render()

    def enter(self):
        if self.focus:
            elt = self.focus

            while elt:
                if isinstance(elt, Element) and elt.tag == "form" and "action" in elt.attributes:
                    return self.submit_form(elt)
                elt = elt.parent
    
    def blur(self):
        if self.focus:
            self.focus.attributes["value"] = ""
            self.focus.is_focused = False
            self.focus = None
            self.render()

    def __repr__(self):
        return "Tab(history={})".format(self.history)

########################################################################
# Browser (Chrome UI)
########################################################################

class Browser:
    def __init__(self):
        self.chrome = Chrome(self)

        self.sdl_window = sdl2.SDL_CreateWindow(b"Browser",
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            WIDTH, HEIGHT, sdl2.SDL_WINDOW_SHOWN)
        self.root_surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
            WIDTH, HEIGHT,
            ct=skia.kRGBA_8888_ColorType,
            at=skia.kUnpremul_AlphaType))
        self.chrome_surface = skia.Surface(
            WIDTH, math.ceil(self.chrome.bottom))
        self.tab_surface = None

        self.tabs = []
        self.active_tab = None
        self.focus = None
        self.address_bar = ""
        self.lock = threading.Lock()
        self.active_tab_url = None
        self.active_tab_scroll = 0

        self.measure = MeasureTime()
        threading.current_thread().name = "Browser thread"

        if sdl2.SDL_BYTEORDER == sdl2.SDL_BIG_ENDIAN:
            self.RED_MASK = 0xff000000
            self.GREEN_MASK = 0x00ff0000
            self.BLUE_MASK = 0x0000ff00
            self.ALPHA_MASK = 0x000000ff
        else:
            self.RED_MASK = 0x000000ff
            self.GREEN_MASK = 0x0000ff00
            self.BLUE_MASK = 0x00ff0000
            self.ALPHA_MASK = 0xff000000

        self.animation_timer = None

        self.needs_animation_frame = False
        self.needs_raster_and_draw = False

        self.active_tab_height = 0
        self.active_tab_display_list = None

    def render(self):
        assert not wbetools.USE_BROWSER_THREAD
        self.active_tab.task_runner.run_tasks()
        if self.active_tab.loaded:
            self.active_tab.run_animation_frame(self.active_tab_scroll)

    def clamp_scroll(self, scroll):
        height = self.active_tab_height
        maxscroll = height - (HEIGHT - self.chrome.bottom)
        return max(0, min(scroll, maxscroll))
    
    def set_active_tab(self, tab):
        self.active_tab = tab
        self.active_tab_scroll = 0
        self.active_tab_url = None
        self.needs_animation_frame = True
        self.animation_timer = None
    
    def handle_up(self):
        self.lock.acquire(blocking=True)
        if self.chrome.scrollup():
            self.set_needs_raster_and_draw()
        self.lock.release()

    def handle_down(self):
        self.lock.acquire(blocking=True)
        if not self.active_tab_height:
            self.lock.release()
            return
        self.active_tab_scroll = self.clamp_scroll(
            self.active_tab_scroll + SCROLL_STEP)
        self.set_needs_raster_and_draw()
        self.needs_animation_frame = True
        self.lock.release()

    def handle_click(self, e):
        self.lock.acquire(blocking=True)
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
            self.set_needs_raster_and_draw()
        else:
            if self.focus != "content":
                self.focus = "content"
                self.chrome.blur()
                self.set_needs_raster_and_draw()
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            task = Task(self.active_tab.click, e.x, tab_y)
            self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def schedule_load(self, url, body=None):
        self.active_tab.task_runner.clear_pending_tasks()
        task = Task(self.active_tab.load, url, body)
        self.active_tab.task_runner.schedule_task(task)

    def handle_key(self, char):
        self.lock.acquire(blocking=True)
        if not (0x20 <= ord(char) < 0x7f): return
        if self.chrome.keypress(char):
            self.set_needs_raster_and_draw()
        elif self.focus == "content":
            task = Task(self.active_tab.keypress, char)
            self.active_tab.task_runner.schedule_task(task)
        self.lock.release()

    def handle_enter(self):
        self.lock.acquire(blocking=True)
        if self.chrome.enter():
            self.set_needs_raster_and_draw()
        self.lock.release()

    def handle_backspace(self):
        self.lock.acquire(blocking=True)
        if self.chrome.backspace():
            self.set_needs_raster_and_draw()
        self.lock.release()

    def handle_left(self):
        self.lock.acquire(blocking=True)
        if self.chrome.arrow("Left"):
            self.set_needs_raster_and_draw()
        self.lock.release()

    def handle_right(self):
        self.lock.acquire(blocking=True)
        if self.chrome.arrow("Right"):
            self.set_needs_raster_and_draw()
        self.lock.release()

    def new_tab(self, url):
        self.lock.acquire(blocking=True)
        self.new_tab_internal(url)
        self.lock.release()

    def new_tab_internal(self, url):
        new_tab = Tab(self, HEIGHT - self.chrome.bottom)
        self.tabs.append(new_tab)
        self.set_active_tab(new_tab)
        self.schedule_load(url)

    def commit(self, tab, data):
        self.lock.acquire(blocking=True)
        if tab == self.active_tab:
            self.active_tab_url = data.url
            if data.scroll != None:
                self.active_tab_scroll = data.scroll
            self.active_tab_height = data.height
            if data.display_list:
                self.active_tab_display_list = data.display_list
            self.animation_timer = None
            self.set_needs_raster_and_draw()
        self.lock.release()

    def set_needs_animation_frame(self, tab):
        self.lock.acquire(blocking=True)
        if tab == self.active_tab:
            self.needs_animation_frame = True
        self.lock.release()

    def raster_tab(self):
        if self.active_tab_height == None:
            return
        if not self.tab_surface or \
                self.active_tab_height != self.tab_surface.height():
            self.tab_surface = skia.Surface(WIDTH, self.active_tab_height)

        canvas = self.tab_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        for cmd in self.active_tab_display_list:
            cmd.execute(canvas)

    def raster_chrome(self):
        canvas = self.chrome_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)

        for cmd in self.chrome.paint():
            cmd.execute(canvas)
    
    def set_needs_raster_and_draw(self):
        self.needs_raster_and_draw = True

    def raster_and_draw(self):
        self.lock.acquire(blocking=True)
        if not self.needs_raster_and_draw:
            self.lock.release()
            return
        self.measure.time('raster/draw')
        self.raster_chrome()
        self.raster_tab()
        self.draw()
        self.measure.stop('raster/draw')
        self.needs_raster_and_draw = False
        self.lock.release()

    def schedule_animation_frame(self):
        def callback():
            self.lock.acquire(blocking=True)
            scroll = self.active_tab_scroll
            active_tab = self.active_tab
            self.needs_animation_frame = False
            self.lock.release()
            task = Task(self.active_tab.run_animation_frame, scroll)
            active_tab.task_runner.schedule_task(task)
        self.lock.acquire(blocking=True)
        if self.needs_animation_frame and not self.animation_timer:
            if wbetools.USE_BROWSER_THREAD:
                self.animation_timer = \
                    threading.Timer(REFRESH_RATE_SEC, callback)
                self.animation_timer.start()
        self.lock.release()

    def draw(self):
        canvas = self.root_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        
        tab_rect = skia.Rect.MakeLTRB(
            0, self.chrome.bottom, WIDTH, HEIGHT)
        tab_offset = self.chrome.bottom - self.active_tab.scroll
        canvas.save()
        canvas.clipRect(tab_rect)
        canvas.translate(0, tab_offset)
        self.tab_surface.draw(canvas, 0, 0)
        canvas.restore()

        chrome_rect = skia.Rect.MakeLTRB(
            0, 0, WIDTH, self.chrome.bottom)
        canvas.save()
        canvas.clipRect(chrome_rect)
        self.chrome_surface.draw(canvas, 0, 0)
        canvas.restore()

        skia_image = self.root_surface.makeImageSnapshot()
        skia_bytes = skia_image.tobytes()

        depth = 32 # Bits per pixel
        pitch = 4 * WIDTH # Bytes per row
        sdl_surface = sdl2.SDL_CreateRGBSurfaceFrom(
            skia_bytes, WIDTH, HEIGHT, depth, pitch,
            self.RED_MASK, self.GREEN_MASK,
            self.BLUE_MASK, self.ALPHA_MASK)

        rect = sdl2.SDL_Rect(0, 0, WIDTH, HEIGHT)
        window_surface = sdl2.SDL_GetWindowSurface(self.sdl_window)
        sdl2.SDL_BlitSurface(sdl_surface, rect, window_surface, rect)
        sdl2.SDL_UpdateWindowSurface(self.sdl_window)
    
    def handle_quit(self):
        self.measure.finish()
        for tab in self.tabs:
            tab.task_runner.set_needs_quit()
        sdl2.SDL_DestroyWindow(self.sdl_window)

########################################################################
# Main
########################################################################

def mainloop(browser):
    event = sdl2.SDL_Event()
    while True:
        while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
            if event.type == sdl2.SDL_QUIT:
                browser.handle_quit()
                sdl2.SDL_Quit()
                sys.exit()
            elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                browser.handle_click(event.button)
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_RETURN:
                    browser.handle_enter()
                elif event.key.keysym.sym == sdl2.SDLK_DOWN:
                    browser.handle_down()
                elif event.key.keysym.sym == sdl2.SDLK_BACKSPACE: 
                    browser.handle_backspace()
                elif event.key.keysym.sym == sdl2.SDLK_LEFT:   
                    browser.handle_left()
                elif event.key.keysym.sym == sdl2.SDLK_RIGHT:    
                    browser.handle_right()
            elif event.type == sdl2.SDL_TEXTINPUT:
                browser.handle_key(event.text.text.decode('utf8'))
        if not wbetools.USE_BROWSER_THREAD:
            if browser.active_tab.task_runner.needs_quit:
                break
            if browser.needs_animation_frame:
                browser.needs_animation_frame = False
                browser.render()
        browser.raster_and_draw()
        browser.schedule_animation_frame()

if __name__ == "__main__":
    wbetools.parse_flags()
    sdl2.SDL_Init(sdl2.SDL_INIT_EVENTS)
    browser = Browser()
    browser.new_tab(URL(sys.argv[1]))
    browser.raster_and_draw()
    mainloop(browser)