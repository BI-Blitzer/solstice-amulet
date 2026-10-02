"""Solstice Amulet: play a Sea of Stars day/night pair on one clock.

Both masters run from the same sample. The amulet dial sets their volumes and
the window art together, and it can sit anywhere between Day and Night.
Run with no arguments to open the window, or ``python player.py --test`` to
check pairing and playback.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import miniaudio
import numpy as np
from PIL import Image, ImageTk

def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


LIBRARY = Path(r"C:\Program Files (x86)\Steam\steamapps\music\Sea of Stars - OST")
SKIN = resource_root() / "skin"
RATE = 48000
RAMP_SEC = 1.8
PREFIX = re.compile(r"^\d+-\d+_")
SWING_DEG = 50.0
DIAL_TRAVEL = 200.0
ICON = 104

GOLD = "#e6b84a"
GOLD_DIM = "#6e5424"
INK = "#0c0a18"
PAPER = "#f4ecd6"
MUTED = "#c4cee8"
HOVER = "#241c38"
FAINT = "#5a546c"
FAINT_HOT = "#8a849c"
STEAM_URL = "https://store.steampowered.com/app/2550490/Sea_of_Stars__OST/"
GIT_URL = "https://github.com/BI-Blitzer/solstice-amulet"


@dataclass(frozen=True)
class Pair:
    title: str
    day: Path
    night: Path


def discover(root: Path) -> list[Pair]:
    groups: dict[str, dict] = {}
    for path in root.rglob("*.mp3"):
        stem = PREFIX.sub("", path.stem)
        low = stem.lower()
        kind = "plain"
        key = stem
        if low.endswith("_day"):
            kind, key = "day", stem[:-4]
        elif low.endswith("_night"):
            kind, key = "night", stem[:-6]
        rec = groups.setdefault(key.lower(), {"title": key, "day": None, "night": None, "plain": None})
        rec[kind] = path
        if kind == "day":
            rec["title"] = key
    pairs: list[Pair] = []
    for rec in groups.values():
        day = rec["day"] or (rec["plain"] if rec["night"] else None)
        night = rec["night"]
        if day and night:
            pairs.append(Pair(rec["title"].replace("_", " "), day, night))
    pairs.sort(key=lambda pair: pair.title.lower())
    return pairs


def load_stem(path: Path) -> np.ndarray:
    decoded = miniaudio.mp3_read_file_f32(str(path))
    if decoded.sample_rate != RATE or decoded.nchannels != 2:
        raw = decoded.samples.tobytes()
        converted = miniaudio.convert_frames(
            miniaudio.SampleFormat.FLOAT32,
            decoded.nchannels,
            decoded.sample_rate,
            raw,
            miniaudio.SampleFormat.FLOAT32,
            2,
            RATE,
        )
        samples = np.frombuffer(converted, dtype=np.float32).copy()
    else:
        samples = np.frombuffer(decoded.samples, dtype=np.float32).copy()
    return np.ascontiguousarray(samples.reshape(-1, 2))


def clamp01(t: float) -> float:
    return min(1.0, max(0.0, t))


def gains(t: float) -> tuple[float, float]:
    t = clamp01(t)
    return math.cos(t * math.pi * 0.5), math.sin(t * math.pi * 0.5)


def turn_degrees(t: float) -> float:
    """Day leans left (counter-clockwise), night leans right."""
    return SWING_DEG * (1.0 - 2.0 * clamp01(t))


def drag_t(origin: float, dx: float, travel: float = DIAL_TRAVEL) -> float:
    return clamp01(origin + dx / travel)


def sky_label(t: float) -> str:
    t = clamp01(t)
    if t <= 0.01:
        return "DAY"
    if t >= 0.99:
        return "NIGHT"
    day = int(round((1.0 - t) * 100))
    return f"DAY {day}   ·   NIGHT {100 - day}"


def compose_icon(day: np.ndarray, night: np.ndarray, t: float, size: int = ICON) -> Image.Image:
    g_day, g_night = gains(t)
    mixed = day.astype(np.float32) * g_day + night.astype(np.float32) * g_night
    image = Image.fromarray(mixed.clip(0, 255).astype(np.uint8), "RGBA")
    image = image.resize((size, size), Image.Resampling.NEAREST)
    return image.rotate(
        turn_degrees(t),
        resample=Image.Resampling.NEAREST,
        expand=False,
        fillcolor=(0, 0, 0, 0),
    )


class Engine:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.day: np.ndarray | None = None
        self.night: np.ndarray | None = None
        self.cursor = 0
        self.t = 0.0
        self.playing = False
        self.pair: Pair | None = None
        self.device = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=2,
            sample_rate=RATE,
            buffersize_msec=50,
        )
        generator = self._generate()
        next(generator)
        self.device.start(generator)

    def close(self) -> None:
        self.playing = False
        self.device.close()

    def load(self, pair: Pair) -> None:
        day = load_stem(pair.day)
        night = load_stem(pair.night)
        with self.lock:
            self.day = day
            self.night = night
            self.cursor = 0
            self.pair = pair

    def set_t(self, t: float) -> None:
        with self.lock:
            self.t = clamp01(t)

    def seek(self, seconds: float) -> None:
        with self.lock:
            if self.day is None or self.night is None:
                return
            loop = min(len(self.day), len(self.night))
            self.cursor = int(min(max(seconds, 0.0), (loop - 1) / RATE) * RATE)

    def position(self) -> tuple[float, float]:
        with self.lock:
            if self.day is None or self.night is None:
                return 0.0, 0.0
            loop = min(len(self.day), len(self.night))
            return self.cursor / RATE, loop / RATE

    def _generate(self):
        frames = yield b""
        while True:
            frames = yield self._mix(frames)

    def _mix(self, frames: int) -> np.ndarray:
        try:
            with self.lock:
                day, night = self.day, self.night
                if day is None or night is None or not self.playing:
                    return np.zeros((frames, 2), np.float32)
                g_day, g_night = gains(self.t)
                loop = min(len(day), len(night))
                cursor = self.cursor
                out = np.empty((frames, 2), np.float32)
                filled = 0
                while filled < frames:
                    if cursor >= loop:
                        cursor = 0
                    count = min(frames - filled, loop - cursor)
                    out[filled : filled + count] = (
                        day[cursor : cursor + count] * g_day
                        + night[cursor : cursor + count] * g_night
                    )
                    cursor += count
                    filled += count
                self.cursor = cursor
            np.clip(out, -1.0, 1.0, out)
            return out
        except Exception:
            return np.zeros((frames, 2), np.float32)


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class SolsticeDial(tk.Canvas):
    """Horizontal dial. Left is Day, right is Night. Drag parks between them."""

    W = 292
    H = 148
    CX = 146
    CY = 74
    R = ICON // 2 + 6
    TRACK = "#8d6b32"

    def __init__(self, master: tk.Misc, on_t, on_ease) -> None:
        super().__init__(
            master,
            width=self.W,
            height=self.H,
            bg=INK,
            highlightthickness=0,
            bd=0,
            cursor="sb_h_double_arrow",
        )
        self.on_t = on_t
        self.on_ease = on_ease
        self.t = 0.0
        self._photo: ImageTk.PhotoImage | None = None
        self._origin: tuple[float, float] | None = None
        self._moved = False
        self._font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_photo(self, photo: ImageTk.PhotoImage) -> None:
        self._photo = photo
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        t = clamp01(self.t)
        box = (self.CX - self.R, self.CY - self.R, self.CX + self.R, self.CY + self.R)
        self.create_arc(box, start=0, extent=180, style=tk.ARC, outline=self.TRACK, width=3)
        if t > 0.004:
            self.create_arc(
                box,
                start=180 * (1.0 - t),
                extent=180 * t,
                style=tk.ARC,
                outline=GOLD,
                width=4,
            )
        if self._photo is not None:
            self.create_image(self.CX, self.CY, image=self._photo)
        theta = math.pi * (1.0 - t)
        px = self.CX + self.R * math.cos(theta)
        py = self.CY - self.R * math.sin(theta)
        self.create_oval(px - 5, py - 5, px + 5, py + 5, fill=GOLD, outline=PAPER, width=2)
        day_ink = GOLD if t < 0.85 else MUTED
        night_ink = GOLD if t > 0.15 else MUTED
        self.create_text(self.CX - self.R - 10, self.CY, text="DAY", fill=day_ink, font=self._font, anchor="e")
        self.create_text(self.CX + self.R + 10, self.CY, text="NIGHT", fill=night_ink, font=self._font, anchor="w")

    def _press(self, event: tk.Event) -> None:
        self._origin = (event.x, self.t)
        self._moved = False

    def _motion(self, event: tk.Event) -> None:
        if self._origin is None:
            return
        dx = event.x - self._origin[0]
        if abs(dx) > 3:
            self._moved = True
        if self._moved:
            self.on_t(drag_t(self._origin[1], dx))

    def _release(self, event: tk.Event) -> None:
        if self._origin is None:
            return
        dx = event.x - self._origin[0]
        origin = self._origin[1]
        self._origin = None
        if not self._moved:
            width = self.winfo_width() if self.winfo_width() > 1 else self.W
            edge = self.CX - ICON // 2 - 6
            if event.x <= edge:
                self.on_ease(0.0)
            elif event.x >= width - edge:
                self.on_ease(1.0)
            return
        self.on_t(drag_t(origin, dx), force=True)

    def _wheel(self, event: tk.Event) -> str:
        step = 0.035 if event.delta > 0 else -0.035
        self.on_t(clamp01(self.t + step))
        return "break"


class ScoreList(tk.Canvas):
    HEADER = 122
    ROW = 32
    FOOT = 32

    def __init__(self, master: tk.Misc, titles: list[str], command) -> None:
        super().__init__(master, bg=INK, highlightthickness=0, bd=0, cursor="hand2")
        self.titles = titles
        self.command = command
        self.selected = 0
        self.hover = -1
        self.offset = 0
        self._drag: tuple[int, int] | None = None
        self.font = tkfont.Font(family="Segoe UI", size=11)
        self.font_bold = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.font_header = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.font_sub = tkfont.Font(family="Segoe UI", size=9)
        self.font_num = tkfont.Font(family="Segoe UI", size=9)
        self.font_faint = tkfont.Font(family="Segoe UI", size=8)
        self._links: list[tuple[tuple[int, int, int, int], str]] = []
        self._link = -1
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda _e: self._end_drag())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", self._leave)
        self.bind("<MouseWheel>", self._wheel)

    def select(self, index: int) -> None:
        self.selected = index
        self._ensure(index)
        self.redraw()

    def _on_configure(self, _event: tk.Event) -> None:
        if self.winfo_height() > self.HEADER + self.ROW:
            self._ensure(self.selected)
        self.redraw()

    def _mark(self, x: int, y: int, fill: str, radius: int = 4) -> None:
        self.create_polygon(x, y - radius, x + radius, y, x, y + radius, x - radius, y, fill=fill, outline="")

    def redraw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        inset = 7
        self.create_rectangle(inset, inset, width - inset, height - inset, outline=GOLD_DIM)
        for cx, cy in (
            (inset, inset),
            (width - inset, inset),
            (inset, height - inset),
            (width - inset, height - inset),
        ):
            self._mark(cx, cy, GOLD, 4)
        self._mark(24, 24, GOLD, 5)
        self.create_text(38, 24, text="Sea of Stars", fill=GOLD, font=self.font_header, anchor="w")
        self.create_text(38, 42, text="Original Soundtrack", fill=PAPER, font=self.font_sub, anchor="w")
        self.create_text(38, 62, text="Eric W. Brown", fill=MUTED, font=self.font_sub, anchor="w")
        self.create_text(38, 78, text="Yasunori Mitsuda", fill=MUTED, font=self.font_faint, anchor="w")
        self.create_text(38, 94, text="Vincent Jones   ·   Reece Miller", fill=MUTED, font=self.font_faint, anchor="w")
        self.create_line(22, 110, width - 22, 110, fill=GOLD)
        view = self._view()
        content = len(self.titles) * self.ROW
        max_off = max(0, content - view)
        self.offset = min(max_off, max(0, self.offset))
        gutter = 26 if max_off else 16
        y = self.HEADER - self.offset
        for index, title in enumerate(self.titles):
            if y < self.HEADER:
                y += self.ROW
                continue
            if y > self.HEADER + view:
                break
            selected = index == self.selected
            if selected:
                self.create_rectangle(16, y + 3, width - gutter, y + self.ROW - 3, fill=GOLD, outline="")
                ink = INK
                num = INK
                font = self.font_bold
            elif index == self.hover:
                self.create_rectangle(16, y + 3, width - gutter, y + self.ROW - 3, fill=HOVER, outline=GOLD_DIM)
                ink = PAPER
                num = GOLD
                font = self.font
            else:
                ink = PAPER
                num = GOLD_DIM
                font = self.font
            self.create_text(28, y + self.ROW / 2, text=f"{index + 1:02d}", fill=num, font=self.font_num, anchor="w")
            shown = self._fit(title, font, width - gutter - 58)
            self.create_text(54, y + self.ROW / 2, text=shown, fill=ink, font=font, anchor="w")
            y += self.ROW
        if max_off:
            thumb_h = max(28, int(view * view / content))
            travel = max(1, view - thumb_h)
            thumb_y = self.HEADER + int(self.offset * travel / max_off)
            track_bottom = self.HEADER + view
            self.create_rectangle(width - 16, self.HEADER, width - 10, track_bottom, fill="#1a1630", outline="")
            self.create_rectangle(width - 16, thumb_y, width - 10, min(track_bottom, thumb_y + thumb_h), fill=GOLD, outline="")
        self._draw_links(width, height)

    def _draw_links(self, width: int, height: int) -> None:
        self._links = []
        y = height - 16
        steam_fill = FAINT_HOT if self._link == 0 else FAINT
        git_fill = FAINT_HOT if self._link == 1 else FAINT
        steam = self.create_text(20, y, text="Steam", fill=steam_fill, font=self.font_faint, anchor="w")
        git = self.create_text(width - 20, y, text="BI-Blitzer", fill=git_fill, font=self.font_faint, anchor="e")
        for item, url in ((steam, STEAM_URL), (git, GIT_URL)):
            box = self.bbox(item)
            if box is None:
                continue
            x1, y1, x2, y2 = box
            self._links.append(((x1 - 4, y1 - 4, x2 + 4, y2 + 4), url))

    def _link_at(self, x: int, y: int) -> int:
        for index, (box, _url) in enumerate(self._links):
            x1, y1, x2, y2 = box
            if x1 <= x <= x2 and y1 <= y <= y2:
                return index
        return -1

    def _fit(self, text: str, font: tkfont.Font, max_w: int) -> str:
        if font.measure(text) <= max_w:
            return text
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi) // 2
            if font.measure(text[:mid].rstrip() + "…") <= max_w:
                lo = mid + 1
            else:
                hi = mid
        return text[: max(1, lo - 1)].rstrip() + "…"

    def _view(self) -> int:
        return max(1, self.winfo_height() - self.HEADER - self.FOOT)

    def _max_offset(self) -> int:
        return max(0, len(self.titles) * self.ROW - self._view())

    def _ensure(self, index: int) -> None:
        if self.winfo_height() <= self.HEADER + self.ROW:
            return
        view = self._view()
        target = index * self.ROW - max(0, (view - self.ROW) // 2)
        self.offset = int(min(self._max_offset(), max(0, target)))

    def _thumb(self) -> tuple[int, int, int, int] | None:
        max_off = self._max_offset()
        if max_off <= 0:
            return None
        view = self._view()
        content = len(self.titles) * self.ROW
        thumb_h = max(28, int(view * view / content))
        travel = max(1, view - thumb_h)
        thumb_y = self.HEADER + int(self.offset * travel / max_off)
        return max_off, thumb_h, thumb_y, travel

    def _press(self, event: tk.Event) -> None:
        link = self._link_at(event.x, event.y)
        if link >= 0:
            webbrowser.open(self._links[link][1])
            return
        if event.y >= self.winfo_height() - self.FOOT:
            return
        width = max(1, self.winfo_width())
        thumb = self._thumb()
        if thumb and event.x >= width - 20:
            max_off, thumb_h, thumb_y, travel = thumb
            if not (thumb_y <= event.y <= thumb_y + thumb_h):
                frac = clamp01((event.y - self.HEADER - thumb_h / 2) / travel)
                self.offset = int(frac * max_off)
                self.redraw()
            self._drag = (event.y, self.offset)
            return
        if event.y < self.HEADER:
            return
        index = int((event.y - self.HEADER + self.offset) // self.ROW)
        if 0 <= index < len(self.titles):
            self.command(index)

    def _motion(self, event: tk.Event) -> None:
        if self._drag is None:
            return
        thumb = self._thumb()
        if thumb is None:
            return
        max_off, _thumb_h, _thumb_y, travel = thumb
        start_y, start_off = self._drag
        self.offset = int(min(max_off, max(0, start_off + (event.y - start_y) * max_off / travel)))
        self.redraw()

    def _end_drag(self) -> None:
        self._drag = None

    def _hover(self, event: tk.Event) -> None:
        link = self._link_at(event.x, event.y)
        if link != self._link:
            self._link = link
            self.redraw()
        if self._drag is not None or event.y < self.HEADER or event.y >= self.winfo_height() - self.FOOT:
            self._set_hover(-1)
            return
        index = int((event.y - self.HEADER + self.offset) // self.ROW)
        self._set_hover(index if 0 <= index < len(self.titles) else -1)

    def _leave(self, _event: tk.Event) -> None:
        changed = self._link != -1 or self.hover != -1
        self._link = -1
        self.hover = -1
        if changed:
            self.redraw()

    def _set_hover(self, index: int) -> None:
        if index == self.hover:
            return
        self.hover = index
        self.redraw()

    def _wheel(self, event: tk.Event) -> str:
        self.offset -= int(event.delta / 120) * self.ROW
        self.redraw()
        return "break"


class GoldSeek(tk.Canvas):
    def __init__(self, master: tk.Misc, command) -> None:
        super().__init__(master, height=22, bg=INK, highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.dragging = False
        self.frac = 0.0
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def set_frac(self, frac: float) -> None:
        if self.dragging:
            return
        self.frac = clamp01(frac)
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        self.create_rectangle(0, 7, width, 15, outline=GOLD, fill="#161226")
        filled = 2 + (width - 4) * self.frac
        if filled > 3:
            self.create_rectangle(2, 9, filled, 13, outline="", fill=GOLD)

    def _at(self, x: int) -> float:
        width = max(1, self.winfo_width() - 4)
        return clamp01((x - 2) / width)

    def _press(self, event: tk.Event) -> None:
        self.dragging = True
        self.frac = self._at(event.x)
        self.redraw()
        self.command(self.frac)

    def _release(self, event: tk.Event) -> None:
        self.frac = self._at(event.x)
        self.dragging = False
        self.redraw()
        self.command(self.frac)


class App(tk.Tk):
    def __init__(self, pairs: list[Pair], engine: Engine) -> None:
        super().__init__()
        self.pairs = pairs
        self.engine = engine
        self.title("Solstice Amulet")
        self.geometry("1280x720")
        self.minsize(960, 560)
        self.configure(bg=INK)
        self._dead = False
        self._ramp_after: str | None = None
        self._bg_wait: str | None = None
        self._load_after: str | None = None
        self._bg_at = 0.0
        self._played_once = False
        self._index = -1
        self._canvas_size = (0, 0)
        self.day_plate = Image.open(SKIN / "bg-day.jpg").convert("RGB")
        self.night_plate = Image.open(SKIN / "bg-night.jpg").convert("RGB")
        self.day_icon = np.asarray(Image.open(SKIN / "amulet-day.png").convert("RGBA"))
        self.night_icon = np.asarray(Image.open(SKIN / "amulet-night.png").convert("RGBA"))
        self.day_bg: np.ndarray | None = None
        self.night_bg: np.ndarray | None = None
        self.bg_photo: ImageTk.PhotoImage | None = None
        self.icon_photo: ImageTk.PhotoImage | None = None
        mark_image = Image.open(SKIN / "amulet-icon.png").convert("RGBA")
        self._marks = [
            ImageTk.PhotoImage(mark_image.resize((size, size), Image.Resampling.NEAREST))
            for size in (16, 32, 48, 64)
        ]
        self.iconphoto(True, *self._marks)

        self.canvas = tk.Canvas(self, bg=INK, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.bg_item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Configure>", self._on_resize)

        self.list_shell = tk.Frame(self.canvas, bg=GOLD)
        self.list_shell.pack_propagate(False)
        list_body = tk.Frame(self.list_shell, bg=INK, highlightbackground=GOLD_DIM, highlightthickness=1)
        list_body.pack(fill="both", expand=True, padx=3, pady=3)
        self.score = ScoreList(list_body, [pair.title for pair in pairs], self._load)
        self.score.pack(fill="both", expand=True, padx=6, pady=6)
        self.list_window = self.canvas.create_window(16, 16, anchor="sw", window=self.list_shell)

        dock_shell = tk.Frame(self.canvas, bg=GOLD)
        dock = tk.Frame(dock_shell, bg=INK, highlightbackground=GOLD_DIM, highlightthickness=1)
        dock.pack(fill="both", expand=True, padx=2, pady=2)
        self.dial = SolsticeDial(dock, on_t=self._dial_t, on_ease=self._animate_to)
        self.dial.grid(row=0, column=0, padx=(8, 4), pady=6)
        text = tk.Frame(dock, bg=INK)
        text.grid(row=0, column=1, sticky="nsew", padx=(4, 12), pady=12)
        dock.columnconfigure(1, weight=1)
        dock.rowconfigure(0, weight=1)
        self.seek = GoldSeek(text, self._on_seek_frac)
        self.seek.pack(side="bottom", fill="x")
        self.kicker = tk.Label(text, text="SOLSTICE AMULET", fg=GOLD, bg=INK, font=("Segoe UI", 10, "bold"))
        self.kicker.pack(side="top", anchor="w")
        self.song = tk.Label(text, text="", fg=PAPER, bg=INK, font=("Segoe UI", 16, "bold"), anchor="w", justify="left")
        self.song.pack(side="top", anchor="w", pady=(4, 0))
        row = tk.Frame(text, bg=INK)
        row.pack(side="top", fill="x", pady=(10, 0))
        self.play_btn = tk.Label(
            row, text="PLAY", bg=GOLD, fg=INK, font=("Segoe UI", 10, "bold"), padx=16, pady=5, cursor="hand2"
        )
        self.play_btn.pack(side="right")
        self.play_btn.bind("<Button-1>", lambda _e: self.toggle_play())
        self.play_btn.bind("<Enter>", lambda _e: self.play_btn.configure(bg="#f3d78a"))
        self.play_btn.bind("<Leave>", lambda _e: self.play_btn.configure(bg=GOLD))
        self.state = tk.Label(row, text="DAY", fg=PAPER, bg=INK, font=("Segoe UI", 11))
        self.state.pack(side="left")
        self.dock_shell = dock_shell
        self.dock_window = self.canvas.create_window(16, 16, anchor="sw", window=dock_shell)

        self.bind_all("<Left>", lambda e: self._nudge(e, -1))
        self.bind_all("<Right>", lambda e: self._nudge(e, 1))
        self.bind_all("<Up>", lambda e: self._move(-1))
        self.bind_all("<Down>", lambda e: self._move(1))
        self.bind_all("<space>", self._on_space)
        self.protocol("WM_DELETE_WINDOW", self._close)

        start = next((i for i, pair in enumerate(pairs) if pair.title == "The Mountain Trail"), 0)
        self._load(start)
        self.after(100, self._poll)

    def _close(self) -> None:
        self._dead = True
        for token in (self._ramp_after, self._bg_wait, self._load_after):
            if token:
                self.after_cancel(token)
        self.engine.close()
        self.destroy()

    def _on_resize(self, event: tk.Event) -> None:
        size = (event.width, event.height)
        if size == self._canvas_size or event.width < 32 or event.height < 32:
            return
        self._canvas_size = size
        self.day_bg = np.asarray(self.day_plate.resize(size, Image.Resampling.BILINEAR), dtype=np.float32)
        self.night_bg = np.asarray(self.night_plate.resize(size, Image.Resampling.BILINEAR), dtype=np.float32)
        list_w = 348
        list_h = min(460, max(280, event.height - 220))
        self.list_shell.configure(width=list_w, height=list_h)
        self.canvas.coords(self.list_window, 16, event.height - 16)
        self.canvas.itemconfigure(self.list_window, width=list_w, height=list_h)
        dock_x = 16 + list_w + 12
        dock_w = min(720, max(420, event.width - dock_x - 16))
        self.canvas.coords(self.dock_window, dock_x, event.height - 16)
        self.canvas.itemconfigure(self.dock_window, width=dock_w)
        self.song.configure(wraplength=max(160, dock_w - 340))
        self._paint_bg()
        self._present_dial()

    def _load(self, index: int) -> None:
        if self._load_after:
            self.after_cancel(self._load_after)
            self._load_after = None
        if index == self._index and self.engine.pair is self.pairs[index]:
            self.score.select(index)
            return
        self._index = index
        self.score.select(index)
        pair = self.pairs[index]
        self.song.configure(text="Loading…")
        self.update_idletasks()
        self.engine.load(pair)
        self.song.configure(text=pair.title)
        self.seek.set_frac(0)
        self._status()
        self._present_dial()
        self._paint_bg()

    def _move(self, delta: int) -> str:
        if self._dead:
            return "break"
        current = self.score.selected
        index = min(len(self.pairs) - 1, max(0, current + delta))
        self.score.select(index)
        if self._load_after:
            self.after_cancel(self._load_after)
        self._load_after = self.after(130, lambda: self._load(index))
        return "break"

    def _on_space(self, _event: tk.Event) -> str:
        self.toggle_play()
        return "break"

    def toggle_play(self) -> None:
        self.engine.playing = not self.engine.playing
        self._played_once = True
        self.play_btn.configure(text="PAUSE" if self.engine.playing else "PLAY")

    def _nudge(self, event: tk.Event, sign: int) -> str:
        if self._dead:
            return "break"
        step = 0.008 if event.state & 0x0001 else 0.02
        self._cancel_ramp()
        self._apply_t(self.engine.t + sign * step)
        return "break"

    def _dial_t(self, t: float, force: bool = False) -> None:
        self._cancel_ramp()
        self._apply_t(t, force=force)

    def _cancel_ramp(self) -> None:
        if self._ramp_after:
            self.after_cancel(self._ramp_after)
            self._ramp_after = None

    def _animate_to(self, target: float) -> None:
        self._cancel_ramp()
        start = self.engine.t
        target = clamp01(target)
        dist = abs(target - start)
        if dist < 0.001:
            self._apply_t(target, force=True)
            return
        duration = max(0.45, RAMP_SEC * dist)
        elapsed = 0.0
        last = time.perf_counter()

        def step() -> None:
            nonlocal elapsed, last
            if self._dead:
                return
            now = time.perf_counter()
            # A pause holds the turn where it is. Before the first play, the
            # mark still eases so the sky can be set ahead of the music.
            if self.engine.playing or not self._played_once:
                elapsed += now - last
            last = now
            u = min(1.0, elapsed / duration)
            eased = u * u * (3.0 - 2.0 * u)
            self._apply_t(start + (target - start) * eased, force=u >= 1.0)
            if u < 1.0:
                self._ramp_after = self.after(32, step)
            else:
                self._ramp_after = None

        step()

    def _apply_t(self, t: float, force: bool = False) -> None:
        t = clamp01(t)
        self.engine.set_t(t)
        self.dial.t = t
        self._status()
        self._present_dial()
        now = time.perf_counter()
        due = now - self._bg_at >= 0.032
        if force or due:
            if self._bg_wait:
                self.after_cancel(self._bg_wait)
                self._bg_wait = None
            self._paint_bg()
        elif self._bg_wait is None:
            delay = max(1, int((0.032 - (now - self._bg_at)) * 1000))
            self._bg_wait = self.after(delay, self._flush_bg)

    def _flush_bg(self) -> None:
        self._bg_wait = None
        if not self._dead:
            self._paint_bg()

    def _on_seek_frac(self, frac: float) -> None:
        _pos, length = self.engine.position()
        self.engine.seek(frac * length)

    def _status(self, pos: float | None = None, length: float | None = None) -> None:
        if pos is None or length is None:
            pos, length = self.engine.position()
        self.state.configure(text=f"{sky_label(self.engine.t)}      {clock(pos)} / {clock(length)}")

    def _poll(self) -> None:
        if self._dead:
            return
        pos, length = self.engine.position()
        if length > 0:
            self.seek.set_frac(pos / length)
        self._status(pos, length)
        self.after(100, self._poll)

    def _present_dial(self) -> None:
        icon = compose_icon(self.day_icon, self.night_icon, self.engine.t, ICON)
        self.icon_photo = ImageTk.PhotoImage(icon)
        self.dial.set_photo(self.icon_photo)

    def _paint_bg(self) -> None:
        if self.day_bg is None or self.night_bg is None:
            return
        g_day, g_night = gains(self.engine.t)
        plate = self.day_bg * g_day + self.night_bg * g_night
        image = Image.fromarray(plate.clip(0, 255).astype(np.uint8), "RGB")
        self.bg_photo = ImageTk.PhotoImage(image)
        self.canvas.itemconfigure(self.bg_item, image=self.bg_photo)
        self._bg_at = time.perf_counter()


def selftest(root: Path) -> None:
    if turn_degrees(0) <= 0 or turn_degrees(1) >= 0 or abs(turn_degrees(0.5)) > 1e-6:
        raise SystemExit("amulet turn direction is wrong")
    if drag_t(0.25, 50, 200) != 0.5 or drag_t(0.9, 80, 200) != 1.0 or drag_t(0.1, -80, 200) != 0.0:
        raise SystemExit("dial drag does not park inside the range")
    if sky_label(0) != "DAY" or sky_label(1) != "NIGHT" or "NIGHT" not in sky_label(0.4):
        raise SystemExit("sky label missed an in-between mix")
    day = np.asarray(Image.open(SKIN / "amulet-day.png").convert("RGBA"))
    night = np.asarray(Image.open(SKIN / "amulet-night.png").convert("RGBA"))
    icon = compose_icon(day, night, 0.35, 96)
    if icon.size != (96, 96) or icon.mode != "RGBA":
        raise SystemExit("dial icon did not compose")
    pairs = discover(root)
    if len(pairs) != 19:
        raise SystemExit(f"expected 19 pairs, found {len(pairs)}")
    trail = next(pair for pair in pairs if pair.title == "The Mountain Trail")
    jungle = next(pair for pair in pairs if pair.title == "Through The Jungle")
    engine = Engine()
    try:
        engine.load(trail)
        if engine.day is None or engine.night is None or engine.day.shape != engine.night.shape:
            raise SystemExit("Mountain Trail stems differ after load")
        engine.load(jungle)
        if engine.day is None or engine.night is None or engine.day.shape[1] != 2:
            raise SystemExit("Jungle did not resample to stereo")
        engine.load(trail)
        engine.playing = True
        time.sleep(0.45)
        engine.set_t(0.4)
        mid = engine.cursor
        time.sleep(0.55)
        pos, _length = engine.position()
        if pos < 0.4:
            raise SystemExit(f"playback did not advance ({pos:.2f}s)")
        if engine.cursor <= mid:
            raise SystemExit("dial moved the playhead")
        if abs(engine.t - 0.4) > 1e-6:
            raise SystemExit("mix parameter did not hold")
    finally:
        engine.close()
    print(f"ok {len(pairs)} pairs, playback advanced {pos:.2f}s, dial holds the beat")


def main() -> None:
    parser = argparse.ArgumentParser(description="Solstice Amulet day/night player")
    parser.add_argument("--library", type=Path, default=LIBRARY)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if not args.library.is_dir():
        raise SystemExit(f"library not found: {args.library}")
    if args.test:
        selftest(args.library)
        return
    pairs = discover(args.library)
    if not pairs:
        raise SystemExit(f"no day/night pairs in {args.library}")
    engine = Engine()
    app = App(pairs, engine)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
