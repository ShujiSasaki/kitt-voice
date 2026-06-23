#!/bin/bash
# launchd plist install / uninstall ヘルパー
#
# 使い方:
#   bash launchd/install_launchd.sh         # install + start
#   bash launchd/install_launchd.sh status  # status確認
#   bash launchd/install_launchd.sh stop    # stop
#   bash launchd/install_launchd.sh uninstall # 完全削除

set -e

LABEL="com.kitt-voice.ai_growth.runner"
PLIST_FILENAME="${LABEL}.plist"
SRC_PLIST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${PLIST_FILENAME}"
DST_PLIST="$HOME/Library/LaunchAgents/${PLIST_FILENAME}"

cmd="${1:-install}"

case "$cmd" in
    install)
        echo "[install] copying plist..."
        mkdir -p "$HOME/Library/LaunchAgents"
        cp "$SRC_PLIST" "$DST_PLIST"
        echo "[install] loading..."
        # 既存があれば unload してから load
        launchctl unload "$DST_PLIST" 2>/dev/null || true
        launchctl load "$DST_PLIST"
        echo "✅ installed: $DST_PLIST"
        echo ""
        echo "確認: launchctl list | grep ai_growth"
        launchctl list | grep ai_growth || echo "(まだ表示されない場合、 数秒後に確認)"
        ;;
    status)
        echo "[status] launchctl list:"
        launchctl list | grep ai_growth || echo "(未load or 未install)"
        echo ""
        echo "[log] 最新 10行:"
        tail -10 "$HOME/Library/Logs/ai_growth_runner.log" 2>/dev/null || echo "(log未生成)"
        ;;
    stop)
        echo "[stop] unloading..."
        launchctl unload "$DST_PLIST" 2>/dev/null || echo "(既にunload)"
        echo "✅ stopped"
        ;;
    uninstall)
        echo "[uninstall] unloading + removing..."
        launchctl unload "$DST_PLIST" 2>/dev/null || true
        rm -f "$DST_PLIST"
        echo "✅ uninstalled (plist removed from $DST_PLIST)"
        echo "ログは残ります: ~/Library/Logs/ai_growth_runner.log"
        ;;
    *)
        echo "Usage: $0 [install|status|stop|uninstall]"
        exit 1
        ;;
esac
