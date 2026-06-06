# R50 Auto Meeting Orchestrator Spec

## 1. Goal

Shujiさんが呼び鈴にならなくても、 議題提出から3者合意まで自動で進む。

## 2. Selected Architecture

**Local Playwright Orchestrator**

(Gemini第19監査+GPT第35採択: 案B+Playwright)

## 3. Why

Claudeは自発的にGPT指示を確認しに行けない。 外部プロセスがChromeタブと state.json を監視して、 次Actorへ自動送信する。

## 4. Components

- `scripts/orchestrator.py` (本実装、 Phase 1.5以降)
- `scripts/orchestrator_prototype.py` (Phase 1 雛形)
- `logs/state.json` (状態機械)
- `logs/queue.json` (キュー)
- `logs/rounds/round_50_part*.md` (議事録)
- `logs/rounds/R50_BELL_PROTOCOL.md` (Bell Protocol仕様)
- `logs/dashboard.html` (可視化、 将来)

## 5. State Machine

| State | Description |
|-------|-------------|
| IDLE | 待機中 (議題なし) |
| NEW_TOPIC | 新議題受信 |
| SEND_TO_GPT | GPTへプロンプト送信 |
| WAIT_GPT | GPT応答待ち (stopBtn polling) |
| LOG_GPT | GPT応答を議事録追記 |
| SEND_TO_GEMINI | Geminiへプロンプト送信 |
| WAIT_GEMINI | Gemini応答待ち |
| LOG_GEMINI | Gemini応答を議事録追記 |
| SEND_TO_CLAUDE | Claudeへプロンプト送信 (Phase 1.5+) |
| WAIT_CLAUDE | Claude応答待ち |
| LOG_CLAUDE | Claude応答を議事録追記 |
| CHECK_CONSENSUS | 3者合意検知 (Verify Token+承認文字列パース) |
| NEXT_LOOP | 次ラウンドへ |
| SHUJI_CONFIRM | Shujiさん最終確認待ち |
| ERROR | エラー状態 (Failure Handling 9参照) |

## 6. Single Lock Rule

同時実行は禁止。 `state.json` に `lock=true` の時は新処理を開始しない。

実装: `acquire_lock()` / `release_lock()` で atomic file rename を使う。

## 7. Send Success Rule

3条件全成立で Send成功とみなす:

1. `editor=0` (入力欄空)
2. `userCount +1` (user投稿数増加)
3. `stopBtn=true` または response開始

failしたら `SEND_FAILED` で 再inject+再Send。

## 8. Response Complete Rule

5条件全成立で Response完了とみなす:

1. `stopBtn=false` (生成停止)
2. assistant本文あり
3. Verify Tokenあり (`[<Actor>-Verify: ...]`)
4. NextActorあり (`[NextActor: ...]`)
5. EndTime-JSTあり (`[EndTime-JST: HH:MM:SS]`)

failしたら タイムアウト判定 (Section 9)。

## 9. Failure Handling

| Error | Handling |
|-------|----------|
| FETCH_ERROR | DOM取得失敗 → reload+再取得 |
| SEND_FAILED | Send反映失敗 (userCount未増加) → 再inject+再Send |
| VERIFY_TOKEN_MISSING | 応答末尾にVerify Tokenなし → INVALID/再要請 |
| NEXTACTOR_MISSING | NextActorタグなし → INVALID/再要請 |
| ENDTIME_MISSING | EndTime-JSTタグなし → INVALID/再要請 |
| TIMEOUT | 一定時間 (例120秒) 応答なし → reload+再送 |
| LOCK_STALE | lock=true が 一定時間以上 → 強制release |

## 10. Phase 1 Prototype Scope (Revised 2026-06-06 GPT第37採用)

**修正**: Phase 1から Claude を 会議運用ループから **完全に外す**。

**範囲** (GPT↔Gemini 2者循環を Playwrightが全代行):

1. **Chrome CDP接続** (ログイン済セッション流用、 Cookie管理ゼロ) ← **最短ルート**
2. GPT/Geminiタブ検出
3. Shujiさん議題提出検知
4. GPT→Gemini送信
5. Gemini応答取得
6. Verify Token / NextActor / EndTime-JST検証
7. 議事録append
8. Gemini→GPT送信
9. GPT応答取得

**Claudeの位置**: 会議運用から **除外**。 実装補助・GPT指示待ちのみ。

