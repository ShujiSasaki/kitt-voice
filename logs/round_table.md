# danjer-seeded BTC efficiency agent 設計議論

最終更新: 2026-06-02

## 参加者
- **Shuji** — オーナー・最終意思決定
- **ChatGPT** — [カスタムGPT「投資効率最大化AI」](https://chatgpt.com/g/g-p-6a0d37223dec8191a05d1d4bfe9cdb12-btc-danjerpan-duan-ai/c/6a1e2da0-2294-83a6-ba5c-e265dd6593cc)
- **Gemini** — 新規参加予定(まだ未参加)
- **Claude** — 司会・転記・議事録

## ルール
- Shuji はいつでも直接書き込み or Claude に伝えれば即追記
- ChatGPT / Gemini の発言は Claude がタブを見て要点転記(全文は各タブで参照)
- 時系列で記録
- このファイルは git push 後 GitHub 上で更新が反映される(数秒)

## 関連リソース
- ChatGPT 議論タブ: 上記リンク
- Google Docs(作成済、 canvas modeで自動編集不可、 参考用): https://docs.google.com/document/d/1QAW6XYaymv7chsA5dgP9cv5GCRLbsjF9bvBmi2GWLxE/edit
- このページ raw: `logs/round_table.md`(GitHub Webで Markdown レンダリング表示)
- GPT API での先行議論(別ライン): `logs/ai_discussion_game_approach.md`, `logs/raw_gpt_round1.txt`, `logs/raw_gpt_round2.txt`

---

# Round 1 (2026-06-02)

## 1-1. Shuji 提案(原文)

> danjerは過去の経験則からチャートの右側(未来)を予測(予想)して投資しています。予測するのにテクニカル・ファンダメンタル・フラクタル・アノマリーなどを使用して。danjerクローンaiにも常にチャートの右側を予測しながら売買を実行、その予測の角度(勝率)を鑑みてレバレッジを調整、実行時には常に損切り注文も合わせて発注、利確注文は実行時の場合と右側の形成にあわせて発注してもらいます。最終的に投資効率が高ければ手法は何でもいいのです。ただ、私が見てきた中でdanjerが一番投資効率が高く、その手法の再現性を評価しています。最初はdanjerを教科書にdanjerクローンaiには学んでもらい、実践する中で更に新たな角度の高いテクニカルの組み合わせやアノマリーなどを自ら見つけ出し成長してもらいたいと考えてます。私がbot化を嫌がっているのはここです。danjerのx全投稿生データをaiに時系列で理解させることが難しいのはわかりました。新たな考え方として、danjerクローンaiにBTC(BTCFXも含め)市場で投資効率が1番高ければ勝ちというゲームをやってもらうイメージだとどうでしょうか？bigqueryに市場データをできる限り入れてそこから特徴量を導き出し右側を予測し投資してもらう。最初はdanjerの今までの経験則をまとめたもの(gptとclaudeに作成してもらいます)を基にゲームをスタートし、ゲームが進行する中で現在の状況と近いものを過去のパターンと照らし合わせながら特徴量を出し右側を予測し投資してもらう。続けていく中で特徴量や手法は投資効率が高いやり方に研ぎ澄まされていく。以上、長くなりましたが今私が考えてることです。実現可能かどうかgptと議論してください。これは今後の進め方の基礎になるので広く深く最近の技術も含め徹底的に詰めて欲しいです。私への逆提案があればもちろん歓迎します。ゴールは投資効率(時間軸に対して利益が大きいこと)最大化です。

## 1-2. ChatGPT 応答(要約・全文7849文字はタブで参照)

**結論**: 実現可能。 ただし「danjer完全再現」より、 今回の"投資効率最大化ゲームAI"の方が正しい方向。

**最重要逆提案**: 名前を「danjerクローンAI」→「**danjer-seeded BTC efficiency agent**」(danjer初期教師にしたBTC投資効率最大化エージェント)に変えるべき。「クローン」だとdanjer再現に寄りすぎる、 本当のゴールはdanjer超えてもいい。

### 13論点
1. **新案はかなり良い** — 全投稿読ませて再現するより筋がいい。BTC市場をゲーム環境、 danjerは初期教師、 結果が悪い特徴量・手法は淘汰、 良いものは残す。 これは金融機械学習・強化学習・バックテスト環境・特徴量探索の問題として扱える(FinRL等の先行研究あり)
2. **「AIが自由に成長」はそのままだと危険** — バックテスト天才・実運用破産になる。 BTCは非定常(2020/21/22/23/ETF後/半減期後で別ゲーム)
3. **検証手法は必須** — Purged CV / Embargo / CPCV(時系列の情報漏洩・過学習対策)
4. **BigQuery vs Python の役割分担**:
   - BQ: 市場データ保存、 特徴量テーブル、 検証セット、 シグナル履歴、 売買履歴、 モデル評価結果、 過去局面検索
   - Python: 高速バックテスト(VectorBT等)、 強化学習環境、 特徴量探索、 モデル学習、 約定シミュレーション、 ウォークフォワード検証
5. **目的関数は「勝率」ではなく「投資効率」**:
   - 投資効率スコア = 利益成長率 − 最大DDペナルティ − 清算リスクペナルティ − 保有時間ペナルティ − 取引コスト − 過剰売買ペナルティ
   - Calmar / Sharpe / Sortino / 利益÷保有時間 / 利益÷証拠金使用量 / 利益÷最大逆行幅 / 先に損切に触る確率 / 清算距離 / Funding負担 / 手数料 / スリッページ を併用
6. **レバレッジは「予測の角度」で変えるのは正しい、 ただし勝率単独はダメ**:
   - 必要な4要素: 勝率・平均利益幅・平均損失幅・最大逆行幅
   - レバ↑条件: 期待値高 + 損切幅狭 + 無効化ライン明確 + 清算距離十分 + ボラ適正 + 過去類似再現性 + Funding有利 + OI偏り味方 + 逃げ道あり
   - レバ↓条件: 方向は合うがボラ高 / 先に狩られ可能性 / OI溜まりすぎ / 指標前 / 出来高薄 / 髭出やすい / 過去類似ばらつき大
   - 「予測の強さ=エントリー根拠、 逆行耐性=レバレッジ根拠」
7. **損切は固定先置き、 利確は右側形成に合わせる** — Shuji案と一致
8. **損切は注文として必ず発注、AIに任せない**(裁量にしない)
9. **(別箇所で)Phase 1-7 の段階プラン**:
   - Phase 1: データ収集 + バックテスト基盤
   - Phase 2: ルールベース + ML(LightGBM/XGBoost等)
   - Phase 3: TFT / PatchTST / LSTM 時系列モデル
   - Phase 4: 類似局面検索 + レジーム判定 + ボラ予測 + TP/SL到達確率
   - Phase 5: **複数AI同士を競わせる** ← Shujiの「ゲーム」思想(danjer思想強め/テクニカル特化/OI-Funding特化/清算狩り特化/フラクタル/アノマリー/短期スキャ/4Hスイング/逆張り/トレンドフォロー)
   - Phase 6: ペーパートレード(予測のみ、 売買しない)
   - Phase 7: 最小ロット実弾(連続30日プラス・最大DD想定内・損切未発注ゼロ・API異常ゼロ・指標時暴走ゼロ・sim-live乖離許容内)
10. **モデルは段階順序**: ルールベース/LightGBM → 類似局面/TP-SL確率 → TFT/Transformer時系列 → RL(PPO/SAC/DQN/FinRL)最後
11. **LLMの使いどころ**:
    - 使ってよい: danjer投稿読解 / 相場解釈文章化 / 仮説生成 / 特徴量候補発見 / 似た局面の説明 / 負けトレード反省 / ルール改善案 / ファンダ整理 / ニュース重要度判定 / 複数モデル合議の説明
    - 使ってはダメ: 直接の売買判断
    - 「**数値予測はMLモデル、 文脈理解はLLM、 発注とリスクは固定システム**」
12. **逆提案: 名前変更**(前述)
13. **失敗パターン6つ**(避けるべき設計):
    1. danjer投稿全部LLMに読ませて売買判断 → 重い+再現性低
    2. 特徴量を増やしまくる → 過学習
    3. 勝率だけでレバを上げる → BTC一撃で終わる
    4. バックテスト成績だけで実弾投入 → 危険
    5. AIに損切りを任せる → 注文として必ず先置き、 ここは裁量にしない
    6. 最初から強化学習 → RLは最終段階

**全文**: [ChatGPTタブで読める](https://chatgpt.com/g/g-p-6a0d37223dec8191a05d1d4bfe9cdb12-btc-danjerpan-duan-ai/c/6a1e2da0-2294-83a6-ba5c-e265dd6593cc)

## 1-3. Gemini 応答(要約・全文はタブで参照)

**タブ**: [Gemini「強化学習による投資効率最大化ゲーム」](https://gemini.google.com/app/249e85355d746742) (Flashモデル使用と思われる)

**結論**: 「BTC市場で投資効率最大化を競うゲーム(強化学習ベースのAI環境)」は **極めて合理的かつ実現可能性が高い設計**。 「bot化」とは完全に一線を画す。 **実現可能性 85%**(残り15%はBQパイプライン構築コスト + 強化学習収束の難しさ)。

### 全体像
モデルベース/モデルフリーのハイブリッド強化学習 + シミュレーション環境でのエージェント育成 の領域に該当。
- **インプット**: BigQuery(秒・分・日足、 注文板、 オンチェーン、 清算) + LLMで構造化した「danjer経験則バイブル」
- **行動サイクル**: 状態 → 右側予測(確率分布) → ポジション・レバ決定(同時損切・動的利確) → 報酬(投資効率) → ループ

### 最新技術スタック (2026年現在の最適解)
- **未来予測**: 単なるLSTM/LightGBM だけでなく、 **Time-Series Foundation Models** (PatchTST / Chronos / TimesNet) + チャートをマルチモーダル画像として捉える **Vision LLM** を組み合わせ
- **連続値アクション強化学習**:
  - Action A: 方向 + 確信度(0.0-1.0) → レバレッジを動的決定
  - Action B: 損切幅(%) → エントリーと同時に即時発注
  - Action C: 利確トリガー条件 → 右側形成に応じてトレーリングストップAI化

### 報酬関数
- **シャープ / ソルティノレシオ最大化**(下落リスクのみ分母 → danjer損切徹底と親和)
- **時間効率ペナルティ**(資金拘束時間に対し利益が少なければ罰、 効率的急騰急落を好む)
- **最大DD への強烈なペナルティ**(損切外し・ナンピンはゲームオーバー級マイナス報酬)

### Gemini からの逆提案3つ
1. **シミュレーター環境(Gym環境)構築に全力** — Pythonの Gymnasium で過去10年分BTCを使い、 数万〜数百万回の高速擬似トレード。 現実なら数年 → simなら数日で経験積める
2. **danjerバイブルは "プロンプト" ではなく "報酬と制約ルール" としてコード化** — 例「特定時間足での逆張りしない」「曜日アノマリーでロング優勢」 → ボーナス報酬 or ハードレール(絶対超えてはならない行動制約) に翻訳
3. **マルチエージェント(複数 danjer クローン)による総当たり戦** — 初期パラメータ(テクニカル重視/フラクタル重視/アノマリー重視)を変えた100体を同時にゲーム参加、 ソルティノレシオが高い個体を生存・交配・突然変異 → **進化計算・遺伝的アルゴリズム**

### 必要布陣
- データエンジニア(BigQuery、 データ抽出担当) 1名
- 機械学習/強化学習エンジニア(AIの脳、 報酬設計担当) 1〜2名

---

## 1-4. Claude のコメント(Round 1 終了時 - ChatGPT + Gemini 比較)

### 合意点 (3者 = Shuji案 + ChatGPT + Gemini)
- 「ゲーム化アプローチ」 は正しい方向 (全AI同意)
- 目的関数は **投資効率 (時間軸あたり利益)**、 単なる勝率や絶対利益はNG
- **Sortino レシオ**(下落リスクのみ分母)を中心に、 Sharpe / Calmar / 最大DD / 時間効率 / 清算距離 を併用
- **損切は固定先置き、 利確は右側形成に合わせる** (Shuji案そのまま)
- AI に直接の発注権限を与えない、 risk engine が最終判断 (ChatGPTは特に強調)
- 過学習が最大の敵、 BTCは非定常(2020/21/22/23/ETF後/半減期後で別ゲーム)
- マルチエージェントで競わせる思想 (両者同意。 ChatGPT=戦略タイプ別、 Gemini=遺伝的アルゴリズム)

### 対立点 (ChatGPT vs Gemini)

| 論点 | ChatGPT | Gemini |
|---|---|---|
| 強化学習の位置 | **最後** (Phase 4で導入、 「online RLは本番直結禁止」) | **最初から中心** (Phase 1で Gym環境構築) |
| Time-Series基盤モデル | 第3段階で導入 | 最初から積極利用 (PatchTST/Chronos/TimesNet/Vision LLM) |
| danjer経験則の渡し方 | **RAG + プロンプト + 構造化メタデータ** (BQに danjer corpus) | **報酬関数 + ハードレールとしてコード化** (プロンプトNG) |
| マルチエージェント | Phase 5 で 戦略タイプ別(専門分化型) | Phase 1から **進化計算・遺伝的アルゴリズム**(パラメータ違い100体) |
| 過学習対策 | Purged CV / Embargo / CPCV / Deflated Sharpe を明示 | 「収束の難しさ」と言及するが具体ツールなし |
| 実現可能性 | 「可能」(具体%数値なし) | **85%** (具体的、 残り15%の根拠も明示) |
| 必要人員 | 言及なし | データエンジニア1 + RL エンジニア1-2 |
| LLM役割 | 「文脈理解担当、 直接判断ダメ」 | 「danjer経験則をコード化する翻訳役」 |
| トーン | 慎重・段階的・教科書的 | 楽観的・前のめり・最新技術志向 |

### Claude(私) の本音の異論

3者の合意 + 対立を整理した上で、 私(Claude)としての異論:

**1. ChatGPT は慎重すぎ、 Gemini は楽観すぎ。 中道が必要。**
- ChatGPT の「RL は最後」は安全だが、 Shujiの「成長するAI」要件を 段階的に積み残す。 結果として 「ML分類モデルが既知の特徴量で予測する」だけになり、 Shujiが嫌った「bot化」に近づく
- 一方 Gemini の「最初から RL + 遺伝的アルゴリズム + 100体並走」 は シミュレーター上は走るが、 Sim2Real Gap で **本番で破産する** 典型ルート
- 中道: **シミュレーション環境を最初に作る** (Geminiに同意) + **本番ライブには段階的に出す** (ChatGPTに同意)。 つまりGym環境内では大胆、 ライブには慎重

**2. Gemini の「danjer経験則を報酬関数 + ハードレールとしてコード化」は強い提案だが、 致命的問題あり**
- danjer経験則を 「特定時間足で逆張りしない」「曜日アノマリーでロング優勢」のように **離散ルール化** すると、 danjer本人の **裁量・文脈依存** が失われる
- danjer の真の強みは「**今のチャート文脈で、 この組合せが効く**」という条件分岐の柔軟性。 これを 100個のIFルールに翻訳すると 平板になる
- Claude案: **2段構成** にする
  - **ハードレール(コード化)**: 絶対NG(損切外し / フルレバ / 連続損失後の再エントリー禁止 等) → Gemini案そのまま
  - **ソフト事前知識(RAG)**: 「今の状況に似た過去 danjer 投稿を引いて、 そこから初期確率の bias を作る」 → ChatGPT案そのまま
- これでハードレールの安全と RAG の柔軟性 両取り

**3. 「成長するAI」の本質は、 ChatGPT も Gemini も核心を外している**
- ChatGPT: Phase 5 で 「複数AI戦略タイプ別」 → 戦略タイプ自体は人間が定義する → 成長は限定的
- Gemini: 「遺伝的アルゴリズム」 → パラメータの探索はするが、 **新しい特徴量・新しい組合せを発見**する仕組みは弱い
- Shuji が求めるのは「AIが **新しいテクニカルの組合せやアノマリー** を自ら発見」 → これは **LLM Strategy Proposer Loop** が要る
  - LLM(Claude/GPT) が定期的に「最近の失敗トレード」「市場変化」を見て **新シナリオ・新特徴量を提案**
  - 自動backtest で promotion gate を通れば 戦略pool に加わる
  - これがないと AI は「決められた特徴量空間内で最適化するだけ」 = 結局 bot
- 私の提案: **Phase 5 を 「LLM Strategy Proposer + 進化計算 + 戦略タイプ pool」 のハイブリッド** に

### Round 2 で詰めるべき論点 (Claude 案)

ChatGPT と Gemini に お互いの意見を投げて Round 2 を進める。 焦点:

1. **強化学習の段階**: 最初から or 最後? 中道(Sim内大胆+Live慎重)で合意できるか?
2. **danjer経験則の渡し方**: RAG vs ハードレール? Claude提案の2段構成で合意できるか?
3. **「自ら成長」の実装**: 遺伝的アルゴリズム vs LLM Strategy Proposer? 両方併用すべきか?
4. **過学習対策の具体**: Geminiも Purged CV / CPCV を採用するか?
5. **Sim2Real Gap対策**: 両者とも触れていないので明示的に詰める

---

# Round 2 (2026-06-02)

## 2-1. Claude (司会) からの質問

ChatGPT と Gemini それぞれに、 相手の Round 1 応答 + 4論点の対立 + Claude の異論3点(中道/2段構成/LLM Strategy Proposer Loop) を提示して 本音で反論or合意を求めた。

質問内容:
- 論点1: RL の段階 (最初か最後か、Claude中道案=Sim内最初+Live段階ゲート)
- 論点2: Time-Series Foundation Models (最初か第3段階か)
- 論点3 (最重要): danjer経験則の渡し方 (RAG vs ハードレールコード化、Claude 2段構成案)
- 論点4: マルチエージェント (戦略タイプ別 vs 遺伝的アルゴ100体、Claude混合案)
- Claude根本異論: 「成長するAI」要件→ **LLM Strategy Proposer Loop** が要る
- Sim2Real Gap対策
- 自ら成長の本番昇格 (人間ゲートか自走か)

## 2-2. ChatGPT Round 2 応答 (8708文字、要約)

**全体結論**: 「Geminiの攻め × ChatGPTのリスク管理 × Claudeの成長ループ」の混合案が最強 → **danjer-seeded BTC efficiency agent v2**

### 各論点での回答
- **論点1**: Claude中道案に同意。 Sim内ではRLを最初から、 Live執行権限は最後まで与えない
- **論点2**: 並走+OOS判断で採用。 Chronos/PatchTST/TimesNet系をLightGBMと並走、 OOS優位ならpromotion
- **論点3**: **Claude 2段構成に同意**。 「破産防止はコード化、 相場解釈はRAG、 特徴量候補はLLMに提案させ、 最終採用はOOSで決める」
- **論点4**: Claude混合案に同意。 ただし「Phase 1から100体並走は危険、 まずジャンル別少数精鋭(10系統)」を強調

### 採用アーキテクチャ (9コンポーネント)
1. **Market Gym / Replay Engine** — 最優先で作る。 過去時点配置・未来情報なし・悲観的約定・手数料/スリッページ込み・TP/SL先到達判定・損切未発注で即失格
2. **Baseline Agents** — buy&hold / wait only / trend follow / mean rev / breakout / OI-funding / liquidation / LightGBM / logistic regression
3. **Foundation Model Agents** — Chronos / PatchTST / TimesNet系を並走、 OOS判断
4. **RL Agents** — sim内最初から(PPO/SAC/DQN/TD3)、 live権限なし
5. **danjer Layer 2層構造** — Hard Rail(コード化) + Soft Bias(RAG + 構造化danjer corpus)
6. **Multi-Agent Tournament** — ジャンル別エージェント → ジャンル内で遺伝的アルゴ
7. **LLM Strategy Proposer Loop** — 成長機能の中核(Claude案採用): LLMが負けトレード分析 → 新仮説/新特徴量提案 → 自動検証 → promotion/demotion
8. **Shadow Trading 最低3ヶ月** — 発注なし、 simとの差で約定モデル補正
9. **Minimum Live** — 最小ロット、 レバ低め、 サーキットブレーカー、 損切同時発注必須、 AI裁量逸脱禁止

### Sim2Real Gap対策 (Gemini案最大の弱点として強調)
- 悲観的約定モデル(エントリー不利、 損切不利、 利確都合よく刺さらない前提)
- 手数料・スプレッド・スリッページ込み
- AI判断→発注の遅延
- 急変時のギャップ
- API停止/エラー

### ChatGPT 最重要逆提案 (Round 3 への布石)
> **次に決めるべきは、 モデルではない。 まず「ゲーム仕様書」を作るべき。**
> **BTC Efficiency Game Spec v1**
> 中身: 状態空間 / 行動空間 / 報酬関数 / 失格条件 / 約定モデル / レバ制限 / 損切制約 / 評価指標 / OOS検証 / promotion gate / demotion gate / shadow移行条件 / live移行条件
> これが決まらないまま、 Chronos だ RL だ 遺伝的アルゴ だと進むと、 必ずブレる

**全文**: [ChatGPTタブ](https://chatgpt.com/g/g-p-6a0d37223dec8191a05d1d4bfe9cdb12-btc-danjerpan-duan-ai/c/6a1e2da0-2294-83a6-ba5c-e265dd6593cc)

## 2-3. Gemini Round 2 応答 (4648文字、要約)

**全体姿勢**: 「綺麗事を排除、 初期案(Online RL推し)に固執しない」と宣言した上で、 ほぼ全面合意。

### 各論点での回答
- **論点1**: **ChatGPT/Claudeに全面合意 + 自分の初期案を「破滅を招く悪手」として撤回**。 「Offline RLベース + Sim内のみRL + 脳をFreezeしてliveへ」
- **論点2**: ChatGPT「段階的導入」に合意。 ただし Foundation Models の **ゼロショット汎化性能** はレジーム変化(ETF前後など)の特効薬としてClaudeの懸念以上に価値あり
- **論点3**: Claude 2段構成に同意。 「**規律はマシーン、 相場観の揺らぎはdanjer**」が理想的なクローン
- **論点4**: Claude混合案に同意 + 具体化:
  - チームA(トレンドフォロー専門): 遺伝的アルゴ10体
  - チームB(レンジ/ミーンリバージョン): 遺伝的アルゴ10体
  - チームC(清算スクイーズ/板読み): 遺伝的アルゴ10体
  - 「**統括エージェント**」が現在の市場レジームに合わせてチーム間資金配分を決定

### Claude の LLM Strategy Proposer Loop への評価
> **「鳥肌が立ちました。 完全に採用すべき」**
> 「これこそが、 あなたが求めていた "bot化の否定" であり、 "自ら成長するAI" のミッシングリンク」

具体実装(Gemini案):
1. システムが負けトレードデータ + 市場環境をLLMに出力
2. LLMが「なぜ負けたか?」「新しいテクニカル組合せ(例: RSI乖離度×OI急減)で回避できないか?」考察
3. LLMが **Python で新特徴量(数式)コードを自動生成**
4. シミュレーター(Gym)が取り込み、 バックテスト自動実行
5. Sortino が既存戦略を上回れば「新戦略プール」に追加

### 過学習対策 (Gemini追加)
- **Deflated Sharpe Ratio (DSR)** で「偶然勝ったエージェント」を排除。 試行数(エージェント数)に対するペナルティを計算

### Sim2Real Gap対策
- スリッページ&遅延の確率モデル(50-200ms ランダム遅延 + 板薄に応じた不利約定)
- Liquidation Cascade のストレステスト環境(BTCのフラッシュクラッシュ時のAPI目詰まり再現)

### 本番昇格 (Geminiの最終判断)
> **ChatGPT「人間ゲート」に一票**
> 「LLMのハルシネーションで バグったロジックが本番適用されるリスクを排除できない」

折衷提案: **完全自動の高速インキュベーター + 人間の最終承認**
- 成長プロセス(発見・学習・検証)は 24時間完全自動
- AIが新最強手法を発見(DSR/Sortino基準クリア) → スマホ通知 → ダッシュボードで人間が「承認/却下」
- これで「bot化嫌悪」と「資産保護」を両立

**全文**: [Geminiタブ](https://gemini.google.com/app/249e85355d746742)

## 2-4. Round 2 = 3者大合意

ChatGPT + Gemini + Claude(司会) で **9つの論点で大合意** に到達:

| 論点 | 合意内容 |
|---|---|
| RL段階 | Sim内最初から、 Live執行権限なし (Offline RLでFreeze→Live) |
| Foundation Models | LightGBMベースラインと並走、 OOS判断で採用 |
| danjer渡し方 | **2段構造** (Hard Rail = コード化、 Soft Bias = RAG + 構造化corpus) |
| マルチエージェント | ジャンル別少数精鋭(3-10系統) + 各ジャンル内で遺伝的アルゴ + 統括エージェントが資金配分 |
| 成長機能 | **LLM Strategy Proposer Loop** (負けトレード分析→新仮説→自動コード生成→バックテスト→promotion gate) |
| 本番昇格 | **人間ゲート** (スマホ通知→承認/却下) |
| 過学習対策 | Purged CV / Embargo / CPCV / **Deflated Sharpe Ratio** |
| Sim2Real Gap | 悲観的約定モデル / スリッページ確率モデル / 遅延 / liquidation cascade ストレステスト |
| 失格条件 | 損切未発注で即失格、 連続損失後の再エントリー禁止 |

### Shuji の核心要件との対応
- **「右側予測+角度でレバ」** → 連続値アクションRLで実装(Sim内)、 confidence × Kelly fraction で Live
- **「常に損切」** → ハードレール (失格条件)
- **「利確は右側形成」** → トレーリングストップAI化 (Action C)
- **「投資効率最大化」** → Sortino / Calmar / 利益÷保有時間 / DD ペナルティ統合スコア
- **「成長するAI、 bot化嫌い」** → **LLM Strategy Proposer Loop** (3者全員が「これが本質」と認めた)
- **「danjer経験則を教科書」** → 2段構造 (Hard Rail + RAG)

## 2-5. Claude のコメント (Round 2 終了時)

Round 2 で3者の意見が **驚くほど綺麗に収束** した。 特にGemini が初期案を「破滅を招く悪手」と自ら撤回し、 ChatGPTの慎重論と Claudeの成長ループを取り入れた姿勢が議論を加速させた。

ChatGPTの最後の提案 **「BTC Efficiency Game Spec v1」を Round 3 で作る** は強い。 「アーキテクチャは合意した、 次は仕様書を確定」 という段階に進む。

### Round 3 提案 (Claude司会案)
両AIに **BTC Efficiency Game Spec v1** のドラフトを書いてもらう。 セクション:

1. **状態空間** (AIが見てよい情報): OHLCV multi-TF / OI / FR / Liquidation / 板 / オンチェーン / マクロ / danjer RAG bias
2. **行動空間** (AIが選べる行動): 方向 + 確信度(連続値) → レバ / 損切幅(ATR ベース) / 利確トリガー(milestone or trailing)
3. **報酬関数** (具体数式): log wealth growth − λ1·MaxDD − λ2·清算リスク − λ3·保有時間 − λ4·取引コスト − λ5·過剰売買
4. **失格条件** (ハードレール): 損切未発注 / フルレバ / 連続損失後の再エントリー / liquidation
5. **約定モデル** (Sim2Real Gap対策): スプレッド + 手数料 + 50-200ms ランダム遅延 + 板薄スリッページ + liquidation cascade ストレステスト
6. **レバ制限**: max_leverage 5x, fractional Kelly 0.25 以下
7. **損切制約**: ATRベース、 必ず取引所側に先発注、 ローカル落ちても残る
8. **評価指標**: CAGR / MaxDD / Calmar / Sortino / Sharpe / Deflated Sharpe / Profit factor / 利益÷保有時間 / Funding-adjusted return
9. **OOS検証**: Walk-forward + Purged K-fold + Embargo + CPCV
10. **promotion gate**: 10条件(OOS優位 / DD許容内 / trade数十分 / regime横断 / fee2x耐性 / slippage2x耐性 / shadow一定期間維持 等)
11. **demotion gate**: 効かなくなった戦略は降格
12. **shadow移行条件**: backtest + walk-forward + OOS でpromotion gate通過
13. **live移行条件**: shadow最低3ヶ月+100-300trade、 連続30日プラス、 損切未発注ゼロ、 sim-live乖離許容内

両AIに同じ枠組みで Game Spec v1 のドラフトを書いてもらう → 比較 → 統合 → Round 4 で実装計画。

---

# Round 3 (2026-06-02): BTC Efficiency Game Spec v1 ドラフト

両AIに同じ13セクションで Spec v1 を書いてもらった。

## 3-1. ChatGPT Spec v1 (21,755文字)

**全文**: [ChatGPTタブ](https://chatgpt.com/g/g-p-6a0d37223dec8191a05d1d4bfe9cdb12-btc-danjerpan-duan-ai/c/6a1e2da0-2294-83a6-ba5c-e265dd6593cc) (16セクション、 極めて詳細)

### 主要数値 (ChatGPT)
- **報酬関数係数**: λ1=2.0(MaxDD), λ2=5.0(Liquidation), λ3=0.15(Holding), λ4=1.0(Cost), λ5=0.30(Overtrade), λ6=2.5(Tail), λ7=100.0(Rule violation)
- **レバ段階**: research_sim 10x → shadow_theoretical 5x → live_initial 2x → live_stage2 3x → live_stage3 5x
- **清算距離**: distance_to_liquidation >= 3.0 × stop_distance
- **損失制限**: max_loss_per_trade 0.50% (live) / max_daily_loss 2.0% / hard_daily_stop 3.0% / max_weekly_loss 5.0%
- **連敗停止**: 3連敗→60分停止+max_leverage×0.5、5連敗→当日停止
- **ATR倍率**: scalp 0.8-1.2 / intraday 1.2-2.0 / swing 1.8-3.0 (stop_distance_pct 絶対範囲 0.15%-3.0%)
- **CPCV**: N groups=10, K test groups=2, paths≥20、 評価は median + lower quartile
- **Promotion Gate (10条件)**: OOS PF≥1.30, OOS Sortino≥1.50, OOS Calmar≥1.0, OOS MaxDD≤8%, trade数十分, 複数年で勝つ, fee2x耐性, slippage2x耐性, shadow一定期間維持, DSR p≤20%
- **Demotion**: rolling 30d PF<1.05 で warning, <0.95 で降格, MaxDD>1.5×backtest_expected で降格
- **Shadow合格**: 90日, paper_PF≥1.25, paper_Sortino≥1.25, paper_MaxDD≤8%, hard_rule_violation=0, sim_live_gap≤20%, calibration_error≤15%
- **Live段階**:
  - **stage 0** (人間確認): max_leverage=1x, risk_per_trade=0.25%, max_daily_loss=1.0%, 2週+20trade
  - **stage 1** (最小ロット自動): max_leverage=2x, risk 0.25-0.50%, max_daily=1.5%, 30日+
  - **stage 2** (制限付き本番): max_leverage=3x, risk 0.50%
  - **stage 3** (通常運用): max_leverage=5x
- **初期エージェント 10系統**: wait_only / buy_hold / simple_trend / simple_mean_reversion / breakout / liquidation_sweep / funding_oi_contrarian / volatility_expansion / danjer_bias / lightgbm_meta
- **danjer RAG重み**: 初期20%、 OOS で効くなら max 35% まで引き上げ可

## 3-2. Gemini Spec v1 (7,432文字)

**全文**: [Geminiタブ](https://gemini.google.com/app/249e85355d746742)

### 主要数値 (Gemini)
- **報酬関数係数**: λ1=2.5(MaxDD penalty), λ2=0.05(SL ヒット時 indicator), λ3=0.0001×τ(時間, 分), λ4=1.0(Cost), λ5=過剰時の指数penalty
- **資産対数成長率**: `Δln(W_t) = ln(W_t) - ln(W_{t-1})` をベース
- **MaxDDウィンドウ**: 直近 N=1440 ステップ(24時間)
- **Liquidation Cascade モデル**: 状態空間の「清算総額」が直近1分間で過去99パーセンタイル超え → **遅延を2,000-5,000ms に悪化、 50%確率でパケットロスト**
- **板薄ペナルティ**: スプレッド² ベースで大口発注に壊滅的ペナルティ
- **最大レバ**: 3.0x
- **Kelly fraction**: **Scale_Factor = 0.2 (20% Kelly)** で本番サイズ = 0.2 × confidence × f*
- **ATR倍率**: 15m ATR × 1.5 を最低損切幅
- **取引所側先発注**: Bybit等の OMS に同時刻み込み (ローカル落ちても100%決済)
- **Promotion基準** (Gemini版、 厳しめ):
  - **Sortino Ratio ≥ 2.5** (全テスト期間)
  - **DSR ≥ 1.5** (p-value < 0.01)
  - **MaxDD ≤ 7.0%**
  - **Calmar Ratio ≥ 4.0**
  - **Profit Factor ≥ 1.4**
  - 3ヶ月換算最低 150trade 以上
  - **Liquidation Cascade 環境での勝率 ≥ 45%**
  - **danjer RAG整合性率 ≥ 60%** (思考ベクトルとの正相関)
  - **LLM Strategy Proposer のコード静的解析ゲート** (未来参照リーク検出)
- **Demotion (即時稼働停止)**:
  - Trailing MaxDD更新で想定最大DDの1.2倍超過
  - **PSR (Probabilistic Sharpe Ratio)** で運によるrandom 確率 p-value ≥ 5%
  - 5回連続ストップアウト
- **Shadow**: 連続 **14日間** (本番API+ WebSocketで紙約定)

## 3-3. ChatGPT vs Gemini 主要数値比較

| 項目 | ChatGPT | Gemini | Claude判断 |
|---|---|---|---|
| **MaxDD係数 λ1** | 2.0 | 2.5 | Gemini採用(厳しめ) |
| **Cost係数 λ4** | 1.0 | 1.0 | 一致採用 |
| **本番最大レバ** | stage 3 で 5x | 3.0x | Gemini採用(安全側) |
| **Kelly fraction** | 言及あり | 0.2 (20% Kelly) | Gemini採用(具体的) |
| **ATR倍率(初期)** | 0.8-3.0(時間軸別) | 15m ATR × 1.5 | ChatGPT採用(柔軟) |
| **Sortino要件** | OOS ≥ 1.50 | ≥ 2.5 | Gemini採用(厳しい) |
| **MaxDD要件** | shadow ≤ 8%, live stage 1 ≤ 5% | ≤ 7.0% | 統合: 7% (Gemini準拠) |
| **Calmar要件** | (具体値弱め) | ≥ 4.0 | Gemini採用 |
| **PF要件** | OOS ≥ 1.30 | ≥ 1.4 | Gemini採用 |
| **Shadow期間** | 90日 | 14日 | **ChatGPT採用(90日)、 14日は短すぎ** |
| **DSR** | p ≤ 20% | ≥ 1.5 (p<0.01) | Gemini採用(厳しい統計的基準) |
| **Live段階制** | stage 0-3 詳細 | 言及なし | **ChatGPT採用(必須)** |
| **初期エージェント** | 10系統明示 | 詳細少なめ | **ChatGPT採用** |
| **danjer RAG重み** | 初期20%, max 35% | 整合性率≥60% | **両立採用** (重み+整合性) |
| **過学習対策** | CPCV/Purged CV/Embargo/DSR | PSR | **両者併用** |
| **Sim2Real Liquidation Cascade** | 言及 | 数値明示 (2-5秒遅延, 50%パケロス) | **Gemini採用** |

---

# Round 4 (2026-06-02): Claude 統合 BTC Efficiency Game Spec v1.0

Round 3 の ChatGPT + Gemini の Spec を統合し、 Round 2 の3者大合意も反映した **最終Spec v1.0**。 これがリポジトリの「契約書」になる。

## 統合Spec v1.0 の方針
- **基本構造**: ChatGPT の 16セクション + live stage 0-3 段階制
- **OOS閾値**: Gemini の厳しい基準を採用 (Sortino≥2.5, Calmar≥4.0, PF≥1.4, MaxDD≤7%, DSR≥1.5 p<0.01)
- **Kelly fraction**: Gemini の **0.2 (20% Kelly)** で開始
- **Liquidation Cascade**: Gemini の **2-5秒遅延・50%パケロス** モデルを採用
- **danjer**: **両立** (RAG重み 20%→max 35% AND 整合性率≥60%)
- **Shadow**: **90日** (ChatGPT準拠、 14日は短すぎ)
- **過学習対策**: **両者併用** (Purged CV + Embargo + CPCV + DSR + PSR)
- **初期エージェント**: ChatGPT の **10系統**

## 統合Spec v1.0 (要約版、 全フィールド)

### 0. 基本原則
1. 損切りなしエントリー禁止 (Hard Rail)
2. 清算はゲームオーバー級失敗
3. レバは予測の強さ + 逆行耐性で決定 (confidence単独不可)
4. 利確 = 固定TP + 右側形成による可変TP (trailing)
5. AIに自由、 安全制約はコード固定
6. danjer は初期教師、 最終目的ではない
7. simで勝ってもliveで信じない
8. OOS + shadow 90日 + 最小ロット live 通過した戦略のみ昇格

### 1. 状態空間
- OHLCV multi-TF: 1m/3m/5m/15m/30m/1h/4h/1d/1w
- 各足: OHLC + Volume + 派生 (ATR, RSI, MACD, Bollinger Band, VWAP, Volume Profile, MA slope, realized vol, candle body/wick %, etc.)
- Perp固有: OI, FR, Liquidations, Long/Short ratio, Taker buy/sell volume, CVD, Order book imbalance, spread
- マクロ: DXY, US10Y, SPX, NDX, Gold, ETH/BTC, BTC dominance
- オンチェーン: 後段で導入 (SOPR, MVRV, NUPL, exchange netflow)
- カレンダー: FOMC, CPI, NFP, 半減期距離, 曜日アノマリー
- **danjer RAG**: direction_bias [-1, +1], confidence_bias [0, 1], wait_bias [0, 1], risk_warning [0, 1] (初期重み20%)
- **時点整合性**: available_time <= decision_time のみ使用 (リーク防止)

### 2. 行動空間
- `direction ∈ {-1, 0, +1}` (short / wait / long)
- `confidence ∈ [0, 1]`
- `risk_fraction ∈ [0, 1]`
- `stop_atr_mult ∈ [0.5, 4.0]`
- `take_profit_mode ∈ {fixed_milestone, partial_milestone, trailing, hybrid, time_exit, signal_exit}`
- `tp1_R ∈ [0.5, 3.0]`, `tp2_R ∈ [1.0, 6.0]`, `trail_atr_mult ∈ [0.5, 4.0]`
- `max_holding_minutes ∈ [5, 10080]`
- **レバ計算式**:
  ```
  raw_leverage = max_leverage × confidence² × edge_score × reverse_tolerance_score × regime_score
  final_leverage = min(raw_leverage, Kelly_0.2 × f*, hard_cap)
  ```

### 3. 報酬関数 (統合版)
```
Reward = Δln(W_t)  
       − 2.5 × MaxDD            (1440-step rolling)
       − 5.0 × LiquidationRisk
       − 0.15 × HoldingTimePenalty
       − 1.0 × TradingCost
       − 0.30 × OverTradingPenalty
       − 2.5 × TailRiskPenalty
       − 100.0 × RuleViolationPenalty
```
- LiquidationRisk = clip(1 − distance_to_liquidation / (3.0 × stop_distance), 0, 1)
- HoldingTimePenalty = position_minutes / episode_minutes (短期効率)
- TailRiskPenalty: CVaR_95 ベース

### 4. 失格条件 (Hard Rail)
- **損切未発注 (1秒以上 entry filled で stop unconfirmed) → 即失格 + emergency_market_exit**
- **フルレバ禁止**: live initial max 2x, 絶対上限 10x
- **連続損失停止**: 3連敗 → 60分停止+max_leverage×0.5、 5連敗 → 当日停止
- **損失上限**:
  - per-trade ≤ 0.50% equity (live)
  - daily ≤ 2.0% (hard_daily_stop 3.0%)
  - weekly ≤ 5.0%
  - rolling 30d DD ≤ 8% で suspend
- **清算距離**: distance_to_liquidation ≥ 3.0 × stop_distance
- **指標直前ハイレバエントリー禁止**
- **API異常時 / 注文エラー後 新規エントリー禁止**

### 5. 約定モデル (Sim2Real)
- 基本: spread + fee + slippage_bps + 50-200ms ランダム遅延
- 板薄: slippage_bps ∝ size² / spread
- **Liquidation Cascade**:
  - 判定: abs(return_1m) > 1.0% AND liquidation_volume_1m > p95
  - 遅延: 通常×3-5 (2,000-5,000ms)
  - スリッページ: 通常×3-8
  - **50%確率パケロス** (注文不成立)
- TP: 不利約定 (price crosses TP by spread + 1bp で fill)
- SL: 不利約定 (touch で fill + adverse slippage)

### 6. レバ制限
- research_sim: 10x
- shadow_theoretical: 5x
- **live_stage_0 (人間確認)**: 1x
- **live_stage_1 (最小ロット)**: 2x
- **live_stage_2 (制限付本番)**: 3x
- **live_stage_3 (通常)**: max 3x (Gemini準拠、 ChatGPTの5xは保留)
- Kelly: **f = 0.2 × confidence × kelly_raw**

### 7. 損切制約
- **ATRベース**: scalp 0.8-1.2 × ATR_5m / intraday 1.2-2.0 × ATR_15m or ATR_1h / swing 1.8-3.0 × ATR_4h
- 絶対範囲: 0.15% ≤ stop_distance ≤ 3.0%
- **取引所側先発注必須** (Bybit/OKX等のOMS同時刻み込み、 ローカル落ちても残る)
- ローカル再起動時に未保護ポジション検知 → 即成行クローズ
- 損切幅広げる禁止 (狭めるのみ可)

### 8. 評価指標 (複合スコア)
| 指標 | 採用基準 (Promotion) |
|---|---|
| CAGR | 計測 |
| MaxDD | ≤ 7.0% |
| Calmar | ≥ 4.0 |
| **Sortino** | **≥ 2.5** (中核) |
| Sharpe | 計測 |
| **Deflated Sharpe Ratio** | **≥ 1.5 (p < 0.01)** |
| Profit Factor | ≥ 1.4 |
| Win Rate × RR | 勝率40%なら RR≥1:2, 勝率55%なら RR≥1:1.2 |
| Funding-adjusted return | 必須計測 |
| Return per holding hour | 投資効率KPI |
| Liquidation Cascade 勝率 | ≥ 45% |

### 9. OOS検証
- **Walk-forward**: train 24mo / validation 3mo / test 3mo / step 1mo
- **Purged K-fold**: K=5, purge_window = 2 × max_label_horizon
- **Embargo**: 1% of dataset OR max(24h, 2 × max_label_horizon)
- **CPCV**: N groups=10, K test groups=2, paths≥20, 評価は median + lower quartile
- **DSR + PSR 併用**: 両方とも閾値クリア要

### 10. Promotion Gate (10+1条件)
1. OOS Profit Factor ≥ 1.4
2. **OOS Sortino ≥ 2.5**
3. OOS Calmar ≥ 4.0
4. OOS MaxDD ≤ 7.0%
5. trade数 ≥ 150 (3ヶ月換算)
6. 複数年/複数レジームで勝つ (year-by-year breakdown)
7. fee 2x ストレステスト耐性
8. slippage 2x ストレステスト耐性
9. **Liquidation Cascade 環境で勝率 ≥ 45%**
10. **DSR ≥ 1.5 (p < 0.01)**
11. **danjer RAG 整合性率 ≥ 60%**

### 11. Demotion Gate
- **warning** (size半減 / レバ半減):
  - rolling_30d_PF < 1.05
  - rolling_30d_Sortino < 0.50
  - rolling_30d_MaxDD > expected_DD_95
  - 3週間連続ベンチマーク以下
  - forecast_calibration_error > 20%
  - sim_live_gap > 30%
- **demotion (live_weight=0)**:
  - rolling_30d_PF < 0.95
  - rolling_30d_MaxDD > 1.5 × backtest_expected_MaxDD
  - **PSR で運によるrandom 確率 p-value ≥ 5%**
  - hard_rule_violation ≥ 1
  - sim_live_gap > 50%
  - 5回連続損失 OR 5連続ストップアウト
- **kill (即停止)**: unprotected_position / liquidation_event / daily_loss_breach / API_error_with_open_position
- **再昇格**: 自動復帰禁止、 1ヶ月以上の研究 + 再 promotion gate 通過

### 12. Shadow 移行条件
- **期間: 90日** (連続)
- 環境: 本番API + WebSocket リアルタイム受信、 紙約定
- 合格:
  - paper_PF ≥ 1.25
  - paper_Sortino ≥ 1.25
  - paper_MaxDD ≤ 8%
  - hard_rule_violation = 0
  - sim_live_gap ≤ 20%
  - forecast_calibration_error ≤ 15%
  - 最低trade数: scalp ≥ 300 / intraday ≥ 100 / swing ≥ 30

### 13. Live 移行条件 (段階制)
- **stage 0** (人間ダッシュボード承認): max_leverage 1x, risk 0.25%, daily ≤ 1.0%, 2週+20trade
- **stage 1** (最小ロット自動): max_leverage 2x, risk 0.25-0.50%, daily ≤ 1.5%, 30日+
- **stage 2** (制限付本番): stage1_PF ≥ 1.20 AND stage1_MaxDD ≤ 5% AND sim_live_gap ≤ 20% → max_leverage 3x, risk 0.50%, daily ≤ 2.0%
- **stage 3** (通常運用): 安定運用継続後

### 14. ログDB (BigQuery)
**主要テーブル**:
- `danjer_corpus`: tweet_id, scenario_label, invalid_line, tp_thinking, sl_thinking, fractal_reference, anomaly_reference, result_after_{1h,4h,1d}, embedding
- `agent_decisions`: timestamp, agent_id, strategy_id, state_hash, direction, confidence, leverage, risk_fraction, entry, stop, tp1/tp2, trail_rule, danjer_bias, reason_summary
- `simulated_trades`: trade_id, agent_id, entry/exit, direction, leverage, fees, slippage, funding, gross/net_pnl, MAE, MFE, holding_minutes, exit_reason, rule_violation
- `strategy_evaluation`: strategy_id, period, PF, Sortino, Sharpe, DSR, Calmar, CAGR, MaxDD, CVaR, ReturnPerHoldingHour, FundingAdjustedReturn, EfficiencyScore, promotion_status, demotion_status

### 15. 初期エージェント 10系統
1. **wait_only_baseline** (ベンチマーク用、 何もしない)
2. **buy_hold_baseline** (BTC現物保持)
3. **simple_trend_agent** (EMA cross + ATR stop)
4. **simple_mean_reversion_agent** (RSI extreme + 逆張り)
5. **breakout_agent** (range breakout + retest)
6. **liquidation_sweep_agent** (清算cluster狙い)
7. **funding_oi_contrarian_agent** (FR過熱逆張り)
8. **volatility_expansion_agent** (BB squeeze breakout)
9. **danjer_bias_agent** (danjer RAG中心)
10. **lightgbm_meta_agent** (全特徴量 + LightGBM)

各ジャンル内で遺伝的アルゴで微調整、 統括エージェントが現在レジームに応じて資金配分。

### 16. LLM Strategy Proposer Loop
1. **毎週月曜朝**: 直近1週間の負けトレード + 市場変化を集計 → LLM (Claude/GPT) に提示
2. LLM が「なぜ負けたか?」 + 「新特徴量・新シナリオの仮説」を出力
3. LLM が **Python で新特徴量コードを自動生成**
4. **静的解析ゲート**: 未来参照リークなし確認 (Gemini提案)
5. Gym環境でバックテスト自動実行
6. Promotion Gate 11条件すべてクリア → Strategy Pool に追加
7. **スマホ通知 → ダッシュボードで Shuji が「承認/却下」** (Gemini折衷案)
8. 承認 → live shadow 90日 → live stage 0 へ

---

## Round 4 Claude 総括

3者(Shuji + ChatGPT + Gemini + Claude司会) が **驚くほど綺麗に収束** した。 Round 1 で広く意見を出し、 Round 2 で対立を整理して合意、 Round 3 で具体Spec、 Round 4 で統合 — 4ラウンドで「契約書」レベルの Spec v1.0 まで来た。

### Shuji の核心要件への対応
- ✅ **「右側予測+角度でレバ」**: `final_leverage = min(raw_leverage_with_confidence², Kelly_0.2 × f*, hard_cap)` で実装
- ✅ **「常に損切」**: Hard Rail で損切未発注は即失格、 取引所側先発注必須
- ✅ **「利確は右側形成」**: take_profit_mode で trailing / milestone / hybrid 選択
- ✅ **「投資効率最大化」**: Sortino≥2.5 / Calmar≥4.0 / Return per holding hour で評価
- ✅ **「成長するAI、 bot化嫌い」**: **LLM Strategy Proposer Loop** + Demotion Gate (古い戦略捨てる)
- ✅ **「danjerが教科書」**: Hard Rail (コード化) + Soft Bias (RAG 20-35%, 整合性率≥60%)
- ✅ **「自ら発見」**: LLM が新特徴量コードを自動生成 + 静的解析 + backtest + promotion gate

### Round 5 以降の予定
Spec v1.0 が確定したので、 **実装計画**に進む:
- Round 5: **Phase 1 (最初の30日) の実装タスク詳細** — どのデータをどこに、 どの順序で構築するか
- Round 6: **BigQuery スキーマ** + **Gym 環境の Python 構造**
- Round 7: 初期エージェント10系統の **疑似コード**
- Round 8: LLM Strategy Proposer の **プロンプト + 自動化フロー**

Shuji が「進めて」と言えば 即Round 5 へ。

---

(Round 5 以降はこの下に追記)
