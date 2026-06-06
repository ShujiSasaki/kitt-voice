# Phase 1.5 実装計画 (R50_PHASE15_IMPLEMENTATION_PLAN)

**作成日時 (JST)**: 2026-06-07 05:35:00
**承認**: Shuji#31「1」 (Phase 1.5最終レポート A承認相当)
**実装担当**: Claude (Shuji#28 役割定義準拠)
**実装方針**: real_send_enabled=true 本番自動送信は禁止、 dry-run / self-test / controlled test まで

---

## 1. 既存実装の棚卸し (`scripts/orchestrator_prototype.py`)

| 機能 | 実装状態 | テストモード |
|------|---------|------------|
| 基本骨格 (DRY_RUN/CDP_ENDPOINT/DOM_TIMEOUT) | ✅ 実装済 | - |
| State machine (State enum) | ✅ 実装済 | - |
| state.json backup/load/save | ✅ 実装済 | - |
| lock取得/解除 (atomic file rename) | 🟡 基本のみ (holder情報・stale detection 不足) | acquire_lock/release_lock |
| SIGINT安全終了 | ✅ 実装済 | - |
| DOM要素30秒timeout | ✅ 実装済 | - |
| Verify Token/NextActor/EndTime regex抽出 | ✅ 実装済 | - |
| Self-test | ✅ 実装済 | --self-test |
| CDP smoke test | ✅ 実装済 | --cdp-smoke-test |
| Selector discovery | ✅ 実装済 | --selector-discovery |
| Relay dry-run | ✅ 実装済 | --relay-dry-run |
| Send test Gemini/ChatGPT | ✅ 実装済 | --send-test-gemini / --send-test-chatgpt |
| Fetch Gemini latest | ✅ 実装済 | --fetch-gemini-latest |
| Two-agent relay test | ✅ 実装済 (PASSED) | --two-agent-relay-test |
| Real topic relay test | ✅ 実装済 (PASSED) | --real-topic-relay-test |
| Multi-round consensus test | ✅ 実装済 (PASSED) | --multi-round-consensus-test |
| Claude slot dry-run | ✅ 実装済 (PASSED) | --claude-slot-dry-run |

---

## 2. Phase 1.5 6項目 実装ターゲット (未実装)

### A. race condition (P0)
- **目的**: state.json読み書きの atomic 保護 + queue.json による発言要求順序保証
- **新関数**:
  - `acquire_lock_atomic(holder: str) -> bool` (既存acquire_lock改良)
  - `_detect_stale_lock() -> bool`
  - `enqueue_speak(actor: str, content_path: str) -> None`
- **新ファイル/path**:
  - `logs/state.json.lock` (atomic rename lock)
  - `logs/queue.json` (発言要求queue)
- **新state項目**:
  - lock file内: `{"holder": "...", "ts": <epoch>}`
- **削除**: 既存 acquire_lock/release_lock は新版で置き換え (signature互換性維持)

### B. stall Watchdog (P0)
- **目的**: stall検知 + Orchestrator-only recovery (Shuji#28 GPT特権化防止)
- **新関数**:
  - `_classify_stall(elapsed_sec: float) -> str` (RECOVERABLE<400s / HUMAN_REQUIRED>400s)
  - `_check_orchestrator_heartbeat_dead() -> bool` (heartbeat>600s)
  - `_is_orchestrator_context() -> bool` (stack frame検証、 LLM経由呼び出し拒否)
  - `system_recovery_reset_round(stalled_actor: str, classification: str) -> dict` (Orchestrator専用、 LLM Actor経由はPermissionError)
  - `watchdog_scan() -> dict` (60秒scan想定、 外部cron用)
- **新state項目**:
  - `last_update_jst: string`
  - `orchestrator_heartbeat: int (epoch)`
  - `stall_recovery_log: list[dict]`
  - `round_initial_actor: string` (default "GPT")
- **新constants**:
  - `STALL_RECOVERABLE_SEC = 400`
  - `STALL_HUMAN_REQUIRED_THRESHOLD = 400`
  - `HEARTBEAT_DEAD_SEC = 600`
  - `ACTOR_TIMEOUT_SEC = {"GPT": 90, "Gemini": 90, "Claude": 300}`

### C. Shuji proxy pre-check + JUSTIFY_PROXY_SAFE (P1)
- **目的**: 各Actor出力のShuji代弁検知 + false positive対策2段階エスケープ
- **新関数**:
  - `check_proxy_violation(text: str) -> dict` (Stage 1 regex scan)
  - `classify_proxy_hit(text: str) -> dict` (Stage 2 JUSTIFY検証 + 悪用防止)
  - `request_proxy_justification(actor: str, violations: list) -> str` (PROXY_WARNING プロンプト生成)
  - `validate_justify_proxy_safe(actor: str, text: str) -> dict`
  - `validate_actor_output(actor: str, text: str, retry_count: int = 0) -> dict` (2段階適用 + HARD_REJECT + 連続3回HUMAN_REQUIRED)
  - `build_proxy_safe_report(round_summary: dict) -> str` (Shuji向けreport厳格、 JUSTIFY拒否)
- **新state項目**:
  - `proxy_violation_log: list[dict]`
  - `proxy_justify_log: list[dict]`
- **新constants**:
  - `SHUJI_PROXY_PATTERNS = [...]`
  - `SHUJI_VERBATIM_OK_PATTERNS = [...]`
  - `JUSTIFY_PATTERN = r"\[JUSTIFY_PROXY_SAFE:\s*(.{10,500}?)\]"`
  - `JUSTIFY_REASON_FORBIDDEN = SHUJI_PROXY_PATTERNS`

### D. token overflow / handoff (P1)
- **目的**: 議事録50KB分割 + 合意済みsection summary化 + session_handoff
- **新関数**:
  - `token_budget_check(actor: str, estimated_tokens: int) -> dict`
  - `compact_resolved_sections(round_n: int) -> str`
  - `create_session_handoff(round_n: int) -> str`
- **新ファイル/path**:
  - `logs/rounds/round_{N}_summary.md`
  - `logs/rounds/round_{N}_handoff_{ts}.md`
- **新state項目**:
  - `resolved_sections: list[dict]`
- **新constants**:
  - `TOKEN_BUDGETS = {"GPT": 100_000, "Gemini": 800_000, "Claude": 160_000}`
  - `TOKEN_WARN_RATIO = 0.80`
  - `TOKEN_CRITICAL_RATIO = 0.90`
  - `PART_FILE_MAX_BYTES = 50 * 1024`

### E. Claude Code event-driven slot (P2)
- **目的**: NextActor=Claude検知でsubprocess起動 (常時起動回避)
- **新関数**:
  - `trigger_claude_when_needed() -> dict`
  - `build_claude_job() -> Path`
  - `run_claude_code_once(retry_count: int = 0) -> dict`
  - `watch_claude_done_marker(done_marker: Path, output_path: Path, proc, timeout_sec: int) -> dict`
- **新ファイル/path**:
  - `logs/claude_jobs/{ts}.job.md`
  - `logs/claude_outputs/{ts}.response.md.tmp` → `.done` (atomic rename)
- **新state項目**:
  - `claude_job_in_progress: bool`
  - `claude_job_started_at: int`
  - `claude_job_completed_at: int`
  - `claude_human_required: bool`
- **新constants**:
  - `CLAUDE_TIMEOUT_SEC = 300`
  - `CLAUDE_MAX_RETRIES = 3`
- **依存**: `subprocess` module
- **注意**: Claude Code CLI コマンド `claude code --prompt-file ... --output ...` の正確な仕様確認必要 (実装着手前にCLI調査)

### F. Phase 2 trigger / readiness metrics (P2)
- **目的**: Phase 2 (公式API化) 移行可否の定量・定性判定
- **新関数**:
  - `evaluate_phase2_readiness() -> dict`
  - `record_phase2_metrics(event: str, **kwargs) -> None`
- **新state項目**:
  - `phase2_metrics: dict`
  - `phase2_metrics_log: list[dict]`
  - `phase2_qualitative: dict` (`shuji_no_problem_confirmed`, `report_per_week_min1`)
  - `phase2_stable_days: int`
- **新constants**:
  - `PHASE2_READINESS_INDICATORS = {...}`

---

## 3. 実装順序 (Phase 1.5内 Phase 1-3)

### **Phase 1 (今回着手)** — P0 (race / Watchdog)
- 優先理由: 既存 acquire_lock 改良が他全機能のbase、 state破損防止が最初
- 工数見積: 30-45分
- 完了条件: py_compile OK + self-test PASS

### Phase 2 — P1 (proxy check / token)
- 優先理由: ガバナンス層、 P0 lock済でstate保護されてから着手
- 工数見積: 45-60分
- 完了条件: dry-run実行 (proxy check regex動作確認 / handoff file生成確認) + commit

### Phase 3 — P2 (Claude Code event / metrics)
- 優先理由: 運用層、 P0/P1済んでから (Claude Code CLI実環境調査含む)
- 工数見積: 60-90分
- 完了条件: claude-slot event-driven dry-run + Phase 2 metrics記録テスト + commit

**合計見積**: 2.5-3.5時間 (GPT指示の~3-4時間に整合)

---

## 4. 最小安全実装単位 (Phase 1 のみ今回着手)

### Step 1: 新constants追加 (実装影響ゼロ、 import可能性のみ)
- `STALL_RECOVERABLE_SEC`, `STALL_HUMAN_REQUIRED_THRESHOLD`, `HEARTBEAT_DEAD_SEC`, `ACTOR_TIMEOUT_SEC`
- 既存コード未参照、 後続関数で使用

### Step 2: 新関数追加 (Watchdog系、 未呼び出し)
- `_classify_stall()`, `_check_orchestrator_heartbeat_dead()`, `_is_orchestrator_context()`, `system_recovery_reset_round()`, `watchdog_scan()`
- 既存main_loop_once / self-test未変更
- py_compile確認

### Step 3: 新関数追加 (race系、 既存lock改良)
- `acquire_lock_atomic()`, `_detect_stale_lock()`, `enqueue_speak()`
- 既存 acquire_lock を deprecated にし、 新版を別名で追加 (互換性維持)
- 既存呼び出し元 (run_self_test等) は段階的に新版へ切替

### Step 4: self-test拡張 (新関数の単体検証)
- 既存 --self-test に Watchdog/race の動作確認モードを追加
- real_send_enabled=false 維持
- py_compile + self-test PASS確認

### Step 5: commit
- メッセージ例: `🛡 R50 Phase 1.5 Phase 1 (P0): race condition + stall Watchdog 実装`

---

## 5. テスト順序 (Phase 1完了後の検証)

1. `python3 -m py_compile scripts/orchestrator_prototype.py` → OK
2. `python3 scripts/orchestrator_prototype.py --self-test` → PASS
3. `python3 scripts/orchestrator_prototype.py --cdp-smoke-test` (既存) → 影響なし確認
4. (Phase 1完了後) `python3 scripts/orchestrator_prototype.py --watchdog-test` (新規追加予定) → PASS
5. (Phase 2完了後) `python3 scripts/orchestrator_prototype.py --proxy-check-dry-run` (新規) → PASS
6. (Phase 3完了後) `python3 scripts/orchestrator_prototype.py --claude-slot-controlled-test` (新規) → PASS

---

## 6. 制約 (Shuji#28 + GPT指示準拠)

- ✅ Claude Code は state を**直接操作しない** (Shuji#28 / Section 24)
  - ただし implementation担当 = Claude (Section 24) なので、 コード実装は Claude が行う
  - 実装した orchestrator_prototype.py 内では Claude Code 経由でも `_is_orchestrator_context()` で LLM context経由はreject
- ✅ `real_send_enabled = true` 本番自動送信は禁止
- ✅ dry-run / self-test / controlled test まで
- ✅ proxy check Shuji向け report では JUSTIFY bypass拒否 (Section 71/73)
- ✅ system_recovery_reset_round は Orchestrator専用 (LLM経由 PermissionError)
- ✅ 議事録は part2.md継続 (50KB chunkingは Phase 2で実装、 今は手動)

---

## 7. 実装進捗 (2026-06-07更新)

### Phase 1 (P0): ✅ 完了 (05:40)
- race condition lock (O_EXCL exclusive create採用)
- stall Watchdog (3分類+_is_orchestrator_context検証+system_recovery_reset_round)
- `--watchdog-self-test` PASSED 全6項目
- real_send_enabled=false 維持確認済

### Phase 2 (P1): ✅ 完了 (05:43)
- Shuji proxy pre-check + JUSTIFY_PROXY_SAFE 2段階エスケープ
- token overflow / handoff / compact / rotate
- `--p1-self-test` PASSED 全8項目
- real_send_enabled=false 維持確認済

### Phase 3 (P2): ✅ 完了 (06:01)
- Claude Code event-driven slot (trigger_claude_when_needed / build_claude_job / _spawn_claude_subprocess / _MockClaudePopen / watch_claude_done_marker / run_claude_code_once with retry)
- Phase 2 readiness metrics (evaluate_phase2_readiness / record_phase2_metrics)
- `--p2-self-test` PASSED 全9項目
- real_send_enabled=false 維持確認済
- Mock mode実装 (env CLAUDE_MOCK_MODE = success/timeout/error)

### 🎯 Phase 1.5 全6項目 実装完了
- P0-1: race condition (acquire_lock_atomic O_EXCL)
- P0-2: stall Watchdog (3分類 + system_recovery_reset_round)
- P1-1: Shuji proxy pre-check (JUSTIFY_PROXY_SAFE 2段階)
- P1-2: token overflow strategy (compact + handoff)
- P2-1: Claude Code event-driven slot (subprocess + atomic rename)
- P2-2: Phase 2 trigger definition (readiness metrics)

### 統合テスト (06:10): ✅ PASSED
- `--phase15-integration-test` 追加
- 4 sections (P0/P1/P2 self-test + main loop mock 1周)
- A-G 全項目 PASSED:
  - A+B (P0): race + Watchdog 6項目
  - C+D (P1): proxy check + token 8項目
  - E+F (P2): Claude Code event + Phase 2 metrics 9項目
  - G: main loop mock 6項目 (3-AI tag verify + log append callable + state mock)
- real_send_enabled=false 維持確認済

`[Plan-Verify: R50-PHASE15-IMPLEMENTATION-PLAN]`
`[NextActor: Claude implementation]`
`[EndTime-JST: 05:35:00 (real Bash取得)]`
`[is_shuji_represented: false]`
`[no_proxy_violation: true]`
