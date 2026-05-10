bl_info = {
    "name": "AI Theme Studio",
    "author": "BlenderThemeMaker",
    "version": (0, 1, 0),
    "blender": (5, 1, 0),
    "location": "3D View > Sidebar > AI Theme",
    "description": "Create Blender UI themes from reference images, manual palettes, or Gemini JSON.",
    "category": "Interface",
}

import base64
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, StringProperty


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
}


def hex_to_rgba(value, alpha=1.0):
    value = str(value).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        value = "ff00ff"
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


def rgba_to_hex(value):
    rgb = [max(0, min(255, round(channel * 255))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


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


def set_space(space, palette, background=None):
    background = background or palette["background"]
    set_color(space, "back", background)
    if hasattr(space, "gradients"):
        try:
            space.gradients.background_type = "SINGLE_COLOR"
            space.gradients.gradient = background[:3]
            space.gradients.high_gradient = palette["panel"][:3]
        except Exception:
            pass
    for attr, value in {
        "title": palette["text"],
        "text": palette["text"],
        "text_hi": (1.0, 0.96, 0.94, 1.0),
        "header": palette["panel_header"],
        "header_text": palette["text"],
        "header_text_hi": (1.0, 0.96, 0.94, 1.0),
    }.items():
        set_color(space, attr, value)


def apply_theme_palette(palette, save_preferences=True):
    theme = bpy.context.preferences.themes[0]
    theme.name = "AI Theme Studio"
    ui = theme.user_interface

    for attr in (
        "wcol_regular", "wcol_tool", "wcol_toolbar_item", "wcol_radio", "wcol_text",
        "wcol_option", "wcol_toggle", "wcol_num", "wcol_numslider", "wcol_box",
        "wcol_curve", "wcol_menu", "wcol_pulldown", "wcol_menu_back",
        "wcol_pie_menu", "wcol_tooltip", "wcol_menu_item", "wcol_scroll",
        "wcol_progress", "wcol_list_item", "wcol_tab",
    ):
        widget = getattr(ui, attr, None)
        if widget is None:
            continue
        for widget_attr, value in {
            "outline": palette["outline"],
            "outline_sel": palette["accent"],
            "inner": palette["panel"],
            "inner_sel": palette["accent"],
            "item": palette["accent_secondary"],
            "text": palette["text"],
            "text_sel": (1.0, 0.96, 0.94, 1.0),
            "shadetop": palette["panel_header"],
            "shadedown": palette["background"],
            "roundness": 0.18,
        }.items():
            set_color(widget, widget_attr, value)

    for attr, value in {
        "panel_roundness": 0.15,
        "panel_header": palette["panel_header"],
        "panel_title": palette["text"],
        "panel_text": palette["muted_text"],
        "panel_back": palette["panel"],
        "panel_sub_back": palette["background"],
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
        "nla_editor", "image_editor", "sequence_editor", "node_editor",
        "text_editor", "file_browser", "preferences", "console", "clip_editor",
        "spreadsheet",
    ):
        editor = getattr(theme, editor_name, None)
        if editor and hasattr(editor, "space"):
            set_space(editor.space, palette)

    for editor_name in ("topbar", "statusbar", "info"):
        editor = getattr(theme, editor_name, None)
        if editor and hasattr(editor, "space"):
            set_space(editor.space, palette, palette["background"])

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
        (regions.asset_shelf, {"back": palette["background"], "header_back": palette["panel_header"]}),
        (regions.channels, {"back": palette["background"], "text": palette["muted_text"], "text_selected": palette["text"]}),
        (regions.scrubbing, {"back": palette["background"], "text": palette["text"], "time_marker": palette["accent"], "time_marker_selected": palette["accent_secondary"]}),
        (regions.sidebars, {"back": palette["background"], "tab_back": palette["panel_header"]}),
    ):
        for attr, value in mapping.items():
            set_color(owner, attr, value)

    anim = theme.common.anim
    for attr, value in {
        "playhead": palette["accent"],
        "preview_range": (*palette["outline"][:3], 0.35),
        "scene_strip_range": (*palette["outline"][:3], 0.35),
        "channels": palette["panel"],
        "channels_sub": palette["background"],
        "channel_group": palette["panel_header"],
        "channel_group_active": palette["accent"],
        "channel": palette["panel"],
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
    set_color(theme.node_editor, "node_backdrop", palette["background"])
    set_color(theme.outliner, "row_alternate", (*palette["panel"][:3], 0.35))

    if save_preferences:
        bpy.ops.wm.save_userpref()


def image_to_base64(path):
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("ascii")


def gemini_palette(api_key, model, image_path, instruction):
    mime = "image/png"
    lower = image_path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif lower.endswith(".webp"):
        mime = "image/webp"

    schema_hint = {key: "#rrggbb" for key in ROLE_KEYS}
    prompt = (
        "Create a bold Blender UI theme palette from this reference image. "
        "Return ONLY valid JSON, no markdown. Use this exact shape: "
        + json.dumps(schema_hint)
        + ". Keep text readable and make panels visually distinct. "
        + instruction
    )
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": image_to_base64(image_path)}},
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.8,
        },
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
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def palette_from_scene(scene):
    return {key: getattr(scene.ai_theme_studio, key) for key in ROLE_KEYS}


def set_scene_palette(scene, palette_json):
    props = scene.ai_theme_studio
    for key in ROLE_KEYS:
        if key in palette_json:
            setattr(props, key, hex_to_rgba(palette_json[key]))
    props.palette_json = json.dumps({key: rgba_to_hex(getattr(props, key)) for key in ROLE_KEYS}, indent=2)


class AIThemeStudioProperties(bpy.types.PropertyGroup):
    reference_image: StringProperty(name="Reference Image", subtype="FILE_PATH")
    api_key: StringProperty(name="Gemini API Key", subtype="PASSWORD")
    model: StringProperty(name="Model", default="gemini-3-flash-preview")
    instruction: StringProperty(name="AI Direction", default="Make it dramatic, readable, and cohesive.")
    palette_json: StringProperty(name="Palette JSON", default=json.dumps(DEFAULT_PALETTE, indent=2))
    apply_after_ai: BoolProperty(name="Apply after AI", default=True)
    background: FloatVectorProperty(name="Background", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["background"]))
    panel: FloatVectorProperty(name="Panel", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["panel"]))
    panel_header: FloatVectorProperty(name="Panel Header", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["panel_header"]))
    accent: FloatVectorProperty(name="Accent", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["accent"]))
    accent_secondary: FloatVectorProperty(name="Accent 2", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["accent_secondary"]))
    outline: FloatVectorProperty(name="Outline", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["outline"]))
    text: FloatVectorProperty(name="Text", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["text"]))
    muted_text: FloatVectorProperty(name="Muted Text", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["muted_text"]))
    grid: FloatVectorProperty(name="Grid", subtype="COLOR", size=4, min=0, max=1, default=hex_to_rgba(DEFAULT_PALETTE["grid"]))


