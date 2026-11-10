<p align="center">
  <img src="assets/icon.png" width="128" alt="PackMerge icon">
</p>

<h1 align="center">PackMerge</h1>

<p align="center">Merge a pile of Minecraft Bedrock <code>.mcaddon</code> / <code>.mcpack</code> files into one, and import them all in a single launch.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="License: GPLv3"></a>
  <img src="https://img.shields.io/badge/python-3.13-3776AB.svg?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6.svg?logo=windows&logoColor=white" alt="Platform: Windows">
</p>

---

## Why

Importing add-ons into Minecraft Bedrock on Windows means opening each file one at a time, and the game often needs closing and relaunching between imports. If you've just downloaded ten add-ons, that's ten restarts.

PackMerge takes all of them, pulls out every resource and behavior pack inside, and packs them into **one** `.mcaddon`. Open that one file and Minecraft imports everything at once.

## Features

- **Right-click merge**: Ctrl+click several `.mcaddon` / `.mcpack` files in Explorer, right-click, and choose **Merge into one .mcaddon**.
- **Handles every common layout**: packs stored as folders, nested `.mcpack` files inside a `.mcaddon`, or zips inside zips.
- **Duplicate removal**: if the same pack (matched by its manifest UUID) appears in more than one file, only the newest version is kept.
- **Tolerant of messy manifests**: comments and trailing commas, which many add-on authors leave in, don't break it.
- **One-click import**: optionally opens the merged file in Minecraft as soon as it's built.
- **Skips bad files**: a corrupt or non-add-on file is skipped and listed in the log, and the rest still merge.
- Also carries along any `.mcworld` / `.mctemplate` files bundled inside an add-on.
- Dark-themed window to add, remove and review files before merging.
- Command-line mode for scripting.

## Requirements

- Windows 10 or 11
- Minecraft Bedrock Edition (to import the result)
- Running from source only: Python 3.13 (no third-party packages needed)

## Installation

### Installer (recommended)

1. Download `PackMerge-Setup-x.y.z.exe` from the [Releases](https://github.com/nullifiedharp/PackMerge/releases) page.
2. Run it. It installs for your user only, so no admin prompt.
3. Leave **Add "Merge into one .mcaddon" to the right-click menu** ticked.

Uninstalling from *Settings → Apps* removes the right-click entry too.

### Run from source

```bat
git clone https://github.com/nullifiedharp/PackMerge.git
cd PackMerge
python packmerge.py --install
```

`--install` adds the right-click entry, which points at wherever `packmerge.py` is when you run it. If you move the file, run it again. `python packmerge.py --uninstall` removes it.

### Build it yourself

Run `build.bat`. It:

1. installs/updates PyInstaller,
2. builds `dist\PackMerge\PackMerge.exe`,
3. installs Inno Setup with `winget` if you don't have it, then builds `dist\PackMerge-Setup-x.y.z.exe`.

The version number is read from `__version__` in `packmerge.py`.

## Usage

**From Explorer**

1. Select your add-ons (Ctrl+click or Shift+click).
2. Right-click → **Merge into one .mcaddon**. On Windows 11, it's under **Show more options**.
3. Check the list and the output name (it defaults to the same folder), then click **Merge**.
4. With **Import into Minecraft when done** ticked, Minecraft opens and imports everything.

**From the Start menu**: open PackMerge and use **Add files...**.

**Command line**

Open the window with some files already listed:

```bat
PackMerge.exe a.mcaddon b.mcaddon
```

Merge without the window (from source, so the log prints to the console):

```bat
python packmerge.py --cli Out.mcaddon a.mcaddon b.mcpack
```

## How it works

A `.mcaddon` / `.mcpack` is just a zip. PackMerge opens each one and finds every folder containing a `manifest.json`; each of those is a pack. Nested `.mcpack`/`.zip` files are opened the same way, up to a few levels deep.

It reads each manifest's name, UUID, version and module type. Packs with the same UUID are de-duplicated, keeping the highest version. Every surviving pack is written to its own folder in the new archive (e.g. `Better Trees_BP/`, `Better Trees_RP/`), which is the layout Minecraft expects from a multi-pack `.mcaddon`. The file is written to a temporary name first and only swapped into place once it's complete.

Explorer starts the program once per selected file. The first copy takes charge, waits about two seconds while the others hand over their file paths, and then opens a single window with all of them.

## Notes and limitations

- **Windows 11's new menu**: the entry appears under **Show more options** (or Shift+F10), the same as most third-party right-click items.
- **Conflicting add-ons stay conflicting**: merging changes how packs are imported, not how they behave. Two add-ons that clash in-game will still clash.
- **Already-imported packs**: if a pack with the same UUID and version is already installed, Minecraft may skip it or report it as a duplicate on import.
- **Encrypted / Marketplace content** isn't supported. PackMerge is for regular community add-ons.
- **Large selections**: the right-click entry works with any number of files, but very large batches (50+) take a few extra seconds to collect.

## License

Copyright (C) 2026 NullHarp

PackMerge is free software released under the [GNU General Public License v3.0](LICENSE). You may use, study, share and modify it, but any distributed version must stay open source under the same license.
