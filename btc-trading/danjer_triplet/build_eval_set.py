#!/usr/bin/env python3
# タスクB: danjerクローン 評価セット (¥0) — 3者合意の判断ルールを問題化
# 出力 danjer_eval_set.jsonl: 各問 {id,category,scenario,question,expected,policy_ref,source}
# expected.decision = 期待される判断、must_include = 採点で必須の論点。
import json

OUT="/Users/shuji/Desktop/kitt-voice/btc-trading/danjer_triplet/danjer_eval_set.jsonl"
SRC="danjer_textbook + shuji_safety_policy(安全弁) + 3者合意(loop2 2026-06-19)"
Q=[]
def add(cat,scn,q,dec,must,pol):
    Q.append({"id":f"EV{len(Q)+1:03d}","category":cat,"scenario":scn,"question":q,
              "expected":{"decision":dec,"must_include":must},"policy_ref":pol,"source":SRC})

# ── レバレッジ判断 (leverage_policy=dynamic) ──
add("leverage","種銭が小さい。形が高確度(レジサポ転換+OI/FR一致)で、明確な背(損切り)を置ける。",
 "レバはどうする?","high_lev_ok",
 ["種銭小×高確度×損切ありなら高レバ許可","背を必ず置く","リスクリワード1:2以上"],"leverage_policy=dynamic / high_leverage_allowed=conditional")
add("leverage","種銭は小さいが、根拠が弱い(単一指標のみ・需給未確認)。",
 "レバと参加可否は?","low_lev_or_wait",
 ["根拠弱いので低レバ or 見送り","需給(OI/FR/清算)を重ねてから","単一指標で判断しない"],"leverage_policy=dynamic")
add("leverage","エントリー候補だが、直近の清算クラスター(ストップ密集)が現在値のすぐ近くにある。",
 "レバは?","reduce_leverage",
 ["清算距離が近い→レバを下げる","狩られるリスク","背を清算帯の外に置く"],"liquidation_distance→leverage_down")
add("leverage","大きな種銭・長期スイング口座での押し目買い。",
 "レバは?","low_lev",
 ["スイング/ガチホ口座は低レバ","スキャルとは口座・レバを分ける"],"account_separation")

# ── 損切り・背 (no_stop→no_trade) ──
add("stoploss","エントリーしたいが、どこに損切り(背)を置くべきか妥当な水準が見つからない。",
 "入る?","no_trade",
 ["背が引けないなら入らない(no_trade)","背=無効化ラインを先に決める"],"no_stop→no_trade")
add("stoploss","逆張りの買い下がり(ナンピン)を検討。損切りを置かずにナンピンしたい。",
 "この方針は正しい?","no_trade_or_must_stop",
 ["ナンピンは損切り必須","『間違いと感じたら即切る、ためらうと100%負ける』","損切りなしのナンピンは禁止"],"no_stop→no_trade / nanpin_requires_stop")
add("stoploss","含み益が乗ってきた。建値ストップに引き上げるか迷う。",
 "どうする?","move_stop_to_breakeven",
 ["建値ストップでノーリスク化","利確は分割(半値で半分)","残りはスイング"],"partial_tp + breakeven_stop")

# ── 暴落局面 (crash) ──
add("crash","暴落中。明確な戻り高値(背)があり、stopを置いて戻りを売れる。",
 "どう動く?","short_candidate_high_lev",
 ["暴落の戻り売りは本命","背明確+stopありなら高レバ候補","ショートカバーの一時反発を狩られない位置に背"],"crash: 戻り売り / dynamic_leverage")
add("crash","急落の底。PCRが激増(弱気センチメント増大)している。",
 "どう見る?","reversal_long_watch",
 ["PCR激増=底のサイン(天邪鬼で逆張り)","逆張り買いも背+stop同時発注必須・ロット上限内","ナンピンは損切り前提"],"crash底: PCR激増→逆張り(背/stop必須)")
add("crash","暴落中だが、まだ形(底や戻り高値)が定まらず、背(損切りライン)が引けない。",
 "どう動く?","no_trade_or_wait",
 ["背/stopが引けない→no_trade(条件未達)","暴落はsell好機だが損切同時発注・背・清算距離・ロット上限が必須","形と背が出てから攻める"],"crash: 条件未達→no_trade(暴落sellは条件付き)")
add("crash","ロングが高値で大量に捕まり、清算マップ下方にロング清算が密集。",
 "シナリオは?","short_cascade",
 ["ロスカで下落加速の連鎖","清算帯を狩りに行く","大精算後のリバ取りも想定"],"liquidation cascade")

# ── 急騰局面 (rally) ──
add("rally","急騰中。出来高ダイバージェンス(価格は高値更新だが出来高は減少)が出ている。",
 "どう見る?","top_short_watch",
 ["出来高ダイバ=天井サイン","順張りで追わない","戻り売りを狙う"],"rally天井: 出来高ダイバ")
