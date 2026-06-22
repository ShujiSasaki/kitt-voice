#!/usr/bin/env python3
# danjerクローンAI 種コーパス生成 (¥0 / API不使用)
# danjer_bottomup の materials(how+citation) と combination+stance を
# 細粒度サブ手法バケットに集計し、実引用つきで textbook_corpus.json を出力する。
import sqlite3, json, collections, re, sys

DB = "/Users/shuji/Desktop/kitt-voice/btc-trading/btc_trading_ai.db"

# 細粒度サブ手法バケット: key -> キーワード(any match で該当)。 章番号順。
TAXO = {
 # 第1章 テクニカル
 "1.1 水平線・サポレジ・節目": ["水平線","サポート","レジスタンス","レジサポ","節目","サポライン","レジライン","抵抗線","支持線","ライン①","ライン②"],
 "1.2 レンジ/ボックス": ["レンジ","ボックス","ヨコヨコ","横ばい","保ち合い","持ち合い","もみ合い","レンジ上限","レンジ下限"],
 "1.3 ブレイク/ブレイクアウト": ["ブレイク","上抜け","下抜け","抜けた","抜ける","ブレイクアウト","レンジブレイク"],
 "1.4 トレンドライン・チャネル": ["トレンドライン","チャネル","チャンネル","平行","ピンクライン","アウトライン","チャネル下限","チャネル上限"],
 "1.5 一目均衡表・雲": ["一目","雲","ねじれ","先行スパン","基準線","転換線","遅行","雲中","雲上","雲下"],
 "1.6 移動平均・グランビル": ["移動平均","SMA","EMA","MA200","200日","ゴールデンクロス","デッドクロス","グランビル","75日","100日","週足SMA","21MA","99SMA"],
 "1.7 サイクル理論": ["サイクル","56時間","6.5時間","レフトトランス","ライトトランス","タイムサイクル","周期","天底サイクル"],
 "1.8 フラクタル": ["フラクタル","似た","コピー","再現","リピート","相似","過去のパターン","同じ動き"],
 "1.9 エリオット波動": ["エリオット","波動","A波","B波","C波","推進波","修正波","1波","3波","5波","ウェッジ"],
 "1.10 チャートパターン(三尊/ダイア等)": ["三尊","逆三尊","ヘッドアンドショルダー","ダイアモンド","ダイヤモンド","アダムイブ","ネックライン","カップ","アセトラ","ディセトラ","上昇三角","下降三角","フラッグ","ペナント","三角持ち合い","三角"],
 "1.11 ローソク足": ["ローソク","陽線","陰線","大陽線","大陰線","坊主","上髭","上ヒゲ","下髭","下ヒゲ","包み足","はらみ","宵の明星","三川","コマ足","十字","ピンバー"],
 "1.12 フィボナッチ・半値": ["フィボ","フィボナッチ","半値","0.618","0.382","0.5","リトレース","戻し"],
 "1.13 窓・CME窓": ["窓","CME","窓埋め","ギャップ","上窓","下窓"],
 "1.14 ボラ・煮詰まり・IVバンド": ["煮詰","収束","ボラ","ボラティリティ","IVバンド","IV","バンド","BB","ボリンジャー","スクイーズ","拡大","縮小"],
 "1.15 オシレーター(MACD/RSI/ダイバ)": ["MACD","RSI","ストキャス","オシレ","ダイバージェンス","ダイバ","ヒドゥン","買われ過ぎ","売られ過ぎ"],
 # 第2章 ファンダ
 "2.1 マクロ(金利/FOMC/CPI/雇用)": ["FOMC","パウエル","CPI","雇用統計","金利","利上げ","利下げ","インフレ","FRB","ドル円","日銀","長期金利","マクロ","ISM","PCE"],
 "2.2 ETFフロー": ["ETF","IBIT","FBTC","GBTC","フィデリティ","現物ETF","ブラックロック","フロー","流入","流出"],
 "2.3 オンチェーン(残高/ハッシュ/クジラ)": ["オンチェーン","取引所残高","ハッシュレート","クジラ","ホエール","アドレス","OUTFLOW","INFLOW","出金","入金","Coinbase","保有"],
 "2.4 ステーブルコイン": ["テザー","USDT","USDC","ステーブル","デペグ","発行"],
 # 第3章 アノマリー
 "3.1 季節・暦・納税": ["アノマリー","季節","1月","暴落アノ","納税","月末","成人式","年末","年始","クリスマス","ハロウィン"],
 "3.2 春節": ["春節","旧正月","中国"],
 "3.3 曜日": ["曜日","金曜","土日","月曜","週末","日曜","週明け"],
 "3.4 月相(満月/新月)": ["満月","新月","月相","月の満ち欠け"],
 "3.5 イベント(SQ/OP期限/半減期)": ["SQ","オプション満期","半減期","ハービング","メジャーSQ","限月"],
 # 第4章 需給・レバ・資金管理
 "4.1 OI(建玉)": ["OI","建玉","オープンインタレスト","未決済"],
 "4.2 資金調達率(FR)": ["資金調達","FR","ファンディング","fr(-)","fr(+)","fr("],
 "4.3 清算・ロスカ狩り": ["清算","ロスカ","ロングが","ショートが","リクイ","liquidation","清算マップ","ストップ狩り","狩り"],
 "4.4 ポジ偏り・踏み上げ・ショートカバー": ["踏み上げ","ショートカバー","L/S","ロングショート","ポジション","偏り","ロング過多","ショート過多","ロスカット連鎖"],
 "4.5 レバ・ロット・利確損切り": ["レバ","ロット","利確","損切り","建値","リグ","ドテン","リスクリワード","RR","ナンピン","分割","スキャ","ガチホ","背"],
 # 第5章 板・フロー
 "5.1 板読み": ["板","買い板","売り板","岩盤","食う","食われ","ヒートマップ","厚い板","蓋","オーダーブック"],
 "5.2 オプション(ピン/MAXPAIN/PCR)": ["ピン","MAX PAIN","マックスペイン","PCR","プットコール","オプション","コール","プット","ガンマ"],
 "5.3 出来高・CVD": ["出来高","ボリューム","CVD","デルタ","大商い"],
 # danjer固有の武器 (3者合意 Q2: 独立タグ化)
 "5.4 VRVP(価格帯別出来高)": ["VRVP","VPVR","ボリュームプロファイル","出来高プロファイル","価格帯別出来高","POC","バリューエリア","ボリュームバンド"],
 "5.5 Coinbase Premium(現物先行)": ["Coinbase Premium","Coinbase Premier","コインベースプレミア","CBプレミア","現物プレミア","プレミアム指数"],
}

