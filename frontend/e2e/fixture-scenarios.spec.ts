// FIXTURE browser checks. The analyze request is intercepted and answered with
// e2e/fixtures/FIXTURE-analysis-response.json, a clearly labelled synthetic response.
// Screenshots are saved as docs/screenshots/fixture-*.png. These are fixture results,
// not live data.
import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const FIXTURE = readFileSync(
  fileURLToPath(new URL('./fixtures/FIXTURE-analysis-response.json', import.meta.url)),
  'utf8',
)
const SHOTS = '../docs/screenshots'

async function loadFixture(page: Page) {
  let analyzeCalls = 0
  await page.route('**/api/routes/analyze', async (route) => {
    analyzeCalls += 1
    await route.fulfill({ status: 200, contentType: 'application/json', body: FIXTURE })
  })
  await page.goto('/')
  await page.getByLabel('Origin', { exact: true }).fill('FIXTURE origin')
  await page.getByLabel('Destination', { exact: true }).fill('FIXTURE destination')
  await page.getByRole('button', { name: 'Find the safest route' }).click()
  await expect(page.getByRole('region', { name: 'Recommendation' })).toBeVisible()
  // The A/B markers appear once the map has loaded the result; then let the fit animation and tiles settle.
  await expect(page.locator('.endpoint-marker')).toHaveCount(2, { timeout: 30_000 })
  await page.waitForTimeout(2500)
  return () => analyzeCalls
}

test('FIXTURE: global warning, High/Severe/No Travel sections, and route summaries', async ({ page }) => {
  await loadFixture(page)
  await expect(page.getByText('No safe route for this trip')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Recommendation' }).getByText('Best available, not safe')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/fixture-desktop-warning-and-hazards.png` })

  // Hover the map at the centre of every route's bounding box area until a route summary appears.
  const map = page.locator('.route-map')
  const box = (await map.boundingBox())!
  let summary: string | null = null
  for (let y = box.y + 40; y < box.y + box.height - 160 && !summary; y += 6) {
    for (let x = box.x + 40; x < box.x + box.width - 40 && !summary; x += 6) {
      await page.mouse.move(x, y)
      const popup = page.locator('.maplibregl-popup')
      if ((await popup.count()) > 0) {
        const text = (await popup.first().textContent()) ?? ''
        if (text.includes('Average risk')) summary = text
      }
    }
  }
  expect(summary).toMatch(/Route \d/)
  expect(summary).toContain('No Travel')
  expect(summary).toContain('Severe')
  expect(summary).toContain('High')
  await page.screenshot({ path: `${SHOTS}/fixture-route-summary-popup.png` })
})

test('FIXTURE: slider disables hours 36-48 and moving it makes no requests', async ({ page }) => {
  const analyzeCalls = await loadFixture(page)
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))

  const slider = page.getByRole('slider', { name: 'Forecast hour after departure' })
  await slider.focus()
  for (let i = 0; i < 48; i++) await page.keyboard.press('ArrowRight')
  await expect(slider).toHaveValue('35') // cannot reach the hours without data
  await expect(page.getByText('No forecast is available for hours 36-48 after departure')).toBeVisible()
  await expect(page.locator('.hour-strip .hour-cell-missing')).toHaveCount(13)
  await page.screenshot({ path: `${SHOTS}/fixture-slider-disabled-hours.png` })

  await page.keyboard.press('Home')
  await expect(slider).toHaveValue('0')
  await page.screenshot({ path: `${SHOTS}/fixture-heatmap-hour-00.png` })
  await slider.fill('20')
  await expect(slider).toHaveValue('20')
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${SHOTS}/fixture-heatmap-hour-20.png` })

  expect(analyzeCalls()).toBe(1)
  expect(requests.filter((url) => url.includes('/api/'))).toEqual([])
})

test('FIXTURE: narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loadFixture(page)
  await page.locator('.route-map').scrollIntoViewIfNeeded()
  await page.waitForTimeout(2500)
  await page.screenshot({ path: `${SHOTS}/fixture-narrow-map-and-slider.png` })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
})
