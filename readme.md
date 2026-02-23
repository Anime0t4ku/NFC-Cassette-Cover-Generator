# NFC Cassette Cover Generator

NFC Cassette Cover Generator is a desktop application for creating a **single print-ready cassette wrap cover**.

Each export generates one complete cover image consisting of:

- Back  
- Spine  
- Front  

The output is designed for printing and folding into a physical cassette-style case, ideal for NFC projects, retro collections, and custom launch systems.

![NFC Cassette Cover Generator Screenshot](assets/screenshot.png)

---

## Download

Pre-built executables are generated automatically via GitHub Actions.

### Latest Release

| Name | Platform | Status | Download |
|------|----------|--------|----------|
| NFC Cassette Cover Generator | Windows | ![Build Status](https://github.com/Anime0t4ku/NFC-Cassette-Cover-Generator/actions/workflows/build.yml/badge.svg) | [Download Latest Release](https://github.com/Anime0t4ku/NFC-Cassette-Cover-Generator/releases) |

---

## Features (v1.0.0)

### Cover Design
- Live full-wrap preview (Back + Spine + Front combined)
- Customizable cover colors (back, spine, banner, text)
- Back summary text with dynamic wrapping
- Automatic image scaling and positioning
- Title logo overrides per side
- System logo overrides per side
- Optional original cover artwork on back
- Poster crop modes (Center / Top / Bottom / Manual slider)

### Asset Import
- Import artwork from file
- Import artwork from URL
- SteamGridDB integration (posters + title logos)
- TMDB integration (movies & TV)
- Unified search system with selectable API sources
- System logo folder search
- Optional web logo caching

### Workflow
- Timestamped exports
- “Export As…” option
- Configurable output directory
- One-click open output folder
- Persistent settings via `config.json`
- Redesigned clean Settings panel

---

## Output

- Single high-resolution PNG file
- Combined Back + Spine + Front layout
- Print-ready wrap format
- Timestamped filenames
- Manual save location via "Export As…"

---

## Supported Platform

### Windows

Pre-built executable provided.  
No Python installation required.

---

## Running From Source

Only required if you want to run or modify the script directly.

### Requirements

- Python 3.9+
- Pillow
- Requests

Install dependencies:

```bash
pip install pillow requests
```

Run:

```bash
python nfc-cassette-cover-generator.py
```

---

## License

This project is licensed under the **GNU General Public License v2.0 (GPL-2.0)**.

See the `LICENSE` file for full license details.