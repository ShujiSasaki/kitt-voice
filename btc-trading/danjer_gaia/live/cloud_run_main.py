"""
Project danjer-GAIA — Cloud Run エントリポイント
==================================================
Phase 2.5 (Round 22 v2 設計):
- Min Instances = 1 (常時起動)
- Cloud Scheduler から 15分毎に /predict が叩かれる
- 内部で KeepAliveThread が 4分毎に Cache life 延長 (R42対策)
- /predict: Slow Brain → Stance → TTL → Fast Guard → Order Gate → place_order

エンドポイント:
  GET /health      → ヘルスチェック
  GET /stats       → keep-alive 統計
  POST /predict    → Slow Brain 実行 (Cloud Scheduler から)
  POST /emergency  → 緊急全閉 (Slack /halt から)
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Cloud Run でも local でも動くように軽量フレームワーク (Flask) を仮定
try:
    from flask import Flask, jsonify, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    Flask = None  # type: ignore


def create_app(
    keep_alive_interval: int = 240,
    cache_name: Optional[str] = None,
):
    """Cloud Run アプリ作成 (起動時に keep_alive スレッド開始)"""
    if not HAS_FLASK:
        raise RuntimeError("Flask not installed. pip install flask")

    from .keep_alive import KeepAliveThread

    app = Flask(__name__)
    keep_alive = KeepAliveThread(
        interval_seconds=keep_alive_interval,
        cache_name=cache_name,
    )
    keep_alive.start()
    app.config["KEEP_ALIVE"] = keep_alive

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "keep_alive_alive": keep_alive.thread.is_alive() if keep_alive.thread else False,
        })

    @app.route("/stats", methods=["GET"])
    def stats():
        return jsonify(keep_alive.stats())

    @app.route("/predict", methods=["POST"])
    def predict():
        """Cloud Scheduler から 15分毎に叩かれる"""
        # ここで Slow Brain 呼び出し → Stance → simulator.step() 相当の処理
        # ただし Phase 2.5 は スケルトン段階、 実 LLM接続は後段
        try:
            data = request.get_json(silent=True) or {}
            # placeholder: 実際は ExchangeBase + PaperSimulator/RealSimulator 呼び出し
            return jsonify({
                "status": "received",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "echo": data,
                "note": "Phase 2.5 skeleton — wire actual Slow Brain here",
            })
        except Exception as e:
            logger.exception("predict failed")
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/emergency", methods=["POST"])
    def emergency():
        """緊急全閉 (Slack /halt コマンドから)"""
        # placeholder
        return jsonify({
            "status": "emergency_close_triggered",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return app


if __name__ == "__main__":
    # Cloud Run の PORT 環境変数を使う
    port = int(os.environ.get("PORT", "8080"))
    app = create_app()
    app.run(host="0.0.0.0", port=port)
