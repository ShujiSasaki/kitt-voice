#!/usr/bin/env python3
# Q3 別冊補強 生成器 (¥0): crash/range/rally の局面別教科書
# 出力: danjer_textbook_regimes.md + .html (attachments)
# 全引用は danjer_bottomup 由来(本人テキスト優先)。ルールは AI推測(整理)。
import json, re, html

S=json.load(open("/tmp/regime_src.json"))
SHORT={"1.1":"水平線","1.2":"レンジ","1.3":"ブレイク","1.4":"チャネル","1.5":"雲","1.6":"MA",
 "1.7":"サイクル","1.8":"フラクタル","1.9":"エリオット","1.10":"パターン","1.11":"ローソク",
 "1.12":"フィボ","1.13":"窓","1.14":"煮詰まり","1.15":"オシレ","4.1":"OI","4.2":"FR",
 "4.3":"清算","4.4":"踏み上げ","4.5":"レバ管理","5.1":"板","5.2":"オプション","5.4":"VRVP"}
def sn(t): return SHORT.get(t.split()[0],t.split()[0])
def trim(s,n=150): s=s.strip(); return s if len(s)<=n else s[:n]+"…"

# 局面別 curated 解説 (全て /tmp/regime_src.json の実データに基づく)
REGIME={
"crash":{"jp":"暴落","prose":[
 "**特徴**: 一方向の急落。主役は OI と 清算。『ロングが高値で捕まる→ロスカで下落加速』。出来高は急落時に激増し、次の戻り高値では細る(=戻りが弱い)。",
 "**支配手法(実データ上位)**: 踏み上げ/ショートカバー > ローソク足 > レンジ > レバ管理 > 水平線 > 清算。暴落でも『踏み上げ(ショートカバー)』を最重視=投げの後の一時的反発を読む。",
 "**立ち回り**: 基本は戻りを売る(ショートが行動の最多)。精算マップでロスカ位置を可視化し『どこで焼かれるか』を把握。低レバなら急落水準を狙え、想定外に突破されてもロールリバーサルで逃げ道を作る。『精算で飛び売り→焼かれて損切り→もう一段上げ』の連鎖を想定。",
 "**底のサイン(天邪鬼)**: 暴落後はPCRが激増(弱気増)→『その逆をいって上がる』=底になりやすい。だから暴落の底では逆張りで買い場を探す。ただし低レバ+背必須、ナンピンは損切り前提。",
 "**⚠ クローンへの確定ルール(Shuji確定仕様・3者検収反映)**: 暴落=sell(売り)の好機として攻めてよい。ただしリスク管理を同時に満たすこと=損切り(stop)同時発注必須/明確な背・無効化ライン/十分な清算距離/ロット上限。レバは低レバ固定ではなく確度に応じた動的管理(条件が揃えば高レバも条件付き許可)。急落は滑るためストップのみに依存しない(清算距離・ロット上限で多重防御)。損切りを置けない/背がない/清算距離が近い/根拠が弱い/感情的追いかけ → lower_leverage/wait/no_trade。(旧『ノーポジ・逃げ優先/低レバ固定』は撤回済)",
]},
"range":{"jp":"レンジ","prose":[
 "**特徴**: 上・中・下3ゾーンの往復。『板』でレンジが作られる(売り板がぎっしり→成行きが無いと突破できない)。OIの両建て増減が転換の先行。",
 "**支配手法(実データ上位)**: 踏み上げ > 水平線 > ローソク足 > レバ管理 > レンジ > OI > サイクル。",
 "**立ち回り**: 上限売り/下限買いの両建てスキャルが中心(ショートと利確が多い)。撤退条件を先に決める(『十字足にならなければ撤退』)。OIの『諦め』を待つ=ショートが諦め始め+ロング利確で大精算→転換。",
 "**命綱**: レンジは損切りを機械的に(損切り行動が多い)。期待値の高いパターンだけ狙う(『期待値の高い形を狙いたい』)。板の厚い側・OIの諦めが出るまで本玉は入れない。",
]},
"rally":{"jp":"急騰","prose":[
 "**特徴**: 急上昇。だがdanjerはむしろ『売り場』を探す(天邪鬼)。実データでも行動はショートが最多で、順張り追撃より天井探しが多い。",
 "**支配手法(実データ上位)**: 踏み上げ > レバ管理 > 水平線 > ブレイク > レンジ > ローソク足 > パターン > サイクル。",
 "**天井のサイン**: 出来高ダイバージェンス(『もう行けーで投げ買う』時)=天井になりやすい。現物/FX乖離20〜30%で警戒。『簡単に儲かる』『初心者の爆益をXで見る』=過熱センチメント警戒。Coinbaseから販売所へBTC移動=売り示唆。",
 "**立ち回り**: 順張りで追わず、天井兆候(出来高ダイバ/乖離/過熱)を待って戻り売り。取れるところで利確。踏み上げ(ショートカバー)主導の上げはOI増を伴わない→続かないと判断。週初め買い→週末利確のファンド資金フローも意識。",
]},
}
ACT_ORDER=["ノーポジ・様子見・見送り","逃げ・撤退・損切り","ショート・売り","買い場・拾う・打診","利確・分割"]

