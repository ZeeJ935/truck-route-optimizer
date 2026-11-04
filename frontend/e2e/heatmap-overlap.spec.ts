// FIXTURE browser check: the highest risk stays visible where heatmap circles overlap.
// A variant of the labelled fixture is built at runtime: every checkpoint is Low (so no
// red or purple road sections are drawn), every corridor cell is Low, except one Severe
// and one No Travel cell at STORM_HOUR, each surrounded by Low cells. Pixels are counted
// in screenshots of the map. These are fixture results, not live data.
import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { PNG } from 'pngjs'

const SHOTS = '../docs/screenshots'
const STORM_HOUR = 10
const BASELINE_HOUR = 5

function overlapFixture(): string {
  const fixture = JSON.parse(
    readFileSync(fileURLToPath(new URL('./fixtures/FIXTURE-analysis-response.json', import.meta.url)), 'utf8'),
  )
  fixture._fixture_note = `${fixture._fixture_note} Variant: heatmap overlap check.`
  for (const route of fixture.routes) {
    for (const checkpoint of route.checkpoints) {
      checkpoint.risk = 0
      checkpoint.risk_label = 'Low'
      checkpoint.reasons = []
    }
  }
  const corridor = fixture.forecast.corridor as { risk: (number | null)[] }[]
  for (const point of corridor) point.risk = point.risk.map((value) => (value === null ? null : 0))
  // Centre points are every third entry; pick two in the middle of the route, with Low neighbours.
  const severeIndex = 3 * Math.floor(corridor.length / 9)
  const noTravelIndex = 3 * Math.floor((2 * corridor.length) / 9)
  corridor[severeIndex].risk[STORM_HOUR] = 3
  corridor[noTravelIndex].risk[STORM_HOUR] = 4
  return JSON.stringify(fixture)
}

async function setHour(page: Page, hour: number) {
  const slider = page.getByRole('slider', { name: 'Forecast hour after departure' })
  await slider.focus()
  await page.keyboard.press('Home')
  for (let i = 0; i < hour; i++) await page.keyboard.press('ArrowRight')
  await expect(slider).toHaveValue(String(hour))
  await page.waitForTimeout(500)
}

/** Count clearly red and clearly purple pixels in the visible map area. */
async function countRiskPixels(page: Page, path: string) {
  const map = (await page.locator('.route-map').boundingBox())!
  const slider = (await page.locator('.forecast-slider').boundingBox())!
  // Exclude the slider panel at the bottom of the map.
  const clip = { x: map.x, y: map.y, width: map.width, height: slider.y - map.y }
  const png = PNG.sync.read(await page.screenshot({ path, clip }))
  let red = 0
  let purple = 0
  for (let i = 0; i < png.data.length; i += 4) {
    const [r, g, b] = [png.data[i], png.data[i + 1], png.data[i + 2]]
    if (r - g > 50 && r - b > 50) red += 1
    else if (b - g > 35 && r - g > 25 && b > r - 10) purple += 1
  }
  return { red, purple }
}

test('FIXTURE: Severe and No Travel heat cells stay visible among overlapping Low cells', async ({ page }) => {
  await page.route('**/api/routes/analyze', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: overlapFixture() }),
  )
  await page.goto('/')
  await page.getByLabel('Origin', { exact: true }).fill('FIXTURE origin')
  await page.getByLabel('Destination', { exact: true }).fill('FIXTURE destination')
  await page.getByRole('button', { name: 'Find the safest route' }).click()
  await expect(page.locator('.endpoint-marker')).toHaveCount(2, { timeout: 30_000 })
  // Close the legend so it does not cover the map, then let tiles and the fit settle.
  await page.locator('.map-legend summary').click()
  await page.waitForTimeout(2500)

  await setHour(page, BASELINE_HOUR)
  const baseline = await countRiskPixels(page, `${SHOTS}/fixture-heatmap-overlap-baseline-all-low.png`)
  await setHour(page, STORM_HOUR)
  const storm = await countRiskPixels(page, `${SHOTS}/fixture-heatmap-overlap-severe-and-no-travel.png`)

  console.log(`FIXTURE overlap pixels: baseline ${JSON.stringify(baseline)}, storm hour ${JSON.stringify(storm)}`)
  expect(baseline.red).toBeLessThan(20)
  expect(baseline.purple).toBeLessThan(20)
  expect(storm.red).toBeGreaterThan(150)
  expect(storm.purple).toBeGreaterThan(150)
})