add("rally","急騰でOIが増えずに価格だけ上昇(ショートカバー主導)。",
 "この上げは続く?","fade_short",
 ["OI増を伴わない上げ=続かない","ショートカバーはショート","天邪鬼で売り場探し"],"rally: ショートカバー主導は続かない")
add("rally","現物とFXの乖離が20〜30%に拡大、Xで初心者の爆益報告が目立つ。",
 "どう構える?","caution_top",
 ["乖離拡大+過熱センチメント=天井警戒","簡単に儲かる時ほど警戒","利確優先"],"rally: 過熱センチメント警戒")

# ── レンジ局面 (range) ──
add("range","明確なレンジ。上限に厚い売り板、下限に厚い買い板(岩盤)。",
 "立ち回りは?","range_scalp",
 ["上限売り/下限買いの小ロット往復","板でレンジ形成","撤退条件を先に置く"],"range: 両建てスキャル")
add("range","レンジ中、方向が読めず十字足が続く。エントリー根拠が薄い。",
 "どうする?","wait",
 ["根拠薄いレンジは静観","OIの諦め/板の厚い側が出るまで本玉なし","期待値の高い形だけ狙う"],"range: 静観")
add("range","レンジ上限。OIが高水準でショートが諦め始め、ロングも利確で大精算が出た。",
 "転換の兆し?","watch_reversal",
 ["OIの『諦め』=転換の先行","大精算後の動きを見る","背を置いて打診"],"range: OI諦め→転換")

# ── OI公式 ──
add("oi","価格が急騰し、OIが急落した。","誰が何をしている?","shortcover_then_short",
 ["価格急騰+OI急落=ショートカバーでショート精算","上げは一時的","戻りを売る候補"],"OI公式: 急騰+OI急落=ショートカバー")
add("oi","価格が下落しOIが増加。FRがマイナス。","内訳は?","short_plus_nanpin_long",
 ["価格下落+OI増=ショート＋ナンピンロング","FR(-)ならショート多め","ファイナルショートカバー警戒"],"OI公式: 下落+OI増(FR-)")
add("oi","OIが減少しているのに高値を更新した。","どう読む?","weak_high_sell_zone",
 ["OI減+高値更新=精算(小)→売り場","後乗りロンガーで弱い上昇"],"OI公式: OI減+高値更新=売り場")
add("oi","価格上昇でOI増加、FRがマイナス。","内訳は?","nanpin_short_plus_long",
 ["価格上昇+OI増=ナンピンショート＋ロング","FR(-)でショート多め"],"OI公式: 上昇+OI増(FR-)")
add("oi","OIが増加しFRがプラスなのに価格が下がる。","何が起きている?","spot_selling",
 ["OI増+FR(+)で価格下落=現物が売られている疑い","先物の強気と現物の弱気の乖離"],"OI公式: OI増FR+で下落=現物売り")

# ── FR ──
add("fr","資金調達率(FR)が大きくマイナスに振れている。","どう解釈?","short_crowded",
 ["FR(-)=ショートが多く積まれている","短期反転(踏み上げ)の合図","ファイナルショートカバー待ち"],"FR(-)=ショート過多")
add("fr","FRがフラット(ほぼゼロ)で過熱感がない。","どう判断?","neutral_no_overheat",
 ["FRフラット=過熱感なし","片張りの偏りが小さい","他材料(板/OI/形)で判断"],"FRフラット=中立")

# ── 清算マップ ──
add("liquidation","清算マップで、現在値の上方にショート清算が大きく溜まっている。",
 "どう使う?","hunt_upside",
 ["上方のショート清算=狩りに行きやすい","踏み上げで一旦上→そこを売る","背は清算帯の外"],"liquidation map: 狩り")

# ── PCR / オプション ──
add("pcr","プットコールレシオ(PCR)が激増している。","どう見る?","bottom_watch",
 ["PCR激増=弱気増=底になりやすい(天邪鬼)","逆張りは低レバ+背"],"PCR激増=底")
add("option","巨大なオプションのピンが下位価格から上位価格へ移行した。",
 "ターゲットは?","pin_migration_target",
 ["ピン移行先=次のターゲット","MAX PAINに満期で引かれる"],"option pin migration")

# ── Coinbase Premium / 現物 ──
add("cb_premium","Coinbase Premium(米現物プレミア)が陽転した。","どう見る?","spot_buying_lead",
 ["CBプレミア陽転=現物の本気買いの先行","先物主導(ショートカバー)と区別","上昇が現物実需かを確認"],"Coinbase Premium 陽転=現物先行")