class AI_THEME_OT_select_reference(bpy.types.Operator):
    bl_idname = "ai_theme.select_reference"
    bl_label = "Import Reference"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.bmp", options={"HIDDEN"})

    def execute(self, context):
        context.scene.ai_theme_studio.reference_image = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AI_THEME_OT_paste_reference(bpy.types.Operator):
    bl_idname = "ai_theme.paste_reference"
    bl_label = "Paste Clipboard Image"

    def execute(self, context):
        output = os.path.join(tempfile.gettempdir(), "blender_ai_theme_clipboard.png")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "if ([Windows.Forms.Clipboard]::ContainsImage()) {"
            "$img=[Windows.Forms.Clipboard]::GetImage();"
            f"$img.Save('{output.replace(chr(92), chr(92) + chr(92))}', [System.Drawing.Imaging.ImageFormat]::Png);"
            "Write-Output 'OK'} else {Write-Output 'NO_IMAGE'}"
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
        if "OK" not in result.stdout:
            self.report({"ERROR"}, "Clipboard does not contain an image.")
            return {"CANCELLED"}
        context.scene.ai_theme_studio.reference_image = output
        self.report({"INFO"}, "Clipboard image imported.")
        return {"FINISHED"}


class AI_THEME_OT_apply(bpy.types.Operator):
    bl_idname = "ai_theme.apply"
    bl_label = "Apply Theme"

    def execute(self, context):
        apply_theme_palette(palette_from_scene(context.scene), True)
        self.report({"INFO"}, "Theme applied and preferences saved.")
        return {"FINISHED"}