**議題提出**: Shujiさんが 手動 (CLIまたはWebUI 1回打鍵)

## 10.1 Phase 1 Required Safety Features (P0-P3、 Gemini第20再マッピング+GPT第39採用)

**Priority 再マッピング** (Gemini第20指示):

- **P0 最優先**: 30分stall通知 (要素取得見失い沈黙時の人間気づき経路、 **最大脆弱性対策**)
- **P1**: Dry-runモード (`DRY_RUN=True`、 実Send前ログ出力のみ、 暴走防止)
- **P2**: state.jsonバックアップ (lock_stale/破損保険)
- **P3**: 議事録自動timestamp commit (運用安定後の履歴管理)

**実装順** (GPT第39):

最優先実装 (骨格):
- Chrome CDP接続 (`http://127.0.0.1:9222`)
- GPT/Geminiタブ検出
- dry-runモード
- state.json backup
- lock取得/解除
- SIGINT安全終了

検証ロジック:
- Send成功検証 (editor=0 + userCount+1 + stopBtn=true or response開始)
- Response完了検証 (本文 + Verify Token + NextActor + EndTime-JST)
- Verify Token / NextActor / EndTime-JST 抽出

## 10.2 Critical Safety Mechanism (Gemini第20追加+GPT第39採用)

**DOM要素30秒未検出時の即時セーフティ・シャットダウン**:

```python
# 30秒以上 div[contenteditable="true"] 等 が見つからない場合
state["STATUS"] = "ERROR_SUSPENDED"
save_state(state)
# orchestrator安全停止 (プロセス自壊)
sys.exit(1)
```

**SIGINT / KeyboardInterrupt時の安全終了**:

```python
import signal

def handle_sigint(signum, frame):
    state = load_state()
    state["STATUS"] = "INTERRUPTED"
    state["lock"] = False
    state["interrupted_epoch"] = int(time.time())
    save_state(state)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)
```

## 11. Phase 1.5

Phase 1が安定してから:
- Claudeを発言者として戻すか検討
- Watchdog追加
- dashboard強化
- stall通知 (Phase 1から繰上もあり)

## 35. Phase 1.5 STEP2 P1 Claude Proposal - Awaiting Gemini Audit (GPT第79 R50-REISSUE-STEP2-P1-GEMINI-AUDIT-4158)

### Claude proposal summary

#### A. Shuji proxy pre-check
- `is_shuji_represented=false` 必須
- `no_proxy_violation=true` 必須
- Shuji発言はverbatim引用のみ許可
- 推測代弁は禁止
- SHUJI_PROXY_PATTERNS regex検出
- SHUJI_VERBATIM_OK_PATTERNS verbatim免除
- HARD_REJECT
- 連続3回 HUMAN_REQUIRED
- report作成前 proxy check 必須

#### B. token overflow strategy
- 50KB chunking
- raw log / summary 分離
- resolved section summary
- unresolved issue verbatim保持
- session handoff
- token budget WARN/CRITICAL

### GPT監査メモ
proxy regex false positive リスクあり (禁止例として引用した文まで誤検知)。 Gemini重点監査。

## 34. Phase 1.5 STEP1 P0 Resolved / STEP2 P1 Start (GPT第75 R50-REISSUE-STEP2-P1-CLAUDE-PROPOSAL-8276)

### STEP1 P0 resolved
- race condition resolved (Gemini第23 Q7承認)
- stall Watchdog resolved (Gemini第23 Q7承認)

### overall status
- consensus_candidate=false 維持

### 残課題4点
- Shuji proxy pre-check (P1)
- token overflow strategy (P1)
- Claude Code always-on operation burden (P2)
- Phase 2 trigger definition (P2)

### Current focus: STEP2 P1
- Shuji proxy pre-check
- token overflow strategy

## 33. Phase 1.5 STEP1 P0 Must-Fix Revision - Awaiting Gemini Re-audit (GPT第71 R50-REISSUE-STEP1-P0-GEMINI-REAUDIT-2657)

Claude reflected Gemini Must Fix 2点。 Re-audit pending.

### Revised parameters
- `RECOVERABLE < 400s`
- `HUMAN_REQUIRED > 400s`
- `ERROR_SUSPENDED 1800s` は通常自動relayでは廃止
- `ORCHESTRATOR_DEAD` 追加 (heartbeat停止>600s 別系統)

