"""Guard: each config/*.yaml carries ONLY allowlisted authored keys (oxjob #405
Phase D — ACCEPTANCE Test 4).

The entity config files were trimmed to exactly the keys the server consumes as
THE entity registry (`core/entities.py`): identity + ID shape + closed-vocab
values + curated display/alias fields. The huge `columns:` block (a stale
duplicate of the `/properties` catalog, derived from `fields.py`) and the
GUI-only display keys (`icon`, `color`, `showOnEntityPage`, `sortByDefault`, …)
were deleted in Phase D. This test stops them growing back: a stray `columns:` or
`icon:` re-added to any file fails CI. It's a pure file check — no app boot, no ES.
"""

import glob
import os

import yaml

# The authored-key allowlist (must match core/entities.py's reads). `values` is
# absent on open entities, `descrFull`/`alternate_names` are optional — the guard
# checks the key set is a SUBSET of this, not that every key is present.
ALLOWED_KEYS = {
    "id",
    "idRegex",
    "values",
    "displayName",
    "displayNameSingular",
    "descrFull",
    "descr",
    "isNative",
    "alternate_names",
}

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
)


def _config_files():
    return sorted(glob.glob(os.path.join(_CONFIG_DIR, "*.yaml")))


def _extra_keys(doc):
    """Keys present in the config doc that are NOT in the allowlist."""
    return set(doc) - ALLOWED_KEYS


def test_all_config_files_present():
    # 23 entity config files (one per browsable entity type).
    assert len(_config_files()) == 23


def test_every_config_yaml_only_has_allowlisted_keys():
    for path in _config_files():
        with open(path) as fh:
            doc = yaml.safe_load(fh) or {}
        extra = _extra_keys(doc)
        assert not extra, (
            f"{os.path.basename(path)} carries non-allowlisted keys {sorted(extra)} "
            f"— the columns:/GUI-display blocks were trimmed in oxjob #405 Phase D; "
            f"don't re-add them (properties are served from fields.py via /properties)."
        )


def test_essential_keys_present():
    # Every file must at least carry its identity + ID shape.
    for path in _config_files():
        with open(path) as fh:
            doc = yaml.safe_load(fh) or {}
        assert "id" in doc, f"{os.path.basename(path)} missing id"
        assert "idRegex" in doc, f"{os.path.basename(path)} missing idRegex"


def test_guard_catches_a_bloated_config():
    # A deliberately-bloated doc must trip the guard — proves it actually blocks
    # regrowth (the columns: block + an icon GUI key are the canonical offenders).
    bloated = {
        "id": "works",
        "idRegex": "(w\\d+)",
        "columns": {"id": {"type": "string"}},
        "icon": "mdi-file",
        "showOnEntityPage": ["id"],
    }
    assert _extra_keys(bloated) == {"columns", "icon", "showOnEntityPage"}
