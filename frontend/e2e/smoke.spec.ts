import { expect, test } from '@playwright/test'

/**
 * End-to-end smoke path from the design spec:
 * Home → (Scan now, mock only) → scan succeeded → browse latest → Sales.vIndividualCustomer →
 * Columns tab → Lineage tab → full explorer → expand pill → Columns toggle → Stats pages.
 *
 * Against `npm run dev:mock` (MSW) a scan is started and observed to completion.
 * Against a real backend (`E2E_BASE_URL=http://localhost:5173` with `npm run dev`) the scan
 * step is skipped — it would hit the live SQL Server — and the latest snapshot is used instead.
 */
const REAL_BACKEND = !!process.env.E2E_BASE_URL

test('home → scan → object detail → lineage → stats', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /connections/i })).toBeVisible()
  await expect(page.getByText('local-aw').first()).toBeVisible()

  if (!REAL_BACKEND) {
    await page.getByRole('link', { name: /scans/i }).first().click()
    await page.getByRole('button', { name: /scan now/i }).click()
    await page.getByRole('button', { name: /start scan/i }).click()
    await expect(page.getByText(/succeeded/i).first()).toBeVisible({ timeout: 20_000 })
  }

  await page.getByRole('link', { name: /browse latest/i }).first().click()
  await expect(page.getByRole('heading', { name: /snapshot overview/i })).toBeVisible()
  await page.getByRole('link', { name: 'vIndividualCustomer' }).first().click()
  await page.getByRole('tab', { name: /columns/i }).click()
  await expect(page.getByRole('cell', { name: 'FirstName' })).toBeVisible()

  await page.getByRole('tab', { name: /lineage/i }).click()
  await page.getByRole('link', { name: /open full explorer/i }).click()
  await expect(page.locator('.react-flow__node').first()).toBeVisible()

  await page.getByRole('button', { name: /\+\d+/ }).first().click()
  await page.getByRole('radio', { name: /columns/i }).click()
  await expect(page.locator('.react-flow__handle').first()).toBeVisible()

  await page.getByRole('link', { name: /stats/i }).first().click()
  await expect(page.getByRole('heading', { name: /largest tables/i })).toBeVisible()
})
