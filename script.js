const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const API_KEY = process.env.BROWSERLESS_API_KEY;
const BROWSERLESS_URL = `wss://chrome.browserless.io?token=${API_KEY}`;

// Đọc tất cả tệp .txt trong thư mục noveldata làm bookid
const dataDir = path.resolve(__dirname, 'noveldata');
const books = fs.readdirSync(dataDir)
  .filter(name => name.endsWith('.txt'))
  .map(name => path.basename(name, '.txt'));

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function postChapters(bookid) {
  const filePath = path.resolve(dataDir, `${bookid}.txt`);
  const progressPath = path.resolve(__dirname, `progress.json`);
  if (!fs.existsSync(filePath)) return;

  const chaptersText = fs.readFileSync(filePath, 'utf-8').split(/\n\s*\n/).map(t => t.trim()).filter(Boolean);
  let progress = fs.existsSync(progressPath) ? JSON.parse(fs.readFileSync(progressPath, 'utf-8')) : {};
  let current = progress[bookid] || 1;

  const browser = await puppeteer.connect({ browserWSEndpoint: BROWSERLESS_URL });
  const page = await browser.newPage();

  const cookies = JSON.parse(fs.readFileSync('cookies.json', 'utf-8'));
  await page.setCookie(...cookies);

  const url = `https://tytnovel.xyz/mystory/${bookid}/chapters/new`;
  await page.goto(url, { waitUntil: 'networkidle2' });

  const start = current;
  const end = current + 9;

  await page.waitForSelector('#published');

  await page.evaluate((start, end) => {
    document.querySelector('#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(6) > div').innerText = start;
    document.querySelector('#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(7) > div').innerText = end;
    document.querySelector('#published').value = "1";
  }, start, end);

  const chapterContents = chaptersText.slice(current - 1, end);
  const combined = chapterContents.join("\n\n====\n\n");

  await page.evaluate(content => {
    const editor = document.querySelector('#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(8) > div > div.ck.ck-reset.ck-editor.ck-rounded-corners > div.ck.ck-editor__main');
    editor.innerText = content;
  }, combined);

  await page.click('#add_chapter');
  progress[bookid] = end + 1;
  fs.writeFileSync(progressPath, JSON.stringify(progress, null, 2));

  await browser.close();

  const randomDelay = Math.floor(60 + Math.random() * 30) * 60 * 1000;
  await delay(randomDelay);
}

(async () => {
  for (const bookid of books) {
    try {
      await postChapters(bookid);
    } catch (err) {
      console.error(`Lỗi khi xử lý bookid ${bookid}:`, err);
    }
  }
})();
