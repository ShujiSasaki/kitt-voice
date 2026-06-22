from openai import OpenAI
import sys
import argparse

client = OpenAI()

DEFAULT_INSTRUCTIONS = """
あなたは Shuji の技術レビュー担当 兼 共同アーキテクト。
専門領域:
- BTC/暗号通貨アルゴリズム取引(強化学習・模倣学習・LLMエージェント・特徴量設計・バックテスト)
- 市場マイクロ構造・リスク管理・レジーム検知
- X(Twitter)データ取得(GraphQL/cursor/pagination/rate limit/Playwright/SQLite)
- 大規模データパイプライン・SQLite/BigQuery
- AIエージェント実装(LLM tool use, RAG, multimodal)
スタイル:
- 楽観論で流さない。具体的に詰める。最新2025年技術前提
- 代替案と反証を必ず添える
- 合意ありきで進めず、Claudeの仮説には率直に異論をぶつける
- 日本語で簡潔に。必要なら長文OK
"""

parser = argparse.ArgumentParser()
parser.add_argument("--role", default=None, help="System instructions override (default: BTC algo trading reviewer)")
parser.add_argument("--model", default="gpt-5.5")
args = parser.parse_args()

instructions = args.role if args.role else DEFAULT_INSTRUCTIONS
prompt = sys.stdin.read()

response = client.responses.create(
    model=args.model,
    instructions=instructions,
    input=prompt,
)

print(response.output_text)
