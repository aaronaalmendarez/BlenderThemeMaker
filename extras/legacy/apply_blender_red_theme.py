import bpy


theme = bpy.context.preferences.themes[0]
theme.name = "Crimson"

colors = {
    "back": (0.045, 0.006, 0.009, 1.0),
    "sub": (0.080, 0.010, 0.015, 1.0),
    "panel": (0.110, 0.014, 0.020, 1.0),
    "panel_hi": (0.180, 0.025, 0.035, 1.0),
    "outline": (0.360, 0.035, 0.050, 1.0),
    "accent": (0.900, 0.030, 0.070, 1.0),
    "accent2": (1.000, 0.170, 0.070, 1.0),
    "text": (0.980, 0.850, 0.820, 1.0),
    "muted": (0.720, 0.470, 0.450, 1.0),
    "black": (0.018, 0.002, 0.004, 1.0),
}


def rgba_for(name):
    n = name.lower()
    if any(k in n for k in ("selected", "active", "highlight", "current", "match", "keytype_keyframe")):
        return colors["accent"]
    if any(k in n for k in ("title", "text_hi", "item", "header_text", "tab_text")):
        return colors["text"]
    if "text" in n:
        return colors["muted"]
    if any(k in n for k in ("outline", "border", "wire", "edge", "grid", "frame")):
        return colors["outline"]
    if any(k in n for k in ("header", "button", "tab", "navigation", "execution")):
        return colors["panel_hi"]
    if any(k in n for k in ("panel", "region", "shade", "inner", "sub")):
        return colors["sub"]
    if any(k in n for k in ("back", "space", "window")):
        return colors["back"]
    if any(k in n for k in ("error", "warning", "delete", "alert")):
        return colors["accent2"]
    return colors["panel"]


def set_color(owner, prop, value):
    current = getattr(owner, prop.identifier)
    if not hasattr(current, "__len__") or isinstance(current, str):
        return
    if len(current) == 3:
        setattr(owner, prop.identifier, value[:3])
    elif len(current) == 4:
        setattr(owner, prop.identifier, value)


def paint(owner):
    for prop in owner.bl_rna.properties:
        if prop.is_readonly or prop.identifier == "rna_type":
            continue
        try:
            set_color(owner, prop, rgba_for(prop.identifier))
        except Exception:
            pass


def set_space(space, back=colors["back"]):
    if hasattr(space, "back"):
        space.back = back[:3]
    if hasattr(space, "gradients"):
        try:
            space.gradients.background_type = "SINGLE_COLOR"
            space.gradients.gradient = back[:3]
            space.gradients.high_gradient = colors["panel"][:3]
        except Exception:
            pass
    for attr, value in {
        "title": colors["text"][:3],
        "text": colors["text"][:3],
        "text_hi": (1.0, 0.95, 0.92),
        "header": colors["panel_hi"],
        "header_text": colors["text"][:3],
        "header_text_hi": (1.0, 0.95, 0.92),
    }.items():
        if hasattr(space, attr):
            try:
                setattr(space, attr, value)
            except Exception:
                pass


def set_attrs(owner, mapping):
    for attr, value in mapping.items():
        if not hasattr(owner, attr):
            continue
        try:
            current = getattr(owner, attr)
            if hasattr(current, "__len__") and not isinstance(current, str):
                if len(current) == 3:
                    setattr(owner, attr, value[:3])
                elif len(current) == 4 and len(value) == 3:
                    setattr(owner, attr, (*value, 1.0))
                else:
                    setattr(owner, attr, value)
            else:
                setattr(owner, attr, value)
        except Exception:
            pass


for prop in theme.bl_rna.properties:
    if prop.is_readonly or prop.identifier in {"rna_type", "name", "filepath"}:
        continue
    try:
        value = getattr(theme, prop.identifier)
    except Exception:
        continue
    if hasattr(value, "bl_rna"):
        paint(value)
    elif hasattr(value, "__iter__") and not isinstance(value, str):
        for item in value:
            if hasattr(item, "bl_rna"):
                paint(item)

for editor_name in (
    "view_3d",
    "properties",
    "outliner",
    "dopesheet_editor",
    "graph_editor",
    "nla_editor",
    "image_editor",
    "sequence_editor",
    "node_editor",
    "text_editor",
    "file_browser",
    "preferences",
    "console",
    "clip_editor",
    "spreadsheet",
):
    editor = getattr(theme, editor_name, None)
    if editor and hasattr(editor, "space"):
        set_space(editor.space)

view = theme.view_3d
for attr, value in {
    "grid": (0.30, 0.04, 0.05, 0.45),
    "grid_major": (0.55, 0.06, 0.08, 0.75),
    "clipping_border_3d": colors["outline"],
    "wire": (0.95, 0.16, 0.12),
    "wire_edit": (1.0, 0.20, 0.14),
    "object_selected": (1.0, 0.12, 0.08),
    "object_active": (1.0, 0.36, 0.08),
    "camera": (1.0, 0.10, 0.08),
    "empty": (0.95, 0.12, 0.10),
    "light": (1.0, 0.18, 0.08, 0.70),
    "view_overlay": (0.06, 0.004, 0.006),
}.items():
    if hasattr(view, attr):
        try:
            setattr(view, attr, value)
        except Exception:
            pass

