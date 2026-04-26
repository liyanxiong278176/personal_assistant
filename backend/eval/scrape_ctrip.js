/**
 * Scrape all Ctrip Q&A pages using Playwright.
 * Run: node eval/scrape_ctrip.js
 *
 * This creates individual JSON files in eval/scraped_pages/ for each page,
 * then a merged raw_queries.json with deduplication.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = path.join(__dirname, 'scraped_pages');
const RAW_OUTPUT = path.join(__dirname, 'raw_queries.json');

const URLS = [
  ["https://you.ctrip.com/asks", "global_hot_p1"],
  ["https://you.ctrip.com/asks/p2", "global_hot_p2"],
  ["https://you.ctrip.com/asks/p3", "global_hot_p3"],
  ["https://you.ctrip.com/asks/p4", "global_hot_p4"],
  ["https://you.ctrip.com/asks/p5", "global_hot_p5"],
  ["https://you.ctrip.com/asks/p6", "global_hot_p6"],
  ["https://you.ctrip.com/asks/p7", "global_hot_p7"],
  ["https://you.ctrip.com/asks/beijing1", "beijing_p1"],
  ["https://you.ctrip.com/asks/beijing1/p2", "beijing_p2"],
  ["https://you.ctrip.com/asks/beijing1/p3", "beijing_p3"],
  ["https://you.ctrip.com/asks/shanghai2", "shanghai_p1"],
  ["https://you.ctrip.com/asks/shanghai2/p2", "shanghai_p2"],
  ["https://you.ctrip.com/asks/shanghai2/p3", "shanghai_p3"],
  ["https://you.ctrip.com/asks/chengdu104", "chengdu_p1"],
  ["https://you.ctrip.com/asks/chengdu104/p2", "chengdu_p2"],
  ["https://you.ctrip.com/asks/t105341", "hotel_tag_p1"],
  ["https://you.ctrip.com/asks/t105341/p2", "hotel_tag_p2"],
  ["https://you.ctrip.com/asks/k1", "latest_p1"],
  ["https://you.ctrip.com/asks/k1/p2", "latest_p2"],
  ["https://you.ctrip.com/asks/k1/p3", "latest_p3"],
  ["https://you.ctrip.com/asks/hangzhou14", "hangzhou_p1"],
  ["https://you.ctrip.com/asks/hangzhou14/p2", "hangzhou_p2"],
];

const EXTRACT_JS = () => {
  const questions = [];
  const links = document.querySelectorAll('a[href*="/asks/detail"]');
  links.forEach(link => {
    const h2 = link.querySelector('h2');
    const answerP = link.querySelector('p');
    if (h2) {
      questions.push({
        query: h2.textContent.trim(),
        answers: answerP ? parseInt(answerP.textContent) || 0 : 0,
        url: link.href
      });
    }
  });
  return questions;
};

const SKIP_WORDS = [
  "客服", "投诉", "电话", "购物车", "订单", "退款", "发货",
  "携程", "APP", "登录", "注册", "账号", "密码", "会员"
];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  // Ensure output dir exists
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  携程问答爬虫 (保守策略)`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  目标页面: ${URLS.length}`);
  console.log(`  预计获取: ~${URLS.length * 20} 条`);
  console.log(`  延迟: 3秒/页\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  let totalExtracted = 0;

  for (let i = 0; i < URLS.length; i++) {
    const [url, name] = URLS[i];
    process.stdout.write(`  [${i+1}/${URLS.length}] ${name}... `);

    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForTimeout(2000); // Wait for JS rendering

      const questions = await page.evaluate(EXTRACT_JS);

      // Save per-page file
      const pageData = {
        source: name,
        scraped_at: new Date().toISOString(),
        count: questions.length,
        questions: questions,
      };
      fs.writeFileSync(
        path.join(OUTPUT_DIR, `${name}.json`),
        JSON.stringify(pageData, null, 2),
        'utf-8'
      );

      totalExtracted += questions.length;
      console.log(`${questions.length} questions`);
    } catch (err) {
      console.log(`ERROR: ${err.message}`);
    }

    // Delay between pages (3 seconds)
    if (i < URLS.length - 1) {
      await sleep(3000);
    }
  }

  await browser.close();

  // Merge and deduplicate
  console.log(`\n  Total extracted: ${totalExtracted}`);
  console.log(`\n  Merging and deduplicating...`);

  const allQuestions = [];
  const seenQueries = new Set();

  const files = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.json')).sort();
  for (const file of files) {
    const data = JSON.parse(fs.readFileSync(path.join(OUTPUT_DIR, file), 'utf-8'));
    for (const q of data.questions || []) {
      // Clean hotel name prefixes: #xxx酒店#
      let cleanQuery = q.query.replace(/#.*?#/g, '').trim();
      if (!cleanQuery || cleanQuery.length < 3) continue;

      // Skip non-travel queries
      if (SKIP_WORDS.some(w => q.query.includes(w))) continue;

      const key = cleanQuery.toLowerCase();
      if (!seenQueries.has(key)) {
        seenQueries.add(key);
        allQuestions.push({
          query: cleanQuery,
          answers: q.answers,
          url: q.url,
          source: data.source,
        });
      }
    }
  }

  const output = {
    source: "ctrip_asks",
    scraped_at: new Date().toISOString(),
    total_pages: files.length,
    total_queries: allQuestions.length,
    queries: allQuestions,
  };

  fs.writeFileSync(RAW_OUTPUT, JSON.stringify(output, null, 2), 'utf-8');

  // Distribution
  const sourceCounts = {};
  for (const q of allQuestions) {
    sourceCounts[q.source] = (sourceCounts[q.source] || 0) + 1;
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  爬取结果`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  去重后query: ${allQuestions.length}`);
  console.log(`\n  按来源分布:`);
  for (const [source, count] of Object.entries(sourceCounts).sort((a,b) => b[1]-a[1])) {
    console.log(`    ${source}: ${count}`);
  }
  console.log(`\n  示例:`);
  for (const q of allQuestions.slice(0, 15)) {
    console.log(`    ${q.query.substring(0, 50)}`);
  }
  console.log(`\n  已保存到: ${RAW_OUTPUT}`);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
