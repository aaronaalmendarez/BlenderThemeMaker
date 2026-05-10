import base64
import json
import os
import subprocess
import tempfile
import threading
import tkinter as tk
import urllib.request
import uuid
from datetime import datetime
from tkinter import colorchooser, filedialog, messagebox, scrolledtext, simpledialog, ttk

from PIL import Image, ImageGrab, ImageTk


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
GEMINI_MODEL = "gemini-3-flash-preview"
APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BlenderThemeMaker")
HISTORY_PATH = os.path.join(APP_DATA_DIR, "theme_history.json")

ROLE_KEYS = (
    "background",
    "panel",
    "panel_header",
    "accent",
    "accent_secondary",
    "outline",
    "text",
    "muted_text",
    "grid",
)

COLOR_KEYS = ROLE_KEYS + (
    "gradient_start",
    "gradient_end",
)

DEFAULT_PALETTE = {
    "background": "#0b0203",
    "panel": "#210508",
    "panel_header": "#41070d",
    "accent": "#ff1430",
    "accent_secondary": "#ff6a1f",
    "outline": "#8a1018",
    "text": "#ffe9e3",
    "muted_text": "#bf7772",
    "grid": "#75101a",
    "gradient_enabled": True,
    "gradient_type": "LINEAR",
    "gradient_start": "#190306",
    "gradient_end": "#4a0710",
}


APPLY_SCRIPT = r'''
import json
import bpy

ROLE_KEYS = (
    "background", "panel", "panel_header", "accent", "accent_secondary",
    "outline", "text", "muted_text", "grid",
)
COLOR_KEYS = ROLE_KEYS + ("gradient_start", "gradient_end")
DEFAULT_EXTRAS = {
    "gradient_enabled": True,
    "gradient_type": "LINEAR",
    "gradient_start": "#190306",
    "gradient_end": "#4a0710",
}

def hex_to_rgba(value, alpha=1.0):
    value = str(value).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)

def rgba_to_hex(value):
    rgb = [max(0, min(255, round(channel * 255))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def saturation(color):
    rgb = color[:3]
    return max(rgb) - min(rgb)

def set_color(owner, attr, value):
    if not hasattr(owner, attr):
        return
    current = getattr(owner, attr)
    try:
        if hasattr(current, "__len__") and not isinstance(current, str):
            if len(current) == 3:
                setattr(owner, attr, value[:3])
            elif len(current) == 4:
                setattr(owner, attr, value)
        else:
            setattr(owner, attr, value)
    except Exception:
        pass

def mix_color(a, b, amount):
    return tuple(a[i] + (b[i] - a[i]) * amount for i in range(3)) + (1.0,)

def rebalance_palette(raw_palette):
    raw_palette = dict(raw_palette)
    colors = {key: hex_to_rgba(raw_palette[key]) for key in COLOR_KEYS if key in raw_palette}
    if not all(key in colors for key in ("panel", "panel_header", "gradient_start", "gradient_end")):
        return raw_palette
    gradient_sat = max(saturation(colors["gradient_start"]), saturation(colors["gradient_end"]))
    panel_sat = saturation(colors["panel"])
    if gradient_sat > 0.18 and panel_sat < 0.08:
        raw_palette["panel"] = rgba_to_hex(mix_color(colors["panel"], colors["gradient_start"], 0.35))
        raw_palette["panel_header"] = rgba_to_hex(mix_color(colors["panel_header"], colors["gradient_end"], 0.35))
    return raw_palette

def set_space(space, palette, background=None):
    background = background or palette["background"]
    if palette["gradient_enabled"]:
        background = palette["surface_low"]
    set_color(space, "back", background)
    if hasattr(space, "gradients"):
        try:
            if palette["gradient_enabled"]:
                space.gradients.background_type = palette["gradient_type"]
                space.gradients.gradient = palette["gradient_start"][:3]
                space.gradients.high_gradient = palette["gradient_end"][:3]
            else:
                space.gradients.background_type = "SINGLE_COLOR"
                space.gradients.gradient = background[:3]
                space.gradients.high_gradient = palette["panel"][:3]
        except Exception:
            pass
    for attr, value in {
        "title": palette["text"],
        "text": palette["text"],
        "text_hi": (1.0, 0.96, 0.94, 1.0),
        "header": palette["surface_high"],
        "header_text": palette["text"],
        "header_text_hi": (1.0, 0.96, 0.94, 1.0),
    }.items():
        set_color(space, attr, value)

def apply_theme_palette(raw_palette):
    raw_palette = {**DEFAULT_EXTRAS, **raw_palette}
    raw_palette = rebalance_palette(raw_palette)
    palette = {key: hex_to_rgba(raw_palette[key]) for key in COLOR_KEYS}
    palette["gradient_enabled"] = bool(raw_palette.get("gradient_enabled", True))
    gradient_type = str(raw_palette.get("gradient_type", "LINEAR")).upper()
    palette["gradient_type"] = gradient_type if gradient_type in {"LINEAR", "RADIAL", "SINGLE_COLOR"} else "LINEAR"
    low = mix_color(palette["panel"], palette["gradient_start"], 0.24) if palette["gradient_enabled"] else palette["panel"]
    high = mix_color(palette["panel_header"], palette["gradient_end"], 0.32) if palette["gradient_enabled"] else palette["panel_header"]
    palette["surface_low"] = low
    palette["surface_high"] = high
    theme = bpy.context.preferences.themes[0]
    theme.name = "cool blender ui thingy"
    ui = theme.user_interface

    for attr in (
        "wcol_regular", "wcol_tool", "wcol_toolbar_item", "wcol_radio", "wcol_text",
        "wcol_option", "wcol_toggle", "wcol_num", "wcol_numslider", "wcol_box",
        "wcol_curve", "wcol_menu", "wcol_pulldown", "wcol_menu_back",
        "wcol_pie_menu", "wcol_tooltip", "wcol_menu_item", "wcol_scroll",
        "wcol_progress", "wcol_list_item", "wcol_state", "wcol_tab",
    ):
        widget = getattr(ui, attr, None)
        if not widget:
            continue
        for widget_attr, value in {
            "outline": palette["outline"],
            "outline_sel": palette["accent"],
            "inner": low,
            "inner_sel": palette["accent"],
            "item": palette["accent_secondary"],
            "text": palette["text"],
            "text_sel": (1.0, 0.96, 0.94, 1.0),
            "shadetop": high,
            "shadedown": low,
            "roundness": 0.18,
        }.items():
            set_color(widget, widget_attr, value)

    for attr, value in {
        "panel_roundness": 0.15,
        "panel_header": high,
        "panel_title": palette["text"],
        "panel_text": palette["muted_text"],
        "panel_back": low,
        "panel_sub_back": low,
        "panel_outline": palette["outline"],
        "panel_active": palette["accent"],
        "editor_border": palette["outline"],
        "editor_outline": palette["outline"],
        "editor_outline_active": palette["accent"],
        "widget_emboss": palette["outline"],
        "icon_alpha": 1.0,
        "icon_saturation": 1.0,
    }.items():
        set_color(ui, attr, value)

    for editor_name in (
        "view_3d", "properties", "outliner", "dopesheet_editor", "graph_editor",
        "nla_editor", "image_editor", "sequence_editor", "node_editor", "text_editor",
        "file_browser", "preferences", "console", "clip_editor", "spreadsheet",
        "topbar", "statusbar", "info",
    ):
        editor = getattr(theme, editor_name, None)
        if editor and hasattr(editor, "space"):
            set_space(editor.space, palette)

    view = theme.view_3d
    for attr, value in {
        "grid": (*palette["grid"][:3], 0.45),
        "grid_major": (*palette["outline"][:3], 0.75),
        "clipping_border_3d": palette["outline"],
        "wire": palette["accent"],
        "wire_edit": palette["accent"],
        "object_selected": palette["accent"],
        "object_active": palette["accent_secondary"],
        "camera": palette["accent"],
        "empty": palette["accent"],
        "light": (*palette["accent_secondary"][:3], 0.7),
        "view_overlay": palette["background"],
    }.items():
        set_color(view, attr, value)

    regions = theme.regions
    for owner, mapping in (
        (regions.asset_shelf, {"back": low, "header_back": high}),
        (regions.channels, {"back": low, "text": palette["muted_text"], "text_selected": palette["text"]}),
        (regions.scrubbing, {"back": low, "text": palette["text"], "time_marker": palette["accent"], "time_marker_selected": palette["accent_secondary"]}),
        (regions.sidebars, {"back": low, "tab_back": high}),
    ):
        for attr, value in mapping.items():
            set_color(owner, attr, value)

    anim = theme.common.anim
    for attr, value in {
        "playhead": palette["accent"],
        "preview_range": (*palette["outline"][:3], 0.35),
        "scene_strip_range": (*palette["outline"][:3], 0.35),
        "channels": low,
        "channels_sub": low,
        "channel_group": high,
        "channel_group_active": palette["accent"],
        "channel": low,
        "channel_selected": palette["accent"],
        "keyframe": palette["accent_secondary"],
        "keyframe_selected": (1.0, 0.88, 0.12, 1.0),
        "long_key": palette["accent"],
        "long_key_selected": palette["accent_secondary"],
    }.items():
        set_color(anim, attr, value)

    for editor_name in ("dopesheet_editor", "graph_editor", "node_editor", "sequence_editor", "image_editor", "nla_editor", "clip_editor"):
        editor = getattr(theme, editor_name, None)
        if editor and hasattr(editor, "grid"):
            set_color(editor, "grid", palette["grid"])
    for editor_name in ("file_browser", "sequence_editor", "image_editor", "nla_editor", "clip_editor", "spreadsheet"):
        editor = getattr(theme, editor_name, None)
        if not editor:
            continue
        for attr, value in {
            "row_alternate": (*high[:3], 0.22),
            "selected_file": palette["accent"],
            "selected_strip": palette["accent"],
            "active_strip": palette["accent_secondary"],
            "scope_back": low,
            "preview_back": low,
            "metadatabg": low,
        }.items():
            set_color(editor, attr, value)
    set_color(theme.node_editor, "node_backdrop", low)
    set_color(theme.outliner, "row_alternate", (*high[:3], 0.22))
    bpy.ops.wm.save_userpref()

with open(r"__PALETTE_PATH__", "r", encoding="utf-8") as handle:
    apply_theme_palette(json.load(handle))
print("Applied cool blender ui thingy palette.")
'''


