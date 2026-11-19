from __future__ import annotations

import json
import os
import shutil
import stat
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = ".honeyos-study-library.json"
DEFAULT_DATA_ROOT = Path(os.environ.get("HONEYOS_STUDY_DATA_ROOT", "/mnt/d/HoneyOS-Data/Study"))
DEFAULT_LIBRARY_ROOT = Path(os.environ.get("HONEYOS_STUDY_LIBRARY_ROOT", "/mnt/d/HoneyOS-Data/StudyLibrary"))

class StudyStorageError(RuntimeError):
    pass

class StudyLibraryNotFoundError(KeyError):
    pass

@dataclass(frozen=True)
class StudyLibraryLocation:
    library_id: str
    name: str
    root: str
    mode: str
    online: bool
    removable: bool
    size_bytes: int
    original_bytes: int
    derived_bytes: int
    temp_bytes: int
    free_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            pass
    return total

def _safe(root: Path, rel: str) -> Path:
    root = root.resolve()
    child = (root / rel).resolve()
    try:
        child.relative_to(root)
    except ValueError as exc:
        raise StudyStorageError("path escapes library root") from exc
    return child

class StudyStorageManager:
    def __init__(self, data_root: Path | str | None = None, default_library_root: Path | str | None = None, mount_root: Path | str = "/mnt"):
        self.data_root = Path(data_root or DEFAULT_DATA_ROOT).expanduser()
        self.default_library_root = Path(default_library_root or DEFAULT_LIBRARY_ROOT).expanduser()
        self.mount_root = Path(mount_root).expanduser()
        self.registry = self.data_root / "storage-registry.json"

    def initialize(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        if not self.registry.exists():
            self._write({"version": 1, "libraries": []})
        if not any(x.get("mode") == "default" for x in self._read()["libraries"]):
            self.create_library(self.default_library_root, "HoneyOS Study Library", mode="default", removable=False)

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.registry.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "libraries": []}
        except (OSError, json.JSONDecodeError) as exc:
            raise StudyStorageError("storage registry is unreadable") from exc
        data.setdefault("libraries", [])
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        tmp = self.registry.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.registry)

    def _manifest(self, root: Path) -> dict[str, Any]:
        try:
            return json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        except Exception as exc:
            raise StudyStorageError(f"invalid library manifest: {root}") from exc

    def _layout(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for rel in ("resources", "derived", "index", "temp"):
            _safe(root, rel).mkdir(parents=True, exist_ok=True)

    def create_library(self, root: Path | str, name: str, *, mode: str = "portable", removable: bool | None = None) -> dict[str, Any]:
        if mode not in {"default", "portable"}:
            raise ValueError("mode must be default or portable")
        name = str(name or "").strip()
        if not name:
            raise ValueError("library name must not be blank")
        root = Path(root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        self._layout(root)
        mp = root / MANIFEST_NAME
        if mp.exists():
            manifest = self._manifest(root)
        else:
            manifest = {"format_version": 1, "library_id": f"lib_{uuid.uuid4().hex}", "name": name, "created_at": _now()}
            mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        removable = self._is_removable(root) if removable is None else bool(removable)
        entry = {"library_id": manifest["library_id"], "name": name, "root": str(root), "mode": mode, "removable": removable, "added_at": _now()}
        data = self._read()
        replaced = False
        for i, old in enumerate(data["libraries"]):
            if old.get("library_id") == entry["library_id"]:
                data["libraries"][i] = {**old, **entry}; replaced = True; break
        if not replaced:
            data["libraries"].append(entry)
        self._write(data)
        return self.describe(entry["library_id"])

    def _entry(self, library_id: str) -> dict[str, Any]:
        for row in self._read()["libraries"]:
            if row.get("library_id") == library_id:
                return row
        raise StudyLibraryNotFoundError(library_id)

    def describe(self, library_id: str) -> dict[str, Any]:
        row = self._entry(library_id)
        root = Path(row["root"])
        if not root.exists():
            raise StudyLibraryNotFoundError(library_id)
        manifest = self._manifest(root)
        if manifest.get("library_id") != library_id:
            raise StudyStorageError("manifest id mismatch")
        original = _size(_safe(root, "resources"))
        derived = _size(_safe(root, "derived")) + _size(_safe(root, "index"))
        temp = _size(_safe(root, "temp"))
        try:
            free = shutil.disk_usage(root).free
        except OSError:
            free = None
        return StudyLibraryLocation(library_id, row.get("name", library_id), str(root.resolve()), row.get("mode", "portable"), True, bool(row.get("removable")), original + derived + temp, original, derived, temp, free).to_dict()

    def list_libraries(self, discover: bool = True) -> list[dict[str, Any]]:
        self.initialize()
        if discover:
            self.discover_external_libraries()
        out = []
        for row in self._read()["libraries"]:
            try:
                out.append(self.describe(row["library_id"]))
            except StudyLibraryNotFoundError:
                out.append(StudyLibraryLocation(row["library_id"], row.get("name", row["library_id"]), row.get("root", ""), row.get("mode", "portable"), False, bool(row.get("removable")), 0, 0, 0, 0, None).to_dict())
        return sorted(out, key=lambda x: (not x["online"], x["name"].casefold()))

    def cleanup_expired_temp(
        self, library_id: str, *, protected_paths: set[Path] | None = None
    ) -> dict[str, Any]:
        library = self.describe(library_id)
        root = Path(library["root"])
        temporary = root / "temp"
        cutoff = time.time() - 24 * 60 * 60
        protected_names = {str(path).casefold() for path in protected_paths or ()}
        freed = 0
        if not temporary.is_symlink() and temporary.is_dir():
            for directory, subdirectories, files in os.walk(temporary, followlinks=False):
                parent = Path(directory)
                subdirectories[:] = [name for name in subdirectories if not (parent / name).is_symlink()]
                for name in files:
                    candidate = parent / name
                    if str(candidate).casefold() in protected_names:
                        continue
                    try:
                        info = candidate.lstat()
                        if stat.S_ISREG(info.st_mode) and max(info.st_mtime, info.st_atime) < cutoff:
                            candidate.unlink()
                            freed += info.st_size
                    except FileNotFoundError:
                        continue
        return {"library_id": library_id, "freed_bytes": freed, "library": self.describe(library_id)}

    def cleanup(
        self, library_id: str, target: str = "temp", *, protected_paths: set[Path] | None = None
    ) -> dict[str, Any]:
        if target == "expired_temp":
            return self.cleanup_expired_temp(library_id, protected_paths=protected_paths)
        row = self._entry(library_id)
        root = Path(row["root"])
        if not root.exists():
            raise StudyLibraryNotFoundError(library_id)
        if target == "temp":
            paths = [_safe(root, "temp")]
        elif target == "derived":
            paths = [_safe(root, "derived"), _safe(root, "index")]
        elif target == "all_derived":
            paths = [_safe(root, "derived"), _safe(root, "index"), _safe(root, "temp")]
        else:
            raise ValueError("target must be temp, derived, or all_derived")
        if any(
            Path(str(source).casefold()).is_relative_to(Path(str(path).casefold()))
            for source in protected_paths or ()
            for path in paths
        ):
            raise StudyStorageError("清理范围包含已引用的原文件")
        before = sum(_size(p) for p in paths)
        for p in paths:
            if p.exists(): shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)
        return {"library_id": library_id, "target": target, "freed_bytes": before, "library": self.describe(library_id)}

    def discover_external_libraries(self) -> list[dict[str, Any]]:
        found = []
        if not self.mount_root.exists():
            return found
        try:
            mounts = [p for p in self.mount_root.iterdir() if p.is_dir() and p.name.lower() != "d"]
        except OSError:
            return found
        for mount in mounts:
            candidates = [mount / "HoneyOS-Study-Library"]
            try:
                candidates.extend(p for p in mount.iterdir() if p.is_dir() and (p / MANIFEST_NAME).is_file())
            except OSError:
                pass
            for root in candidates:
                if not (root / MANIFEST_NAME).is_file():
                    continue
                try:
                    m = self._manifest(root)
                    data = self._read()
                    entry = {"library_id": m["library_id"], "name": m.get("name", root.name), "root": str(root.resolve()), "mode": "portable", "removable": True, "added_at": _now()}
                    matched = False
                    for i, old in enumerate(data["libraries"]):
                        if old.get("library_id") == entry["library_id"]:
                            data["libraries"][i] = {**old, **entry}; matched = True; break
                    if not matched: data["libraries"].append(entry)
                    self._write(data)
                    found.append(self.describe(entry["library_id"]))
                except Exception:
                    continue
        return found

    def _is_removable(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.mount_root.resolve())
        except ValueError:
            return False
        return bool(rel.parts and rel.parts[0].lower() != "d")