md=[]
md.append("# danjer 手法 教科書 別冊 — 局面別(暴落・レンジ・急騰)")
md.append("")
md.append("> 3者合意Q3の補強。本編はトレンド(平常)局面が81%を占めるため、薄い『暴落/レンジ/急騰』をdanjerの実挙動から別冊化。")
md.append("> 出典: danjer_bottomup の該当局面投稿。**[特徴/支配手法/立ち回り]はAI推測(整理=model_inference)**、**引用は本人テキスト(danjer_text)優先**。")
md.append("> ★最重要メッセージ: 暴落はノーポジ・逃げ・ショート可否が命綱。クローンは下記『安全弁』を本編ルールより優先する。")
md.append("")
for rg in ["crash","range","rally"]:
    d=S[rg]; R=REGIME[rg]
    md.append("---")
    md.append(f"## {R['jp']} (該当 {d['n_posts']}投稿)")
    for p in R["prose"]: md.append(f"- {p}")
    # 行動別 実引用
    md.append("")
    md.append("**▸ 行動別の実例**(〔本人〕=danjer原文)")
    for act in ACT_ORDER:
        a=d["actions"].get(act)
        if not a or not a["ex"]: continue
        md.append(f"- **{act}** (言及{a['n']}件)")
        for e in a["ex"][:3]:
            md.append(f"    - 〔本人〕〈{e['date']}〉「{trim(e['cite'])}」")
    # 実判断連鎖
    md.append("")
    md.append("**▸ この局面の判断連鎖(AI推測・1投稿=1件)**")
    for e in d["combos"][:6]:
        md.append(f"- 〈{e['date']}〉{trim(e['combo'],200)}")
        if e.get("stance"): md.append(f"    └ スタンス: {trim(e['stance'],110)}")
    md.append("")

md.append("---")
md.append("## クローン実装メモ(局面ハンドリング)")
for line in [
 "局面判定 → 暴落: sellの好機として攻める。損切同時発注+背+清算距離+ロット上限が必須、レバは確度で動的管理(条件付き高レバ可)。戻りを売る/底はPCR激増→逆張り買い(背+stop必須)。条件未達→lower_leverage/wait/no_trade。",
 "レンジ: 上限売り/下限買いの小ロット往復。撤退条件(十字足崩れ等)を先に置く。OIの諦め・板の厚い側が出るまで本玉なし。",
 "急騰: 順張り追撃しない。出来高ダイバ/乖離/過熱センチメントで天井探し→戻り売り。OI増を伴わない上げ(ショートカバー)は続かない。",
 "全局面共通: 単一指標で判断しない。需給(OI/FR/清算)を必ず重ね、背とリスクリワード1:2、条件未達なら見送り。",
]:
    md.append(f"- {line}")

open("danjer_textbook_regimes.md","w",encoding="utf-8").write("\n".join(md))
print("WROTE danjer_textbook_regimes.md lines=",len(md))

# HTML
def inl(s):
    s=html.escape(s); return re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
out=[];il=False
for ln in md:
    if ln.startswith("    └") or ln.startswith("    - "):
        out.append(f'<div class=sub>{inl(ln.strip())}</div>'); continue
    if ln.strip()=="---": out.append("<hr>"); continue
    if ln.startswith("## "):
        if il:out.append("</ul>");il=False
        out.append(f"<h2>{inl(ln[3:])}</h2>");continue
    if ln.startswith("# "): out.append(f"<h1>{inl(ln[2:])}</h1>");continue
    if ln.startswith("> "): out.append(f"<blockquote>{inl(ln[2:])}</blockquote>");continue
    if ln.startswith("- "):
        if not il:out.append("<ul>");il=True
        out.append(f"<li>{inl(ln[2:])}</li>");continue
    if il:out.append("</ul>");il=False
    if ln.strip(): out.append(f"<p>{inl(ln)}</p>")
if il:out.append("</ul>")
doc=f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>danjer教科書 別冊 局面別</title><style>
body{{font-family:-apple-system,sans-serif;margin:0;padding:14px;background:#0d1117;color:#e6edf3;font-size:15px;line-height:1.75;max-width:860px}}
h1{{font-size:19px;color:#fff;border-bottom:2px solid #30363d;padding-bottom:6px}}
h2{{font-size:18px;color:#ff7b72;margin-top:24px;border-left:4px solid #da3633;padding-left:8px}}
blockquote{{background:#161b22;border-left:3px solid #30363d;margin:6px 0;padding:8px 12px;color:#9bd;font-size:12.5px}}
ul{{margin:4px 0 10px;padding-left:20px}} li{{margin:5px 0}} b{{color:#ffd87a}}
.sub{{color:#7ee787;font-size:13px;margin:2px 0 4px 22px}}
hr{{border:none;border-top:1px solid #30363d;margin:16px 0}} p{{margin:6px 0}}</style>
{chr(10).join(out)}"""
open("/Users/shuji/Desktop/kitt-voice/meeting_system/data/attachments/btc_auto_trade/danjer_textbook_regimes.html","w",encoding="utf-8").write(doc)
print("WROTE danjer_textbook_regimes.html KB=",len(doc)//1024)