EXTRACT_BLENDER_PALETTE_SCRIPT = r'''
import json
import bpy

def to_hex(value):
    rgb = [max(0, min(255, round(channel * 255))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)

theme = bpy.context.preferences.themes[0]
ui = theme.user_interface
view = theme.view_3d
gradients = view.space.gradients
background_type = gradients.background_type

palette = {
    "background": to_hex(view.space.back if hasattr(view.space, "back") else gradients.gradient),
    "panel": to_hex(ui.panel_back),
    "panel_header": to_hex(ui.panel_header),
    "accent": to_hex(ui.editor_outline_active),
    "accent_secondary": to_hex(ui.wcol_regular.item),
    "outline": to_hex(ui.panel_outline),
    "text": to_hex(ui.panel_title),
    "muted_text": to_hex(ui.panel_text),
    "grid": to_hex(view.grid),
    "gradient_start": to_hex(gradients.gradient),
    "gradient_end": to_hex(gradients.high_gradient),
    "gradient_enabled": background_type != "SINGLE_COLOR",
    "gradient_type": background_type,
}

payload = {
    "name": theme.name or "Blender Theme",
    "palette": palette,
}
print("BLENDER_THEME_MAKER_JSON_START")
print(json.dumps(payload))
print("BLENDER_THEME_MAKER_JSON_END")
'''


EXPORT_BLENDER_THEME_XML_SCRIPT = r'''
import os
import shutil
import bpy

name = "__PRESET_NAME__"
output_path = r"__OUTPUT_PATH__"
scripts_root = os.environ["BLENDER_USER_SCRIPTS"]

bpy.ops.wm.interface_theme_preset_add(name=name)
source = os.path.join(scripts_root, "presets", "interface_theme", name + ".xml")
shutil.copyfile(source, output_path)
print("Exported full Blender theme XML:", output_path)
'''


