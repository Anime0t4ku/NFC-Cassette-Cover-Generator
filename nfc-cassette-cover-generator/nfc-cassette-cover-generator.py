import os
import sys
import json
import subprocess

import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog

from datetime import datetime

import requests
from io import BytesIO

import threading
from PIL import Image, ImageDraw, ImageTk, ImageFont

# ============================================================
# CONFIG
# ============================================================

APP_TITLE = "Cassette Cover Generator v2.2.0 by Anime0t4ku"
CONFIG_FILE = "config.json"
BASE_DIR = os.path.abspath(".")
WEB_IMAGE_DIR = os.path.join(BASE_DIR, "web-images")
WEB_LOGO_DIR = os.path.join(WEB_IMAGE_DIR, "logos")

DEFAULT_CONFIG = {
    "output_dir": "output",
    "system_logo_dir": "",
    "cache_web_system_logos": False,
    "search_cached_system_logos": False,
    "steamgriddb": {"api_key": ""},
    "tmdb": {"api_key": ""},
    "colors": {
        "back": [20, 20, 20],
        "spine": [30, 30, 30],
        "banner": [200, 30, 30],
        "text": [255, 255, 255]
    },
    "nfc_logo": {
        "front": "white",
        "spine": "white",
        "back": "white"
    }
}

# ============================================================
# LOCKED PIXEL DIMENSIONS
# ============================================================

CARD_W = 1629
CARD_H = 1600

BACK_W = 403
SPINE_W = 199
FRONT_W = 1027

FRONT_X = BACK_W + SPINE_W

BANNER_H = 165
POSTER_H = 1435

PADDING = 16
NFC_MARGIN = 30

# NFC logo max sizes
NFC_FRONT_MAX = (360, 150)
NFC_SPINE_MAX = (270, 150)
NFC_BACK_MAX = (300, 100)

# ASSET SIZES
TITLE_LOGO_BACK_MAX = (375, 180)
TITLE_LOGO_SPINE_MAX = (183, 520)

SCREENSHOT_MAX = (350, 420)
EDITOR_HANDLE_SIZE = 10

ORIGINAL_COVER_BACK_MAX = (320, 320)

SYSTEM_LOGO_FRONT_MAX = (360, 100)
SYSTEM_LOGO_SPINE_MAX = (120, 300)
SYSTEM_LOGO_BACK_MAX = (300, 100)

BACK_TEXT_H = 520
BACK_BRAND_ZONE_H = 220
BACK_GAP = 30


