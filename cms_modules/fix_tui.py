"""A terminal editor for lining up material links with their names, used by the command line.

When a course page shows a different number of links and names (a teacher wrote a title in an
unusual way), line N on the left has to get the name on line N on the right, so the order matters.
The editor shows both lists side by side with their counts, numbers every row, and marks where each
week starts on both sides, so a row where only one side starts a week shows where things slipped.
"""
import curses
import locale
import re

SECTION_RE = re.compile(r"/Uploads/[^/]+/[^/]+/([^/]+)/")
UPLOAD_TIME_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})T(\d{2})_(\d{2})_\d{2}(\.\w+)$")
NUMBER_RE = re.compile(r"^\s*(\d+)\s*-")
KEYS = "Up/Down move  Tab side  d delete  a/A add below/above  Enter edit  K/J move line  u undo  s save  q skip"


def link_section(link):
    """The week (section) id in a CMS upload link: /Uploads/<season>/<course>/<section>/<file>."""
    match = SECTION_RE.search(link.replace("\\", "/"))
    return match.group(1) if match else ""


def describe_link(link):
    """A short label for a link: when it was uploaded and its file type, or else its file name."""
    file_name = link.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    match = UPLOAD_TIME_RE.search(file_name)
    if not match:
        return file_name
    date, hour, minute, extension = match.groups()
    return f"{date} {hour}:{minute} {extension}"


def week_starts(links, names):
    """Rows where a week starts: a new section among the links, a name numbered 1 among the names."""
    on_left = {i for i, link in enumerate(links) if i == 0 or link_section(link) != link_section(links[i - 1])}
    on_right = {i for i, name in enumerate(names) if (match := NUMBER_RE.match(name)) and match.group(1) == "1"}
    return on_left, on_right


