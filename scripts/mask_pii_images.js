#!/usr/bin/env node
/**
 * GCS画像のPII (個人情報) マスク処理
 *
 * Gemini Vision APIで画像内の個人情報を検出し、黒塗りマスクを適用。
 *
 * マスク対象:
 * - 集合住宅の部屋番号 (建物名は残す)
 * - 個人宅の住所末尾 (号)
 * - 顧客名
 *
 * 使い方:
 *   GEMINI_API_KEY=xxx node scripts/mask_pii_images.js
 */

const { Storage } = require('@google-cloud/storage');
const sharp = require('sharp');

const BUCKET = 'kitt-screenshots-0549297663';
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_MODEL = 'gemini-2.5-flash';
const PROJECT_ID = 'gen-lang-client-0549297663';

const storage = new Storage({ projectId: PROJECT_ID });
const bucket = storage.bucket(BUCKET);

async function main() {
  if (!GEMINI_API_KEY) {
    console.error('GEMINI_API_KEY environment variable required');
    process.exit(1);
  }

  // 全画像を取得
  const [files] = await bucket.getFiles();
  console.log(`Total images: ${files.length}`);

  let processed = 0;
  let masked = 0;
  let errors = 0;

  for (const file of files) {
    try {
      const result = await processImage(file);
      processed++;
      if (result) masked++;
      if (processed % 50 === 0) {
        console.log(`Progress: ${processed}/${files.length} (masked: ${masked}, errors: ${errors})`);
      }
    } catch (e) {
      errors++;
      console.warn(`Error processing ${file.name}: ${e.message}`);
    }

    // Rate limiting (Gemini API)
    await sleep(500);
  }

  console.log(`\nDone: ${processed} processed, ${masked} masked, ${errors} errors`);
}

async function processImage(file) {
  // 画像をダウンロード
  const [buffer] = await file.download();
  const base64 = buffer.toString('base64');
  const mimeType = file.name.endsWith('.png') ? 'image/png' : 'image/jpeg';

  // Gemini VisionでPII領域を検出
  const piiRegions = await detectPII(base64, mimeType);

  if (!piiRegions || piiRegions.length === 0) {
    return false; // PIIなし
  }

  console.log(`  ${file.name}: ${piiRegions.length} PII regions found`);

  // sharpで黒塗りマスクを適用
  const metadata = await sharp(buffer).metadata();
  const width = metadata.width;
  const height = metadata.height;

  // SVGオーバーレイで黒塗り
  const rects = piiRegions.map(r => {
    const x = Math.round(r.x * width);
    const y = Math.round(r.y * height);
    const w = Math.round(r.w * width);
    const h = Math.round(r.h * height);
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="black"/>`;
  }).join('\n');

  const overlay = Buffer.from(
    `<svg width="${width}" height="${height}">${rects}</svg>`
  );

  const maskedBuffer = await sharp(buffer)
    .composite([{ input: overlay, top: 0, left: 0 }])
    .toBuffer();

  // マスク済み画像で上書き
  await file.save(maskedBuffer, { contentType: mimeType });

  return true;
}

async function detectPII(base64, mimeType) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;

  const body = {
    contents: [{
      parts: [
        {
          text: `この配達アプリのスクリーンショットに、以下の個人情報が含まれていますか？
- 顧客の名前（漢字・カタカナ・ひらがな）
- 集合住宅の部屋番号（101号室、302号等）
- 個人宅の住所の最後の部分（番地の末尾、号）

建物名・マンション名・店名・地名は個人情報ではありません。無視してください。

個人情報が見つかった場合、それぞれの位置を画像の相対座標(0.0〜1.0)で返してください。
見つからなければ空配列を返してください。

JSON形式で返してください:
[{"type": "name"|"room"|"address", "text": "検出テキスト", "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}]`
        },
        {
          inlineData: { mimeType, data: base64 }
        }
      ]
    }],
    generationConfig: {
      responseMimeType: 'application/json',
      maxOutputTokens: 1024,
      thinkingConfig: { thinkingBudget: 0 }
    }
  };

  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  if (!resp.ok) {
    throw new Error(`Gemini API error: ${resp.status}`);
  }

  const data = await resp.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;

  if (!text) return [];

  try {
    const regions = JSON.parse(text);
    return Array.isArray(regions) ? regions.filter(r =>
      r.x != null && r.y != null && r.w != null && r.h != null &&
      r.w > 0 && r.h > 0
    ) : [];
  } catch {
    return [];
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

main().catch(console.error);
