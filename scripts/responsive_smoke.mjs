import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
const require = createRequire(`${process.cwd()}/package.json`)
const { chromium } = require('playwright')

const host = '127.0.0.1'
const port = 4173
const url = `http://${host}:${port}`
const server = spawn('npm', ['run', 'preview', '--', '--host', host, '--port', String(port), '--strictPort'], {
  stdio: 'ignore',
  shell: process.platform === 'win32',
})
const browser = await chromium.launch({ headless: true })
const errors = []
try {
  let ready = false
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(url)
      if (response.ok) { ready = true; break }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  assert.ok(ready, 'Vite preview server failed to become ready')
  const page = await browser.newPage()
  page.on('pageerror', error => errors.push(error.message))
  const widths = [320, 375, 430, 768, 1024, 1280, 1440, 1920]
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#root > *', { timeout: 15000 })
  await page.waitForLoadState('load')
  const performanceBaseline = await page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0]
    const resources = performance.getEntriesByType('resource')
    return {
      domContentLoadedMs: Math.round(navigation?.domContentLoadedEventEnd ?? 0),
      loadEventMs: Math.round(navigation?.loadEventEnd ?? 0),
      resourceCount: resources.length,
      transferredBytes: resources.reduce((total, resource) => total + resource.transferSize, 0),
    }
  })
  console.log(`frontend cold-load baseline: ${JSON.stringify(performanceBaseline)}`)
  const connectionNoticeClose = page.locator('.startup-toast-dismiss')
  if (await connectionNoticeClose.count()) {
    await connectionNoticeClose.click({ force: true })
    await page.waitForFunction(() => !document.querySelector('.startup-toast'))
  }
  assert.ok(await page.locator('#application-navigation').count(), 'Application navigation should be rendered')
  await page.locator('#market-chart').waitFor({ state: 'attached' })
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    await page.waitForTimeout(250)
    const metrics = await page.evaluate(() => ({
      viewport: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      rootPresent: Boolean(document.querySelector('#root')?.firstElementChild),
    }))
    assert.ok(metrics.rootPresent, `React root did not render at ${width}px`)
    assert.ok(metrics.documentWidth <= width + 1, `Horizontal document overflow at ${width}px: ${JSON.stringify(metrics)}`)
    console.log(`responsive ${width}px: document=${metrics.documentWidth}px body=${metrics.bodyWidth}px`)
    const openNavigationIfNeeded = async () => {
      const navigation = page.locator('#application-navigation')
      if (!(await navigation.isVisible())) {
        await page.getByRole('button', { name: 'Toggle navigation' }).click()
      }
    }
    const marketsTab = page.locator('#application-navigation button[title="Markets"]')
    await openNavigationIfNeeded()
    await marketsTab.click()
    assert.equal(await marketsTab.getAttribute('aria-current'), 'page', `Markets navigation failed at ${width}px`)
    const overviewTab = page.locator('#application-navigation button[title="Overview"]')
    await openNavigationIfNeeded()
    await overviewTab.click()
    assert.equal(await overviewTab.getAttribute('aria-current'), 'page', `Overview navigation failed at ${width}px`)
  }
  const chartSettings = page.getByRole('button', { name: 'Chart settings' })
  await chartSettings.click()
  assert.ok(await page.locator('.settings-options').isVisible(), 'Chart settings panel should open')
  await chartSettings.click()
  assert.deepEqual(errors, [], 'Frontend threw uncaught runtime errors during responsive smoke test')
} finally {
  await browser.close()
  server.kill('SIGTERM')
}
