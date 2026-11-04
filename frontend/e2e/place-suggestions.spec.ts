// Browser check for the place suggestion list. Suggestions and the analysis are
// intercepted (FIXTURE responses), so no backend or provider is called.
import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const FIXTURE = readFileSync(
  fileURLToPath(new URL('./fixtures/FIXTURE-analysis-response.json', import.meta.url)),
  'utf8',
)

const DENVER = [
  { label: 'Denver, CO', type: 'area' },
  { label: 'Denver, PA', type: 'area' },
  { label: 'Denver, NC', type: 'area' },
  { label: 'Denver City, TX', type: 'area' },
  { label: 'Denver, IA', type: 'area' },
]

test('a typed suggestion can be followed by a real click on the submit button', async ({ page }) => {
  await page.route('**/api/places/suggest?**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ suggestions: DENVER }) }),
  )
  const analyzeBodies: Record<string, unknown>[] = []
  await page.route('**/api/routes/analyze', async (route) => {
    analyzeBodies.push(route.request().postDataJSON())
    await route.fulfill({ status: 200, contentType: 'application/json', body: FIXTURE })
  })

  await page.goto('/')
  await page.getByLabel('Origin', { exact: true }).fill('Dallas, TX')
  const destination = page.getByRole('combobox', { name: 'Destination' })
  await destination.pressSequentially('Denver', { delay: 40 })
  // The list really opens while the text is still partial...
  await expect(page.getByRole('listbox', { name: 'Destination suggestions' })).toBeVisible()
  await destination.pressSequentially(', CO', { delay: 40 })
  // ...and is gone once the text equals a suggestion, even after the debounce settles.
  await page.waitForTimeout(700)
  await expect(page.getByRole('listbox', { name: 'Destination suggestions' })).toBeHidden()

  // A real click: no force, and a short timeout so an intercepted click fails fast.
  await page.getByRole('button', { name: 'Find the safest route' }).click({ timeout: 5_000 })

  await expect(page.getByRole('region', { name: 'Recommendation' })).toBeVisible()
  expect(analyzeBodies).toHaveLength(1)
  expect(analyzeBodies[0]).toMatchObject({ origin: 'Dallas, TX', destination: 'Denver, CO' })
})