class FixEditor:
    LINKS, NAMES = 0, 1

    def __init__(self, links, names, title):
        self.lists = [list(links), list(names)]
        self.title = title
        self.row = 0
        self.side = self.NAMES  # most fixes happen among the names
        self.top = 0
        self.history = []
        self.message = ""
        self.attrs = {}

    # --- Editing (separate from drawing, so it can be tested without a terminal) ---

    @property
    def row_count(self):
        return max(len(self.lists[0]), len(self.lists[1]), 1)

    def lists_match(self):
        return len(self.lists[0]) == len(self.lists[1])

    def _remember(self):
        self.history.append(([*self.lists[0]], [*self.lists[1]], self.row, self.side))

    def delete(self):
        items = self.lists[self.side]
        if self.row >= len(items):
            return
        self._remember()
        del items[self.row]
        self.message = "Link deleted: it's skipped from now on." if self.side == self.LINKS else "Name deleted."

    def add_name(self, text, below=True):
        names = self.lists[self.NAMES]
        position = min(self.row + (1 if below and self.row < len(names) else 0), len(names))
        self._remember()
        names.insert(position, text)
        self.row, self.side = position, self.NAMES

    def rename(self, text):
        if self.row < len(self.lists[self.NAMES]):
            self._remember()
            self.lists[self.NAMES][self.row] = text

    def move(self, step):
        items = self.lists[self.side]
        target = self.row + step
        if self.row < len(items) and 0 <= target < len(items):
            self._remember()
            items[self.row], items[target] = items[target], items[self.row]
            self.row = target

    def undo(self):
        if self.history:
            links, names, self.row, self.side = self.history.pop()
            self.lists = [links, names]
            self.message = "Undone."
        else:
            self.message = "Nothing to undo."

    # --- Drawing ---

    def _set_up_colors(self):
        self.attrs = {"header": curses.A_REVERSE, "warn": curses.A_BOLD, "ok": curses.A_BOLD, "mark": curses.A_BOLD,
                      "dim": curses.A_DIM}
        if not curses.has_colors():
            return
        curses.start_color()
        try:
            curses.use_default_colors()
            background = -1
        except curses.error:
            background = curses.COLOR_BLACK
        for number, (foreground, back) in enumerate([
            (curses.COLOR_WHITE, curses.COLOR_BLUE),  # header
            (curses.COLOR_RED, background),  # rows where only one side starts a week, missing lines
            (curses.COLOR_GREEN, background),  # the lists match
            (curses.COLOR_YELLOW, background),  # week marks
        ], start=1):
            curses.init_pair(number, foreground, back)
        self.attrs.update(header=curses.color_pair(1) | curses.A_BOLD, warn=curses.color_pair(2),
                          ok=curses.color_pair(3) | curses.A_BOLD, mark=curses.color_pair(4) | curses.A_BOLD)

    @staticmethod
    def _put(screen, y, x, text, width, attr=0):
        """Writes text cut or padded to width; never into the bottom-right cell, which curses refuses."""
        height, screen_width = screen.getmaxyx()
        width = min(width, screen_width - x - (1 if y == height - 1 else 0))
        if width <= 0:
            return
        try:
            screen.addnstr(y, x, text.ljust(width), width, attr)
        except curses.error:
            pass

    def draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 10 or width < 60:
            self._put(screen, 0, 0, "Make the terminal bigger (at least 60 x 10)", width)
            screen.refresh()
            return

        links, names = self.lists
        difference = len(links) - len(names)
        if difference == 0:
            status, status_attr = "the lists match, press s to save", self.attrs["ok"]
        elif difference > 0:
            status, status_attr = f"{difference} more links than names", self.attrs["warn"] | curses.A_BOLD
        else:
            status, status_attr = f"{-difference} more names than links", self.attrs["warn"] | curses.A_BOLD
        counts = f"Links {len(links)}  Names {len(names)}  "
        self._put(screen, 0, 0, f" Fix material names: {self.title}", width, self.attrs["header"])
        self._put(screen, 1, 0, " " + counts, len(counts) + 1, curses.A_BOLD)
        self._put(screen, 1, len(counts) + 1, status, width - len(counts) - 1, status_attr)
        self._put(screen, 2, 0, " Line N on the left gets the name on line N. '>' marks the first item of a week "
                                "on each side; red rows don't line up.", width, self.attrs["dim"])

        number_width = 5
        left_width = max(30, (width - number_width) * 2 // 5)
        right_x = number_width + left_width + 1
        right_width = width - right_x
        self._put(screen, 3, 0, "   #", number_width, curses.A_UNDERLINE)
        self._put(screen, 3, number_width, " Links (week, uploaded)", left_width, curses.A_UNDERLINE)
        self._put(screen, 3, right_x, " Names", right_width, curses.A_UNDERLINE)

        visible = height - 6
        self.row = max(0, min(self.row, self.row_count - 1))
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + visible:
            self.top = self.row - visible + 1

        starts_left, starts_right = week_starts(links, names)
        for line in range(visible):
            i = self.top + line
            if i >= self.row_count:
                break
            y = 4 + line
            both = i < len(links) and i < len(names)
            out_of_step = both and (i in starts_left) != (i in starts_right)
            self._put(screen, y, 0, f"{i + 1:>4}", number_width, self.attrs["warn"] if out_of_step else self.attrs["dim"])

            if i < len(links):
                link = links[i]
                left = f"{'>' if i in starts_left else ' '}{link_section(link):>6}  {describe_link(link)}"
                left_attr = self.attrs["warn"] if out_of_step else 0
            else:
                left, left_attr = "  (no link)", self.attrs["warn"]
            if i < len(names):
                right = f"{'>' if i in starts_right else ' '}{names[i]}"
                right_attr = self.attrs["warn"] if out_of_step else 0
            else:
                right, right_attr = "  (no name)", self.attrs["warn"]

            if i == self.row:
                left_attr |= curses.A_REVERSE if self.side == self.LINKS else curses.A_UNDERLINE
                right_attr |= curses.A_REVERSE if self.side == self.NAMES else curses.A_UNDERLINE
            self._put(screen, y, number_width, left, left_width, left_attr)
            self._put(screen, y, number_width + left_width, "|", 1, self.attrs["dim"])
            self._put(screen, y, right_x, right, right_width, right_attr)

        side_name = "links" if self.side == self.LINKS else "names"
        self._put(screen, height - 2, 0, f" [{side_name}] {self.message}", width, curses.A_BOLD)
        self._put(screen, height - 1, 0, " " + KEYS, width, self.attrs["dim"])
        screen.refresh()

    # --- Input ---

    @staticmethod
    def _show_cursor(visible):
        try:
            curses.curs_set(1 if visible else 0)
        except curses.error:  # the terminal can't hide or show it
            pass

    @staticmethod
    def _key(screen):
        while True:
            try:
                return screen.get_wch()
            except curses.error:  # interrupted, e.g. while the window is resized
                continue

    def _read_line(self, screen, label, text=""):
        """A one-line text field at the bottom; returns the text, or None for Esc."""
        height, width = screen.getmaxyx()
        position = len(text)
        self._show_cursor(True)
        try:
            while True:
                visible = width - len(label) - 2
                start = max(0, position - visible)
                self._put(screen, height - 2, 0, f" {label}{text[start:start + visible]}", width, curses.A_BOLD)
                screen.move(height - 2, 1 + len(label) + position - start)
                key = self._key(screen)
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return text.strip()
                if key == "\x1b":
                    return None
                if key in (curses.KEY_BACKSPACE, "\x7f", "\b") and position > 0:
                    text, position = text[:position - 1] + text[position:], position - 1
                elif key == curses.KEY_DC:
                    text = text[:position] + text[position + 1:]
                elif key == curses.KEY_LEFT:
                    position = max(0, position - 1)
                elif key == curses.KEY_RIGHT:
                    position = min(len(text), position + 1)
                elif key == curses.KEY_HOME:
                    position = 0
                elif key == curses.KEY_END:
                    position = len(text)
                elif isinstance(key, str) and key.isprintable():
                    text, position = text[:position] + key + text[position:], position + 1
        finally:
            self._show_cursor(False)

    def run(self, screen):
        if hasattr(curses, "set_escdelay"):
            curses.set_escdelay(25)  # Esc responds right away instead of after a second
        self._set_up_colors()
        screen.keypad(True)
        self._show_cursor(False)
        while True:
            self.draw(screen)
            key = self._key(screen)
            self.message = ""
            if key in (curses.KEY_UP, "k"):
                self.row -= 1
            elif key in (curses.KEY_DOWN, "j"):
                self.row += 1
            elif key == curses.KEY_PPAGE:
                self.row -= screen.getmaxyx()[0] - 7
            elif key == curses.KEY_NPAGE:
                self.row += screen.getmaxyx()[0] - 7
            elif key in (curses.KEY_HOME, "g"):
                self.row = 0
            elif key in (curses.KEY_END, "G"):
                self.row = self.row_count - 1
            elif key in ("\t", curses.KEY_BTAB, curses.KEY_LEFT, curses.KEY_RIGHT):
                self.side = 1 - self.side
            elif key in ("d", curses.KEY_DC):
                self.delete()
            elif key in ("a", "A"):
                text = self._read_line(screen, "New name, Enter adds it (Esc cancels): ")
                if text:
                    self.add_name(text, below=key == "a")
            elif key in ("e", "\n", "\r", curses.KEY_ENTER):
                if self.row < len(self.lists[self.NAMES]):
                    text = self._read_line(screen, "Name: ", self.lists[self.NAMES][self.row])
                    if text:
                        self.rename(text)
                        self.side = self.NAMES
            elif key == "K":
                self.move(-1)
            elif key == "J":
                self.move(1)
            elif key == "u":
                self.undo()
            elif key == "s":
                if self.lists_match():
                    return self.lists[0], self.lists[1]
                self.message = "The lists don't match yet: make both the same length first."
            elif key in ("q", "\x1b"):
                answer = self._read_line(screen, "Skip these materials for now? Type y and Enter: ")
                if answer and answer.lower().startswith("y"):
                    return None


def fix_in_terminal(links, names, title):
    """Opens the editor; returns the edited (links, names) when saved, or None when skipped."""
    locale.setlocale(locale.LC_ALL, "")
    return curses.wrapper(FixEditor(links, names, title).run)
