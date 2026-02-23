import os
import sys
import json
import subprocess

import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog

from datetime import datetime

import requests
from io import BytesIO

from PIL import Image, ImageDraw, ImageTk, ImageFont

# ============================================================
# CONFIG
# ============================================================

APP_TITLE = "Cassette Cover Generator v0.1.0 by Anime0t4ku"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "output_dir": "output",
    "system_logo_dir": "system-logos",
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

BACK_W  = 403
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
NFC_BACK_MAX  = (300, 100)

# ASSET SIZES
TITLE_LOGO_BACK_MAX = (375, 180)
TITLE_LOGO_SPINE_MAX = (183, 520)

SCREENSHOT_MAX = (350, 420)

SYSTEM_LOGO_FRONT_MAX = (360, 100)
SYSTEM_LOGO_SPINE_MAX = (120, 300)
SYSTEM_LOGO_BACK_MAX = (300, 100)

BACK_TEXT_H = 520
BACK_BRAND_ZONE_H = 220
BACK_GAP = 30

# ============================================================
# UTIL
# ============================================================

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
            self.iconphoto(True, tk.PhotoImage(file="icon.png"))
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
            "screenshot": None,
            "summary": ""
        }

        # NFC logos
        self.nfc_logos = {
            "white": Image.open("assets/nfc_logo_white.png").convert("RGBA"),
            "black": Image.open("assets/nfc_logo_black.png").convert("RGBA")
        }

        self._build_ui()
        self.update_preview()
        self.update_output_button_state()

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

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{e}")

        finally:
            self.config(cursor="")

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

        for key in ("back", "spine", "banner", "text"):
            row = ttk.Frame(color_frame)
            row.pack(anchor="w", pady=2)

            ttk.Label(row, text=key.capitalize(), width=7).pack(side="left")

            # Color preview square
            preview = tk.Label(row, width=2, background=self._rgb_to_hex(self.colors[key]))
            preview.pack(side="left", padx=4)

            # Hex entry
            hex_var = tk.StringVar(value=self._rgb_to_hex(self.colors[key]))
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
            ttk.Button(row, text="White", command=lambda s=side: set_nfc(s, "white")).pack(side="left")
            ttk.Button(row, text="Black", command=lambda s=side: set_nfc(s, "black")).pack(side="left")

        # --------------------------------------------------------
        # Asset loading
        # --------------------------------------------------------

        assets_container = ttk.Frame(self)
        assets_container.pack(fill="x", padx=10, pady=3)

        assets_center = ttk.Frame(assets_container)
        assets_center.pack()

        asset_frame = ttk.LabelFrame(assets_center, text="Assets", padding=8)
        asset_frame.pack()

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

            menu_button["menu"] = menu
            column = 2 if key == "screenshot" else 0
            menu_button.grid(row=1, column=column, padx=6, pady=6)

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

        title_menu.add_cascade(label="All Sides", menu=title_all_menu)
        title_menu.add_separator()

        # ----- Overrides -----
        self.title_logo_menu_indices = {}

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

            title_menu.add_cascade(
                label=f"Override {side.capitalize()}",
                menu=sub
            )

            self.title_logo_menu_indices[side] = title_menu.index("end")

        title_btn["menu"] = title_menu
        self.title_logo_menu = title_menu
        title_btn.grid(row=1, column=1, padx=6, pady=6)

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

        system_menu.add_cascade(label="All Sides", menu=all_menu)
        system_menu.add_separator()

        # ---------- OVERRIDES ----------
        self.system_logo_menu_indices = {}

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

            index = system_menu.index("end") + 1
            system_menu.add_cascade(
                label=f"Override {side.capitalize()}",
                menu=sub
            )

            self.system_logo_menu_indices[side] = system_menu.index("end")

        system_btn["menu"] = system_menu
        system_btn.grid(row=1, column=3, padx=6, pady=6)

        self.system_logo_menu = system_menu
        self.update_override_states()

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
        win.grab_set()
        win.resizable(False, False)

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

        # -------------------------------
        # Output Folder
        # -------------------------------

        ttk.Label(win, text="Output Folder").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 2)
        )

        raw_output = self.config_data.get("output_dir", "")
        status_text, status_color = status_label(raw_output)

        status_lbl = tk.Label(
            win,
            text=status_text,
            fg=status_color,
            anchor="w",
            justify="left",
            wraplength=500
        )
        status_lbl.grid(row=1, column=0, columnspan=3, sticky="w", padx=10)

        out_var = tk.StringVar(value=raw_output)

        ttk.Entry(
            win,
            textvariable=out_var,
            width=40
        ).grid(row=2, column=0, padx=10, pady=5)

        def browse_output():
            folder = filedialog.askdirectory()
            if folder:
                out_var.set(folder)

        ttk.Button(
            win,
            text="Browse",
            command=browse_output
        ).grid(row=2, column=1, padx=5)

        # -------------------------------
        # System Logo (Disabled)
        # -------------------------------

        ttk.Label(win, text="System Logo Folder").grid(
            row=3, column=0, sticky="w", padx=10, pady=(15, 2)
        )

        ttk.Label(
            win,
            text="Handled in a future update",
            foreground="gray"
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=10)

        ttk.Entry(
            win,
            width=40,
            state="disabled"
        ).grid(row=5, column=0, padx=10, pady=5)

        ttk.Button(
            win,
            text="Browse",
            state="disabled"
        ).grid(row=5, column=1, padx=5)

        # -------------------------------
        # Save
        # -------------------------------

        def save():
            self.config_data["output_dir"] = out_var.get()
            save_config(self.config_data)
            self.update_output_button_state()
            win.destroy()

        ttk.Button(
            win,
            text="Save",
            command=save
        ).grid(row=6, column=0, columnspan=2, pady=15)

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
            poster = fit_fill(self.assets["poster"], FRONT_W, POSTER_H)
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
        nfc_front = fit_image(
            self.nfc_logos[self.nfc_logo_colors["front"]],
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

        nfc_spine = fit_image(self.nfc_logos[self.nfc_logo_colors["spine"]], *NFC_SPINE_MAX).rotate(-90, expand=True)
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

        # --------------------------------------------------
        # Pre-calc back logos (needed for summary height)
        # --------------------------------------------------

        nfc_back = fit_image(
            self.nfc_logos[self.nfc_logo_colors["back"]],
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
            x_pos = (BACK_W - shot.width) // 2
            img.paste(shot, (x_pos, y))
            y += shot.height + BACK_GAP

        if self.assets["summary"]:
            # Calculate bottom limit dynamically
            bottom_reserved = NFC_MARGIN + nfc_back.height + BACK_GAP

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
                font = ImageFont.truetype("arialbd.ttf", 32)
            except:
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

        # Paste NFC back
        img.paste(
            nfc_back,
            ((BACK_W - nfc_back.width) // 2,
             CARD_H - nfc_back.height - NFC_MARGIN),
            nfc_back
        )

        # Paste system logo above NFC
        if sys_back:
            img.paste(
                sys_back,
                ((BACK_W - sys_back.width) // 2,
                 CARD_H - nfc_back.height - sys_back.height - BACK_GAP - NFC_MARGIN),
                sys_back
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
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            initialfile="cassette_cover.png"
        )

        if not file_path:
            return

        try:
            img = self.render()
            img.save(file_path, "PNG")
            messagebox.showinfo("Export Complete", f"Saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))
            
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
            if sys.platform.startswith("win"):
                os.startfile(output_dir)
            elif sys.platform.startswith("darwin"):
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ========================================================
    # SYSTEM LOGO (DEFAULT + OVERRIDES)
    # ========================================================

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

            key = "system_logo_default" if target == "default" else f"system_logo_{target}"
            self.assets[key] = img

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
            self.assets[key] = img
            self.update_override_states()
            self.update_preview()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_override_states(self):
        # ----- System Logo -----
        has_system_default = self.assets["system_logo_default"] is not None

        for side, index in self.system_logo_menu_indices.items():
            state = "normal" if has_system_default else "disabled"
            self.system_logo_menu.entryconfig(index, state=state)

        # ----- Title Logo -----
        has_title_default = self.assets["title_logo_default"] is not None

        for side, index in self.title_logo_menu_indices.items():
            state = "normal" if has_title_default else "disabled"
            self.title_logo_menu.entryconfig(index, state=state)

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