for editor_name in ("dopesheet_editor", "graph_editor", "node_editor"):
    editor = getattr(theme, editor_name, None)
    if editor and hasattr(editor, "grid"):
        try:
            editor.grid = (0.32, 0.035, 0.045)
        except Exception:
            pass

if hasattr(theme.node_editor, "node_backdrop"):
    theme.node_editor.node_backdrop = colors["back"]
if hasattr(theme.outliner, "row_alternate"):
    theme.outliner.row_alternate = (0.18, 0.02, 0.025, 0.35)

for editor_name in ("topbar", "statusbar", "info"):
    editor = getattr(theme, editor_name, None)
    if editor and hasattr(editor, "space"):
        set_space(editor.space, colors["black"])

regions = theme.regions
set_attrs(regions.asset_shelf, {
    "back": colors["back"][:3],
    "header_back": colors["panel_hi"],
})
set_attrs(regions.channels, {
    "back": colors["back"][:3],
    "text": colors["muted"][:3],
    "text_selected": colors["text"][:3],
})
set_attrs(regions.scrubbing, {
    "back": colors["black"][:3],
    "text": colors["text"][:3],
    "time_marker": colors["accent"],
    "time_marker_selected": colors["accent2"],
})
set_attrs(regions.sidebars, {
    "back": colors["black"],
    "tab_back": colors["panel_hi"],
})

anim = theme.common.anim
set_attrs(anim, {
    "playhead": colors["accent"],
    "preview_range": (0.45, 0.02, 0.04, 0.35),
    "scene_strip_range": (0.50, 0.03, 0.04, 0.35),
    "channels": colors["panel"],
    "channels_sub": colors["sub"],
    "channel_group": colors["panel_hi"],
    "channel_group_active": colors["accent"],
    "channel": colors["panel"],
    "channel_selected": colors["accent"],
    "keyframe": colors["accent2"],
    "keyframe_selected": (1.0, 0.88, 0.12),
    "long_key": colors["accent"],
    "long_key_selected": colors["accent2"],
})

for editor_name in ("file_browser", "sequence_editor", "image_editor", "nla_editor", "clip_editor", "spreadsheet"):
    editor = getattr(theme, editor_name, None)
    if not editor:
        continue
    for attr in ("row_alternate", "selected_file", "selected_strip", "active_strip", "scope_back"):
        if hasattr(editor, attr):
            try:
                value = colors["accent"] if "selected" in attr or "active" in attr else (0.16, 0.02, 0.025, 0.35)
                setattr(editor, attr, value)
            except Exception:
                pass

ui = theme.user_interface
for attr in (
    "wcol_regular",
    "wcol_tool",
    "wcol_toolbar_item",
    "wcol_radio",
    "wcol_text",
    "wcol_option",
    "wcol_toggle",
    "wcol_num",
    "wcol_numslider",
    "wcol_box",
    "wcol_curve",
    "wcol_menu",
    "wcol_pulldown",
    "wcol_menu_back",
    "wcol_pie_menu",
    "wcol_tooltip",
    "wcol_menu_item",
    "wcol_scroll",
    "wcol_progress",
    "wcol_list_item",
    "wcol_tab",
):
    if not hasattr(ui, attr):
        continue
    widget = getattr(ui, attr)
    for widget_attr, value in {
        "outline": colors["outline"],
        "outline_sel": colors["accent"],
        "inner": colors["panel"],
        "inner_sel": colors["accent"],
        "item": colors["accent2"],
        "text": colors["text"],
        "text_sel": (1.0, 0.96, 0.94, 1.0),
        "shadetop": (0.28, 0.03, 0.04, 1.0),
        "shadedown": colors["black"] if "black" in colors else colors["back"],
        "roundness": 0.18,
    }.items():
        if hasattr(widget, widget_attr):
            try:
                setattr(widget, widget_attr, value)
            except Exception:
                pass

for attr, value in {
    "icon_alpha": 1.0,
    "icon_saturation": 1.0,
    "panel_roundness": 0.15,
    "panel_header": colors["panel_hi"],
    "panel_title": colors["text"],
    "panel_text": colors["muted"],
    "panel_back": colors["panel"],
    "panel_sub_back": colors["sub"],
    "panel_outline": colors["outline"],
    "panel_active": colors["accent"],
    "widget_emboss": (0.55, 0.03, 0.04, 1.0),
    "editor_border": (0.55, 0.02, 0.04, 1.0),
    "editor_outline": (0.30, 0.02, 0.03, 1.0),
    "editor_outline_active": (1.00, 0.05, 0.08, 1.0),
    "axis_x": (1.00, 0.04, 0.06, 1.0),
    "axis_y": (0.20, 0.85, 0.25, 1.0),
    "axis_z": (0.20, 0.45, 1.00, 1.0),
}.items():
    if hasattr(ui, attr):
        try:
            setattr(ui, attr, value)
        except Exception:
            pass

bpy.ops.wm.save_userpref()
print("Applied Crimson theme and saved Blender preferences.")
