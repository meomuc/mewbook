# SPDX-License-Identifier: AGPL-3.0-or-later
"""Language dispatcher: re-exports the right strings module based on AppConfig.ui_language.

Usage (replaces `from smartdoc.presentation import strings_vi as vi`):
    from smartdoc.presentation import strings as vi

The active language is resolved once at import time, so the app needs a restart
after changing the language in Settings.  That is intentional for the MVP — a full
hot-swap would require all widgets to listen for a language-change event and call
retranslateUi(), which is a larger refactor.

Adding a new language: create `strings_<code>.py` with the same identifiers, add an
entry to `_MODULES`, done.
"""
from __future__ import annotations

import importlib
import json
import types

_MODULES: dict[str, str] = {
    "vi": "smartdoc.presentation.strings_vi",
    "en": "smartdoc.presentation.strings_en",
}

_DEFAULT_LANG = "vi"


def _active_language() -> str:
    """Read ui_language from the saved settings without constructing the full app."""
    try:
        from smartdoc.core.config import default_app_data_dir  # noqa: PLC0415
        settings_path = default_app_data_dir() / "settings.json"
        if settings_path.exists():
            raw = json.loads(settings_path.read_text(encoding="utf-8-sig"))
            return str(raw.get("ui_language", _DEFAULT_LANG))
    except Exception:  # noqa: BLE001 -- never break module import
        pass
    return _DEFAULT_LANG


def _load() -> types.ModuleType:
    lang = _active_language()
    module_name = _MODULES.get(lang, _MODULES[_DEFAULT_LANG])
    return importlib.import_module(module_name)


# Resolve at import time and inject all public names into this module's namespace.
_active_mod = _load()
for _name in dir(_active_mod):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_active_mod, _name)