def g(d,k):
    v=d.get(k); return (v if isinstance(v,str) else "").strip()

def main():
    db=sqlite3.connect(DB); c=db.cursor()
    buckets={k:[] for k in TAXO}
    combos=collections.defaultdict(list)  # regime -> [{combo,stance,date,topics}]
    rows=c.execute("SELECT tweet_id,posted_at_utc,regime,extract_json FROM danjer_bottomup WHERE extracted=1").fetchall()
    for tid,dt,rg,js in rows:
        try: j=json.loads(js)
        except: continue
        if not isinstance(j,dict): continue
        day=(dt or "")[:10]
        topics=set()
        for m in j.get("materials",[]) or []:
            if not isinstance(m,dict): continue
            how=g(m,"how"); cite=g(m,"citation"); what=g(m,"what")
            blob=" ".join([what,how,cite])
            for key,kws in TAXO.items():
                if any(kw in blob for kw in kws):
                    topics.add(key)
                    if cite and len(cite)>=15:
                        buckets[key].append({"how":how,"cite":cite,"date":day,"rg":rg,"tid":tid})
        combo=g(j,"combination"); stance=g(j,"stance")
        if combo and len(combo)>=40:
            combos[rg or "?"].append({"combo":combo,"stance":stance,"date":day,"topics":sorted(topics),"tid":tid})
    # 各バケット: 重複除去(citeの先頭40字)+品質順で上位を残す。
    # danjer本人の生テキスト(画像読取でない)を強く優先 = クローンが学ぶべき"本人の言葉"。
    def clean(s):
        s=re.sub(r"\s+"," ",s).strip()
        return s
    # AI画像描写の言い回し(=danjerの肉声でない)
    READOUT=["が表示されて","描画されて","描かれて","ローソク足は","チャートには","チャート上に",
             "価格スケール","現在の売値","現在の買値","現在価格を示す","と表示され","図が示され",
             "画像読取","画像:","スケールは右","軸は","の範囲。","ローソク足で"]
    # danjerの教える肉声マーカー
    VOICE=["＠","⇒","→","1️⃣","2️⃣","3️⃣","背に","だぬ","かぬ","やぬ","ぬ。","ぬ！","ですぬ","w",
           "想定","狙","利確","損切","ロング","ショート","買い","売り","ここ","この後","と思","かな","です。","ます。"]
    def is_text(cite):
        ro=sum(cite.count(x) for x in READOUT)
        vo=sum(1 for x in VOICE if x in cite)
        # 肉声マーカーが画像描写より優勢なら本人テキスト扱い
        return vo>=2 and ro<=1
    # 3者合意 Q4: 出典ラベル 本人 / AI画像 (引用文の由来)
    def src_label(cite):
        if "画像読取" in cite or "画像:" in cite: return "AI画像"
        ro=sum(cite.count(x) for x in READOUT)
        vo=sum(1 for x in VOICE if x in cite)
        return "AI画像" if ro>vo else "本人"
    def qual(e):
        cite=e["cite"]; cl=len(cite); hl=len(e["how"])
        clen = cl if 40<=cl<=260 else (150 if cl>260 else cl*0.4)
        ro=sum(cite.count(x) for x in READOUT)
        vo=sum(1 for x in VOICE if x in cite)
        return clen + min(hl,150)*0.3 + vo*60 - ro*90
    out={"meta":{"posts":len(rows)},"buckets":{},"combos":{}}
    for key,lst in buckets.items():
        seen=set(); uniq=[]
        for e in sorted(lst,key=qual,reverse=True):
            sig=re.sub(r"\s+","",e["cite"])[:40]
            if sig in seen: continue
            seen.add(sig)
            uniq.append({"how":clean(e["how"]),"cite":clean(e["cite"]),
                         "date":e["date"],"rg":e["rg"],"txt":is_text(e["cite"]),
                         "src":src_label(e["cite"])})
        out["buckets"][key]={"n":len(lst),"uniq":len(uniq),"ex":uniq[:18]}
    # combos: regime毎に重複除去+多topic優先で上位
    for rg,lst in combos.items():
        seen=set(); uniq=[]
        for e in sorted(lst,key=lambda x:(len(x["topics"]),len(x["combo"])),reverse=True):
            sig=re.sub(r"\s+","",e["combo"])[:50]
            if sig in seen: continue
            seen.add(sig)
            uniq.append({"combo":clean(e["combo"]),"stance":clean(e["stance"]),
                         "date":e["date"],"topics":e["topics"]})
        out["combos"][rg]={"n":len(lst),"ex":uniq[:120]}
    json.dump(out,open("/tmp/textbook_corpus.json","w"),ensure_ascii=False)
    print("=== bucket counts (n hits / unique cites) ===")
    for k in TAXO:
        b=out["buckets"][k]; print(f"{k:42s} n={b['n']:5d} uniq={b['uniq']:5d}")
    print("=== combos by regime ===")
    for rg,d in out["combos"].items(): print(f"{rg:8s} n={d['n']}")
    print("WROTE /tmp/textbook_corpus.json")

main()
