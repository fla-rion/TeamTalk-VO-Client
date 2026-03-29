"""PluginPackage – .ttplugin-Paketformat (v4.10.0).

Ein .ttplugin-Paket ist eine ZIP-Datei mit folgendem Inhalt::

    manifest.json        – Pflichtfeld, Paketbeschreibung
    <plugin>.py          – Haupt-Plugin-Datei (name aus manifest)
    *.py                 – optionale Hilfsdateien

Manifest-Schema::

    {
        "name": "my_plugin",
        "display_name": "Mein Plugin",
        "version": "1.2.0",
        "description": "Was das Plugin tut",
        "author": "Autor",
        "min_app_version": "4.10.0",
        "signature": "<sha256_hex>",   # optional (v4.10.0 Signierung)
        "requires": []
    }

``signature`` ist der SHA-256-Hash der Haupt-Plugin-Datei als Hex-String.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Pflichtfelder im Manifest
_REQUIRED_FIELDS = {"name", "display_name", "version", "author"}


class PluginManifestError(ValueError):
    """Wird geworfen, wenn das Manifest ungültig ist."""


class PluginPackage:
    """Repräsentiert ein gelesenes .ttplugin-Paket."""

    def __init__(
        self,
        manifest: Dict,
        main_source: bytes,
        extra_files: Dict[str, bytes],
    ) -> None:
        self.manifest = manifest
        self.main_source = main_source
        self.extra_files = extra_files  # filename → bytes

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def display_name(self) -> str:
        return str(self.manifest.get("display_name", self.name))

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", ""))

    @property
    def author(self) -> str:
        return str(self.manifest.get("author", ""))

    @property
    def description(self) -> str:
        return str(self.manifest.get("description", ""))

    @property
    def signature(self) -> Optional[str]:
        return self.manifest.get("signature")

    def verify_signature(self) -> bool:
        """Prüft ob die Signatur des Haupt-Plugins korrekt ist.

        Gibt ``True`` zurück wenn kein Signatur-Feld vorhanden (kein Pinning).
        Gibt ``True`` zurück wenn SHA-256 der Hauptdatei mit ``signature`` übereinstimmt.
        """
        if not self.signature:
            return True
        actual = hashlib.sha256(self.main_source).hexdigest()
        return actual.lower() == self.signature.lower()


def read_package(path: Path) -> PluginPackage:
    """Liest eine .ttplugin-Datei und gibt ein :class:`PluginPackage` zurück.

    Raises:
        PluginManifestError: Wenn das Paket ungültig ist.
        zipfile.BadZipFile: Wenn die Datei kein gültiges ZIP ist.
    """
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()

        # Manifest lesen
        if "manifest.json" not in names:
            raise PluginManifestError("manifest.json fehlt im Paket")
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PluginManifestError(f"manifest.json ist kein gültiges JSON: {exc}") from exc

        if not isinstance(manifest, dict):
            raise PluginManifestError("manifest.json muss ein Objekt sein")

        missing = _REQUIRED_FIELDS - set(manifest.keys())
        if missing:
            raise PluginManifestError(f"Fehlende Pflichtfelder: {', '.join(sorted(missing))}")

        plugin_name = str(manifest["name"])
        main_filename = f"{plugin_name}.py"
        if main_filename not in names:
            raise PluginManifestError(f"Haupt-Plugin-Datei {main_filename!r} fehlt im Paket")

        main_source = zf.read(main_filename)

        # Alle weiteren .py-Dateien lesen
        extra: Dict[str, bytes] = {}
        for fname in names:
            if fname.endswith(".py") and fname != main_filename:
                extra[fname] = zf.read(fname)

    pkg = PluginPackage(manifest=manifest, main_source=main_source, extra_files=extra)
    if not pkg.verify_signature():
        raise PluginManifestError(
            f"Signatur-Prüfung fehlgeschlagen für {plugin_name}. "
            "Das Paket wurde möglicherweise verändert."
        )
    return pkg


def install_package(pkg: PluginPackage, plugins_dir: Path) -> List[Path]:
    """Installiert ein :class:`PluginPackage` ins Plugin-Verzeichnis.

    Schreibt die Haupt-Datei und alle Extra-Dateien in ``plugins_dir``.
    Gibt Liste der geschriebenen Pfade zurück.
    """
    plugins_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    main_path = plugins_dir / f"{pkg.name}.py"
    main_path.write_bytes(pkg.main_source)
    written.append(main_path)

    for fname, data in pkg.extra_files.items():
        # Nur Dateiname, keine Pfad-Traversal-Angriffe
        safe_name = Path(fname).name
        if safe_name and safe_name.endswith(".py"):
            extra_path = plugins_dir / safe_name
            extra_path.write_bytes(data)
            written.append(extra_path)

    return written


def create_package(
    plugin_path: Path,
    manifest: Dict,
    output_path: Optional[Path] = None,
    sign: bool = True,
) -> Path:
    """Erstellt eine .ttplugin-Datei aus einer Plugin-Quelle.

    Args:
        plugin_path:  Pfad zur Plugin-.py-Datei.
        manifest:     Manifest-Dict (ohne ``signature`` – wird berechnet).
        output_path:  Ausgabepfad. Standard: gleicher Ordner wie plugin_path.
        sign:         Wenn True, wird SHA-256-Signatur automatisch hinzugefügt.

    Returns:
        Pfad zur erstellten .ttplugin-Datei.
    """
    source = plugin_path.read_bytes()
    m = dict(manifest)
    m["name"] = m.get("name", plugin_path.stem)

    if sign:
        m["signature"] = hashlib.sha256(source).hexdigest()

    if output_path is None:
        output_path = plugin_path.with_suffix(".ttplugin")

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(m, ensure_ascii=False, indent=2))
        zf.write(plugin_path, f"{m['name']}.py")

    return output_path