def image_to_base64(path):
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def rgb_from_hex(value):
    value = str(value).strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def hex_from_rgb(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, round(channel))) for channel in rgb])


def mix_hex(a, b, amount):
    ar, ag, ab = rgb_from_hex(a)
    br, bg, bb = rgb_from_hex(b)
    return hex_from_rgb((
        ar + (br - ar) * amount,
        ag + (bg - ag) * amount,
        ab + (bb - ab) * amount,
    ))


def hex_saturation(value):
    rgb = rgb_from_hex(value)
    return (max(rgb) - min(rgb)) / 255


def rebalance_palette_json(palette):
    palette = dict(palette)
    required = {"panel", "panel_header", "gradient_start", "gradient_end"}
    if not required.issubset(palette):
        return palette
    gradient_sat = max(hex_saturation(palette["gradient_start"]), hex_saturation(palette["gradient_end"]))
    panel_sat = hex_saturation(palette["panel"])
    if gradient_sat > 0.18 and panel_sat < 0.08:
        palette["panel"] = mix_hex(palette["panel"], palette["gradient_start"], 0.35)
        palette["panel_header"] = mix_hex(palette["panel_header"], palette["gradient_end"], 0.35)
    return palette


def load_theme_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_theme_history(history):
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2)


def mime_for_image(path):
    lower = path.lower()
    mime = "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif lower.endswith(".webp"):
        mime = "image/webp"
    return mime


def palette_prompt(instruction, reference_count=1):
    shape = {key: "#rrggbb" for key in COLOR_KEYS}
    shape["gradient_enabled"] = True
    shape["gradient_type"] = "LINEAR or RADIAL"
    reference_text = (
        f"You will receive {reference_count} reference image(s). "
        if reference_count
        else "The user may provide screenshots or reference images after this prompt. "
    )
    return (
        reference_text
        + "Create a Blender UI theme palette from the reference image(s). "
        + "Return ONLY valid JSON. Do not include markdown, comments, explanation, or code fences. "
        + "Use this exact JSON shape and include every key: "
        + json.dumps(shape)
        + ". Hex colors must be #rrggbb strings. gradient_enabled must be true or false. "
        + "gradient_type must be LINEAR or RADIAL. "
        + "Blend the references into one cohesive theme, but preserve the recognizable mood of the main reference. "
        + "Use a flexible 60/30/10 balance: roughly 60 percent dominant surface color, 30 percent related support color, "
        + "and 10 percent high-energy accent. Large-surface colors may be colorful, but they must stay dark enough for "
        + "readable UI text and should not become generic gray unless the reference is gray. For a purple Discord-like "
        + "reference, keep the Blender panels visibly purple/plum instead of neutral charcoal. background, panel, "
        + "panel_header, gradient_start, and gradient_end are large-surface colors; keep them related, not identical. "
        + "accent and accent_secondary are for selections, active tabs, icons, and small buttons. Avoid splitting the UI "
        + "into two equally strong unrelated colors; if the reference has a secondary green/blue/orange area, use it as "
        + "a support tint or accent, not half the interface. Gradients should be visible but smooth, with one dominant hue. "
        + "Keep text readable and panels distinct. "
        + instruction
    )


def gemini_palette(api_key, model, image_paths, instruction):
    image_paths = list(image_paths)
    prompt = palette_prompt(instruction, len(image_paths))
    parts = [{"text": prompt}]
    for path in image_paths:
        parts.append({"inline_data": {"mime_type": mime_for_image(path), "data": image_to_base64(path)}})
    body = {
        "contents": [{
            "parts": parts
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.65},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])


class ThemeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("cool blender ui thingy")
        self.geometry("1280x900")
        self.minsize(1160, 820)
        self.configure(bg="#120507")

        self.image_path = tk.StringVar()
        self.api_key = tk.StringVar(value=os.environ.get("GEMINI_API_KEY", ""))
        self.model = tk.StringVar(value=GEMINI_MODEL)
        self.default_instruction = "Make it dramatic, readable, cohesive, and faithful to the dominant reference colors."
        self.blender_exe = tk.StringVar(value=BLENDER_EXE)
        self.status = tk.StringVar(value="Ready")
        self.palette = dict(DEFAULT_PALETTE)
        self.gradient_enabled = tk.BooleanVar(value=bool(self.palette["gradient_enabled"]))
        self.gradient_type = tk.StringVar(value=self.palette["gradient_type"])
        self.swatches = {}
        self.preview_items = {}
        self.action_buttons = []
        self.busy = False
        self.reference_paths = []
        self.reference_images = []
        self.reference_hitboxes = []
        self.reference_cache = {}
        self.theme_history = load_theme_history()
        self.history_widgets = []

        self._build_style()
        self._build_ui()
        self._refresh_json()
        self._refresh_preview()

    def _build_style(self):
        style = ttk.Style(self)
        self.style = style
        style.theme_use("clam")
        style.configure(".", background="#120507", foreground="#f7dfd8", fieldbackground="#18080a")
        style.configure("TFrame", background="#120507")
        style.configure("Surface.TFrame", background="#18080a")
        style.configure("TLabel", background="#120507", foreground="#f7dfd8")
        style.configure("Muted.TLabel", background="#120507", foreground="#b98982")
        style.configure("Title.TLabel", background="#120507", foreground="#fff4ee", font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabel", background="#120507", foreground="#ff6a1f", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", background="#2a0b0f", foreground="#f7dfd8", bordercolor="#6f1018", padding=(10, 7))
        style.map("TButton", background=[("active", "#5c1018"), ("disabled", "#201113")], foreground=[("disabled", "#765b58")])
        style.configure("Accent.TButton", background="#d9152c", foreground="#fff7f3", bordercolor="#ff6a1f", padding=(12, 8))
        style.map("Accent.TButton", background=[("active", "#ff1430"), ("disabled", "#361217")])
        style.configure("TEntry", fieldbackground="#18080a", foreground="#f7dfd8", bordercolor="#6f1018", insertcolor="#ff1430")
        style.configure("TCheckbutton", background="#120507", foreground="#f7dfd8")
        style.map("TCheckbutton", background=[("active", "#120507")], foreground=[("disabled", "#765b58")])
        style.configure("TCombobox", fieldbackground="#18080a", background="#2a0b0f", foreground="#f7dfd8", arrowcolor="#ff1430")
        style.configure("TProgressbar", background="#ff1430", troughcolor="#18080a", bordercolor="#6f1018", lightcolor="#ff1430", darkcolor="#8a1018")

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1, minsize=430)
        root.columnconfigure(1, weight=2, minsize=680)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="cool blender ui thingy", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Build, inspect, and apply Blender UI palettes from images or JSON.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        left = ttk.Frame(root)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ref = self._section(left, "Reference", fill=False)
        ref.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Entry(ref, textvariable=self.image_path).pack(fill="x", pady=(0, 8))
        row = ttk.Frame(ref)
        row.pack(fill="x")
        self._button(row, "Import", self.import_image).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._button(row, "Paste Image", self.paste_clipboard).pack(side="left", fill="x", expand=True)

        ai = self._section(left, "AI", fill=False)
        ai.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.reference_preview = tk.Canvas(ref, height=270, highlightthickness=0, bg=self.palette["background"], cursor="hand2")
        self.reference_preview.pack(fill="x", pady=(10, 0))
        self.reference_preview.bind("<Button-1>", self._reference_canvas_click)
        self.reference_preview.create_text(
            14,
            75,
            text="No reference image",
            fill=self.palette["muted_text"],
            anchor="w",
            font=("Segoe UI", 10),
        )

        ttk.Label(ai, text="AI API Key", style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(ai, textvariable=self.api_key, show="*").pack(fill="x", pady=(2, 8))
        direction_header = ttk.Frame(ai, style="Surface.TFrame")
        direction_header.pack(fill="x")
        ttk.Label(direction_header, text="Direction", style="Muted.TLabel").pack(side="left")
        ttk.Button(direction_header, text="+", width=3, command=lambda: self.resize_direction(1)).pack(side="right")
        ttk.Button(direction_header, text="-", width=3, command=lambda: self.resize_direction(-1)).pack(side="right", padx=(0, 4))
        self.instruction_text = tk.Text(
            ai,
            height=5,
            wrap="word",
            bg="#18080a",
            fg="#f7dfd8",
            insertbackground="#ff1430",
            relief="flat",
            padx=8,
            pady=7,
            font=("Segoe UI", 9),
        )
        self.instruction_text.insert("1.0", self.default_instruction)
        self.instruction_text.pack(fill="both", expand=True, pady=(2, 8))
        ai_row = ttk.Frame(ai)
        ai_row.pack(fill="x")
        self._button(ai_row, "Generate Palette", self.generate_palette, style="Accent.TButton").pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._button(ai_row, "Copy Prompt", self.copy_prompt).pack(side="left", fill="x", expand=True)

        manual_outer, manual = self._scrollable_section(left, "Manual Palette")
        manual_outer.grid(row=2, column=0, sticky="nsew")
        for key in COLOR_KEYS:
            row = ttk.Frame(manual)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=key.replace("_", " ").title(), width=17).pack(side="left")
            swatch = tk.Button(row, text=self.palette[key], width=10, command=lambda k=key: self.pick_color(k))
            swatch.pack(side="right")
            self.swatches[key] = swatch
        gradient_row = ttk.Frame(manual)
        gradient_row.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            gradient_row,
            text="Use Gradient",
            variable=self.gradient_enabled,
            command=self._refresh_json,
        ).pack(side="left")
        gradient_mode = ttk.Combobox(
            gradient_row,
            textvariable=self.gradient_type,
            values=("LINEAR", "RADIAL", "SINGLE_COLOR"),
            state="readonly",
            width=14,
        )
        gradient_mode.pack(side="right")
        gradient_mode.bind("<<ComboboxSelected>>", lambda _event: self._refresh_json())

        preview_box = self._section(right, "Preview", fill=False)
        preview_box.grid(row=0, column=0, sticky="ew")
        self.preview = tk.Canvas(preview_box, height=240, highlightthickness=0, bg="#0b0203")
        self.preview.pack(fill="x")
        self._draw_preview()

        json_box = self._section(right, "Palette JSON", fill=False)
        json_box.grid(row=1, column=0, sticky="nsew", pady=12)
        json_box.rowconfigure(0, weight=1)
        json_box.columnconfigure(0, weight=1)
        row = ttk.Frame(json_box)
        row.pack(fill="x", pady=(0, 8))
        self._button(row, "Load JSON", self.load_json).pack(side="left")
        self._button(row, "Paste JSON", self.paste_json).pack(side="left", padx=8)
        self._button(row, "Update JSON", self._refresh_json).pack(side="left")
        self.json_text = scrolledtext.ScrolledText(
            json_box,
            height=10,
            bg="#080203",
            fg="#ffe9e3",
            insertbackground="#ff1430",
            relief="flat",
            padx=10,
            pady=10,
            font=("Consolas", 10),
        )
        self.json_text.pack(fill="both", expand=True)

        apply_box = self._section(right, "Blender Theme", fill=False)
        apply_box.grid(row=2, column=0, sticky="ew")
        ttk.Entry(apply_box, textvariable=self.blender_exe).pack(fill="x", pady=(0, 8))
        row = ttk.Frame(apply_box)
        row.pack(fill="x")
        self._button(row, "Find Blender", self.pick_blender).pack(side="left")
        self._button(row, "Replace Blender Theme", self.apply_to_blender, style="Accent.TButton").pack(side="right")
        row = ttk.Frame(apply_box)
        row.pack(fill="x", pady=(8, 0))
        self._button(row, "Import Current Theme", self.import_current_blender_theme).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._button(row, "Export Full XML", self.export_current_blender_theme_xml).pack(side="left", fill="x", expand=True)

        history_outer, self.history_content = self._scrollable_section(right, "Theme History")
        history_outer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        history_actions = ttk.Frame(self.history_content, style="Surface.TFrame")
        history_actions.pack(fill="x", pady=(0, 8))
        self._button(history_actions, "Save Current Theme", self.save_current_theme, style="Accent.TButton").pack(side="left", fill="x", expand=True)
        self._button(history_actions, "Refresh", self.render_theme_history).pack(side="left", padx=(8, 0))
        self.history_list = ttk.Frame(self.history_content, style="Surface.TFrame")
        self.history_list.pack(fill="x")
        self.render_theme_history()

        footer = ttk.Frame(root)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=160)
        self.progress.grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").grid(row=0, column=1, sticky="w")

        self.log = tk.Text(
            footer,
            height=3,
            bg="#080203",
            fg="#b98982",
            relief="flat",
            padx=8,
            pady=6,
            state="disabled",
            font=("Consolas", 9),
        )
        self.log.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _section(self, parent, title, fill=True):
        frame = ttk.Frame(parent, padding=12, style="Surface.TFrame")
        if fill:
            frame.pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def _scrollable_section(self, parent, title):
        outer = ttk.Frame(parent, padding=12, style="Surface.TFrame")
        ttk.Label(outer, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        canvas = tk.Canvas(outer, height=260, highlightthickness=0, bg="#18080a")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="Surface.TFrame")
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def configure_content(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def configure_canvas(event):
            canvas.itemconfigure(window, width=event.width)

        def on_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", configure_content)
        canvas.bind("<Configure>", configure_canvas)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", on_wheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        if not hasattr(self, "theme_canvases"):
            self.theme_canvases = []
        self.theme_canvases.append(canvas)
        return outer, content

    def _button(self, parent, text, command, style="TButton"):
        button = ttk.Button(parent, text=text, command=command, style=style)
        self.action_buttons.append(button)
        return button

    def _log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy, status=None):
        self.busy = busy
        if status:
            self.status.set(status)
        for button in self.action_buttons:
            if button.winfo_exists():
                button.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _run_task(self, status, worker, on_success):
        if self.busy:
            return
        self._set_busy(True, status)
        self._log(status)

        def run():
            try:
                result = worker()
            except Exception as exc:
                self.after(0, lambda: self._task_failed(exc))
                return
            self.after(0, lambda: self._task_finished(result, on_success))

        threading.Thread(target=run, daemon=True).start()

    def _task_finished(self, result, on_success):
        self._set_busy(False, "Ready")
        try:
            on_success(result)
        except Exception as exc:
            self._task_failed(exc)

    def _task_failed(self, exc):
        self._set_busy(False, "Ready")
        self._log(f"Error: {exc}")
        messagebox.showerror("cool blender ui thingy", str(exc))

    def _sync_palette_settings(self):
        self.palette["gradient_enabled"] = bool(self.gradient_enabled.get())
        gradient_type = self.gradient_type.get().upper()
        self.palette["gradient_type"] = gradient_type if gradient_type in {"LINEAR", "RADIAL", "SINGLE_COLOR"} else "LINEAR"

    def _draw_gradient(self, canvas, width, height, start, end):
        if not self.gradient_enabled.get() or self.gradient_type.get() == "SINGLE_COLOR":
            canvas.create_rectangle(0, 0, width, height, fill=self.palette["background"], outline="")
            return
        s = tuple(int(start.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        e = tuple(int(end.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        steps = max(1, height if self.gradient_type.get() == "LINEAR" else min(width, height))
        for i in range(steps):
            t = i / max(1, steps - 1)
            if self.gradient_type.get() == "RADIAL":
                t = min(1, (i / max(1, steps - 1)) ** 1.7)
            rgb = tuple(round(s[channel] + (e[channel] - s[channel]) * t) for channel in range(3))
            color = "#{:02x}{:02x}{:02x}".format(*rgb)
            if self.gradient_type.get() == "RADIAL":
                inset = i // 2
                canvas.create_rectangle(inset, inset, width - inset, height - inset, outline=color)
            else:
                canvas.create_line(0, i, width, i, fill=color)

    def _draw_preview(self):
        c = self.preview
        c.delete("all")
        self._sync_palette_settings()
        self._draw_gradient(c, 2000, 260, self.palette["gradient_start"], self.palette["gradient_end"])
        self.preview_items["top"] = c.create_rectangle(0, 0, 2000, 34, fill=self.palette["panel_header"], outline=self.palette["outline"])
        c.create_text(18, 17, text="cool blender ui thingy", fill=self.palette["text"], anchor="w", font=("Segoe UI", 11, "bold"))
        self.preview_items["panel"] = c.create_rectangle(22, 54, 330, 198, fill=self.palette["panel"], outline=self.palette["outline"])
        c.create_text(42, 78, text="Panel Header", fill=self.palette["text"], anchor="w", font=("Segoe UI", 10, "bold"))
        self.preview_items["button"] = c.create_rectangle(42, 112, 180, 150, fill=self.palette["accent"], outline=self.palette["accent_secondary"])
        c.create_text(111, 131, text="Apply", fill=self.palette["text"], font=("Segoe UI", 10, "bold"))
        c.create_text(42, 174, text="Muted text and secondary labels", fill=self.palette["muted_text"], anchor="w")
        for x in range(380, 980, 36):
            c.create_line(x, 54, x, 198, fill=self.palette["grid"])
        for y in range(54, 210, 36):
            c.create_line(380, y, 980, y, fill=self.palette["grid"])
        c.create_rectangle(520, 92, 620, 158, fill="#a9abad", outline=self.palette["accent"], width=2)

    def _make_preview_png(self, path):
        if not path or not os.path.exists(path):
            return None
        cached = self.reference_cache.get(path)
        mtime = os.path.getmtime(path)
        if cached and cached[0] == mtime:
            return cached[1]

        with Image.open(path) as image:
            image = image.convert("RGBA")
            image.thumbnail((116, 86), Image.Resampling.LANCZOS)
            preview = ImageTk.PhotoImage(image)
        self.reference_cache[path] = (mtime, preview)
        return preview

    def _draw_reference_preview(self):
        if not hasattr(self, "reference_preview"):
            return
        c = self.reference_preview
        c.delete("all")
        self.reference_hitboxes = []
        width = max(c.winfo_width(), 340)
        self._draw_gradient(c, 2000, 270, self.palette["gradient_start"], self.palette["gradient_end"])
        c.create_rectangle(0, 0, 2000, 270, outline=self.palette["outline"])
        if not self.reference_paths:
            c.create_text(
                14,
                135,
                text="No reference images",
                fill=self.palette["muted_text"],
                anchor="w",
                font=("Segoe UI", 10),
            )
            return

        self.reference_images = []
        x = 12
        y = 12
        for index, path in enumerate(self.reference_paths):
            try:
                image = self._make_preview_png(path)
            except Exception as exc:
                self._log(f"Preview failed: {exc}")
                continue
            self.reference_images.append(image)
            c.create_rectangle(x, y, x + 126, y + 126, fill=self.palette["panel"], outline=self.palette["outline"])
            c.create_image(x + 5, y + 5, image=image, anchor="nw")
            c.create_rectangle(x + 102, y + 4, x + 122, y + 24, fill=self.palette["accent"], outline=self.palette["accent_secondary"])
            c.create_text(x + 112, y + 14, text="x", fill=self.palette["text"], font=("Segoe UI", 10, "bold"))
            label = os.path.basename(path)
            if len(label) > 18:
                label = label[:15] + "..."
            c.create_text(x + 8, y + 111, text=label, fill=self.palette["text"], anchor="w", font=("Segoe UI", 8, "bold"))
            self.reference_hitboxes.append((x + 102, y + 4, x + 122, y + 24, index))
            x += 138
            if x + 126 > width - 12:
                x = 12
                y += 138

    def _reference_canvas_click(self, event):
        for x1, y1, x2, y2, index in self.reference_hitboxes:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.remove_reference(index)
                break

    def _update_reference_summary(self):
        if not self.reference_paths:
            self.image_path.set("")
        elif len(self.reference_paths) == 1:
            self.image_path.set(self.reference_paths[0])
        else:
            self.image_path.set(f"{len(self.reference_paths)} reference images")

    def add_reference_paths(self, paths):
        added = 0
        for path in paths:
            if path and os.path.exists(path) and path not in self.reference_paths:
                self.reference_paths.append(path)
                added += 1
        self._update_reference_summary()
        self._draw_reference_preview()
        return added

    def remove_reference(self, index):
        if 0 <= index < len(self.reference_paths):
            removed = self.reference_paths.pop(index)
            self._update_reference_summary()
            self._draw_reference_preview()
            self.status.set("Reference image removed")
            self._log(f"Removed reference: {removed}")

    def _refresh_preview(self):
        self._apply_app_theme()
        for key, button in self.swatches.items():
            button.configure(text=self.palette[key], bg=self.palette[key], fg=self._text_color(self.palette[key]))
        self._draw_preview()

    def _refresh_json(self):
        self._sync_palette_settings()
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", json.dumps(self.palette, indent=2))
        self._refresh_preview()

    def _text_color(self, hex_color):
        value = hex_color.lstrip("#")
        r, g, b = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
        return "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 150 else "#ffffff"

    def _apply_app_theme(self):
        self._sync_palette_settings()
        bg = self.palette["background"]
        panel = self.palette["panel"]
        header = self.palette["panel_header"]
        accent = self.palette["accent"]
        accent2 = self.palette["accent_secondary"]
        outline = self.palette["outline"]
        text = self.palette["text"]
        muted = self.palette["muted_text"]
        self.configure(bg=bg)
        self.style.configure(".", background=bg, foreground=text, fieldbackground=panel)
        self.style.configure("TFrame", background=bg)
        self.style.configure("Surface.TFrame", background=panel)
        self.style.configure("TLabel", background=bg, foreground=text)
        self.style.configure("Muted.TLabel", background=bg, foreground=muted)
        self.style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI", 18, "bold"))
        self.style.configure("Section.TLabel", background=panel, foreground=accent2, font=("Segoe UI", 10, "bold"))
        self.style.configure("TButton", background=header, foreground=text, bordercolor=outline, padding=(10, 7))
        self.style.map("TButton", background=[("active", accent), ("disabled", panel)], foreground=[("disabled", muted)])
        self.style.configure("Accent.TButton", background=accent, foreground=self._text_color(accent), bordercolor=accent2, padding=(12, 8))
        self.style.map("Accent.TButton", background=[("active", accent2), ("disabled", header)])
        self.style.configure("TEntry", fieldbackground=panel, foreground=text, bordercolor=outline, insertcolor=accent)
        self.style.configure("TCheckbutton", background=panel, foreground=text)
        self.style.map("TCheckbutton", background=[("active", panel)], foreground=[("disabled", muted)])
        self.style.configure("TCombobox", fieldbackground=panel, background=header, foreground=text, arrowcolor=accent)
        self.style.configure("TProgressbar", background=accent, troughcolor=panel, bordercolor=outline, lightcolor=accent, darkcolor=outline)
        if hasattr(self, "json_text"):
            self.json_text.configure(bg=bg, fg=text, insertbackground=accent)
        if hasattr(self, "instruction_text"):
            self.instruction_text.configure(bg=panel, fg=text, insertbackground=accent)
        if hasattr(self, "log"):
            self.log.configure(bg=bg, fg=muted, insertbackground=accent)
        for canvas in getattr(self, "theme_canvases", []):
            if canvas.winfo_exists():
                canvas.configure(bg=panel)
        if hasattr(self, "preview"):
            self.preview.configure(bg=bg)
        if hasattr(self, "reference_preview"):
            self.reference_preview.configure(bg=bg)
            self._draw_reference_preview()
        if hasattr(self, "history_list"):
            self.render_theme_history()

    def pick_color(self, key):
        _, chosen = colorchooser.askcolor(color=self.palette[key], title=key.replace("_", " ").title())
        if chosen:
            self.palette[key] = chosen.lower()
            self._refresh_json()

    def copy_prompt(self):
        prompt = palette_prompt(self.get_direction(), len(self.reference_paths))
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self.status.set("Prompt copied")
        self._log("Prompt copied. Paste it into ChatGPT or another AI with your screenshots, then paste the JSON back here.")

    def paste_json(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showerror("JSON", "Clipboard does not contain text.")
            return
        text = self._clean_json_text(text)
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", text)
        self.load_json()

    def _clean_json_text(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
        return text

    def get_direction(self):
        if hasattr(self, "instruction_text"):
            value = self.instruction_text.get("1.0", "end").strip()
            return value or self.default_instruction
        return self.default_instruction

    def resize_direction(self, delta):
        if not hasattr(self, "instruction_text"):
            return
        height = int(str(self.instruction_text.cget("height")))
        self.instruction_text.configure(height=max(3, min(14, height + delta)))

    def current_palette_snapshot(self):
        self._sync_palette_settings()
        return dict(self.palette)

    def save_current_theme(self):
        name = simpledialog.askstring("Save Theme", "Theme name:", parent=self)
        if not name:
            return
        entry = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "palette": self.current_palette_snapshot(),
        }
        self.theme_history.insert(0, entry)
        save_theme_history(self.theme_history)
        self.render_theme_history()
        self.status.set("Theme saved")
        self._log(f"Saved theme: {entry['name']}")

    def render_theme_history(self):
        if not hasattr(self, "history_list"):
            return
        for child in self.history_list.winfo_children():
            child.destroy()
        if not self.theme_history:
            ttk.Label(
                self.history_list,
                text="No saved themes yet.",
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(4, 0))
            return
        for entry in self.theme_history:
            self._render_theme_entry(entry)

    def _render_theme_entry(self, entry):
        card = ttk.Frame(self.history_list, padding=8, style="Surface.TFrame")
        card.pack(fill="x", pady=(0, 8))
        header = ttk.Frame(card, style="Surface.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=entry.get("name", "Untitled"), style="TLabel").pack(side="left")
        ttk.Label(header, text=entry.get("created_at", ""), style="Muted.TLabel").pack(side="right")

        swatches = tk.Frame(card, bg=self.palette["panel"])
        swatches.pack(fill="x", pady=6)
        palette = entry.get("palette", {})
        for key in COLOR_KEYS:
            color = palette.get(key, DEFAULT_PALETTE.get(key, "#000000"))
            swatch = tk.Frame(swatches, width=24, height=18, bg=color, highlightthickness=1, highlightbackground=self.palette["outline"])
            swatch.pack(side="left", padx=(0, 3))
            swatch.pack_propagate(False)

        actions = ttk.Frame(card, style="Surface.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Edit", command=lambda theme_id=entry["id"]: self.edit_theme(theme_id)).pack(side="left")
        ttk.Button(actions, text="Export", command=lambda theme_id=entry["id"]: self.export_theme(theme_id)).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Rename", command=lambda theme_id=entry["id"]: self.rename_theme(theme_id)).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Delete", command=lambda theme_id=entry["id"]: self.delete_theme(theme_id)).pack(side="right")

    def find_theme_entry(self, theme_id):
        for entry in self.theme_history:
            if entry.get("id") == theme_id:
                return entry
        return None

    def edit_theme(self, theme_id):
        entry = self.find_theme_entry(theme_id)
        if not entry:
            return
        self._set_palette(entry.get("palette", {}))
        self.status.set("Theme loaded for editing")
        self._log(f"Loaded theme: {entry.get('name', 'Untitled')}")

    def export_theme(self, theme_id):
        entry = self.find_theme_entry(theme_id)
        if not entry:
            return
        safe_name = "".join(ch for ch in entry.get("name", "theme") if ch.isalnum() or ch in (" ", "-", "_")).strip() or "theme"
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"{safe_name}.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(entry.get("palette", {}), handle, indent=2)
        self.status.set("Theme exported")
        self._log(f"Exported theme: {path}")

    def rename_theme(self, theme_id):
        entry = self.find_theme_entry(theme_id)
        if not entry:
            return
        name = simpledialog.askstring("Rename Theme", "Theme name:", initialvalue=entry.get("name", ""), parent=self)
        if not name:
            return
        entry["name"] = name.strip()
        save_theme_history(self.theme_history)
        self.render_theme_history()
        self.status.set("Theme renamed")

    def delete_theme(self, theme_id):
        entry = self.find_theme_entry(theme_id)
        if not entry:
            return
        if not messagebox.askyesno("Delete Theme", f"Delete '{entry.get('name', 'Untitled')}'?"):
            return
        self.theme_history = [theme for theme in self.theme_history if theme.get("id") != theme_id]
        save_theme_history(self.theme_history)
        self.render_theme_history()
        self.status.set("Theme deleted")

    def save_imported_blender_theme(self, name, palette):
        entry = {
            "id": str(uuid.uuid4()),
            "name": name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "palette": dict(palette),
        }
        self.theme_history.insert(0, entry)
        save_theme_history(self.theme_history)
        self.render_theme_history()

    def parse_blender_json_payload(self, output):
        start = "BLENDER_THEME_MAKER_JSON_START"
        end = "BLENDER_THEME_MAKER_JSON_END"
        if start not in output or end not in output:
            raise RuntimeError("Blender did not return theme data.")
        json_text = output.split(start, 1)[1].split(end, 1)[0].strip()
        return json.loads(json_text)

    def import_image(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if paths:
            added = self.add_reference_paths(paths)
            self.status.set(f"{added} reference image{'s' if added != 1 else ''} added")
            for path in paths:
                self._log(f"Reference: {path}")

    def paste_clipboard(self):
        if self.busy:
            return
        fd, output = tempfile.mkstemp(suffix=".png", prefix="ai_blender_theme_clipboard_")
        os.close(fd)
        clipboard = ImageGrab.grabclipboard()
        if isinstance(clipboard, list):
            image_files = [item for item in clipboard if str(item).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))]
            if image_files:
                added = self.add_reference_paths(image_files)
                self.status.set(f"{added} clipboard image file{'s' if added != 1 else ''} added")
                for image_file in image_files:
                    self._log(f"Clipboard image file: {image_file}")
                return
        if clipboard is None or not hasattr(clipboard, "save"):
            messagebox.showerror("Clipboard", "Clipboard does not contain an image.")
            return
        clipboard.convert("RGBA").save(output, "PNG")
        self.add_reference_paths([output])
        self.status.set("Clipboard image loaded")
        self._log(f"Clipboard image: {output}")

    def generate_palette(self):
        if not self.api_key.get().strip():
            messagebox.showerror("AI", "Enter an AI API key first.")
            return
        if not self.reference_paths:
            messagebox.showerror("Reference Images", "Import or paste at least one image first.")
            return
        api_key = self.api_key.get().strip()
        model = self.model.get().strip() or GEMINI_MODEL
        image_paths = list(self.reference_paths)
        instruction = self.get_direction()

        def worker():
            return gemini_palette(
                api_key,
                model,
                image_paths,
                instruction,
            )

        def done(palette):
            self._set_palette(palette)
            self._log("AI palette generated and loaded.")
            self.status.set("AI palette loaded")

        self._run_task("Generating palette with AI...", worker, done)

    def _set_palette(self, palette):
        merged = {**DEFAULT_PALETTE, **palette}
        merged = rebalance_palette_json(merged)
        for key in COLOR_KEYS:
            if key not in merged:
                raise ValueError(f"Missing palette key: {key}")
            value = str(merged[key]).strip()
            if not value.startswith("#"):
                value = "#" + value
            if len(value) != 7:
                raise ValueError(f"Invalid color for {key}: {merged[key]}")
            int(value[1:], 16)
            self.palette[key] = value.lower()
        self.palette["gradient_enabled"] = bool(merged.get("gradient_enabled", True))
        gradient_type = str(merged.get("gradient_type", "LINEAR")).upper()
        if gradient_type not in {"LINEAR", "RADIAL", "SINGLE_COLOR"}:
            raise ValueError("gradient_type must be LINEAR, RADIAL, or SINGLE_COLOR")
        self.palette["gradient_type"] = gradient_type
        self.gradient_enabled.set(self.palette["gradient_enabled"])
        self.gradient_type.set(self.palette["gradient_type"])
        self._refresh_json()

    def load_json(self):
        try:
            self._set_palette(json.loads(self.json_text.get("1.0", "end")))
        except Exception as exc:
            messagebox.showerror("JSON", str(exc))
            return False
        self.status.set("JSON loaded")
        self._log("JSON loaded into controls.")
        return True

    def pick_blender(self):
        path = filedialog.askopenfilename(filetypes=[("Blender", "blender.exe"), ("All files", "*.*")])
        if path:
            self.blender_exe.set(path)
            self._log(f"Blender: {path}")

    def import_current_blender_theme(self):
        blender = self.blender_exe.get()
        if not os.path.exists(blender):
            messagebox.showerror("Blender", "Blender executable path is invalid.")
            return

        def worker():
            with tempfile.TemporaryDirectory() as folder:
                script_path = os.path.join(folder, "extract_theme.py")
                with open(script_path, "w", encoding="utf-8") as handle:
                    handle.write(EXTRACT_BLENDER_PALETTE_SCRIPT)
                result = subprocess.run([blender, "--background", "--python", script_path], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout or "Blender returned an error.")
            return self.parse_blender_json_payload(result.stdout + result.stderr)

        def done(payload):
            name = f"Imported {payload.get('name') or 'Blender Theme'}"
            palette = payload["palette"]
            self._set_palette(palette)
            self.save_imported_blender_theme(name, self.current_palette_snapshot())
            self.status.set("Blender theme imported")
            self._log(f"Imported current Blender theme into app history: {name}")

        self._run_task("Importing current Blender theme...", worker, done)

    def export_current_blender_theme_xml(self):
        blender = self.blender_exe.get()
        if not os.path.exists(blender):
            messagebox.showerror("Blender", "Blender executable path is invalid.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            initialfile="current-blender-theme.xml",
            filetypes=[("Blender theme XML", "*.xml"), ("All files", "*.*")],
        )
        if not path:
            return

        def worker():
            preset_name = "BlenderThemeMakerFullExport"
            with tempfile.TemporaryDirectory() as folder:
                script = EXPORT_BLENDER_THEME_XML_SCRIPT
                script = script.replace("__PRESET_NAME__", preset_name)
                script = script.replace("__OUTPUT_PATH__", path.replace("\\", "\\\\"))
                script_path = os.path.join(folder, "export_theme_xml.py")
                scripts_root = os.path.join(folder, "blender_scripts")
                os.makedirs(scripts_root, exist_ok=True)
                with open(script_path, "w", encoding="utf-8") as handle:
                    handle.write(script)
                env = os.environ.copy()
                env["BLENDER_USER_SCRIPTS"] = scripts_root
                result = subprocess.run([blender, "--background", "--python", script_path], capture_output=True, text=True, env=env)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout or "Blender returned an error.")
            return path

        def done(export_path):
            self.status.set("Full Blender theme exported")
            self._log(f"Exported full Blender theme XML: {export_path}")

        self._run_task("Exporting full Blender theme XML...", worker, done)

    def apply_to_blender(self):
        blender = self.blender_exe.get()
        if not os.path.exists(blender):
            messagebox.showerror("Blender", "Blender executable path is invalid.")
            return
        if not self.load_json():
            return
        palette = dict(self.palette)

        def worker():
            with tempfile.TemporaryDirectory() as folder:
                palette_path = os.path.join(folder, "palette.json")
                script_path = os.path.join(folder, "apply_theme.py")
                with open(palette_path, "w", encoding="utf-8") as handle:
                    json.dump(palette, handle)
                script = APPLY_SCRIPT.replace("__PALETTE_PATH__", palette_path.replace("\\", "\\\\"))
                with open(script_path, "w", encoding="utf-8") as handle:
                    handle.write(script)
                result = subprocess.run([blender, "--background", "--python", script_path], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout or "Blender returned an error.")
            return result.stdout

        def done(output):
            self._log("Theme applied and Blender preferences saved.")
            self.status.set("Theme applied")
            messagebox.showinfo("Applied", "Theme applied and Blender preferences saved. Restart Blender to reload every UI area.")

        self._run_task("Applying theme through Blender...", worker, done)


if __name__ == "__main__":
    ThemeApp().mainloop()