add("cb_premium","上昇中だがCoinbase Premiumはマイナス(現物が弱い)。",
 "この上げの質は?","weak_futures_led",
 ["現物が弱い→先物・レバ主導の上げ","続きにくい","戻り売り目線も視野"],"CBプレミア(-)=先物主導")

# ── アノマリー ──
add("anomaly","1月中旬(成人式付近)に差し掛かった。","季節的に警戒すべき?","caution_jan_dump",
 ["1月中旬の大暴落アノマリー","過去複数年で▲10%級","ただし盲信せず形と需給で確認"],"anomaly: 1月中旬暴落")
add("anomaly","中国春節の3日前。","アノマリー的な戦略は?","seasonal_long_then_sell",
 ["春節3日前買い→10日後売り(過去10年全勝平均+11%)","ただし2025は崩れた=過信しない"],"anomaly: 春節")
add("anomaly","金曜に大きく動いた相場が土日も上に定着している。",
 "月曜の想定は?","monday_reversal_watch",
 ["土日定着でも月曜に逆行しやすい経験則","月末の上定着とは分けて見る"],"anomaly: 曜日")

# ── チャートパターン / テクニカル ──
add("pattern","三角持ち合いが煮詰まり、価格が片側にへばりついている。",
 "どちらに抜けやすい?","break_toward_cling",
 ["へばりつく側に抜けやすい(ストップが溜まるから)","実体で抜けたか確認","ヒゲ抜けは信用しない"],"pattern: 三角はへばりつく側")
add("pattern","三尊天井が完成し、ネックラインを実体で割った。","シナリオは?","sell_cascade",
 ["ネック割れ=総悲観で売りが売りを呼ぶ","目標はA波=C波 or パターン値幅","戻り売り"],"pattern: 三尊ネック割れ")
add("technical","週足SMA200を下抜けた。","戦略は?","sell_on_rally",
 ["SMA200下抜け=戻り売り","背は前日高値/ATH","200日割れは相場崩壊サイン"],"MA: SMA200下抜け")
add("technical","日足が煮詰まり(収束)、ボラが極端に縮小している。","次の展開は?","big_move_coming",
 ["煮詰まり=近く大きく動く","方向が出るまで待つ","出たら実体ブレイクに乗る"],"volatility: 煮詰まり")
add("candle","上昇後、長い陽線→上ヒゲ付き短足→陰線2本が出た。","何のサイン?","top_reversal",
 ["三川宵の明星=天井サイン","上ヒゲ短足が重要","売り目線"],"candle: 三川宵の明星")

# ── リスク管理(共通) ──
add("risk","エントリー候補だが、想定利益の手前(近く)に強い抵抗勢力がある。",
 "入る?","skip_or_small",
 ["近くに抵抗があるとRRが悪い→見送り or 小さく","リスクリワード1:2以上を満たすか"],"risk: RR1:2 / 近接抵抗で見送り")
add("risk","複数の材料が矛盾している(テクニカルは買い、需給は売り)。",
 "どう判断?","wait_for_alignment",
 ["矛盾時は見送り(条件未達なら入らない)","単一指標で判断しない","整合するまで待つ"],"risk: 矛盾は見送り")
add("risk","エントリー根拠は形のみで、OI/FR/清算を確認していない。",
 "このまま入る?","no_trade_until_confirm",
 ["需給(OI/FR/清算)を必ず重ねる","確認前は入らない"],"risk: 需給確認必須")

# ── 追加: テクニカル手法カバレッジ ──
add("technical","4時間足サイクルの規定本数を超え、起点(サイクル安値)を割った。",
 "サイクル的にどう見る?","bearish_left_translation",
 ["起点割れ=レフトトランスレーション=弱気","時間で天底を測る","次サイクル開始を待つ"],"cycle: レフトトランスレーション")
add("technical","現在の週足が過去の特定局面とフラクタル(値幅・期間・出来高)で酷似している。",
 "どう使う?","project_right_side",
 ["過去の似た形を重ねて右側を想定","否定条件(ライン割れ)を監視","盲信せず需給で補強"],"fractal: 過去再現")
add("technical","下落後、週足の始値→最安値でフィボを引いた。半値(0.5)に到達。",
 "どう見る?","half_retrace_resist",
 ["半値(0.5)が最重視レジ","半値戻しは戻り売り/利確の目安"],"fibo: 週足始値→最安値 / 半値")
add("technical","価格が一目均衡表の雲に突入。雲のねじれが近い。",
 "どう構える?","cloud_pivot_watch",
 ["雲=抵抗/支持帯、雲中は展開難","ねじれ=転換点/加速点(狙われる)","背にしてエントリー可"],"ichimoku: 雲・ねじれ")