class AI_THEME_OT_json_to_controls(bpy.types.Operator):
    bl_idname = "ai_theme.json_to_controls"
    bl_label = "Load JSON"

    def execute(self, context):
        try:
            palette = json.loads(context.scene.ai_theme_studio.palette_json)
            set_scene_palette(context.scene, palette)
        except Exception as exc:
            self.report({"ERROR"}, f"Invalid palette JSON: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


class AI_THEME_OT_controls_to_json(bpy.types.Operator):
    bl_idname = "ai_theme.controls_to_json"
    bl_label = "Update JSON"

    def execute(self, context):
        props = context.scene.ai_theme_studio
        props.palette_json = json.dumps({key: rgba_to_hex(getattr(props, key)) for key in ROLE_KEYS}, indent=2)
        return {"FINISHED"}


class AI_THEME_OT_generate(bpy.types.Operator):
    bl_idname = "ai_theme.generate"
    bl_label = "Generate From AI"

    def execute(self, context):
        props = context.scene.ai_theme_studio
        api_key = props.api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            self.report({"ERROR"}, "Set Gemini API key in the panel or GEMINI_API_KEY.")
            return {"CANCELLED"}
        image_path = bpy.path.abspath(props.reference_image)
        if not image_path or not os.path.exists(image_path):
            self.report({"ERROR"}, "Import or paste a reference image first.")
            return {"CANCELLED"}
        try:
            palette = gemini_palette(api_key, props.model, image_path, props.instruction)
            set_scene_palette(context.scene, palette)
            if props.apply_after_ai:
                apply_theme_palette(palette_from_scene(context.scene), True)
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError) as exc:
            self.report({"ERROR"}, f"AI palette failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "AI palette generated.")
        return {"FINISHED"}


class AI_THEME_PT_panel(bpy.types.Panel):
    bl_label = "AI Theme Studio"
    bl_idname = "AI_THEME_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Theme"

    def draw(self, context):
        layout = self.layout
        props = context.scene.ai_theme_studio

        box = layout.box()
        box.label(text="Reference")
        box.prop(props, "reference_image", text="")
        row = box.row(align=True)
        row.operator("ai_theme.select_reference", icon="FILE_IMAGE")
        row.operator("ai_theme.paste_reference", icon="PASTEDOWN")

        box = layout.box()
        box.label(text="AI")
        box.prop(props, "api_key")
        box.prop(props, "model")
        box.prop(props, "instruction")
        box.prop(props, "apply_after_ai")
        box.operator("ai_theme.generate", icon="LIGHT")

        box = layout.box()
        box.label(text="Palette")
        for key in ROLE_KEYS:
            box.prop(props, key)
        row = box.row(align=True)
        row.operator("ai_theme.apply", icon="CHECKMARK")
        row.operator("ai_theme.controls_to_json", icon="EXPORT")

        box = layout.box()
        box.label(text="JSON")
        box.prop(props, "palette_json", text="")
        box.operator("ai_theme.json_to_controls", icon="IMPORT")


classes = (
    AIThemeStudioProperties,
    AI_THEME_OT_select_reference,
    AI_THEME_OT_paste_reference,
    AI_THEME_OT_apply,
    AI_THEME_OT_json_to_controls,
    AI_THEME_OT_controls_to_json,
    AI_THEME_OT_generate,
    AI_THEME_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ai_theme_studio = bpy.props.PointerProperty(type=AIThemeStudioProperties)


def unregister():
    del bpy.types.Scene.ai_theme_studio
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