# ============================================================
# UTIL
# ============================================================

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def load_image_from_file(path):
    img = Image.open(path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def fit_image(img, max_w, max_h):
    img = img.copy()
    iw, ih = img.size

    # Only shrink if bigger than max
    if iw > max_w or ih > max_h:
        scale = min(max_w / iw, max_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def fit_image_upscale_only(img, max_w, max_h):
    img = img.copy()
    iw, ih = img.size

    if iw < max_w and ih < max_h:
        scale = min(max_w / iw, max_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return img


def fit_fill(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))

# ============================================================
# APP
# ============================================================

class CassetteApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x880")
        try:
            self.iconphoto(True, tk.PhotoImage(file=resource_path("icon.png")))
        except:
            pass

        self.minsize(1200, 820)

        self.config_data = load_config()

        # Ensure colors section exists
        if "colors" not in self.config_data:
            self.config_data["colors"] = DEFAULT_CONFIG["colors"].copy()

        # Ensure all default color keys exist (migration-safe)
        for key, value in DEFAULT_CONFIG["colors"].items():
            if key not in self.config_data["colors"]:
                self.config_data["colors"][key] = value

        save_config(self.config_data)

        self.colors = {
            k: tuple(v)
            for k, v in self.config_data["colors"].items()
        }

        # NFC logo colors (migrate old configs safely)
        self.nfc_logo_colors = self.config_data.get(
            "nfc_logo",
            {"front": "white", "spine": "white", "back": "white"}
        )
        if "nfc_logo" not in self.config_data:
            self.config_data["nfc_logo"] = self.nfc_logo_colors
            save_config(self.config_data)

        # Assets
        self.assets = {
            "poster": None,
            "title_logo_default": None,
            "title_logo_spine": None,
            "title_logo_back": None,
            "system_logo_default": None,
            "system_logo_front": None,
            "system_logo_spine": None,
            "system_logo_back": None,
            "original_cover_back": None,
            "screenshot": None,
            "summary": ""
        }

        self.system_logo_paths = {
            "default": None,
            "front": None,
            "spine": None,
            "back": None
        }

        self.poster_orientation = "portrait"

        # Poster Editor overlays
        self.poster_overlays = []

        # NFC logos
        self.nfc_logos = {
            "white": Image.open(resource_path("assets/nfc_logo_white.png")).convert("RGBA"),
            "black": Image.open(resource_path("assets/nfc_logo_black.png")).convert("RGBA")
        }

        self._build_ui()
        self.update_crop_visibility()
        self.update_preview()
        self.update_output_button_state()
        self.update_search_menu_states()

    def load_asset_file(self, key):
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
        )
        if not path:
            return

        try:
            img = Image.open(path)

            if img.mode != "RGBA":
                img = img.convert("RGBA")

            self.assets[key] = img
            self.update_preview()

            if key == "poster":
                self.update_crop_visibility()
                self.update_poster_orientation()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{e}")

    def load_asset_url(self, key):
        url = self.ask_url()
        if not url:
            return

        # STEP 5 INSERTED HERE
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("Error", "Invalid URL")
            return

        try:
            self.config(cursor="watch")
            self.update()

            response = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()

            img = Image.open(BytesIO(response.content))

            if img.mode != "RGBA":
                img = img.convert("RGBA")

            self.assets[key] = img
            self.update_preview()

            if key == "poster":
                self.update_crop_visibility()
                self.update_poster_orientation()


        except Exception as e:

            messagebox.showerror("Error", f"Failed to load image:\n{e}")


        finally:

            self.config(cursor="")

    # ========================================================
    # CLEAR ASSETS
    # ========================================================

    def clear_asset(self, key):

        self.assets[key] = None

        if key == "poster":
            self.update_crop_visibility()

        self.update_preview()

    def clear_title_logo(self, target):

        key = "title_logo_default" if target == "default" else f"title_logo_{target}"
        self.assets[key] = None

        if target == "default":
            self.assets["title_logo_spine"] = None
            self.assets["title_logo_back"] = None

        self.update_override_states()
        self.update_preview()

    def clear_system_logo(self, target):

        key = "system_logo_default" if target == "default" else f"system_logo_{target}"
        self.assets[key] = None

        if target == "default":
            self.assets["system_logo_front"] = None
            self.assets["system_logo_spine"] = None
            self.assets["system_logo_back"] = None

        self.update_override_states()
        self.update_preview()

    # ========================================================
    # UI
    # ========================================================

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)

        top_center = ttk.Frame(top)
        top_center.pack()

        color_frame = ttk.LabelFrame(top_center, text="Cover Colors", padding=8)
        color_frame.pack(side="left", padx=12)

        self.color_hex_vars = {}
        self.color_preview_boxes = {}

        for key in ("back", "spine", "banner", "text"):
            row = ttk.Frame(color_frame)
            row.pack(anchor="w", pady=2)

            ttk.Label(row, text=key.capitalize(), width=7).pack(side="left")

            # Color preview square
            preview = tk.Label(row, width=2, background=self._rgb_to_hex(self.colors[key]))
            self.color_preview_boxes[key] = preview
            preview.pack(side="left", padx=4)

            # Hex entry
            hex_var = tk.StringVar(value=self._rgb_to_hex(self.colors[key]))
            self.color_hex_vars[key] = hex_var
            entry = ttk.Entry(row, textvariable=hex_var, width=9)
            entry.pack(side="left", padx=4)

            def update_color(*_, k=key, var=hex_var, box=preview):
                value = var.get().strip()

                if not value.startswith("#"):
                    value = "#" + value

                try:
                    rgb = self._hex_to_rgb(value)
                    self.colors[k] = rgb
                    self.config_data.setdefault("colors", {})[k] = list(rgb)
                    save_config(self.config_data)

                    box.config(background=value)
                    self.update_preview()
                except ValueError:
                    pass  # Ignore invalid hex while typing

            hex_var.trace_add("write", update_color)

            # Optional picker button
            def open_picker(k=key, var=hex_var, box=preview):
                rgb, _ = colorchooser.askcolor(color=self.colors[k], parent=self)
                if rgb:
                    rgb = tuple(int(c) for c in rgb)
                    hex_value = self._rgb_to_hex(rgb)

                    self.colors[k] = rgb
                    self.config_data.setdefault("colors", {})[k] = list(rgb)
                    save_config(self.config_data)

                    var.set(hex_value)
                    box.config(background=hex_value)
                    self.update_preview()

            ttk.Button(row, text="🎨", width=3, command=open_picker).pack(side="left", padx=2)

        nfc_frame = ttk.LabelFrame(top_center, text="NFC Logo Color")
        nfc_frame.pack(side="left", padx=12)

        # --------------------------------------------------------
        # Back Summary (Compact)
        # --------------------------------------------------------

        summary_frame = ttk.LabelFrame(top_center, text="Back Summary", padding=8)
        summary_frame.pack(side="left", padx=12)

        self.summary_text = tk.Text(
            summary_frame,
            height=4,
            width=30,
            wrap="word"
        )
        self.summary_text.pack()

        def update_summary(*_):
            self.assets["summary"] = self.summary_text.get("1.0", "end").strip()
            self.update_preview()

        def on_summary_change(event=None):
            self.assets["summary"] = self.summary_text.get("1.0", "end-1c")
            self.update_preview()

        self.summary_text.bind("<KeyRelease>", on_summary_change)
        self.summary_text.bind("<FocusOut>", on_summary_change)
        self.summary_text.bind("<<Paste>>", on_summary_change)

        def set_nfc(side, color):
            self.nfc_logo_colors[side] = color
            self.config_data["nfc_logo"] = self.nfc_logo_colors
            save_config(self.config_data)
            self.update_preview()

        for side in ("front", "spine", "back"):
            row = ttk.Frame(nfc_frame)
            row.pack(anchor="w")

            ttk.Label(row, text=side.capitalize(), width=6).pack(side="left")

            ttk.Button(
                row,
                text="White",
                command=lambda s=side: set_nfc(s, "white")
            ).pack(side="left")

            ttk.Button(
                row,
                text="Black",
                command=lambda s=side: set_nfc(s, "black")
            ).pack(side="left")

            ttk.Button(
                row,
                text="None",
                command=lambda s=side: set_nfc(s, "none")
            ).pack(side="left")

        # --------------------------------------------------------
        # Asset loading
        # --------------------------------------------------------

        assets_container = ttk.Frame(self)
        assets_container.pack(fill="x", padx=10, pady=3)

        assets_center = ttk.Frame(assets_container)
        assets_center.pack()

        asset_frame = ttk.LabelFrame(assets_center, text="Assets", padding=8)
        asset_frame.pack(side="left", padx=10)

        def load_asset(key):
            path = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
            )
            if not path:
                return
            self.assets[key] = load_image_from_file(path)
            self.update_preview()

        # Standard buttons
        buttons = [
            ("Poster", "poster"),
            ("Screenshot", "screenshot"),
            ("Original Cover", "original_cover_back"),
        ]

        for i, (label, key) in enumerate(buttons):
            menu_button = ttk.Menubutton(
                asset_frame,
                text=label,
                direction="below"
            )

            menu = tk.Menu(menu_button, tearoff=False)

            menu.add_command(
                label="Import from file",
                command=lambda k=key: self.load_asset_file(k)
            )

            menu.add_command(
                label="Import from URL",
                command=lambda k=key: self.load_asset_url(k)
            )

            if key == "poster":
                menu.add_separator()

                def make_search_cmd(k):
                    return lambda: self.open_search_window(k)

                menu.add_command(
                    label="Search...",
                    command=make_search_cmd(key)
                )

            # -------- CLEAR OPTION --------
            menu.add_separator()

            menu.add_command(
                label="Clear",
                command=lambda k=key: self.clear_asset(k)
            )
            # ------------------------------

            menu_button["menu"] = menu

            if key == "poster":
                self.poster_menu = menu

            menu_button.grid(row=1, column=i, padx=6, pady=6)

            
        # --------------------------------------------------
        # TITLE LOGO (NESTED MENU LIKE SYSTEM LOGO)
        # --------------------------------------------------

        title_btn = ttk.Menubutton(
            asset_frame,
            text="Title Logo",
            direction="below"
        )

        title_menu = tk.Menu(title_btn, tearoff=False)

        # ----- All Sides (Default) -----
        title_all_menu = tk.Menu(title_menu, tearoff=False)

        title_all_menu.add_command(
            label="Import from file",
            command=lambda: self.load_title_logo("default", "file")
        )

        title_all_menu.add_command(
            label="Import from URL",
            command=lambda: self.load_title_logo("default", "url")
        )
        title_all_menu.add_separator()

        title_all_menu.add_command(
            label="Search...",
            command=lambda: self.open_search_window("title_logo_default")
        )

        title_all_menu.add_separator()

        title_all_menu.add_command(
            label="Clear",
            command=lambda: self.clear_title_logo("default")
        )

        self.title_logo_all_search_index = title_all_menu.index("end")
        self.title_logo_all_menu = title_all_menu

        title_menu.add_cascade(label="All Sides", menu=title_all_menu)
        title_menu.add_separator()

        # ----- Overrides -----
        self.title_logo_menu_indices = {}

        self.title_logo_override_menus = {}

        for side in ("spine", "back"):
            sub = tk.Menu(title_menu, tearoff=False)

            sub.add_command(
                label="Import from file",
                command=lambda s=side: self.load_title_logo(s, "file")
            )

            sub.add_command(
                label="Import from URL",
                command=lambda s=side: self.load_title_logo(s, "url")
            )

            sub.add_separator()

            sub.add_command(
                label="Search...",
                command=lambda s=side: self.open_search_window(f"title_logo_{s}")
            )

            sub.add_separator()

            sub.add_command(
                label="Clear",
                command=lambda s=side: self.clear_title_logo(s)
            )

            # Store override menu reference
            self.title_logo_override_menus[side] = sub

            title_menu.add_cascade(
                label=f"Override {side.capitalize()}",
                menu=sub
            )

            self.title_logo_menu_indices[side] = title_menu.index("end")

        title_btn["menu"] = title_menu
        self.title_logo_menu = title_menu
        title_btn.grid(row=1, column=3, padx=6, pady=6)
        self.update_override_states()

        # --------------------------------------------------
        # SYSTEM LOGO (SPECIAL NESTED MENU)
        # --------------------------------------------------

        system_btn = ttk.Menubutton(
            asset_frame,
            text="System Logo",
            direction="below"
        )

        system_menu = tk.Menu(system_btn, tearoff=False)

        # ---------- ALL SIDES ----------
        all_menu = tk.Menu(system_menu, tearoff=False)

        all_menu.add_command(
            label="Import from file",
            command=lambda: self.load_system_logo("default", "file")
        )

        all_menu.add_command(
            label="Import from URL",
            command=lambda: self.load_system_logo("default", "url")
        )
        all_menu.add_separator()
        all_menu.add_command(
            label="Search Folder...",
            command=lambda: self.search_system_logo_folder("default")
        )

        self.system_search_default_index = all_menu.index("end")

        all_menu.add_separator()

        all_menu.add_command(
            label="Clear",
            command=lambda: self.clear_system_logo("default")
        )

        system_menu.add_cascade(label="All Sides", menu=all_menu)
        system_menu.add_separator()

        # ---------- OVERRIDES ----------

        self.system_logo_override_menus = {}

        for side in ("front", "spine", "back"):
            sub = tk.Menu(system_menu, tearoff=False)

            sub.add_command(
                label="Import from file",
                command=lambda s=side: self.load_system_logo(s, "file")
            )

            sub.add_command(
                label="Import from URL",
                command=lambda s=side: self.load_system_logo(s, "url")
            )

            sub.add_separator()

            sub.add_command(
                label="Search Folder...",
                command=lambda s=side: self.search_system_logo_folder(s)
            )

            search_index = sub.index("end")

            sub.add_separator()

            sub.add_command(
                label="Clear",
                command=lambda s=side: self.clear_system_logo(s)
            )

            # Store reference
            self.system_logo_override_menus[side] = sub

            if not hasattr(self, "system_search_override_indices"):
                self.system_search_override_indices = {}

            self.system_search_override_indices[side] = (sub, search_index)

            system_menu.add_cascade(
                label=f"Override {side.capitalize()}",
                menu=sub
            )

        system_btn["menu"] = system_menu
        system_btn.grid(row=1, column=4, padx=6, pady=6)

        # --------------------------------------------------------
        # Poster Editor Button (hidden until poster exists)
        # --------------------------------------------------------

        self.poster_editor_btn = ttk.Button(
            asset_frame,
            text="Poster Editor",
            command=self.open_poster_editor
        )

        self.poster_editor_btn.grid(row=1, column=5, padx=6, pady=6)
        self.poster_editor_btn.grid_remove()

        self.system_logo_menu = system_menu
        self.update_override_states()
        self.update_system_folder_search_state()

        # --------------------------------------------------------
        # Poster Crop Controls (hidden until poster is set)
        # --------------------------------------------------------

        self.crop_frame = ttk.LabelFrame(assets_center, text="Poster Crop", padding=8)

        self.crop_mode_var = tk.StringVar(value="center")
        self.crop_offset_var = tk.IntVar(value=0)

        self.crop_center_btn = ttk.Radiobutton(
            self.crop_frame,
            text="Center",
            variable=self.crop_mode_var,
            value="center",
            command=self.on_crop_mode_change
        )
        self.crop_center_btn.pack(side="left", padx=5)

        self.crop_top_btn = ttk.Radiobutton(
            self.crop_frame,
            text="Top",
            variable=self.crop_mode_var,
            value="top",
            command=self.on_crop_mode_change
        )
        self.crop_top_btn.pack(side="left", padx=5)

        self.crop_bottom_btn = ttk.Radiobutton(
            self.crop_frame,
            text="Bottom",
            variable=self.crop_mode_var,
            value="bottom",
            command=self.on_crop_mode_change
        )
        self.crop_bottom_btn.pack(side="left", padx=5)

        self.crop_manual_btn = ttk.Radiobutton(
            self.crop_frame,
            text="Manual",
            variable=self.crop_mode_var,
            value="manual",
            command=self.on_crop_mode_change
        )
        self.crop_manual_btn.pack(side="left", padx=5)

        self.crop_slider = ttk.Scale(
            self.crop_frame,
            from_=0,
            to=1000,
            orient="horizontal",
            variable=self.crop_offset_var,
            command=lambda e: self.update_preview()
        )

        # --------------------------------------------------------
        # Preview
        # --------------------------------------------------------

        self.preview_label = ttk.Label(self)
        self.preview_label.pack(expand=True, pady=(4, 4))

        # --------------------------------------------------------
        # Bottom Action Buttons (Centered)
        # --------------------------------------------------------

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(pady=(0, 8))

        ttk.Button(
            bottom_frame,
            text="Export",
            width=16,
            command=self.export_cover
        ).pack(side="left", padx=8)

        ttk.Button(
            bottom_frame,
            text="Export As...",
            width=16,
            command=self.export_cover_as
        ).pack(side="left", padx=8)

        ttk.Button(
            bottom_frame,
            text="Create Print PDF",
            width=18,
            command=self.open_print_pdf_window
        ).pack(side="left", padx=8)

        ttk.Button(
            bottom_frame,
            text="Load Template",
            width=16,
            command=self.load_template
        ).pack(side="left", padx=8)

        ttk.Button(
            bottom_frame,
            text="Save Template",
            width=16,
            command=self.save_template
        ).pack(side="left", padx=8)

        self.open_output_btn = ttk.Button(
            bottom_frame,
            text="Open Output Folder",
            width=20,
            command=self.open_output_folder
        )
        self.open_output_btn.pack(side="left", padx=8)

        ttk.Button(
            bottom_frame,
            text="Settings",
            width=16,
            command=self.open_settings
        ).pack(side="left", padx=8)

    # ========================================================
    # SETTINGS
    # ========================================================

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("760x780")
        win.minsize(720, 720)
        win.resizable(True, True)
        win.transient(self)
        win.grab_set()

        def resolve_path(path):
            if not path:
                return ""
            return os.path.abspath(path)

        def status_label(path):
            full_path = resolve_path(path)
            if full_path:
                if os.path.exists(full_path):
                    return f"Current: {full_path}", "green"
                else:
                    return f"Current: {full_path} (Not created yet)", "orange"
            return "Current: Not set", "red"

        # ==========================================================
        # Folder Settings (Clean Layout)
        # ==========================================================

        def resolve_path(path):
            if not path:
                return ""
            return os.path.abspath(path)

        # -------------------------------
        # Output Folder
        # -------------------------------

        output_section = ttk.Frame(win)
        output_section.pack(fill="x", padx=15, pady=(15, 10))

        ttk.Label(
            output_section,
            text="Output Folder",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        raw_output = self.config_data.get("output_dir", "")
        full_output = resolve_path(raw_output)

        output_path_label = tk.Label(
            output_section,
            text=full_output if full_output else "Not set",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=720
        )
        output_path_label.pack(anchor="w", pady=(4, 8))

        def set_output_folder():
            folder = filedialog.askdirectory()
            if folder:
                self.config_data["output_dir"] = folder
                save_config(self.config_data)
                win.destroy()
                self.open_settings()

        ttk.Button(
            output_section,
            text="Set / Change Output Folder",
            command=set_output_folder
        ).pack(anchor="w")

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=15, pady=10)

        # -------------------------------
        # System Logo Pack Folder
        # -------------------------------

        system_section = ttk.Frame(win)
        system_section.pack(fill="x", padx=15, pady=(10, 10))

        ttk.Label(
            system_section,
            text="System Logo Pack Folder",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        raw_system = self.config_data.get("system_logo_dir", "")
        full_system = resolve_path(raw_system)

        system_path_label = tk.Label(
            system_section,
            text=full_system if full_system else "Not set",
            fg="#666666",
            anchor="w",
            justify="left",
            wraplength=720
        )
        system_path_label.pack(anchor="w", pady=(4, 8))

        def set_system_folder():
            folder = filedialog.askdirectory()
            if folder:
                self.config_data["system_logo_dir"] = folder
                save_config(self.config_data)
                win.destroy()
                self.open_settings()

        ttk.Button(
            system_section,
            text="Set / Change System Logo Pack Folder",
            command=set_system_folder
        ).pack(anchor="w")

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=15, pady=10)

        # -------------------------------
        # Web Cache Options
        # -------------------------------

        cache_section = ttk.Frame(win)
        cache_section.pack(fill="x", padx=15, pady=(5, 10))

        ttk.Label(
            cache_section,
            text="Web Cache Options",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        cache_var = tk.BooleanVar(
            value=self.config_data.get("cache_web_system_logos", False)
        )

        search_cached_var = tk.BooleanVar(
            value=self.config_data.get("search_cached_system_logos", False)
        )

        ttk.Checkbutton(
            cache_section,
            text="Cache system logos loaded from URL",
            variable=cache_var
        ).pack(anchor="w", pady=(6, 2))

        ttk.Checkbutton(
            cache_section,
            text="Include cached web logos in system logo search",
            variable=search_cached_var
        ).pack(anchor="w", pady=(0, 6))

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=15, pady=10)

        # ==========================================================
        # API Management
        # ==========================================================

        def update_api_status():
            steam_key = self.config_data.get("steamgriddb", {}).get("api_key", "")
            tmdb_key = self.config_data.get("tmdb", {}).get("api_key", "")

            if steam_key:
                steam_status_label.config(text="Status: API Key Set", fg="green")
                steam_set_btn.config(text="Change API Key")
            else:
                steam_status_label.config(text="Status: Not Set", fg="red")
                steam_set_btn.config(text="Set API Key")

            if tmdb_key:
                tmdb_status_label.config(text="Status: API Key Set", fg="green")
                tmdb_set_btn.config(text="Change API Key")
            else:
                tmdb_status_label.config(text="Status: Not Set", fg="red")
                tmdb_set_btn.config(text="Set API Key")

        def set_api(service):
            key = simpledialog.askstring(
                "API Key",
                f"Enter {service} API Key:",
                parent=win
            )
            if key:
                self.config_data.setdefault(service, {})["api_key"] = key.strip()
                save_config(self.config_data)
                update_api_status()
                self.update_search_menu_states()

        def remove_api(service):
            self.config_data.setdefault(service, {})["api_key"] = ""
            save_config(self.config_data)
            update_api_status()
            self.update_search_menu_states()

        # -------------------------------
        # SteamGridDB API
        # -------------------------------

        steam_section = ttk.Frame(win)
        steam_section.pack(fill="x", padx=15, pady=(5, 10))

        ttk.Label(
            steam_section,
            text="SteamGridDB API",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        steam_status_label = tk.Label(steam_section, text="")
        steam_status_label.pack(anchor="w", pady=(4, 6))

        steam_btn_frame = ttk.Frame(steam_section)
        steam_btn_frame.pack(anchor="w")

        steam_set_btn = ttk.Button(
            steam_btn_frame,
            text="Set API Key",
            command=lambda: set_api("steamgriddb")
        )
        steam_set_btn.pack(side="left")

        ttk.Button(
            steam_btn_frame,
            text="Remove",
            command=lambda: remove_api("steamgriddb")
        ).pack(side="left", padx=6)

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=15, pady=10)

        # -------------------------------
        # TMDB API
        # -------------------------------

        tmdb_section = ttk.Frame(win)
        tmdb_section.pack(fill="x", padx=15, pady=(5, 10))

        ttk.Label(
            tmdb_section,
            text="TMDB API",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        tmdb_status_label = tk.Label(tmdb_section, text="")
        tmdb_status_label.pack(anchor="w", pady=(4, 6))

        tmdb_btn_frame = ttk.Frame(tmdb_section)
        tmdb_btn_frame.pack(anchor="w")

        tmdb_set_btn = ttk.Button(
            tmdb_btn_frame,
            text="Set API Key",
            command=lambda: set_api("tmdb")
        )
        tmdb_set_btn.pack(side="left")

        ttk.Button(
            tmdb_btn_frame,
            text="Remove",
            command=lambda: remove_api("tmdb")
        ).pack(side="left", padx=6)

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=15, pady=10)

        # -------------------------------
        # Save Button
        # -------------------------------

        def save():
            self.config_data["cache_web_system_logos"] = cache_var.get()
            self.config_data["search_cached_system_logos"] = search_cached_var.get()
            save_config(self.config_data)
            self.update_output_button_state()
            self.update_system_folder_search_state()
            win.destroy()

        save_frame = ttk.Frame(win)
        save_frame.pack(pady=20)

        ttk.Button(
            save_frame,
            text="Save",
            width=16,
            command=save
        ).pack()

        update_api_status()

    # ========================================================
    # RENDERER
    # ========================================================

    def render(self):
        img = Image.new("RGB", (CARD_W, CARD_H), self.colors["back"])
        draw = ImageDraw.Draw(img)

        # Spine background
        draw.rectangle((BACK_W, 0, BACK_W + SPINE_W, CARD_H), fill=self.colors["spine"])

        # Front banner
        draw.rectangle((FRONT_X, 0, CARD_W, BANNER_H), fill=self.colors["banner"])

        # FRONT
        if self.assets["poster"]:

            poster = self.crop_poster(self.assets["poster"], FRONT_W, POSTER_H)

            # ---------------------------------
            # Apply Poster Editor overlays
            # ---------------------------------
            if self.poster_overlays:

                poster = poster.convert("RGBA")

                scale_x = FRONT_W / self.editor_w
                scale_y = POSTER_H / self.editor_h

                for overlay in self.poster_overlays:
                    overlay_img = overlay["image"].copy()

                    w, h = overlay_img.size
                    overlay_img = overlay_img.resize(
                        (
                            int(w * overlay["scale"] * scale_x),
                            int(h * overlay["scale"] * scale_y)
                        ),
                        Image.LANCZOS
                    )

                    x = int((overlay["x"] * scale_x) - overlay_img.width / 2)
                    y = int((overlay["y"] * scale_y) - overlay_img.height / 2)

                    poster.paste(overlay_img, (x, y), overlay_img)

                poster = poster.convert("RGB")

            img.paste(poster, (FRONT_X, BANNER_H))

        logo = self.assets["system_logo_front"] or self.assets["system_logo_default"]

        if logo:
            logo_img = fit_image(logo, *SYSTEM_LOGO_FRONT_MAX)
            img.paste(
                logo_img,
                (FRONT_X + PADDING, (BANNER_H - logo_img.height) // 2),
                logo_img
            )
        # NFC FRONT
        mode = self.nfc_logo_colors["front"]

        if mode != "none":
            nfc_front = fit_image(
                self.nfc_logos[mode],
                *NFC_FRONT_MAX
            )

            img.paste(
                nfc_front,
                (CARD_W - nfc_front.width - NFC_MARGIN, NFC_MARGIN),
                nfc_front
            )
        # SPINE
        logo = self.assets["system_logo_spine"] or self.assets["system_logo_default"]

        if logo:
            rotated = logo.rotate(-90, expand=True)
            sys_spine = fit_image(rotated, *SYSTEM_LOGO_SPINE_MAX)
            img.paste(
                sys_spine,
                (BACK_W + (SPINE_W - sys_spine.width) // 2, NFC_MARGIN),
                sys_spine
            )

        title_spine = self.assets["title_logo_spine"] or self.assets["title_logo_default"]

        if title_spine:
            rotated_logo = title_spine.rotate(-90, expand=True)
            title_spine = fit_image(rotated_logo, *TITLE_LOGO_SPINE_MAX)

            img.paste(
                title_spine,
                (BACK_W + (SPINE_W - title_spine.width) // 2,
                 (CARD_H - title_spine.height) // 2),
                title_spine
            )

        mode = self.nfc_logo_colors["spine"]

        if mode != "none":
            nfc_spine = fit_image(
                self.nfc_logos[mode],
                *NFC_SPINE_MAX
            ).rotate(-90, expand=True)

            img.paste(
                nfc_spine,
                (
                    BACK_W + (SPINE_W - nfc_spine.width) // 2,
                    CARD_H - nfc_spine.height - NFC_MARGIN
                ),
                nfc_spine
            )

        # BACK
        y = PADDING

        mode = self.nfc_logo_colors["back"]

        nfc_back = None

        if mode != "none":
            nfc_back = fit_image(
                self.nfc_logos[mode],
                *NFC_BACK_MAX
            )

        back_logo_asset = self.assets["system_logo_back"] or self.assets["system_logo_default"]

        sys_back = None
        if back_logo_asset:
            sys_back = fit_image(back_logo_asset, *SYSTEM_LOGO_BACK_MAX)

        title_back = self.assets["title_logo_back"] or self.assets["title_logo_default"]

        if title_back:
            back_logo = fit_image(title_back, *TITLE_LOGO_BACK_MAX)
            img.paste(back_logo, ((BACK_W - back_logo.width) // 2, y), back_logo)
            y += back_logo.height + BACK_GAP

        if self.assets["screenshot"]:
            shot = fit_image(self.assets["screenshot"], *SCREENSHOT_MAX)
            shot = fit_image_upscale_only(shot, *SCREENSHOT_MAX)
            x_pos = (BACK_W - shot.width) // 2
            img.paste(shot, (x_pos, y))
            y += shot.height + BACK_GAP

        if self.assets["summary"]:
            # Calculate bottom limit dynamically
            bottom_reserved = NFC_MARGIN + BACK_GAP

            if nfc_back:
                bottom_reserved += nfc_back.height

            if sys_back:
                bottom_reserved += sys_back.height + BACK_GAP

            max_text_height = CARD_H - bottom_reserved - y

            # Match text width to screenshot if present
            if self.assets["screenshot"]:
                text_width = shot.width
            else:
                text_width = BACK_W - 2 * PADDING

            text_box = Image.new(
                "RGBA",
                (text_width, max_text_height),
                (0, 0, 0, 0)
            )
            td = ImageDraw.Draw(text_box)

            text = self.assets["summary"]

            # Safe font loading
            try:
                # Windows
                if sys.platform.startswith("win"):
                    font = ImageFont.truetype("arialbd.ttf", 32)

                # Linux
                elif sys.platform.startswith("linux"):
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)

                # macOS
                elif sys.platform == "darwin":
                    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 32)

                else:
                    font = ImageFont.load_default()

            except Exception:
                font = ImageFont.load_default()

            max_width = text_box.width
            max_height = text_box.height

            # Proper line height from font metrics
            ascent, descent = font.getmetrics()
            line_height = ascent + descent + 4

            # Improved wrapping engine (preserves empty lines)
            lines = []

            for raw_line in text.split("\n"):

                # Preserve empty paragraphs
                if raw_line.strip() == "":
                    lines.append("")  # blank line
                    continue

                words = raw_line.split(" ")
                current = ""

                for word in words:
                    test = word if current == "" else current + " " + word
                    width = font.getlength(test)

                    if width <= max_width:
                        current = test
                    else:
                        if current:
                            lines.append(current)
                        current = word

                if current:
                    lines.append(current)

            # Exact line height from font
            ascent, descent = font.getmetrics()
            line_height = ascent + descent

            y_offset = 0

            for line in lines:

                # Stop if next line would overflow
                if y_offset >= max_height:
                    break

                if line == "":
                    y_offset += line_height
                    continue

                td.text((0, y_offset), line, fill=self.colors["text"], font=font)
                y_offset += line_height

            if self.assets["screenshot"]:
                x_pos = (BACK_W - shot.width) // 2
            else:
                x_pos = (BACK_W - text_box.width) // 2
            img.paste(text_box, (x_pos, y), text_box)

            y += text_box.height + BACK_GAP

        # --- ORIGINAL COVER  ---

        original_cover = self.assets["original_cover_back"]

        # Calculate base Y positions
        if nfc_back:
            nfc_y = CARD_H - nfc_back.height - NFC_MARGIN
        else:
            nfc_y = CARD_H - NFC_MARGIN

        sys_y = None
        if sys_back:
            sys_y = nfc_y - sys_back.height - BACK_GAP

        orig_y = None
        if original_cover:
            original_img = fit_image(original_cover, *ORIGINAL_COVER_BACK_MAX)

            if sys_back:
                orig_y = sys_y - original_img.height - BACK_GAP
            else:
                orig_y = nfc_y - original_img.height - BACK_GAP

            img.paste(
                original_img,
                ((BACK_W - original_img.width) // 2, orig_y),
                original_img
            )

        # --- Paste system logo ---
        if sys_back:
            img.paste(
                sys_back,
                ((BACK_W - sys_back.width) // 2, sys_y),
                sys_back
            )

        # --- Paste NFC back ---
        if nfc_back:
            img.paste(
                nfc_back,
                ((BACK_W - nfc_back.width) // 2, nfc_y),
                nfc_back
            )

        return img

    # ========================================================
    # PREVIEW
    # ========================================================

    def update_preview(self):
        img = self.render()
        preview = img.resize((int(CARD_W * 0.35), int(CARD_H * 0.35)), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.tk_img)

    def refresh_color_ui(self):

        for key, rgb in self.colors.items():

            hex_value = self._rgb_to_hex(rgb)

            if key in self.color_hex_vars:
                self.color_hex_vars[key].set(hex_value)

            if key in self.color_preview_boxes:
                self.color_preview_boxes[key].config(background=hex_value)

    def _rgb_to_hex(self, rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            raise ValueError("Invalid hex")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def update_output_button_state(self):
        output_dir = self.config_data.get("output_dir", "")
        if output_dir and os.path.exists(os.path.abspath(output_dir)):
            self.open_output_btn.config(state="normal")
        else:
            self.open_output_btn.config(state="disabled")

    def update_crop_visibility(self):

        if self.assets.get("poster"):

            if not self.crop_frame.winfo_ismapped():
                self.crop_frame.pack(side="left", padx=10)

            if hasattr(self, "poster_editor_btn"):
                self.poster_editor_btn.grid()

        else:

            if self.crop_frame.winfo_ismapped():
                self.crop_frame.pack_forget()

            if hasattr(self, "poster_editor_btn"):
                self.poster_editor_btn.grid_remove()

    def update_poster_orientation(self):
        poster = self.assets.get("poster")
        if not poster:
            return

        w, h = poster.size

        if w > h:
            self.poster_orientation = "landscape"
        else:
            self.poster_orientation = "portrait"

        self.update_crop_labels()

    def update_crop_labels(self):
        if self.poster_orientation == "landscape":
            self.crop_top_btn.config(text="Left")
            self.crop_bottom_btn.config(text="Right")
        else:
            self.crop_top_btn.config(text="Top")
            self.crop_bottom_btn.config(text="Bottom")

    def crop_poster(self, img, target_w, target_h):
        iw, ih = img.size

        # Determine orientation
        landscape = iw > ih

        # Scale to fill
        scale = max(target_w / iw, target_h / ih)
        new_w = int(iw * scale)
        new_h = int(ih * scale)

        img = img.resize((new_w, new_h), Image.LANCZOS)

        mode = self.crop_mode_var.get()

        if landscape:
            # Horizontal crop
            overflow = new_w - target_w

            if mode == "center":
                left = overflow // 2
            elif mode == "top":  # means Left in landscape
                left = 0
            elif mode == "bottom":  # means Right in landscape
                left = overflow
            else:  # manual
                percent = self.crop_offset_var.get() / 1000
                left = int(overflow * percent)

            top = (new_h - target_h) // 2

        else:
            # Vertical crop
            overflow = new_h - target_h

            if mode == "center":
                top = overflow // 2
            elif mode == "top":
                top = 0
            elif mode == "bottom":
                top = overflow
            else:  # manual
                percent = self.crop_offset_var.get() / 1000
                top = int(overflow * percent)

            left = (new_w - target_w) // 2

        return img.crop((left, top, left + target_w, top + target_h))

    def on_crop_mode_change(self):
        if self.crop_mode_var.get() == "manual":
            if not self.crop_slider.winfo_ismapped():
                self.crop_slider.pack(fill="x", padx=5, pady=(6, 0))
        else:
            if self.crop_slider.winfo_ismapped():
                self.crop_slider.pack_forget()

        self.update_preview()

    def get_template_dir(self):
        path = os.path.join(BASE_DIR, "templates")
        os.makedirs(path, exist_ok=True)
        return path

    def save_template(self):

        name = simpledialog.askstring(
            "Save Template",
            "Template name:",
            parent=self
        )

        if not name:
            return

        # -------------------------------
        # Template Export Options Window
        # -------------------------------

        win = tk.Toplevel(self)
        win.title("Template Options")
        win.geometry("260x180")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Include in template:").pack(pady=(10, 5))

        colors_var = tk.BooleanVar(value=True)
        nfc_var = tk.BooleanVar(value=True)
        system_logo_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            win,
            text="Colors",
            variable=colors_var
        ).pack(anchor="w", padx=20)

        ttk.Checkbutton(
            win,
            text="NFC Logo Modes",
            variable=nfc_var
        ).pack(anchor="w", padx=20)

        ttk.Checkbutton(
            win,
            text="System Logo",
            variable=system_logo_var
        ).pack(anchor="w", padx=20)

        def confirm():

            template = {
                "version": 1
            }

            # -------------------------------
            # Colors
            # -------------------------------

            if colors_var.get():
                template["colors"] = {
                    k: list(v) for k, v in self.colors.items()
                }

            # -------------------------------
            # NFC logos
            # -------------------------------

            if nfc_var.get():
                template["nfc_logo"] = self.nfc_logo_colors.copy()

            # -------------------------------
            # System logo
            # -------------------------------

            if system_logo_var.get():

                paths = {
                    k: v for k, v in self.system_logo_paths.items() if v
                }

                if paths:
                    template["system_logo_paths"] = paths

            template_dir = self.get_template_dir()
            path = os.path.join(template_dir, f"{name}.json")

            try:

                with open(path, "w", encoding="utf-8") as f:
                    json.dump(template, f, indent=2)

                messagebox.showinfo(
                    "Template Saved",
                    f"Template '{name}' saved."
                )

                win.destroy()

            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(
            win,
            text="Save Template",
            command=confirm
        ).pack(pady=10)

    def load_template(self):

        template_dir = self.get_template_dir()

        files = [
            f for f in os.listdir(template_dir)
            if f.lower().endswith(".json")
        ]

        if not files:
            messagebox.showinfo("Templates", "No templates found.")
            return

        win = tk.Toplevel(self)
        win.title("Load Template")
        win.geometry("300x300")
        win.grab_set()

        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True, padx=10, pady=10)

        for f in files:
            listbox.insert("end", f)

        def load_selected():
            sel = listbox.curselection()
            if not sel:
                return

            file = files[sel[0]]
            path = os.path.join(template_dir, file)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Load colors
                if "colors" in data:
                    for k, v in data["colors"].items():
                        self.colors[k] = tuple(v)
                        self.config_data.setdefault("colors", {})[k] = v

                # Load NFC logo modes
                if "nfc_logo" in data:
                    self.nfc_logo_colors = data["nfc_logo"]
                    self.config_data["nfc_logo"] = self.nfc_logo_colors

                # Load system logos
                if "system_logo_paths" in data:

                    for target, path in data["system_logo_paths"].items():

                        try:

                            if path.startswith(("http://", "https://")):

                                response = requests.get(
                                    path,
                                    timeout=10,
                                    headers={"User-Agent": "Mozilla/5.0"}
                                )

                                response.raise_for_status()

                                img = Image.open(BytesIO(response.content)).convert("RGBA")

                            else:

                                if not os.path.exists(path):
                                    continue

                                img = load_image_from_file(path)

                            key = "system_logo_default" if target == "default" else f"system_logo_{target}"

                            self.assets[key] = img
                            self.system_logo_paths[target] = path

                        except Exception as e:
                            print("Failed loading system logo:", e)

                save_config(self.config_data)

                self.refresh_color_ui()
                self.update_override_states()
                self.update_preview()

                win.destroy()

            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(
            win,
            text="Load",
            command=load_selected
        ).pack(pady=6)

    def export_cover(self):
        output_dir = self.config_data.get("output_dir", "output")

        if not output_dir:
            messagebox.showerror("Error", "No output folder set.")
            return

        output_dir = os.path.abspath(output_dir)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"cassette_cover_{timestamp}.png"
        full_path = os.path.join(output_dir, filename)

        try:
            img = self.render()
            img.save(full_path, "PNG")
            messagebox.showinfo("Export Complete", f"Saved to:\n{full_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def export_cover_as(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            initialfile=f"cassette_cover_{timestamp}.png"
        )

        if not file_path:
            return

        try:
            img = self.render()
            img.save(file_path, "PNG")
            messagebox.showinfo("Export Complete", f"Saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def open_print_pdf_window(self):
        win = tk.Toplevel(self)
        win.title("Print PDF Template")
        win.geometry("950x900")
        win.minsize(820, 820)
        win.transient(self)
        win.grab_set()

        # Two fixed slots
        slots = {
            "cover1": None,
            "cover2": None
        }

        preview_label = ttk.Label(win)
        preview_label.pack(pady=(12, 8), expand=True)

        status_var = tk.StringVar(value="Cover 1: Empty    Cover 2: Empty")

        ttk.Label(
            win,
            textvariable=status_var
        ).pack(pady=(0, 8))

        def normalize_slots():
            # If only slot 2 has an image, move it to slot 1
            if slots["cover1"] is None and slots["cover2"] is not None:
                slots["cover1"] = slots["cover2"]
                slots["cover2"] = None

        def update_status():
            c1 = "Loaded" if slots["cover1"] is not None else "Empty"
            c2 = "Loaded" if slots["cover2"] is not None else "Empty"
            status_var.set(f"Cover 1: {c1}    Cover 2: {c2}")

        def render_print_page():
            # A4 at 300 DPI
            page_w, page_h = 2480, 3508
            page = Image.new("RGB", (page_w, page_h), "white")

            # Exact physical cover size
            cover_w = round((104 / 25.4) * 300)
            cover_h = round((101.5 / 25.4) * 300)

            # Gap between covers
            gap_mm = 8
            gap_px = round((gap_mm / 25.4) * 300)

            total_block_h = (cover_h * 2) + gap_px
            start_y = (page_h - total_block_h) // 2
            x = (page_w - cover_w) // 2

            y1 = start_y
            y2 = start_y + cover_h + gap_px

            cover1 = slots["cover1"]
            cover2 = slots["cover2"]

            if cover1 is not None:
                fitted1 = fit_fill(cover1.convert("RGB"), cover_w, cover_h)
                page.paste(fitted1, (x, y1))

            if cover2 is not None:
                fitted2 = fit_fill(cover2.convert("RGB"), cover_w, cover_h)
                page.paste(fitted2, (x, y2))

            return page

        def update_preview():
            normalize_slots()
            update_status()

            page = render_print_page()

            preview_w = 450
            preview_h = int(page.height * (preview_w / page.width))
            preview = page.resize((preview_w, preview_h), Image.LANCZOS)

            tk_img = ImageTk.PhotoImage(preview)
            preview_label.configure(image=tk_img)
            preview_label.image = tk_img

        def load_into_slot(slot_key):
            path = filedialog.askopenfilename(
                title="Select Cover Image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
            )
            if not path:
                return

            try:
                img = Image.open(path).convert("RGBA")
                slots[slot_key] = img
                update_preview()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image:\n{e}", parent=win)

        def load_multiple():
            paths = filedialog.askopenfilenames(
                title="Select Cover Images",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
            )

            if not paths:
                return

            try:
                selected = list(paths)

                if len(selected) > 2:
                    messagebox.showinfo(
                        "Notice",
                        "Only the first 2 images will be loaded.",
                        parent=win
                    )
                    selected = selected[:2]

                if len(selected) >= 1:
                    slots["cover1"] = Image.open(selected[0]).convert("RGBA")

                if len(selected) >= 2:
                    slots["cover2"] = Image.open(selected[1]).convert("RGBA")
                else:
                    slots["cover2"] = None

                update_preview()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load images:\n{e}", parent=win)

        def clear_slot(slot_key):
            slots[slot_key] = None
            update_preview()

        def clear_all():
            slots["cover1"] = None
            slots["cover2"] = None
            update_preview()

        def export_pdf():
            normalize_slots()

            if slots["cover1"] is None and slots["cover2"] is None:
                messagebox.showerror("Error", "Load at least one cover first.", parent=win)
                return

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            file_path = filedialog.asksaveasfilename(
                title="Save Print PDF",
                defaultextension=".pdf",
                filetypes=[("PDF File", "*.pdf")],
                initialfile=f"cassette_print_sheet_{timestamp}.pdf",
                parent=win
            )

            if not file_path:
                return

            try:
                page = render_print_page()
                page.save(file_path, "PDF", resolution=300.0)

                messagebox.showinfo(
                    "Export Complete",
                    f"Print PDF saved to:\n{file_path}",
                    parent=win
                )

            except Exception as e:
                messagebox.showerror("Error", f"Failed to create print PDF:\n{e}", parent=win)

        controls = ttk.Frame(win)
        controls.pack(pady=(0, 12))

        row1 = ttk.Frame(controls)
        row1.pack(pady=4)

        ttk.Button(
            row1,
            text="Load Cover 1",
            width=16,
            command=lambda: load_into_slot("cover1")
        ).pack(side="left", padx=6)

        ttk.Button(
            row1,
            text="Load Cover 2",
            width=16,
            command=lambda: load_into_slot("cover2")
        ).pack(side="left", padx=6)

        ttk.Button(
            row1,
            text="Load Covers",
            width=16,
            command=load_multiple
        ).pack(side="left", padx=6)

        row2 = ttk.Frame(controls)
        row2.pack(pady=4)

        ttk.Button(
            row2,
            text="Clear Cover 1",
            width=16,
            command=lambda: clear_slot("cover1")
        ).pack(side="left", padx=6)

        ttk.Button(
            row2,
            text="Clear Cover 2",
            width=16,
            command=lambda: clear_slot("cover2")
        ).pack(side="left", padx=6)

        ttk.Button(
            row2,
            text="Clear All",
            width=16,
            command=clear_all
        ).pack(side="left", padx=6)

        row3 = ttk.Frame(controls)
        row3.pack(pady=(10, 0))

        ttk.Button(
            row3,
            text="Export PDF",
            width=16,
            command=export_pdf
        ).pack(side="left", padx=6)

        ttk.Button(
            row3,
            text="Close",
            width=16,
            command=win.destroy
        ).pack(side="left", padx=6)

        update_preview()

    def open_output_folder(self):

        output_dir = self.config_data.get("output_dir", "output")

        if not output_dir:
            messagebox.showerror("Error", "No output folder set.")
            return

        output_dir = os.path.abspath(output_dir)

        if not os.path.exists(output_dir):
            messagebox.showerror("Error", "Output folder does not exist yet.")
            return

        try:
            path = os.path.abspath(output_dir)

            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", path])

            elif sys.platform.startswith("linux"):
                env = os.environ.copy()
                subprocess.Popen(
                    ["gio", "open", path],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ========================================================
    # SYSTEM LOGO (DEFAULT + OVERRIDES)
    # ========================================================

    def maybe_cache_web_logo(self, img, url):
        if not self.config_data.get("cache_web_system_logos"):
            return img

        os.makedirs(WEB_LOGO_DIR, exist_ok=True)

        name = os.path.basename(url.split("?")[0])
        name = os.path.splitext(name)[0] + ".png"

        path = os.path.join(WEB_LOGO_DIR, name)

        try:
            img = img.convert("RGBA")
            img.save(path, format="PNG")
        except Exception as e:
            print("Failed to cache system logo:", e)

        return img

    def load_system_logo(self, target, source):

        if target != "default" and not self.assets["system_logo_default"]:
            return

        try:

            if source == "file":

                path = filedialog.askopenfilename(
                    filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
                )

                if not path:
                    return

                img = load_image_from_file(path)

            else:

                url = self.ask_url()

                if not url or not url.startswith(("http://", "https://")):
                    return

                response = requests.get(
                    url,
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0"}
                )

                response.raise_for_status()

                img = Image.open(BytesIO(response.content)).convert("RGBA")

                img = self.maybe_cache_web_logo(img, url)

                path = url

            key = "system_logo_default" if target == "default" else f"system_logo_{target}"

            # Clear overrides if default changes
            if target == "default":
                self.assets["system_logo_front"] = None
                self.assets["system_logo_spine"] = None
                self.assets["system_logo_back"] = None

                self.system_logo_paths["front"] = None
                self.system_logo_paths["spine"] = None
                self.system_logo_paths["back"] = None

            self.assets[key] = img
            self.system_logo_paths[target] = path

            self.update_override_states()
            self.update_preview()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_title_logo(self, target, source):
        if target != "default" and not self.assets["title_logo_default"]:
            return

        try:
            if source == "file":
                path = filedialog.askopenfilename(
                    filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
                )
                if not path:
                    return
                img = load_image_from_file(path)
            else:
                url = self.ask_url()
                if not url or not url.startswith(("http://", "https://")):
                    return
                response = requests.get(
                    url,
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                response.raise_for_status()
                img = Image.open(BytesIO(response.content)).convert("RGBA")

            key = "title_logo_default" if target == "default" else f"title_logo_{target}"

            # If setting new default, clear overrides
            if target == "default":
                self.assets["title_logo_spine"] = None
                self.assets["title_logo_back"] = None

            self.assets[key] = img

            self.update_override_states()
            self.update_search_menu_states()
            self.update_preview()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_override_states(self):

        # ===============================
        # TITLE LOGO
        # ===============================
        has_title_default = self.assets["title_logo_default"] is not None

        if hasattr(self, "title_logo_menu"):
            end_index = self.title_logo_menu.index("end")
            if end_index is not None:
                # 0 = All Sides
                # 1 = separator
                # 2+ = overrides
                for i in range(2, end_index + 1):
                    try:
                        self.title_logo_menu.entryconfig(
                            i,
                            state="normal" if has_title_default else "disabled"
                        )
                    except:
                        pass

        # ===============================
        # SYSTEM LOGO
        # ===============================
        has_system_default = self.assets["system_logo_default"] is not None

        if hasattr(self, "system_logo_menu"):
            end_index = self.system_logo_menu.index("end")
            if end_index is not None:
                for i in range(2, end_index + 1):
                    try:
                        self.system_logo_menu.entryconfig(
                            i,
                            state="normal" if has_system_default else "disabled"
                        )
                    except:
                        pass

    def update_system_folder_search_state(self):
        folder = self.config_data.get("system_logo_dir", "")
        folder_valid = bool(folder and os.path.isdir(folder))

        state = "normal" if folder_valid else "disabled"

        # Default (All Sides)
        if hasattr(self, "system_search_default_index"):
            try:
                all_sides_menu = self.system_logo_menu.entrycget(0, "menu")
                all_sides_menu = self.nametowidget(all_sides_menu)
                all_sides_menu.entryconfig(self.system_search_default_index, state=state)
            except:
                pass

        # Overrides
        if hasattr(self, "system_search_override_indices"):
            for side, (menu, index) in self.system_search_override_indices.items():
                try:
                    menu.entryconfig(index, state=state)
                except:
                    pass

    def search_system_logo_folder(self, target):

        folder = self.config_data.get("system_logo_dir", "")
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "System logo folder not set or invalid.")
            return

        # ----------------------------------------
        # Ask for search query FIRST
        # ----------------------------------------
        query = simpledialog.askstring(
            "Search System Logos",
            "Enter filename search term:",
            parent=self
        )

        if not query:
            return

        query = query.lower().strip()

        # ----------------------------------------
        # Scan filenames ONLY (fast)
        # ----------------------------------------
        image_files = []

        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    if query in f.lower():
                        image_files.append(os.path.join(root, f))

        # Cached logos (optional)
        if self.config_data.get("search_cached_system_logos"):
            if os.path.isdir(WEB_LOGO_DIR):
                for f in os.listdir(WEB_LOGO_DIR):
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        if query in f.lower():
                            image_files.append(os.path.join(WEB_LOGO_DIR, f))

        if not image_files:
            messagebox.showinfo("No Results", "No matching system logos found.")
            return

        # ----------------------------------------
        # Show only filtered results
        # ----------------------------------------
        self.show_local_logo_grid(image_files, target)

    def show_local_logo_grid(self, paths, target):

        win = tk.Toplevel(self)
        win.title("Select System Logo")
        win.geometry("900x650")
        win.grab_set()

        canvas = tk.Canvas(win)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --------------------------------------------------
        # Mouse Wheel Support (Windows / Mac / Linux)
        # --------------------------------------------------

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_linux_scroll_up(event):
            canvas.yview_scroll(-1, "units")

        def _on_linux_scroll_down(event):
            canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_linux_scroll_up)
        canvas.bind_all("<Button-5>", _on_linux_scroll_down)

        def _unbind_mousewheel():
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        win.protocol("WM_DELETE_WINDOW", lambda: (_unbind_mousewheel(), win.destroy()))

        row = 0
        col = 0
        cols = 4

        for path in paths:
            try:
                img = Image.open(path).convert("RGBA")
                thumb = fit_image(img, 200, 200)
                tk_img = ImageTk.PhotoImage(thumb)

                lbl = tk.Label(frame, image=tk_img, cursor="hand2")
                lbl.image = tk_img

                def select_image(event, p=path):
                    full_img = Image.open(p).convert("RGBA")

                    key = "system_logo_default" if target == "default" else f"system_logo_{target}"

                    if target == "default":
                        self.assets["system_logo_front"] = None
                        self.assets["system_logo_spine"] = None
                        self.assets["system_logo_back"] = None

                    self.assets[key] = full_img
                    self.system_logo_paths[target] = p

                    self.update_override_states()
                    self.update_preview()
                    win.destroy()

                lbl.bind("<Button-1>", select_image)
                lbl.grid(row=row, column=col, padx=10, pady=10)

                col += 1
                if col >= cols:
                    col = 0
                    row += 1

            except:
                continue

    # ========================================================
    # API Helpers
    # ========================================================

    def has_steam_api(self):
        return bool(
            self.config_data.get("steamgriddb", {}).get("api_key", "").strip()
        )

    def has_tmdb_api(self):
        return bool(
            self.config_data.get("tmdb", {}).get("api_key", "").strip()
        )

    def has_any_api(self):
        return self.has_steam_api() or self.has_tmdb_api()

    def update_search_menu_states(self):
        has_api = self.has_any_api()
        has_title_default = self.assets["title_logo_default"] is not None

        # -------------------------
        # Poster
        # -------------------------
        if hasattr(self, "poster_menu"):
            end_index = self.poster_menu.index("end")
            if end_index is not None:
                for i in range(end_index + 1):
                    try:
                        if self.poster_menu.type(i) == "command":
                            if self.poster_menu.entrycget(i, "label") == "Search...":
                                self.poster_menu.entryconfig(
                                    i,
                                    state="normal" if has_api else "disabled"
                                )
                    except:
                        pass

        # -------------------------
        # Title Logo - All Sides
        # -------------------------
        if hasattr(self, "title_logo_all_menu"):
            end_index = self.title_logo_all_menu.index("end")
            if end_index is not None:
                for i in range(end_index + 1):
                    try:
                        if self.title_logo_all_menu.type(i) == "command":
                            if self.title_logo_all_menu.entrycget(i, "label") == "Search...":
                                self.title_logo_all_menu.entryconfig(
                                    i,
                                    state="normal" if has_api else "disabled"
                                )
                    except:
                        pass

        # -------------------------
        # Title Logo - Overrides
        # -------------------------
        if hasattr(self, "title_logo_override_menus"):
            for side, menu in self.title_logo_override_menus.items():
                end_index = menu.index("end")
                if end_index is not None:
                    for i in range(end_index + 1):
                        try:
                            if menu.type(i) == "command":
                                if menu.entrycget(i, "label") == "Search...":
                                    state = "normal" if (has_api and has_title_default) else "disabled"
                                    menu.entryconfig(i, state=state)
                        except:
                            pass

    # ========================================================
    # SEARCH WINDOW (TITLE SELECTOR VERSION)
    # ========================================================

    def open_search_window(self, asset_key):
        if not self.has_any_api():
            messagebox.showerror("Error", "No API key configured.")
            return

        win = tk.Toplevel(self)
        win.title("Search Title")
        win.geometry("500x200")
        win.grab_set()

        query_var = tk.StringVar()

        # --------------------------------------------------
        # API Selection (Checkboxes)
        # --------------------------------------------------

        api_frame = ttk.Frame(win)
        api_frame.pack(pady=(10, 5))

        steam_available = self.has_steam_api()
        tmdb_available = self.has_tmdb_api()

        steam_var = tk.BooleanVar(value=steam_available)
        tmdb_var = tk.BooleanVar(value=tmdb_available)

        steam_cb = ttk.Checkbutton(
            api_frame,
            text="SteamGridDB",
            variable=steam_var
        )
        steam_cb.pack(side="left", padx=10)

        tmdb_cb = ttk.Checkbutton(
            api_frame,
            text="TMDB",
            variable=tmdb_var
        )
        tmdb_cb.pack(side="left", padx=10)

        # Grey out APIs that are not configured
        if not steam_available:
            steam_cb.state(["disabled"])

        if not tmdb_available:
            tmdb_cb.state(["disabled"])

        # --------------------------------------------------
        # Search Entry
        # --------------------------------------------------

        entry = ttk.Entry(win, textvariable=query_var)
        entry.pack(fill="x", padx=15, pady=10)
        entry.focus()

        def perform_search():
            query = query_var.get().strip()
            if not query:
                return

            if not steam_var.get() and not tmdb_var.get():
                messagebox.showerror("Error", "Select at least one source.")
                return

            titles = []

            if steam_var.get():
                titles.extend(self.search_steam_titles(query))

            if tmdb_var.get():
                titles.extend(self.search_tmdb_titles(query))

            if titles:
                win.destroy()
                self.show_title_list_window(titles, asset_key)
            else:
                messagebox.showinfo("No Results", "No titles found.")

        ttk.Button(win, text="Search", command=perform_search).pack(pady=5)
        entry.bind("<Return>", lambda e: perform_search())

    # ========================================================
    # TITLE SEARCH
    # ========================================================

    def search_steam_titles(self, query):
        api_key = self.config_data["steamgriddb"]["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        results = []

        try:
            r = requests.get(
                f"https://www.steamgriddb.com/api/v2/search/autocomplete/{query}",
                headers=headers,
                timeout=10
            )
            r.raise_for_status()

            for item in r.json().get("data", [])[:10]:
                results.append({
                    "source": "steam",
                    "id": item["id"],
                    "name": item["name"]
                })

        except:
            pass

        return results

    def search_tmdb_titles(self, query):
        api_key = self.config_data["tmdb"]["api_key"]
        results = []

        try:
            r = requests.get(
                "https://api.themoviedb.org/3/search/multi",
                params={"api_key": api_key, "query": query},
                timeout=10
            )
            r.raise_for_status()

            for item in r.json().get("results", [])[:10]:

                media_type = item.get("media_type")

                # Only allow movie + tv
                if media_type not in ("movie", "tv"):
                    continue

                name = item.get("title") or item.get("name")
                if not name:
                    continue

                results.append({
                    "source": "tmdb",
                    "id": item["id"],
                    "name": name,
                    "media_type": media_type
                })

        except:
            pass

        return results

    # ========================================================
    # TITLE LIST WINDOW
    # ========================================================

    def show_title_list_window(self, titles, asset_key):
        win = tk.Toplevel(self)
        win.title("Select Title")
        win.geometry("400x400")
        win.grab_set()

        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True, padx=10, pady=10)

        for t in titles:
            if t["source"] == "steam":
                source_label = "SteamGridDB"
            else:
                source_label = "TMDB"

            listbox.insert("end", f"{t['name']} ({source_label})")

        def on_select(event):
            selection = listbox.curselection()
            if not selection:
                return

            index = selection[0]
            selected = titles[index]

            win.destroy()

            if asset_key == "poster":
                if selected["source"] == "steam":
                    urls = self.fetch_steam_posters_by_id(selected["id"])
                else:
                    urls = self.fetch_tmdb_posters_by_id(
                        selected["id"],
                        selected.get("media_type", "movie")
                    )

            else:  # Title logo search
                if selected["source"] == "steam":
                    urls = self.fetch_steam_logos_by_id(selected["id"])
                else:
                    urls = self.fetch_tmdb_logos_by_id(
                        selected["id"],
                        selected.get("media_type", "movie")
                    )

            self.show_poster_grid(urls, asset_key)

        listbox.bind("<Double-Button-1>", on_select)

    # ========================================================
    # POSTER FETCH BY ID
    # ========================================================

    def fetch_steam_posters_by_id(self, game_id):
        api_key = self.config_data["steamgriddb"]["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        urls = []

        try:
            grids = requests.get(
                f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}?dimensions=600x900",
                headers=headers,
                timeout=10
            )
            grids.raise_for_status()

            for g in grids.json().get("data", []):
                urls.append(g["url"])

        except:
            pass

        return urls

    def fetch_steam_logos_by_id(self, game_id):
        api_key = self.config_data["steamgriddb"]["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        urls = []

        try:
            r = requests.get(
                f"https://www.steamgriddb.com/api/v2/logos/game/{game_id}",
                headers=headers,
                timeout=10
            )
            r.raise_for_status()

            for item in r.json().get("data", [])[:20]:
                urls.append(item["url"])

        except:
            pass

        return urls

    def fetch_tmdb_posters_by_id(self, tmdb_id, media_type="movie"):
        api_key = self.config_data["tmdb"]["api_key"]
        urls = []

        try:
            r = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images",
                params={"api_key": api_key},
                timeout=10
            )
            r.raise_for_status()

            posters = r.json().get("posters", [])

            # Filter strictly English posters
            english_posters = [
                p for p in posters
                if p.get("iso_639_1") == "en"
            ]

            # Optional fallback if no English posters exist
            if not english_posters:
                english_posters = posters

            # NO LIMIT HERE
            for p in english_posters:
                urls.append(f"https://image.tmdb.org/t/p/w500{p['file_path']}")

        except Exception as e:
            print("TMDB poster fetch failed:", e)

        return urls

    def fetch_tmdb_logos_by_id(self, tmdb_id, media_type="movie"):
        api_key = self.config_data["tmdb"]["api_key"]
        urls = []

        try:
            r = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images",
                params={"api_key": api_key, "include_image_language": "en,null"},
                timeout=10
            )
            r.raise_for_status()

            logos = r.json().get("logos", [])

            english_logos = [
                l for l in logos
                if l.get("iso_639_1") == "en"
            ]

            if not english_logos:
                english_logos = logos

            for logo in english_logos:
                urls.append(f"https://image.tmdb.org/t/p/original{logo['file_path']}")

        except:
            pass

        return urls

    # ========================================================
    # POSTER GRID WINDOW
    # ========================================================

    def show_poster_grid(self, urls, asset_key):
        win = tk.Toplevel(self)
        if asset_key == "poster":
            win.title("Select Poster")
        elif "title_logo" in asset_key:
            win.title("Select Title Logo")
        else:
            win.title("Select Image")
        win.geometry("900x650")
        win.grab_set()

        self._thumb_refs = []

        canvas = tk.Canvas(win)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)

        frame = ttk.Frame(canvas)

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --------------------------------------------------
        # Mouse Wheel Support (Windows / Mac / Linux)
        # --------------------------------------------------

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_linux_scroll_up(event):
            canvas.yview_scroll(-1, "units")

        def _on_linux_scroll_down(event):
            canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_linux_scroll_up)
        canvas.bind_all("<Button-5>", _on_linux_scroll_down)

        def _unbind_mousewheel():
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        win.protocol("WM_DELETE_WINDOW", lambda: (_unbind_mousewheel(), win.destroy()))

        loading_label = ttk.Label(frame, text="Loading posters...")
        loading_label.grid(row=0, column=0, padx=20, pady=20)

        def load_images():
            if win.winfo_exists():
                self.after(0, loading_label.destroy)
            else:
                return

            row = 0
            col = 0
            cols = 4

            for url in urls:
                try:
                    thumb_url = url.replace("w500", "w342")

                    r = requests.get(thumb_url, timeout=10)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content)).convert("RGBA")
                    thumb = fit_image(img, 200, 300)

                    tk_img = ImageTk.PhotoImage(thumb)
                    self._thumb_refs.append(tk_img)

                    def create_label(tk_img=tk_img, full_url=url):
                        nonlocal row, col

                        lbl = tk.Label(
                            frame,
                            image=tk_img,
                            cursor="hand2",
                            bd=2,
                            relief="flat"
                        )
                        lbl.image = tk_img

                        lbl.bind("<Enter>", lambda e: e.widget.config(relief="solid"))
                        lbl.bind("<Leave>", lambda e: e.widget.config(relief="flat"))

                        def select_image(event):
                            full_r = requests.get(full_url, timeout=10)
                            full_r.raise_for_status()
                            full_img = Image.open(BytesIO(full_r.content)).convert("RGBA")

                            self.assets[asset_key] = full_img

                            if asset_key == "title_logo_default":
                                self.assets["title_logo_spine"] = None
                                self.assets["title_logo_back"] = None
                                self.update_override_states()
                                self.update_search_menu_states()

                            if asset_key == "poster":
                                self.update_crop_visibility()
                                self.update_poster_orientation()

                            self.update_preview()
                            win.destroy()

                        lbl.bind("<Button-1>", select_image)
                        lbl.grid(row=row, column=col, padx=10, pady=10)

                        col += 1
                        if col >= cols:
                            col = 0
                            row += 1

                    if win.winfo_exists():
                        self.after(0, create_label)
                    else:
                        return

                except:
                    continue

        threading.Thread(target=load_images, daemon=True).start()

    # ========================================================
    # DISPLAY GRID
    # ========================================================

    def display_thumbnails(self, urls, container, asset_key, win):
        cols = 4
        row = 0
        col = 0

        for url in urls:
            try:
                thumb_url = url.replace("w500", "w342")

                r = requests.get(thumb_url, timeout=10)
                r.raise_for_status()

                img = Image.open(BytesIO(r.content)).convert("RGBA")
                thumb = fit_image(img, 200, 300)

                tk_img = ImageTk.PhotoImage(thumb)

                lbl = tk.Label(container, image=tk_img, cursor="hand2", bd=2, relief="flat")
                lbl.image = tk_img
                self._thumb_refs.append(tk_img)

                lbl.bind("<Enter>", lambda e: e.widget.config(relief="solid"))
                lbl.bind("<Leave>", lambda e: e.widget.config(relief="flat"))

                def select_image(event, full_url=url):
                    full_r = requests.get(full_url, timeout=10)
                    full_r.raise_for_status()
                    full_img = Image.open(BytesIO(full_r.content)).convert("RGBA")

                    self.assets[asset_key] = full_img
                    self.update_preview()
                    win.destroy()

                lbl.bind("<Button-1>", select_image)
                lbl.grid(row=row, column=col, padx=10, pady=10)

                col += 1
                if col >= cols:
                    col = 0
                    row += 1

            except:
                continue

    # ========================================================
    # POSTER EDITOR
    # ========================================================

    def open_poster_editor(self):

        if not self.assets.get("poster"):
            messagebox.showerror("Error", "Load a poster first.")
            return

        self.editor_window = tk.Toplevel(self)
        win = self.editor_window
        win.title("Poster Editor")
        win.geometry("900x820")
        win.grab_set()

        poster = self.assets["poster"]

        preview = poster.copy()

        # scale poster to fill canvas height
        editor_h = 700
        editor_w = int(editor_h * FRONT_W / POSTER_H)

        preview = poster.copy()
        preview = self.crop_poster(preview, FRONT_W, POSTER_H)
        preview = preview.resize((editor_w, editor_h), Image.LANCZOS)

        pw, ph = preview.size

        canvas = tk.Canvas(
            win,
            width=editor_w,
            height=editor_h,
            bg="#222",
            highlightthickness=0
        )

        self.editor_canvas = canvas
        self.selected_overlay = None
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        canvas.pack(pady=10)

        tk_img = ImageTk.PhotoImage(preview)
        canvas.image = tk_img

        canvas.create_image(editor_w // 2, editor_h // 2, image=tk_img)

        # store editor size
        self.editor_w = editor_w
        self.editor_h = editor_h

        self.redraw_editor(canvas)

        canvas.bind("<Button-1>", self.select_overlay)
        canvas.bind("<B1-Motion>", self.drag_overlay)
        canvas.bind("<ButtonRelease-1>", self.release_overlay)
        


        # --------------------------------------------------
        # Toolbar
        # --------------------------------------------------

        toolbar = ttk.Frame(win)
        toolbar.pack(fill="x")

        ttk.Button(
            toolbar,
            text="Add Overlay (File)",
            command=lambda: self.add_overlay_file(canvas)
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Add Overlay (URL)",
            command=lambda: self.add_overlay_url(canvas)
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Delete Overlay",
            command=self.delete_selected_overlay
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Layer Up",
            command=self.overlay_layer_up
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Layer Down",
            command=self.overlay_layer_down
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Clear Overlays",
            command=self.clear_all_overlays
        ).pack(side="left", padx=5, pady=5)

        ttk.Button(
            toolbar,
            text="Apply To Cover",
            command=self.apply_poster_editor_result
        ).pack(side="left", padx=5, pady=5)

    def add_overlay_file(self, canvas):

        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")]
        )

        if not path:
            return

        try:
            img = Image.open(path).convert("RGBA")

            # Auto resize if too large for editor
            max_size = 500
            iw, ih = img.size

            scale = 1.0
            if iw > max_size or ih > max_size:
                scale = min(max_size / iw, max_size / ih)

            self.poster_overlays.append({
                "image": img,
                "x": self.editor_w // 2,
                "y": self.editor_h // 2,
                "scale": scale
            })

            self.redraw_editor(canvas)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_overlay_url(self, canvas):

        url = self.ask_url()

        if not url or not url.startswith(("http://", "https://")):
            return

        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()

            img = Image.open(BytesIO(r.content)).convert("RGBA")

            # Auto resize if too large for editor
            max_size = 500
            iw, ih = img.size

            scale = 1.0
            if iw > max_size or ih > max_size:
                scale = min(max_size / iw, max_size / ih)

            self.poster_overlays.append({
                "image": img,
                "x": self.editor_w // 2,
                "y": self.editor_h // 2,
                "scale": scale
            })

            self.redraw_editor(canvas)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def redraw_editor(self, canvas):

        canvas.delete("overlay")
        canvas.delete("handle")

        for overlay in self.poster_overlays:

            img = overlay["image"].copy()
            scale = overlay["scale"]

            w, h = img.size
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            tk_img = ImageTk.PhotoImage(img)
            overlay["tk_img"] = tk_img

            x = overlay["x"]
            y = overlay["y"]

            item = canvas.create_image(
                x,
                y,
                image=tk_img,
                anchor="center",
                tags=("overlay",)
            )

            overlay["canvas_id"] = item
            overlay["width"] = img.width
            overlay["height"] = img.height

            # Draw selection outline if active
            if overlay == self.selected_overlay:
                canvas.create_rectangle(
                    x - img.width // 2,
                    y - img.height // 2,
                    x + img.width // 2,
                    y + img.height // 2,
                    outline="#00A2FF",
                    width=2,
                    tags=("overlay",)
                )

            # ---- draw resize handles ----
            half_w = img.width // 2
            half_h = img.height // 2

            corners = [
                (x - half_w, y - half_h),
                (x + half_w, y - half_h),
                (x - half_w, y + half_h),
                (x + half_w, y + half_h),
            ]

            overlay["handles"] = []

            for cx, cy in corners:
                handle = canvas.create_rectangle(
                    cx - EDITOR_HANDLE_SIZE,
                    cy - EDITOR_HANDLE_SIZE,
                    cx + EDITOR_HANDLE_SIZE,
                    cy + EDITOR_HANDLE_SIZE,
                    fill="white",
                    outline="black",
                    tags=("handle",)
                )

                overlay["handles"].append(handle)

    def select_overlay(self, event):

        self.selected_overlay = None
        self.resize_mode = False
        
        canvas = self.editor_canvas

        item = canvas.find_closest(event.x, event.y)
        
        # Check handles first
        for overlay in self.poster_overlays:
            if item[0] in overlay.get("handles", []):
                self.selected_overlay = overlay
                self.resize_mode = True

                # Store starting scale and distance
                cx = overlay["x"]
                cy = overlay["y"]

                dx = event.x - cx
                dy = event.y - cy

                self.resize_start_distance = max((dx ** 2 + dy ** 2) ** 0.5, 1)
                self.resize_start_scale = overlay["scale"]

                return

        # Otherwise check overlay image
        for overlay in self.poster_overlays:
            if overlay.get("canvas_id") == item[0]:
                self.selected_overlay = overlay
                self.resize_mode = False
                self.drag_offset_x = overlay["x"] - event.x
                self.drag_offset_y = overlay["y"] - event.y
                return

    def drag_overlay(self, event):

        if not self.selected_overlay:
            return

        if getattr(self, "resize_mode", False):

            overlay = self.selected_overlay

            cx = overlay["x"]
            cy = overlay["y"]

            dx = event.x - cx
            dy = event.y - cy

            current_distance = max((dx ** 2 + dy ** 2) ** 0.5, 1)

            scale_ratio = current_distance / self.resize_start_distance

            overlay["scale"] = self.resize_start_scale * scale_ratio

            # Clamp scale
            overlay["scale"] = max(0.005, min(overlay["scale"], 5))

        else:

            overlay = self.selected_overlay

            new_x = event.x + self.drag_offset_x
            new_y = event.y + self.drag_offset_y

            half_w = overlay["width"] // 2
            half_h = overlay["height"] // 2

            min_x = half_w
            max_x = self.editor_w - half_w

            min_y = half_h
            max_y = self.editor_h - half_h

            new_x = max(min_x, min(max_x, new_x))
            new_y = max(min_y, min(max_y, new_y))

            overlay["x"] = new_x
            overlay["y"] = new_y

        self.redraw_editor(self.editor_canvas)

    def release_overlay(self, event):
        self.resize_mode = False
        self.redraw_editor(self.editor_canvas)

    def delete_selected_overlay(self):

        if not self.selected_overlay:
            return

        if self.selected_overlay in self.poster_overlays:
            self.poster_overlays.remove(self.selected_overlay)

        self.selected_overlay = None

        if hasattr(self, "editor_canvas"):
            self.redraw_editor(self.editor_canvas)

    def overlay_layer_up(self):

        if not self.selected_overlay:
            return

        i = self.poster_overlays.index(self.selected_overlay)

        if i < len(self.poster_overlays) - 1:
            self.poster_overlays[i], self.poster_overlays[i + 1] = \
                self.poster_overlays[i + 1], self.poster_overlays[i]

        self.redraw_editor(self.editor_canvas)

    def overlay_layer_down(self):

        if not self.selected_overlay:
            return

        i = self.poster_overlays.index(self.selected_overlay)

        if i > 0:
            self.poster_overlays[i], self.poster_overlays[i - 1] = \
                self.poster_overlays[i - 1], self.poster_overlays[i]

        self.redraw_editor(self.editor_canvas)

    def clear_all_overlays(self):

        if not self.poster_overlays:
            return

        confirm = messagebox.askyesno(
            "Clear Overlays",
            "Remove all overlays from the poster?"
        )

        if not confirm:
            return

        self.poster_overlays.clear()
        self.selected_overlay = None

        if hasattr(self, "editor_canvas"):
            self.redraw_editor(self.editor_canvas)

    def apply_poster_editor_result(self):

        if not self.assets.get("poster"):
            return

        # Confirmation dialog
        confirm = messagebox.askyesno(
            "Apply Poster Edits",
            "This will permanently merge the overlays into the poster.\n\n"
            "You will NOT be able to edit them afterwards.\n\n"
            "Continue?"
        )

        if not confirm:
            return

        poster = self.crop_poster(self.assets["poster"], FRONT_W, POSTER_H).convert("RGBA")

        scale_x = FRONT_W / self.editor_w
        scale_y = POSTER_H / self.editor_h

        for overlay in self.poster_overlays:
            overlay_img = overlay["image"].copy()

            w, h = overlay_img.size

            overlay_img = overlay_img.resize(
                (
                    int(w * overlay["scale"] * scale_x),
                    int(h * overlay["scale"] * scale_y)
                ),
                Image.LANCZOS
            )

            x = int((overlay["x"] * scale_x) - overlay_img.width / 2)
            y = int((overlay["y"] * scale_y) - overlay_img.height / 2)

            poster.paste(overlay_img, (x, y), overlay_img)

        poster = poster.convert("RGBA")

        # Replace poster in main app
        self.assets["poster"] = poster

        # Clear editor overlays
        self.poster_overlays.clear()
        self.selected_overlay = None

        # Refresh preview
        self.update_preview()

        # Close editor window
        if hasattr(self, "editor_window") and self.editor_window.winfo_exists():
            self.editor_window.destroy()

    # ========================================================
    # CUSTOM URL DIALOG
    # ========================================================

    def ask_url(self):
        win = tk.Toplevel(self)
        win.title("Enter Image URL")
        win.geometry("600x130")
        win.resizable(True, False)
        win.grab_set()

        ttk.Label(win, text="Enter image URL:").pack(anchor="w", padx=10, pady=(10, 0))

        url_var = tk.StringVar()

        entry = ttk.Entry(win, textvariable=url_var)
        entry.pack(fill="x", padx=10, pady=8)
        entry.focus()

        result = {"value": None}

        def confirm():
            result["value"] = url_var.get().strip()
            win.destroy()

        def cancel():
            win.destroy()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=5)

        ttk.Button(btn_frame, text="OK", width=10, command=confirm).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", width=10, command=cancel).pack(side="left", padx=5)

        win.wait_window()
        return result["value"]


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    CassetteApp().mainloop()
