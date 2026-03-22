"""Save generated project files to the local filesystem under /generatedprojects."""
from __future__ import annotations

import io
import logging
import os
import platform
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Root folder lives next to the backend/ directory (i.e. repo root)
_GENERATED_ROOT = Path(__file__).resolve().parents[3] / "generatedprojects"


def _sanitize(name: str) -> str:
    """Remove characters that are unsafe for directory names."""
    return "".join(c if (c.isalnum() or c in " _-") else "_" for c in name).strip()


def save_project_files(
    project_name: str,
    project_id: str,
    files: dict[str, str],
) -> Path:
    """Write every file in *files* to generatedprojects/<project_name>_<short_id>/.

    Returns the Path to the project directory that was written.
    """
    safe_name = _sanitize(project_name) or "untitled"
    short_id = project_id[:8] if project_id else "0000"
    folder = _GENERATED_ROOT / f"{safe_name}_{short_id}"
    folder.mkdir(parents=True, exist_ok=True)

    resolved_folder = folder.resolve()
    for filename, content in files.items():
        fpath = (folder / filename).resolve()
        # Guard against path traversal (e.g. filename = "../../etc/passwd")
        if not fpath.is_relative_to(resolved_folder):
            logger.warning("Skipping unsafe filename %r — resolves outside project folder", filename)
            continue
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        logger.debug("Saved %s", fpath)

    logger.info("Saved %d files to %s", len(files), folder)
    return folder


def get_project_dir(project_name: str, project_id: str) -> Path | None:
    """Return the project directory if it exists on disk."""
    safe_name = _sanitize(project_name) or "untitled"
    short_id = project_id[:8] if project_id else "0000"
    folder = _GENERATED_ROOT / f"{safe_name}_{short_id}"
    return folder if folder.is_dir() else None


def zip_project(project_name: str, project_id: str) -> bytes | None:
    """Create an in-memory ZIP of the project folder. Returns bytes or None."""
    folder = get_project_dir(project_name, project_id)
    if not folder:
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(folder.rglob("*")):
            if fpath.is_file():
                arcname = fpath.relative_to(folder.parent).as_posix()
                zf.write(fpath, arcname)
    buf.seek(0)
    return buf.read()


def zip_project_from_files(project_name: str, files: dict[str, str]) -> bytes:
    """Create an in-memory ZIP purely from the files dict (no disk needed)."""
    safe_name = _sanitize(project_name) or "untitled"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            # Normalise the archive entry path to prevent zip-slip attacks.
            # posixpath.normpath collapses '..' components; we also strip any
            # leading slashes so the entry is always relative.
            import posixpath
            safe_entry = posixpath.normpath(filename).lstrip("/")
            if safe_entry.startswith(".."):
                logger.warning("Skipping unsafe archive entry %r", filename)
                continue
            zf.writestr(f"{safe_name}/{safe_entry}", content)
    buf.seek(0)
    return buf.read()


def open_project_folder(project_name: str, project_id: str) -> dict[str, Any]:
    """Open the project folder in the system file explorer. Returns status dict."""
    folder = get_project_dir(project_name, project_id)
    if not folder:
        return {"success": False, "error": "Project folder not found on disk. Generate the game first.", "path": None}

    path_str = str(folder)
    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", path_str])
        elif system == "Darwin":
            subprocess.Popen(["open", path_str])
        else:
            subprocess.Popen(["xdg-open", path_str])
        return {"success": True, "path": path_str, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e), "path": path_str}


def _rglob_bounded(directory: Path, pattern: str, max_depth: int = 3):
    """rglob with a maximum directory depth to avoid scanning huge trees."""
    for item in directory.iterdir():
        if item.is_file() and item.match(pattern):
            yield item
        elif item.is_dir() and max_depth > 1:
            yield from _rglob_bounded(item, pattern, max_depth - 1)


def find_godot_executable() -> str | None:
    """Attempt to locate the Godot 4 executable on the system."""
    # Check PATH first — fastest and most reliable
    godot = shutil.which("godot") or shutil.which("godot4") or shutil.which("Godot_v4")
    if godot:
        return godot

    # Common install locations (Windows) — depth-limited to avoid scanning all of Program Files
    if platform.system() == "Windows":
        search_dirs = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")),
            Path(os.environ.get("USERPROFILE", "")) / "Downloads",
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
            Path("C:\\Godot"),
        ]
        for d in search_dirs:
            if not d.is_dir():
                continue
            try:
                for exe in _rglob_bounded(d, "Godot*.exe", max_depth=3):
                    if "console" not in exe.name.lower():
                        return str(exe)
            except PermissionError:
                continue

    # macOS
    elif platform.system() == "Darwin":
        app_path = Path("/Applications/Godot.app/Contents/MacOS/Godot")
        if app_path.exists():
            return str(app_path)

    return None


def launch_godot(project_name: str, project_id: str) -> dict[str, Any]:
    """Try to launch Godot editor with the project. Returns status dict."""
    folder = get_project_dir(project_name, project_id)
    if not folder:
        return {
            "success": False,
            "error": "Project folder not found on disk. Generate the game first.",
            "godot_found": False,
            "path": None,
        }

    godot_exe = find_godot_executable()
    if not godot_exe:
        return {
            "success": False,
            "error": "Godot not found. Download Godot 4 from https://godotengine.org/download and place it in PATH.",
            "godot_found": False,
            "path": str(folder),
        }

    try:
        subprocess.Popen([godot_exe, "--path", str(folder)])
        return {
            "success": True,
            "godot_found": True,
            "godot_path": godot_exe,
            "path": str(folder),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to launch Godot: {e}",
            "godot_found": True,
            "godot_path": godot_exe,
            "path": str(folder),
        }
