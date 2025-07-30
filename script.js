// script.js
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');
const fetch = require('node-fetch');

const BROWSERLESS_API_KEY = process.env.BROWSERLESS_API_KEY;
const bookid = process.env.BOOK_ID;
const cookiesPath = './cookies.json';
const chaptersPath = `./${bookid}.txt`;
const progressPath = './progress.json';

const BASE_URL = `https://tytnovel.xyz/mystory/${bookid}/chapters/new`;

const delay = (ms) => new Promise(res => setTimeout(res, ms));

async function loadChapters(bookid) {
  const raw = fs.readFileSync(chaptersPath, 'utf8');
  const chapters = [];
  const lines = raw.split(/\r?\n/);

  let current = null;
  for (const line of lines) {
    const match = line.match(/^Chương\s+(\d+):?\s*(.*)?$/i);
    if (match) {
      if (current) chapters.push(current);
      current = { number: parseInt(match[1]), title: match[2] || '', content: '' };
    } else if (current) {
      current.content += line + '\n';
    }
  }
  if (current) chapters.push(current);
  return chapters;
}

async function run() {
  const browser = await puppeteer.connect({
    browserWSEndpoint: `wss://chrome.browserless.io?token=${BROWSERLESS_API_KEY}`
  });
  const page = await browser.newPage();

  // Set cookies
  const cookies = JSON.parse(fs.readFileSync(cookiesPath, 'utf8'));
  await page.setCookie(...cookies);

  await page.goto(BASE_URL, { waitUntil: 'networkidle2' });

  // Load progress
  let progress = {};
  if (fs.existsSync(progressPath)) {
    progress = JSON.parse(fs.readFileSync(progressPath));
  }
  const currentIndex = progress[bookid] || 0;

  const chapters = await loadChapters(bookid);
  const batch = chapters.slice(currentIndex, currentIndex + 10);
  if (batch.length === 0) {
    console.log('No chapters left to post.');
    return;
  }

  // Read chapter start
  const startNumber = batch[0].number;
  const endNumber = batch[batch.length - 1].number;

  await page.waitForSelector('#wrap');

  await page.evaluate((start, end) => {
    document.querySelector('#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(6) > div').innerText = start;
    document.querySelector('#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(7) > div').innerText = end;
    document.querySelector('#published').value = '1';
  }, startNumber, endNumber);

  // Fill in content
  for (const chap of batch) {
    await page.evaluate((content) => {
      const editor = document.querySelector(
        '#wrap > div:nth-child(4) > div > div.col-lg-9.col-xs-12 > div:nth-child(8) > div > div.ck.ck-reset.ck-editor.ck-rounded-corners > div.ck.ck-editor__main > div'
      );
      editor.innerHTML += `<p>${content}</p>`;
    }, `<b>Chương ${chap.number}: ${chap.title}</b><br/>${chap.content.replace(/\n/g, '<br/>')}`);
  }

  // Submit
  await page.click('#add_chapter');
  await page.waitForTimeout(5000);

  // Update progress
  progress[bookid] = currentIndex + batch.length;
  fs.writeFileSync(progressPath, JSON.stringify(progress, null, 2));

  console.log(`Posted chapters ${startNumber} to ${endNumber}`);

  await browser.close();

  // Delay random 60–90 minutes (for GitHub Actions)
  const delayMinutes = 60 + Math.floor(Math.random() * 31);
  console.log(`Sleeping for ${delayMinutes} minutes...`);
  await delay(delayMinutes * 60 * 1000);
}

run().catch(console.error);