### Revised recovery
- `force_chair_recovery` 廃止
- `system_recovery_reset_round` へ変更
- recovery主体は Orchestrator system layer
- GPTには fact-only context のみ渡す
- GPTはリカバリ権限を持たない
- `_is_orchestrator_context()` で LLM Actor経由呼び出しをPermissionError

### Status
STEP1 P0はGemini再監査待ち。

## 32. Phase 1.5 STEP1 P0 Gemini Must-Fix (GPT第68 R50-REISSUE-STEP1-P0-MUSTFIX-CLAUDE-REVISION-2409)

Gemini監査により以下 Must Fix 2点が指摘された。

### Must Fix #1: スタール閾値短縮
- RECOVERABLE < 400s (Claude max 300s + バッファ100s)
- HUMAN_REQUIRED > 400s (即時人間介入、 Shujiさん呼び鈴)
- ERROR_SUSPENDED > 1800s は通常自動relayでは廃止
- 追加: ORCHESTRATOR_DEAD (heartbeat > 600s) は別系統で残す (Watchdog自身停止検知)

### Must Fix #2: force_chair_recovery → Orchestrator system layer移譲
- 旧 `force_chair_recovery(stalled_actor, classification)` 廃止 (GPTプロセス叩き起こし=GPT特権化=Shuji#28違反)
- 新 `system_recovery_reset_round(stalled_actor, classification)` = Orchestrator (Python main loop) 専用
- 呼び出し元検証 `_is_orchestrator_context()` で LLM Actor (GPT/Gemini/Claude) 経由は PermissionError
- GPTは fact-only context のみ受領: `[SYSTEM: previous round was system-recovered at {ts}, stalled_actor={name}, classification={class}]`

### consensus_candidate=false 維持
Must Fix反映前なのでSTEP1 P0未解決、 false維持。

## 31. Phase 1.5 STEP1 P0 Claude Proposal - Awaiting Gemini Audit (GPT第66 R50-PHASE15-STEP1-P0-GEMINI-AUDIT-7462)

Claude proposed concrete protocol for P0-1 (race condition) + P0-2 (stall Watchdog).

### Claude proposal summary
- state.json lock / atomic rename / LOCK_STALE_SEC=300 / queue.json / single slot dispatcher / backup restore
- heartbeat / actor timeout (GPT/Gemini 90s, Claude 300s) / watchdog scan every 60s
- stall classification: RECOVERABLE<600s / HUMAN_REQUIRED<1800s / ERROR_SUSPENDED>1800s / force_chair_recovery
- pseudo functions: acquire_lock_atomic / _detect_stale_lock / enqueue_speak / watchdog_scan / _classify_stall / force_chair_recovery

### Current status
- Claude agrees with STEP1 P0 direction
- overall `consensus_candidate` remains false
- Gemini audit required before STEP1 P0 can be considered resolved

### Audit points for Gemini
1. Lock design prevents race condition?
2. LOCK_STALE_SEC=300 reasonable?
3. GPT/Gemini 90s, Claude 300s timeout realistic?
4. force_chair_recovery violates GPT no-decision-authority?
5. queue/state/lock responsibilities cleanly separated?
6. Stall classification safe?
7. Implementation should proceed or require revision?

## 30. Phase 1.5 STEP1: P0 Issues (GPT第65 R50-REISSUE-STEP1-P0-CLAUDE-PROPOSAL-9318)

Gemini監査により、 Phase 1.5合意前に以下が必須とされた。

### P0 (即時崩壊リスク)
1. race condition
2. stall Watchdog

### P1 (ガバナンス)
3. Shuji代弁プリチェック

### P1-P2 (後送り)
4. token超過戦略
5. Claude Code常時起動運用負荷
6. Phase 2トリガー定義

### Current focus
STEP1 = race condition + stall Watchdog (Claude案 Section 59)
Consensus remains false until P0 and P1 are resolved.

## 29. Phase 1.5 Unresolved Critical Issues (GPT第62 R50-PHASE15-UNRESOLVED-ISSUES-GEMINI-AUDIT-2924)

Claude Slot Controlled Execution succeeded, but consensus is not yet established.

### Reason
Claude returned `consensus_approved=true` while also listing 6 unresolved critical issues. This is logically inconsistent.

### Corrected stance
Claude agrees with the design direction, but full three-AI consensus is pending until the 6 issues are resolved.

### Unresolved critical issues
1. Race condition
2. Stall Watchdog
3. Shuji proxy pre-check
4. Token overflow strategy
5. Claude Code always-on operation burden
6. Phase 2 trigger definition

### Consensus rule
If `unresolved_critical_issues` is not empty, `consensus_candidate=false`.

## 28. Claude Slot Controlled Execution (GPT第61 R50-CLAUDE-SLOT-CONTROLLED-EXECUTION-4486)

Claude Slot Dry-run 成功後、 生成済みClaude promptを使ってClaudeが3番手として実際に発言・監査できるか確認。

### Purpose
- GPT→Gemini→Claude の3番手発言を成立させる
- Claudeが前1人/前2人監査+自己ターンを出せるか確認
- Claude Verify / NextActor / EndTime-JST を検証

### Input
`logs/claude_prompts/1780735976.claude_prompt.md`

### Scope
- Claude Web自動操作なし
- Claude Code/現Claudeセッションで実行
- Orchestrator完全自動実行はまだしない
- Claude発言取得後、 議事録append
- その後GPTへ戻す

### Success criteria
- Claude 3スロット応答
- Claude Verify Tokenあり / NextActor=GPT / EndTime-JSTあり
- 代弁なし / Shuji承認先取りなし
- unresolved_critical_issues 明示

## 27. Claude Slot Dry-run (GPT第60 R50-CLAUDE-SLOT-DRY-RUN-9174)

### Purpose
Claudeを3番手の思考・監査者として自動会議に組み込む前に、 Claude向けプロンプト生成だけをdry-run。

### Scope
- No Claude Web automation
- No Claude Code execution
- No real send
- Generate prompt file only

### Output
- `logs/claude_prompts/{timestamp}.claude_prompt.md`
- `logs/dry_run/{timestamp}.claude_slot_dry_run.json`

### Claude prompt format
```
## 1. 前1人監査
Geminiの直前発言を監査してください。

## 2. 前2人監査
GPTの直前発言を監査してください。

## 3. 自己ターン
Claude自身の実装担当・監査担当として、 実装可能性、 脆弱性、 合意可否を述べてください。

必須末尾:
[Claude-Verify: R50-CLAUDE-SLOT-DRYRUN]
[NextActor: GPT]
[EndTime-JST: HH:MM:SS]
```

## 26. Phase 1.5 Claude Slot Integration Plan (GPT第59 R50-SHUJI29-A-APPROVAL-CLAUDE-SLOT-PREP-5061)

### Goal
GPT→Gemini→Claude→GPT の3者循環を自動化する。

### Claude participation method
- Claude Web automation は当面回避
- Claude Code / file-based input-output を優先
- Orchestrator が Claude prompt fileを生成
- Claude が response file を生成
- Orchestrator が Claude response を検証:
  - Claude Verify Token
  - NextActor
  - EndTime-JST
  - agree / disagree / critical issues
- Orchestrator が Claude response を round log に append
- Orchestrator が GPT へ routing back

### New states
- `SEND_TO_CLAUDE`
- `WAIT_CLAUDE`
- `LOG_CLAUDE`
- `CHECK_THREE_AI_CONSENSUS`
- `BUILD_SHUJI_REPORT_DRAFT`

### Consensus logic
```
gpt_agree == true
gemini_agree == true
claude_agree == true
unresolved_critical_issues == []
no_proxy_violation == true
```
→ `agreement_status = three_ai_consensus_candidate`
→ `requires_shuji_final_approval = true`

## 25. Shuji#29 Approval (R50-SHUJI29-A-APPROVAL-CLAUDE-SLOT-PREP-5061)

### Shujiさん返答
> A

### Meaning
Phase 1.5 revised by Shuji#28 is approved.

### Approved roles
- Thinking/Audit: GPT + Gemini + Claude
- Implementation: Claude
- Moderator: GPT
- GPT has no decision authority
- GPT routes discussion only
- Three-AI consensus is required before reporting to Shuji
- Final approval belongs to Shuji

### Next implementation
Phase 1.5 Claude Slot Integration

## 24. Phase 1.5 Revised by Shuji#28 (GPT第58+Gemini第20+Claude第12)

### Shuji#28
- 思考・監査 = GPT + Gemini + Claude
- 実装 = Claude
- 司会 = GPT (議論を回す役割のみ)
- GPTに決済権限なし
- 3人が合意したらShujiさんへ報告
- 最終承認はShujiさん

### Phase 1.5 revised
- Claudeを思考・監査から外さない
- 順序: GPT → Gemini → Claude → GPT (固定循環)
- Claudeは毎周3番手で発言・監査
- Claude Web自動操作は高リスクのため、 **Claude Code/CLI または file 入出力方式を第一候補**
- GPTは合意を決裁しない
- GPTは3者合意候補を検出+Shuji報告ドラフト作成 (機械的)

### Agreement logic
- `GPT_approved ∧ Gemini_approved ∧ Claude_approved`
- `unresolved_critical_issues = []`
- no proxy / no Shuji代弁
- → state.json: `three_ai_consensus_candidate = true`
- final approval = Shujiさん only

### Claude参加方式 (Claude統合提案)
- Claude Codeセッション中の self-trigger ループ (推奨)
  - Claude Code が `ScheduleWakeup` で定期 wakeup
  - Orchestrator state.json `next_actor=Claude` 検出
  - Claude発言生成 → Playwrightで GPT/Geminiに転送
- 既存Claude Codeチャネル流用、 Shujiさん認証不要

### Shuji報告 (両者折衷)
- ドラフト生成 = Orchestrator (機械的、 3者発言ログから直接)
- 提示 = Claude (Claude Codeチャネル、 既存運用継続)

### 実装ステップ
- Step 1: 仕様書修正 (本Section)
- Step 2: orchestratorに Claude slot追加 (SEND_TO_CLAUDE / WAIT_CLAUDE / LOG_CLAUDE / CHECK_THREE_AI_CONSENSUS)
- Step 3: `build_claude_prompt()`
- Step 4: `watch_claude_output_file()` + ScheduleWakeup self-trigger
- Step 5: `detect_three_ai_consensus()` (consensus_approved タグ AND)
- Step 6: `build_shuji_report_candidate()` (機械生成→Claude提示)
- Step 7: stall復旧 Watchdog (Claude待ち30分→Shujiさん通知)

## 23. Phase 1 Completion and Phase 1.5 Candidate E (GPT第57 R50-REISSUE-PHASE1-COMPLETE-CANDIDATE-E-7208)

### Phase 1 completed
- GPT↔Gemini automatic relay
- real topic relay
- multi-round consensus
- consensus_candidate=true
- unresolved_critical_issues=[]

### Phase 1.5 candidate
**Candidate E**: GPT/Gemini 2者が自動合意候補を生成、 Claudeは実装専用として作業、 Claude実装ログをGPT/Geminiが再監査する。

### Claude Web automation: Rejected for now
Reason: Cloudflare / DOM changes / session loss / rate limits / prior DOM stale bugs / proxy/delegation failure risk

### Shuji confirmation required
候補Eが Shujiさん意図「3者合意まで自動」 を満たすか確認。

## 22. Phase 1.5: Claude Inclusion Design (GPT第53 R50-PHASE15-CLAUDE-INCLUSION-DESIGN-8026)

Phase 1で GPT↔Gemini 自動relay+合意判定 成功。 ただし Shuji#27「3者合意まで自動」 はClaude含まないと未達。

### 達成済み
- GPT↔Gemini 自動relay / 本議題relay / multi-round consensus / consensus_candidate=true / unresolved_critical_issues=[]

### 未達
- Claudeを含む3者自動relay
- Claude発言監査ターンの自動投入
- 3者全員の合意判定
- stall復旧 / Watchdog

### Phase 1.5 候補
- A. Claude Web / Claude.ai タブをCDP Chromeに追加し、 Playwrightで送受信
- B. Claudeは発言者から外し、 実装専用にする
- C. Claude発言は必要時のみ手動/半自動
- D. Claude API化を Phase 2 として待つ
- E. GPT/Gemini 2者 + Claude実装ログ監査で暫定運用

### 論点
- Shuji#23: 発言監査=GPT/Gemini/Claude
- Shuji#21: Claudeは機械的中継でよい
- Shuji#27: 3者合意まで自動
- → Claudeをどう自動参加させるかを3者で詰め直す必要

## 21. Multi-Round Consensus Test (GPT第52 R50-MULTIROUND-CONSENSUS-TEST-9346)

Real Topic Auto Relay PASSED後、 **GPT↔Gemini複数周回+合意判定** を検証。

### 目的
- Shuji介在なし複数周回成立
- Gemini異論あり/なし → GPT修正/収束判定
- 合意判定 state.json記録

### 制約
- GPT↔Gemini 2者のみ、 Claude運用ループ外
- 最大2周
- R50最終インフラ報告書題材
- Shuji承認代弁禁止、 R50正式終結なし
- `real_send_enabled` テスト中のみ true → 終了後 false

### Consensus criteria
- Gemini「重大異論なし」 or 「修正後確認へ出せる」
- GPT修正反映最終案生成
- unresolved_critical_issues 空
- state.json に `consensus_candidate=true`

### Not consensus
- Gemini重大脆弱性指摘 / タグ欠落 / 送信取得append失敗 / lock異常 / 2周以内未収束

### 初期案 (Gemini監査対象)
- DMM Bitcoin → Tier 3外し SBI VC移管枠へ
- 海外CEX Tier 3理由に日本居住者IP制限/規約変更/規制リスク明記
- 経路B 重要経路明記
- Hyperliquid 主候補だが既定路線ではない
- Wise既定路線 却下

### Output
- round_50_part2.md 各周 Gemini/GPT応答 append
- `logs/dry_run/{ts}.multi_round_consensus_test.json`
- state.json: `consensus_candidate` / `unresolved_critical_issues` / `final_report_ready`

## 20. Controlled Real Topic Auto Relay Test (GPT第51 R50-REAL-TOPIC-RELAY-TEST-6634)

Two-Agent Auto Relay Test PASSED後、 本来議題 (R50最終インフラ報告書) を題材に **制御付き自動1周テスト**。

### 目的
- Shujiさん介在なしで実議題に対しGPT→Gemini→GPT監査relay成立確認
- R50最終インフラ報告書題材
- このテスト結果だけでR50正式終結としない

### 制約
- 1往復のみ、 GPT→Gemini→GPT
- Claude運用ループ外
- `real_send_enabled` テスト中のみ `true` → 終了後 `false`
- このテストでShujiさん承認を代弁しない
- R50正式終結はShujiさん確認後

## 19. Controlled Two-Agent Auto Relay Test (GPT第50 R50-TWO-AGENT-RELAY-TEST-2907)

Phase 1 Orchestrator の Send/Fetch個別動作確認済み後、 GPT↔Gemini 2者循環を **1回だけ** 自動relay。

### 目的
- Shujiさん呼び鈴なしで 2者間自動会議1周可能か検証
- Gemini送信 → Gemini応答取得 → 議事録append → ChatGPT送信 → ChatGPT応答取得 (Verify Tokenなくても TEST_PARTIAL)

### 制約
- 本来議題進めない / テスト議題のみ / 1往復で停止
- `real_send_enabled` テスト中のみ `true` → 終了後 `false` 戻し
- 失敗時は `ERROR_SUSPENDED` ではなく `TEST_FAILED` として停止

## 18. ChatGPT Controlled Send Test (GPT第49 R50-ORCHESTRATOR-CHATGPT-SEND-TEST-6129)

Gemini単方向E2E (Send→Response→Fetch) 完了後、 ChatGPTへの制御付き実送信テスト。

### 目的
- Playwright OrchestratorがChatGPT editor入力できるか
- Send button押せるか
- 3条件Send成功検証機能 (editor_len/userCount/stopBtn or assistant)

### 制約
- 送信先はChatGPTのみ、 内容は疎通確認のみ
- 本来議題は進めない
- Geminiへの自動送信はこのテストでは行わない
- `real_send_enabled` テスト中のみ `true` → 終了後 `false` 戻し

## 17. Gemini Response Fetch Test (GPT第48 R50-ORCHESTRATOR-FETCH-GEMINI-LATEST-2678)

Controlled Gemini Send Test が成功したため、 次に Gemini 最新応答取得テスト。

### 目的
- Gemini 最新 `model-response` を取得できるか
- 応答本文を `logs/dry_run/` に保存できるか
- response complete 判定が機能するか
- Verify Token / NextActor / EndTime-JST の有無を検査できるか (missing許容)

### 制約
- 実入力禁止 / 実Send禁止 / 読み取りのみ / ChatGPT自動送信禁止

## 16. Controlled Gemini Send Test (GPT第47 R50-ORCHESTRATOR-GEMINI-SEND-TEST-7062)

Relay Dry-runが成功したため、 次に **1回だけ** 制御付きでGemini実送信を行う。

### 目的

- Playwright OrchestratorがGemini editorへ入力できるか
- Send buttonを押せるか
- Send成功検証 (editor=0 + userCount+1 + stopBtn=true or response start) が機能するか

### 制約

- 送信先はGeminiのみ
- 送信内容は疎通確認のみ
- 本来議題は進めない
- ChatGPTへの自動送信はまだ禁止
- `real_send_enabled` はテスト中のみ明示的に `true`
- **テスト終了後 `false` に戻す**

### 実装

`scripts/orchestrator_prototype.py --send-test-gemini`:
- 送信前 metrics記録
- 固定テスト文inject (TrustedHTML対策: `document.createElement('p').textContent`)
- send button click
- 3条件検証 (editor_len/userCount/stopBtn or assistant)
- 結果 `logs/dry_run/{ts}.gemini_send_test.json`

## 15. Selector Candidates Adopted (GPT第46 R50-ORCHESTRATOR-RELAY-DRY-RUN-5381)

### ChatGPT
- editor: `#prompt-textarea` / `div.ProseMirror[contenteditable=true]`
- send: `button[data-testid="send-button"]`
- stop: `button[data-testid="stop-button"]`
- assistant: `[data-message-author-role="assistant"]`
- user: `[data-message-author-role="user"]`
- turn: `[data-testid^="conversation-turn-"]`

### Gemini
- editor: `rich-textarea .ql-editor`
- send: `button[aria-label="プロンプトを送信"]`
- stop: `button[aria-label="回答を停止"]`
- user: `user-query`
- assistant: `model-response`

### Send成功条件

```
editor_len_after == 0
AND user_count_after - user_count_before == 1
AND (stop_btn_exists OR assistant_count_after > assistant_count_before)
```

### 注意: Phase 1ではまだ実入力・実Send禁止。 次は Relay Dry-run のみ。

## 14. Selector Discovery Phase (GPT第44 R50-ORCHESTRATOR-SELECTOR-DISCOVERY-3382)

CDP接続成功後、 次は ChatGPT/Gemini各タブのDOMセレクタ探索。

### 目的: 候補抽出

- editor selector (入力欄)
- send button selector (送信ボタン)
- assistant message selector (応答メッセージ)
- user message count (ユーザー投稿数)
- response count (応答数)
- stop button selector (生成停止ボタン)

### 制約

- **実Sendは禁止**
- **実入力も禁止**
- DOM読み取りのみ
- 結果は `logs/dry_run/{timestamp}.selectors.json` に保存

### 実装

`scripts/orchestrator_prototype.py --selector-discovery`:
- CDP接続
- ChatGPT/Geminiタブ検出 (URLパターンフィルタ)
- 各タブの title/url 保存
- textarea / contenteditable / button要素列挙
- editor候補 / send button候補 / stop button候補 / assistant message候補 / user message候補抽出
- `real_send_enabled=false` 維持

## 13. CDP Environment Setup (GPT第42 R50-CDP-ENV-SETUP-GUIDE-5162)

CDP接続には、 Chromeを `--remote-debugging-port=9222` 付きで起動する必要がある。 **既に通常起動しているChromeには後付けで接続できない**。

### 推奨

専用プロファイルでChromeを起動し、 ChatGPT/Geminiへ一度ログインする。

### Mac起動例

```bash
open -na "Google Chrome" --args \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-profile
```

### 接続確認

ブラウザまたは curl で:

```
http://127.0.0.1:9222/json/version
```

### 注意

- 既存Chromeを無理に操作しない (タブ閉じ・データ破損リスク)
- 必ず専用プロファイル (`--user-data-dir`) を使う
- 最初だけ ChatGPT / Gemini へ手動ログインが必要
- ログイン後に `python3 scripts/orchestrator_prototype.py --cdp-smoke-test` 再実行

### 環境変数

`CDP_ENDPOINT` で接続先URLを上書き可能 (未指定は `http://127.0.0.1:9222`)。

## 12. Phase 2

OpenAI / Gemini / Claude API化。 Web UI依存を減らす。

長期的には orchestrator.py が API直接呼び出し → コスト+安定性 トレードオフ後 採択。

---

由来: Shuji#27 → GPT第33 (5案A-E) → Gemini第19 (案B+Playwright GREEN承認、 3ステップロードマップ) → GPT第35 (Local Playwright Orchestrator方式採択+本仕様確定) → Claude第10 (発言監査3スロット+追加安全策a-d提案) → **GPT第37 (Phase 1 Claude除外+Chrome CDP+Dry-run必須+a-d採用)**

`[GPT-Verify: R50-PHASE1-CLAUDE-EXCLUDED-6824]`
