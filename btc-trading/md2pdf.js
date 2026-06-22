#!/usr/bin/env node
const fs = require('fs');
const { marked } = require('marked');

const inputFile = process.argv[2];
const title = process.argv[3] || 'BTC Trading Manual';

const md = fs.readFileSync(inputFile, 'utf8');
const htmlBody = marked.parse(md);

const html = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>${title}</title>
<style>
  body { font-family: 'Hiragino Kaku Gothic ProN', 'Yu Gothic', sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.8; color: #333; font-size: 14px; }
  h1 { font-size: 24px; border-bottom: 3px solid #333; padding-bottom: 10px; page-break-before: always; }
  h1:first-of-type { page-break-before: avoid; }
  h2 { font-size: 20px; border-bottom: 2px solid #666; padding-bottom: 8px; margin-top: 40px; }
  h3 { font-size: 17px; margin-top: 30px; }
  h4 { font-size: 15px; margin-top: 20px; }
  hr { margin: 40px 0; border: none; border-top: 1px solid #ccc; }
  ul, ol { padding-left: 24px; }
  li { margin: 4px 0; }
  table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 12px; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }
  th { background: #f5f5f5; font-weight: bold; }
  code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
  pre { background: #f4f4f4; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 12px; }
  blockquote { border-left: 4px solid #ddd; margin: 16px 0; padding: 8px 16px; color: #555; background: #fafafa; }
  strong { color: #111; }
  a { color: #0366d6; }
  @media print {
    body { margin: 15px; font-size: 11px; line-height: 1.6; }
    h1 { font-size: 18px; }
    h2 { font-size: 15px; }
    h3 { font-size: 13px; }
    table { font-size: 10px; }
    pre { font-size: 10px; }
  }
</style>
</head>
<body>
${htmlBody}
</body>
</html>`;

const outHtml = inputFile.replace('.md', '.html');
fs.writeFileSync(outHtml, html);
console.log('HTML:', outHtml, html.length, 'chars');