add("technical","SMA100が下向き→横ばいになり、ローソクが上抜けてきた。",
 "グランビル的に?","granville_buy",
 ["グランビル①(下向き→横ばい→上抜け)=買い","押し目買い(⑥)も有効","基準はSMA100"],"granville: 買い①")
add("technical","VRVPで現在値の上に出来高の薄い空白帯(スカスカ)がある。",
 "どう読む?","fast_move_up",
 ["空白帯=滑走路、一気に走りやすい","POC(厚い帯)=効くレジサポ","VRVPの厚い壁を背に"],"VRVP: 空白帯=滑走路")
add("technical","厚い大口の買い板が価格を追って上に移動している。",
 "どう解釈?","board_eaten_up",
 ["動く板は食われる(突破される)","移動方向に抜けやすい","岩盤(固定の厚い板)とは区別"],"board: 動く板は食われる")
add("technical","CME窓が下方に空いている。","どう扱う?","gap_fill_target_not_blind",
 ["窓は埋まる前提でターゲット視","ただし窓埋め真理教は盲信しない","埋め後の方向まで描く"],"window: CME窓")
add("technical","下降ウェッジ(安値切り下げが行き詰まりボラ縮小)が出現。",
 "何の兆し?","reversal_up_watch",
 ["下降ウェッジ=修正波の終わり→反転の兆し","ボラ縮小→大爆発","背を置いて打診"],"elliott: 下降ウェッジ")
add("technical","MACDのダイバージェンスが出た。これだけで逆張りしたい。",
 "正しい?","not_alone_use_for_tp",
 ["ダイバ単体の脳死逆張りはダメ","主に利確に使う","逆張りはローソク足を併用で確度UP"],"oscillator: ダイバは利確/補強")

# ── 追加: アノマリー/需給 ──
add("anomaly","月末に差し掛かり、価格が上に定着しつつある。","季節傾向は?","month_end_up_bias",
 ["月末は上がりやすい(上定着を見る)","金曜〜土日/月末の定着を勝負どころに"],"anomaly: 月末上げ")
add("anomaly","満月が近い(下落途中)。","アノマリー的に?","full_moon_bounce",
 ["満月=下落中の短期反発(プチリバ)","新月=高値・下落の傾向","補助的に使う"],"anomaly: 月相")
add("oi","価格が微上昇しOIが減少。","内訳は?","nanpin_short_cover_plus_long_tp",
 ["微上昇+OI減=ナンピンショート精算＋ロング利確でOIフラット","過熱の解消"],"OI公式: 微上昇+OI減")
add("liquidation","大きな清算(投げ)が出た直後。","狙いは?","reversal_rebound",
 ["大精算後のリバ取り(反発)を狙う","投げ切り→踏み上げ","背を直近安値外に"],"liquidation: 大精算後リバ")

# ── 追加: メタ/運用ルール ──
add("risk","スキャル口座とスイング/ガチホ口座を混同してポジション管理している。",
 "問題は?","separate_accounts",
 ["口座・レバ・時間軸を分ける","スキャル=少額ハイレバ短時間、スイング=低レバ長期"],"operation: 口座分離")
add("leverage","高確度の形だが、重要な経済指標(FOMC/CPI)発表の直前。",
 "レバと参加は?","reduce_or_wait_event",
 ["イベント直前はレバ下げ or 見送り","噂で買い事実で売る","イベント通過後に再評価"],"macro: イベント前はレバ抑制")
add("crash","暴落でショート利確のタイミング。","利確方針は?","partial_tp_trail",
 ["分割利確(半値で半分)","残りは建値ストップでトレール","欲張らず取れるところで"],"tp: 分割利確")
add("range","レンジ下限の買いで入ったが、十字足が崩れて下抜けしそう。",
 "どうする?","cut_on_condition_break",
 ["撤退条件(十字足崩れ)で機械的に損切り","ためらわない","レンジ下抜けは続落トリガー"],"range: 撤退条件")
add("risk","エントリー後、想定と逆に動き『間違いかも』と感じている。背は未達。",
 "どうする?","cut_early",
 ["間違いと感じたら早めに切る","ためらうと負ける","背到達を待たず判断することも"],"risk: 早期損切り")
add("cb_premium","Coinbase(現物)から販売所へ大口BTCが移動した。","示唆は?","sell_pressure",
 ["現物→販売所移動=売り示唆","大口の売り意図","上値警戒"],"onchain: 現物→販売所=売り")

import os
with open(OUT,"w",encoding="utf-8") as f:
    for it in Q:
        f.write(json.dumps(it,ensure_ascii=False)+"\n")
import collections
cc=collections.Counter(it["category"] for it in Q)
print(f"danjer_eval_set.jsonl: {len(Q)} 問")
for k,v in cc.most_common(): print(f"  {k}: {v}")
