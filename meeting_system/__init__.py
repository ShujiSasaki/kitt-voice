"""
meeting_system — R50 3者会議運営パッケージ (Phase 1)
3者合意 (loop2 完了) 仕様の実装:
- queue_io: File Lock + Atomic Move + UTF-8/LF固定 の Markdown キュー
- state_schema: schema_v2 (room_id分離 + 巡数管理 + 合意成立フラグ)
- validator: 7検証 + 追加インスピレーション + X風スレッド検出
- validator_consensus: 最低2巡ルール + 合意成立機械判定
- port_manager: CDPポート 9222-9253 連番マップ + Chrome→Edge fallback
- chrome_relay: Playwright connect_over_cdp + 3タブ動的探索 + Rate Limit対策
- global_relay_serializer: asyncio.PriorityQueue + Lock シングルスレッド順次リレー
- rooms_overview: 集約サマリー生成 (single source of truth = 各room state.json)
- server: FastAPI + SSE + Shuji入力 + X風スレッド
- notification_controller: Mac osascript + Slack/Discord Webhook (LINE Notify 不採用)
- sigint_handler: Shuji割込 二重防御 (state書換 + SIGINT)
- local_board: Tailwind CSS CDN + LINE風吹き出し + X風スレッド + 2カラム
"""

__version__ = "1.0.0"
__schema_version__ = 2
