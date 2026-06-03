"""
Project danjer-GAIA — TTL Manager (Slow Brain応答監視)
=========================================================
Phase 1 Round 7 (Claude) + Round 8 (GPT) 合意:
- Slow Brain は 15分間隔でスタンス出力
- TTL切れ (15min超) → new entry禁止モード
- 応答停止 5分 → 全閉 (Mass Close)
- 連続3回 JSON崩壊 (parse失敗) → Slow Brain停止+全閉 (R33対策)

Actions enum:
- USE_STANCE: 通常通り Stance を Fast Guard に渡す
- USE_DECAYED: 期限切れだが応答待ち、 decayed Stance使用
- LOCK_NEW_ENTRY: 新規エントリー禁止、 既存ポジ保持のみ可
- HALT_AND_CLOSE_ALL: 全閉+Slow Brain停止
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from .stance import Stance, decay_stance


class TTLAction(Enum):
    USE_STANCE = "use_stance"
    USE_DECAYED = "use_decayed"
    LOCK_NEW_ENTRY = "lock_new_entry"
    HALT_AND_CLOSE_ALL = "halt_and_close_all"


@dataclass
class TTLConfig:
    """TTL管理 設定"""
    ttl_seconds: int = 900        # 15分
    decay_grace_seconds: int = 300  # 5分 (TTL切れ後の grace、 decayed使用)
    halt_after_seconds: int = 300   # decay grace 終了後この秒で全閉
    decay_per_minute: float = 0.9
    max_consecutive_failures: int = 3  # 連続JSON parse失敗で halt (R33)


@dataclass
class TTLState:
    """TTL Manager の状態 (永続化対象)"""
    last_valid_stance: Optional[Stance] = None
    last_received_at: Optional[datetime] = None  # 最後にSlow Brainから何か受信した時刻
    consecutive_failures: int = 0  # 連続 JSON parse 失敗回数
    is_halted: bool = False        # halt状態か


class TTLManager:
    """
    Slow Brain → Fast Guard の橋渡し管理。

    使い方:
      mgr = TTLManager(config=TTLConfig())
      # Slow Brain から新スタンス受信
      mgr.on_stance_received(stance)
      # JSON parse失敗
      mgr.on_parse_failure()
      # Fast Guard が現在のアクションを問い合わせ
      action, stance = mgr.decide_action(now=...)
    """

    def __init__(self, config: Optional[TTLConfig] = None,
                 state: Optional[TTLState] = None):
        self.config = config or TTLConfig()
        self.state = state or TTLState()

    def on_stance_received(self, stance: Stance,
                           received_at: Optional[datetime] = None) -> None:
        """Slow Brain から新スタンスを受信"""
        n = received_at or datetime.now(timezone.utc)
        self.state.last_valid_stance = stance
        self.state.last_received_at = n
        self.state.consecutive_failures = 0
        self.state.is_halted = False

    def on_parse_failure(self, occurred_at: Optional[datetime] = None) -> None:
        """JSON parse 失敗を記録 (R33対策)"""
        self.state.consecutive_failures += 1
        if self.state.consecutive_failures >= self.config.max_consecutive_failures:
            self.state.is_halted = True

    def decide_action(self, now: Optional[datetime] = None
                      ) -> tuple[TTLAction, Optional[Stance]]:
        """
        現在の時刻における推奨アクション+使用するスタンス。

        Returns:
            (action, stance)
            stance は None の場合あり (halt 状態 or 初期化前)
        """
        n = now or datetime.now(timezone.utc)

        # halt状態 → 即全閉
        if self.state.is_halted:
            return (TTLAction.HALT_AND_CLOSE_ALL, None)

        # スタンス未受信 → new entry禁止
        if self.state.last_valid_stance is None:
            return (TTLAction.LOCK_NEW_ENTRY, None)

        stance = self.state.last_valid_stance

        # 最終受信時刻からの経過 (Slow Brain応答監視)
        if self.state.last_received_at is not None:
            seconds_since_recv = (n - self.state.last_received_at).total_seconds()
        else:
            seconds_since_recv = 0.0

        # TTL期限内 → 通常使用
        if not stance.is_expired(n):
            return (TTLAction.USE_STANCE, stance)

        # TTL期限切れ
        # grace期間内なら decayed stance を使用 (new entry禁止)
        ttl_elapsed = -stance.remaining_seconds(n)  # 期限切れからの経過
        if ttl_elapsed <= self.config.decay_grace_seconds:
            decayed = decay_stance(stance, self.config.decay_per_minute, n)
            return (TTLAction.USE_DECAYED, decayed)

        # grace超え → 全閉
        if ttl_elapsed > self.config.decay_grace_seconds + self.config.halt_after_seconds:
            self.state.is_halted = True
            return (TTLAction.HALT_AND_CLOSE_ALL, None)

        # 中間帯 (grace超え〜halt未満) → new entry禁止
        return (TTLAction.LOCK_NEW_ENTRY, None)

    def reset(self) -> None:
        """halt解除 (Slow Brain復活時に呼ぶ)"""
        self.state.consecutive_failures = 0
        self.state.is_halted = False
