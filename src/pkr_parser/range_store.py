from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

MOSPosition = str


@dataclass(frozen=True)
class RangePack:
    meta: Dict[str, Any]
    rfi: Dict[MOSPosition, Set[str]]
    order: List[MOSPosition]


def _project_root() -> Path:
    # F:\pkr-hand-parser\src\pkr_parser\range_store.py -> parents[2] = F:\pkr-hand-parser
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_hand_key(x: str) -> str:
    return x.strip()


def _to_set_list(values: Any) -> Set[str]:
    if not isinstance(values, list):
        return set()
    out: Set[str] = set()
    for v in values:
        if isinstance(v, str) and v.strip():
            out.add(_normalize_hand_key(v))
    return out


def load_mos_rfi_pack(
    *,
    default_rel: str = "ranges/default_rfi.json",
    user_rel: str = "ranges/user_rfi.json",
) -> RangePack:
    """
    Берём MOS RFI из:
      - ranges/default_rfi.json (база)
      - ranges/user_rfi.json (оверрайд)

    ВАЖНО (MVP-семантика):
      - если user_rfi[pos] = [] (пусто) -> считаем, что юзер НЕ переопределял, берём default
      - если user_rfi[pos] содержит хотя бы 1 руку -> используем user
    Это нужно, чтобы твой текущий user_rfi.json (где везде []) не обнулял диапазоны.
    """
    root = _project_root()
    default_path = root / default_rel
    user_path = root / user_rel

    default_data = _read_json(default_path)
    user_data = _read_json(user_path)

    default_rfi_raw = default_data.get("rfi", {}) if isinstance(default_data, dict) else {}
    user_rfi_raw = user_data.get("rfi", {}) if isinstance(user_data, dict) else {}

    order: List[MOSPosition] = ["EP", "MP", "HJ", "CO"]

    rfi: Dict[MOSPosition, Set[str]] = {}
    for pos in order:
        base = _to_set_list(default_rfi_raw.get(pos)) if isinstance(default_rfi_raw, dict) else set()

        override_list = user_rfi_raw.get(pos) if isinstance(user_rfi_raw, dict) else None
        override = _to_set_list(override_list)

        if isinstance(override_list, list) and len(override_list) > 0:
            rfi[pos] = override
        else:
            rfi[pos] = base

    meta: Dict[str, Any] = {}
    if isinstance(default_data, dict) and isinstance(default_data.get("meta"), dict):
        meta.update(default_data["meta"])
    if isinstance(user_data, dict) and isinstance(user_data.get("meta"), dict):
        meta.update(user_data["meta"])

    return RangePack(meta=meta, rfi=rfi, order=order)


# Кеш, чтобы не читать JSON на каждую руку
_CACHED_PACK: Optional[RangePack] = None


def get_mos_rfi_pack() -> RangePack:
    global _CACHED_PACK
    if _CACHED_PACK is None:
        _CACHED_PACK = load_mos_rfi_pack()
    return _CACHED_PACK


def mos_min_position(hand_key: str) -> Optional[str]:
    """
    Возвращает минимальную MOS-позицию (EP/MP/HJ/CO) для hand_key по JSON-диапазонам.
    """
    hk = _normalize_hand_key(hand_key)
    pack = get_mos_rfi_pack()
    for pos in pack.order:
        if hk in pack.rfi.get(pos, set()):
            return pos
    return None
