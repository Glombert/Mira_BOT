const puppeteer = require('puppeteer-core');
const { spawn } = require('child_process');
const path = require('path');

const DIST = path.join(__dirname, '../dist');
const OUT = path.join(__dirname, '../screenshots');
const CHROMIUM = '/usr/bin/chromium';

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const server = spawn('npx', ['serve', DIST, '-l', '3456'], {
    stdio: 'ignore',
    detached: false,
  });

  await sleep(2000);

  const browser = await puppeteer.launch({
    executablePath: CHROMIUM,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
  });

  const page = await browser.newPage();

  // 1. Desktop - auth screen
  await page.setViewport({ width: 1280, height: 800 });
  await page.goto('http://localhost:3456', { waitUntil: 'networkidle2' });
  await sleep(800);
  await page.screenshot({ path: path.join(OUT, '01-auth-desktop.png') });

  // Login via localStorage to skip auth screen
  await page.evaluate(() => {
    localStorage.setItem('mira_session', 'mock-session-123');
  });
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(1500);

  // 2. Desktop - empty chat
  await page.screenshot({ path: path.join(OUT, '02-chat-empty-desktop.png') });

  // 3. Mobile - empty chat
  await page.setViewport({ width: 375, height: 812 });
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(1500);
  await page.screenshot({ path: path.join(OUT, '03-chat-empty-mobile.png') });

  // 4. Desktop - with messages
  await page.setViewport({ width: 1280, height: 800 });
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(1500);
  const input = await page.$('textarea');
  if (input) {
    await input.type('Привет, Мира!');
    await sleep(200);
    await page.keyboard.press('Enter');
    await sleep(2500);
  }
  await page.screenshot({ path: path.join(OUT, '04-chat-with-messages.png') });

  await browser.close();
  server.kill();
  console.log('Screenshots done in', OUT);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
