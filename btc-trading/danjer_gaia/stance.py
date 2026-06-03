"""
Project danjer-GAIA — Slow Brain Stance
==========================================
3者会議 Phase 1 Round 10 合意:
- スタンス JSON 9項目: direction / confidence / risk_level / valid_until /
                       max_lev / sl_atr_mult / tp_policy / stance / notes
- TTL = 15分 (デフォルト)
- R33 対策: strict_json_schema 強制 + パース失敗時 decay フォールバック
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Any
import json
import math


StanceLabel = Literal["long_bias", "short_bias", "neutral", "wait"]
TPPolicy = Literal["fixed", "trailing", "scenario"]


# JSON Schema (Gemini API の structured output 用)
STANCE_JSON_SCHEMA = {
    "type": "object",
    "required": [
        "direction", "confidence", "risk_level", "valid_until",
        "max_lev", "sl_atr_mult", "tp_policy", "stance",
    ],
    "properties": {
        "direction":    {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "confidence":   {"type": "number", "minimum": 0.0,  "maximum": 1.0},
        "risk_level":   {"type": "number", "minimum": 0.0,  "maximum": 1.0},
        "valid_until":  {"type": "string", "format": "date-time"},
        "max_lev":      {"type": "number", "minimum": 0.0,  "maximum": 10.0},
        "sl_atr_mult":  {"type": "number", "minimum": 0.5,  "maximum": 5.0},
        "tp_policy":    {"type": "string", "enum": ["fixed", "trailing", "scenario"]},
        "stance":       {"type": "string", "enum": ["long_bias", "short_bias", "neutral", "wait"]},
        "notes":        {"type": "string"},  # monitor用、 報酬関数の入力からは除外
    },
}


@dataclass
class Stance:
    """Slow Brain 出力の 1スタンス"""

    direction: float        # -1.0 (full short) 〜 +1.0 (full long)
    confidence: float       # 0.0 (薄い) 〜 1.0 (確信)
    risk_level: float       # 0.0 (安全) 〜 1.0 (要警戒/罠の匂い)
    valid_until: datetime   # TTL 期限 (UTC)
    max_lev: float          # 0.0-10.0
    sl_atr_mult: float      # 0.5-5.0 (ATR×係数 で SL距離)
    tp_policy: TPPolicy     # 利確戦略
    stance: StanceLabel     # 全体姿勢ラベル
    notes: str = ""         # monitor用 (報酬関数の入力からは除外、 R33対策)
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """TTL 期限切れか?"""
        n = now if now is not None else datetime.now(timezone.utc)
        # 比較のため timezone-aware に揃える
        vu = self.valid_until
        if vu.tzinfo is None:
            vu = vu.replace(tzinfo=timezone.utc)
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        return n > vu

    def remaining_seconds(self, now: Optional[datetime] = None) -> float:
        """TTL 残り秒数 (期限切れなら 負値)"""
        n = now if now is not None else datetime.now(timezone.utc)
        vu = self.valid_until
        if vu.tzinfo is None:
            vu = vu.replace(tzinfo=timezone.utc)
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        return (vu - n).total_seconds()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["valid_until"] = self.valid_until.isoformat()
        d["issued_at"] = self.issued_at.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def parse_stance(raw: str | dict, default_ttl_seconds: int = 900) -> Stance:
    """
    LLM出力のJSON文字列 (or dict) を Stance に変換。
    valid_until が無い場合は issued_at + default_ttl_seconds で補完。

    Raises: ValueError if 必須フィールド欠落 or 値域違反 (strict_json_schema 違反)
    """
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    else:
        data = dict(raw)

    # 必須フィールド
    required = ["direction", "confidence", "risk_level", "max_lev",
                "sl_atr_mult", "tp_policy", "stance"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # 値域チェック
    def check(name, value, lo, hi):
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} not numeric: {value}")
        if not (lo <= v <= hi):
            raise ValueError(f"{name} out of range [{lo}, {hi}]: {v}")
        return v

    direction = check("direction", data["direction"], -1.0, 1.0)
    confidence = check("confidence", data["confidence"], 0.0, 1.0)
    risk_level = check("risk_level", data["risk_level"], 0.0, 1.0)
    max_lev = check("max_lev", data["max_lev"], 0.0, 10.0)
    sl_atr_mult = check("sl_atr_mult", data["sl_atr_mult"], 0.5, 5.0)

    tp_policy = data["tp_policy"]
    if tp_policy not in ("fixed", "trailing", "scenario"):
        raise ValueError(f"tp_policy invalid: {tp_policy}")
    stance_label = data["stance"]
    if stance_label not in ("long_bias", "short_bias", "neutral", "wait"):
        raise ValueError(f"stance invalid: {stance_label}")

    issued_at = datetime.now(timezone.utc)
    if "valid_until" in data:
        try:
            valid_until = datetime.fromisoformat(data["valid_until"].replace("Z", "+00:00"))
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            raise ValueError(f"valid_until invalid: {data['valid_until']}")
    else:
        valid_until = issued_at + timedelta(seconds=default_ttl_seconds)

    return Stance(
        direction=direction,
        confidence=confidence,
        risk_level=risk_level,
        valid_until=valid_until,
        max_lev=max_lev,
        sl_atr_mult=sl_atr_mult,
        tp_policy=tp_policy,
        stance=stance_label,
        notes=data.get("notes", ""),
        issued_at=issued_at,
    )


def decay_stance(stance: Stance, decay_per_minute: float = 0.9,
                 now: Optional[datetime] = None) -> Stance:
    """
    Slow Brain 応答停止時の decay フォールバック (R33対策)
    confidence を 1分ごとに decay_per_minute 倍する。
    Returns: 新しい Stance (元のは変更しない)
    """
    n = now if now is not None else datetime.now(timezone.utc)
    elapsed_min = max(0.0, (n - stance.issued_at).total_seconds() / 60.0)
    factor = decay_per_minute ** elapsed_min
    new_conf = max(0.0, min(1.0, stance.confidence * factor))
    # decay すると stance label も neutral 寄りに

    new_stance_label: StanceLabel = stance.stance
    if new_conf < 0.3 and stance.stance in ("long_bias", "short_bias"):
        new_stance_label = "neutral"

    return Stance(
        direction=stance.direction,
        confidence=new_conf,
        risk_level=min(1.0, stance.risk_level + 0.1 * elapsed_min),  # 時間経過で危険度UP
        valid_until=stance.valid_until,
        max_lev=stance.max_lev,
        sl_atr_mult=stance.sl_atr_mult,
        tp_policy=stance.tp_policy,
        stance=new_stance_label,
        notes=stance.notes + f" [decayed {elapsed_min:.1f}min, conf×{factor:.3f}]",
        issued_at=stance.issued_at,
    )
