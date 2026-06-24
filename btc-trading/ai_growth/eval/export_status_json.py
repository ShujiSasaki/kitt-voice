"""育成状況をJSONで出力 (PWA統合用)

3者合意 (2026-06-24): iPhone PWA から育成状況見れるように。
meeting_system server.py が読む `/data/ai_growth_status.json` を定期生成。

実行:
    python3 eval/export_status_json.py
    → /Users/shuji/Desktop/kitt-voice/meeting_system/data/ai_growth_status.json 生成

定期実行 (launchd plist) で5分ごとに更新。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "eval"))

from metrics import all_metrics, load_signals, _load_config_value


OUTPUT_PATH = Path("/Users/shuji/Desktop/kitt-voice/meeting_system/data/ai_growth_status.json")


def export():
    metrics = all_metrics()
    mv = metrics['model_version']
    signals = load_signals(mv)

    # 最新10件の信号 (簡易表示用)
    recent = []
    for s in signals[-10:]:
        sig = s.get('signal', {})
        recent.append({
            'ts': s.get('ts', ''),
            'btc_price': s.get('btc_price', 0),
            'regime': s.get('regime'),
            'signal': sig.get('signal'),
            'stance': sig.get('stance', ''),
            'force_stopped': sig.get('force_stopped', False),
            'response_excerpt': (s.get('response', '') or '')[:120],
        })

    target_min = int(_load_config_value('cycle_target_count_min', '50'))
    target_max = int(_load_config_value('cycle_target_count_max', '100'))

    status = {
        'updated_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'model_version': mv,
        'cycle': {
            'total': metrics['defense'].get('total', 0),
            'target_min': target_min,
            'target_max': target_max,
            'labeled': metrics['defense'].get('labeled', 0),
            'unlabeled': metrics['defense'].get('unlabeled', 0),
            'progress_pct': min(100, int(metrics['defense'].get('total', 0) / target_max * 100)) if target_max > 0 else 0,
        },
        'defense': metrics['defense'],
        'offense': metrics['offense'],
        'caution': metrics['caution'],
        'recent_signals': recent,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f"✅ exported to {OUTPUT_PATH}")
    return status


if __name__ == "__main__":
    s = export()
    print(f"  cycle: {s['cycle']['total']}/{s['cycle']['target_max']} ({s['cycle']['progress_pct']}%)")
    print(f"  defense: {'✅ PASS' if s['defense'].get('defense_passed') else '❌ FAIL'}")
    print(f"  caution warnings: {len(s['caution'].get('warnings', []))}")
