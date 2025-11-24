"""duet - a self-editing terminal workspace where human and AI collaborate."""
import curses, anthropic, re, sys, os

SYSTEM_PROMPT = """You are a self-editing document—a living Python program that modifies its own source.

Structure (separated by MARKER line):
- Kernel: Python code above MARKER. Edits trigger automatic hot-reload.
- Conversation: Comments below MARKER where you communicate.

When using the respond tool:
- edits: Each 'old' must match source EXACTLY (every character, space, newline) with enough context to be unique
- message: Your response (added as comments)

Be concise. Never edit the MARKER line."""
EDIT_TOOL = {"name": "respond", "description": "Respond with optional edits", "input_schema": {
    "type": "object",
    "properties": {
        "edits": {"type": "array", "items": {"type": "object", "properties": {
            "old": {"type": "string"}, "new": {"type": "string"}
        }, "required": ["old", "new"]}},
        "message": {"type": "string"}
    },
    "required": ["message"]
}}
FILE = __file__
MARKER = "# === CONVERSATION ==="
MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 4096

class Editor:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        self.lines = []
        self.cursor_y = self.cursor_x = self.scroll_y = 0
        self.status = "Ctrl+F: agent | Ctrl+R: reload | Ctrl+S: save | Ctrl+Q: quit"
        self.last_error = None
        self.load()

    def load(self):
        with open(FILE) as f:
            self.lines = f.read().split('\n')
        self.cursor_y = len(self.lines) - 1
        self.cursor_x = len(self.lines[self.cursor_y]) if self.lines else 0

    def validate(self, content):
        """Validate content, return error message or None if valid."""
        marker_matches = re.findall(r'^' + re.escape(MARKER) + r'$', content, re.MULTILINE)
        if len(marker_matches) == 0:
            return "Structure broken: MARKER missing"
        if len(marker_matches) > 1:
            return "Structure broken: multiple MARKERs"
        kernel = content.split('\n' + MARKER)[0]
        try:
            compile(kernel, FILE, 'exec')
        except SyntaxError as e:
            return f"Syntax error line {e.lineno}: {e.msg}"
        return None

    def hot_reload(self):
        """Reload kernel - swap __class__ to pick up new methods."""
        try:
            with open(FILE) as f:
                kernel = f.read().split('\n' + MARKER)[0]
            ns = {'__name__': '__main__', '__file__': FILE, 'curses': curses, 'anthropic': anthropic, 're': re, 'sys': sys, 'os': os}
            exec(compile(kernel, FILE, 'exec'), ns)
            self.__class__ = ns['Editor']
            self.status = "Reloaded!"
            return True
        except Exception as e:
            self.status = f"Reload failed: {str(e)[:40]}"
            return False

    def save(self, content=None):
        if content is None:
            content = '\n'.join(self.lines)
        error = self.validate(content)
        if error:
            self.status = error[:60]
            return False, error
        try:
            with open(FILE) as f:
                old_kernel = f.read().split('\n' + MARKER)[0]
        except FileNotFoundError:
            old_kernel = ""
        new_kernel = content.split('\n' + MARKER)[0]
        kernel_changed = old_kernel != new_kernel
        with open(FILE, 'w') as f:
            f.write(content)
        if kernel_changed:
            self.hot_reload()
        else:
            self.status = "Saved!"
        return True, None

    def get_marker_line(self):
        for i, line in enumerate(self.lines):
            if line == MARKER:
                return i
        return -1

    def in_conversation_section(self):
        marker_line = self.get_marker_line()
        return marker_line >= 0 and self.cursor_y > marker_line

    def apply_edits(self, src, edits):
        """Apply edits list. Returns (new_src, kernel_changed, error)."""
        if not edits:
            return src, False, None
        kernel_before = src.split('\n' + MARKER)[0]
        new_src = src
        for edit in edits:
            old, new = edit["old"], edit["new"]
            count = new_src.count(old)
            if count == 0:
                return src, False, f"Edit not found: '{old[:30]}...'"
            if count > 1:
                return src, False, f"Edit ambiguous ({count}x): '{old[:20]}...'"
            new_src = new_src.replace(old, new, 1)
        error = self.validate(new_src)
        if error:
            return src, False, f"Edit would cause: {error}"
        kernel_after = new_src.split('\n' + MARKER)[0]
        return new_src, kernel_before != kernel_after, None

    def invoke_agent(self):
        self.status = "Thinking..."
        self.render()
        curses.doupdate()
        src = '\n'.join(self.lines)
        error_context = f"\n<error>{self.last_error}</error>\nPlease fix this." if self.last_error else ""
        try:
            response = anthropic.Anthropic().messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=[EDIT_TOOL],
                tool_choice={"type": "tool", "name": "respond"},
                messages=[{"role": "user", "content": f"<source>\n{src}\n</source>{error_context}"}]
            )
            tool_input = next((b.input for b in response.content if b.type == "tool_use"), None)
            if not tool_input:
                self.status = "No tool response"
                return
            edits = tool_input.get("edits", [])
            message = tool_input.get("message", "")
            new_src, kernel_changed, error = self.apply_edits(src, edits)
            if error:
                self.last_error = error
                self.status = f"Edit failed: {error[:50]}"
                return
            self.last_error = None
            if message:
                prefixed = '\n'.join('# ' + line if line else '#' for line in message.split('\n'))
                new_src = new_src.rstrip() + '\n#\n' + prefixed
            self.lines = new_src.split('\n')
            success, save_error = self.save(new_src)
            if success:
                self.status = "Agent responded!"
            else:
                self.last_error = save_error
            self.cursor_y = len(self.lines) - 1
            self.cursor_x = 0
        except Exception as e:
            self.status = f"Error: {str(e)[:40]}"

    def render(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if self.cursor_y < self.scroll_y:
            self.scroll_y = self.cursor_y
        if self.cursor_y >= self.scroll_y + h - 2:
            self.scroll_y = self.cursor_y - h + 3
        for i in range(h - 2):
            idx = i + self.scroll_y
            if idx < len(self.lines):
                try:
                    self.stdscr.addstr(i, 0, self.lines[idx][:w-1])
                except curses.error:
                    pass
        try:
            status = f" {self.status} | Line {self.cursor_y+1}:{self.cursor_x+1} "
            self.stdscr.addstr(h-1, 0, status[:w-1].ljust(w-1), curses.A_REVERSE)
        except curses.error:
            pass
        sy = self.cursor_y - self.scroll_y
        if 0 <= sy < h - 1:
            self.stdscr.move(sy, min(self.cursor_x, w-1))
        self.stdscr.noutrefresh()

    def handle_key(self, key):
        h, w = self.stdscr.getmaxyx()
        if key == curses.KEY_UP and self.cursor_y > 0:
            self.cursor_y -= 1
            self.cursor_x = min(self.cursor_x, len(self.lines[self.cursor_y]))
        elif key == curses.KEY_DOWN and self.cursor_y < len(self.lines) - 1:
            self.cursor_y += 1
            self.cursor_x = min(self.cursor_x, len(self.lines[self.cursor_y]))
        elif key == curses.KEY_LEFT and self.cursor_x > 0:
            self.cursor_x -= 1
        elif key == curses.KEY_RIGHT and self.cursor_x < len(self.lines[self.cursor_y]):
            self.cursor_x += 1
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.cursor_x > 0:
                ln = self.lines[self.cursor_y]
                self.lines[self.cursor_y] = ln[:self.cursor_x-1] + ln[self.cursor_x:]
                self.cursor_x -= 1
            elif self.cursor_y > 0:
                self.cursor_x = len(self.lines[self.cursor_y - 1])
                self.lines[self.cursor_y - 1] += self.lines[self.cursor_y]
                del self.lines[self.cursor_y]
                self.cursor_y -= 1
        elif key == curses.KEY_DC:
            ln = self.lines[self.cursor_y]
            if self.cursor_x < len(ln):
                self.lines[self.cursor_y] = ln[:self.cursor_x] + ln[self.cursor_x+1:]
            elif self.cursor_y < len(self.lines) - 1:
                self.lines[self.cursor_y] += self.lines[self.cursor_y + 1]
                del self.lines[self.cursor_y + 1]
        elif key in (10, 13):
            ln = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = ln[:self.cursor_x]
            remainder = ln[self.cursor_x:]
            if self.in_conversation_section():
                if remainder and not remainder.startswith('#'):
                    remainder = '# ' + remainder.lstrip()
                elif not remainder:
                    remainder = '# '
            self.lines.insert(self.cursor_y + 1, remainder)
            self.cursor_y += 1
            self.cursor_x = 2 if self.in_conversation_section() else 0
        elif key == 19: self.save()  # Ctrl+S
        elif key == 17: return False  # Ctrl+Q
        elif key == 18: self.hot_reload()  # Ctrl+R
        elif key == 6: self.invoke_agent()  # Ctrl+F
        elif 32 <= key <= 126:
            ln = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = ln[:self.cursor_x] + chr(key) + ln[self.cursor_x:]
            self.cursor_x += 1
        return True

    def run(self):
        curses.raw()
        self.stdscr.keypad(True)
        curses.curs_set(1)
        while True:
            self.render()
            curses.doupdate()
            if not self.handle_key(self.stdscr.getch()):
                break

if __name__ == "__main__":
    curses.wrapper(lambda s: Editor(s).run())

# === CONVERSATION ===
# 