"""v6 LoRA推論 (CPU、 Mac local)

3者合意 (2026-06-24) のv6 adapter を使って danjer風判定を生成。
- ベース: Qwen2.5-1.5B-Instruct
- LoRA: /tmp/kaggle_v6_output/danjer_lora_planA_adapter
- 推論: CPU (Mac local)、 20-60秒/件想定
- ハーネス v2 設定 (Q1-Q6で検証済): pad_token分離、 STOP_IDS=im_end+eos、 inference_mode

このファイルは「ローカルファイル読み書きのみ」、 注文関連処理は一切含まない。
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Optional

HERE = Path(__file__).parent

# config を読み込み (yaml parse 依存避け、 シンプル grep)
def _load_config_value(key: str) -> Optional[str]:
    config_path = HERE / "config.yml"
    if not config_path.exists():
        return None
    for line in config_path.read_text(encoding='utf-8').splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean.startswith(f'{key}:'):
            return line_clean.split(':', 1)[1].strip().strip('"\'')
    return None


# システムプロンプト (既存danjerデータと同じ、 元データ system: コピー)
SYS = (
    "あなたはBTCトレーダー「danjer」の思考を学習したクローンAI。"
    "danjerの手法(水平線/レンジ・ブレイク/トレンドライン/一目雲/移動平均・"
    "グランビル/サイクル理論/フラクタル/エリオット/チャートパターン/ローソク足/"
    "フィボ半値/CME窓/煮詰まり・IVバンド/オシレーター、需給=OI公式・FR・清算・"
    "踏み上げ、アノマリー、板読み・オプション・出来高・VRVP・Coinbase Premium)"
    "を複数組み合わせて相場を読む。単一指標で判断せず、必ず需給(OI/FR/清算)を"
    "重ね、最後に背(損切り)とリスクリワード1:2以上、条件未達なら見送りを"
    "選ぶ。"
)


class V6Inference:
    """v6 LoRA推論ラッパー (lazy load、 1度ロードしたら使い回し)"""

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.stop_ids = None
        self.pad_id = None
        self.dry_run = False

    def _load(self):
        if self.model is not None:
            return  # 既にロード済

        adapter_path = _load_config_value('model_adapter_local')
        base_model = _load_config_value('base_model') or 'Qwen/Qwen2.5-1.5B-Instruct'

        if not adapter_path or not Path(adapter_path).exists():
            print(f"⚠️  v6 LoRA adapter not found at {adapter_path}")
            print("    dry_run モードで動作 (応答は固定文字列)")
            self.dry_run = True
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            import torch
        except ImportError as e:
            print(f"⚠️  推論ライブラリ不足 ({e})、 dry_run モード")
            self.dry_run = True
            return

        print(f"[inference] base={base_model} adapter={adapter_path} loading...")
        self.tokenizer = AutoTokenizer.from_pretrained(base_model)
        if self.tokenizer.pad_token is None or self.tokenizer.pad_token == self.tokenizer.eos_token:
            self.tokenizer.add_special_tokens({'pad_token': '<|endoftext|>'})

        # CPU推論 (Mac local、 GPU無し前提)
        base = AutoModelForCausalLM.from_pretrained(
            base_model, torch_dtype=torch.float32
        )
        if base.get_input_embeddings().num_embeddings < len(self.tokenizer):
            base.resize_token_embeddings(len(self.tokenizer))
        base.config.pad_token_id = self.tokenizer.pad_token_id

        self.model = PeftModel.from_pretrained(base, adapter_path)
        self.model.eval()
        self.model.config.use_cache = True

        # ハーネス設定 (v2、 v6で検証済)
        im_end_id = self.tokenizer.convert_tokens_to_ids('<|im_end|>')
        eos_id = self.tokenizer.eos_token_id
        self.pad_id = self.tokenizer.pad_token_id
        self.stop_ids = list({im_end_id, eos_id})

        print(f"[inference] loaded. stop_ids={self.stop_ids} pad_id={self.pad_id}")

    def predict(
        self,
        regime: str,
        materials: list[str],
        date_str: str = "2026-06-24",
    ) -> str:
        """danjer風判定生成

        入力 format (既存学習データと同じ):
        【局面】<regime>
        【日付】<date>
        【今わたし(danjer)が見ている材料】
        - <m1>
        - <m2>

        この状況をどう読む?
        """
        self._load()

        # user prompt組み立て
        bullets = '\n'.join(f'- {m}' for m in materials)
        user = (
            f"【局面】{regime}\n"
            f"【日付】{date_str}\n"
            f"【今わたし(danjer)が見ている材料】\n"
            f"{bullets}\n\n"
            f"この状況をどう読む?"
        )

        if self.dry_run:
            return (
                f"[dry_run] regime={regime}、 materials不足のため判断保留。\n\n"
                f"【スタンス】様子見"
            )

        import torch

        messages = [
            {'role': 'system', 'content': SYS},
            {'role': 'user', 'content': user},
        ]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        ids = self.tokenizer(prompt, return_tensors='pt').to(self.model.device)

        with torch.inference_mode():
            out = self.model.generate(
                **ids,
                max_new_tokens=1024,
                do_sample=False,
                repetition_penalty=1.0,
                eos_token_id=self.stop_ids,
                pad_token_id=self.pad_id,
            )
        response = self.tokenizer.decode(
            out[0][ids['input_ids'].shape[1]:],
            skip_special_tokens=True,
        ).strip()
        return response


# モジュールレベル singleton (1度ロードして使い回し)
_inference = None


def predict(regime: str, materials: list[str], date_str: str = "2026-06-24") -> str:
    """便利関数 (1行で推論)"""
    global _inference
    if _inference is None:
        _inference = V6Inference()
    return _inference.predict(regime, materials, date_str)


if __name__ == "__main__":
    # 動作確認
    print("=== inference.py 動作確認 ===")
    response = predict(
        regime='trend',
        materials=['ブレイクアウト', '押し目浅い'],
    )
    print(f"応答: {response}")
