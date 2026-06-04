/**
 * Theme management: auto (by time) / light / dark.
 *
 * - 'auto'  → dark during night (18:00–05:59), light during day (06:00–17:59),
 *             and re-evaluates while the page is open so it flips at the boundary.
 * - 'light' / 'dark' → manual override, fixed.
 *
 * Default (no stored preference) is 'auto'.
 * Backward-compat: migrates the old 'darkMode' = '1'/'0' key to themeMode.
 */

const KEY = 'themeMode'           // 'auto' | 'light' | 'dark'
const NIGHT_START = 18            // 18:00 → night
const NIGHT_END = 6               // 06:00 → day

export function getThemeMode() {
  const m = localStorage.getItem(KEY)
  if (m === 'auto' || m === 'light' || m === 'dark') return m
  // migrate legacy darkMode flag → manual light/dark; else default auto
  const legacy = localStorage.getItem('darkMode')
  if (legacy === '1') return 'dark'
  if (legacy === '0') return 'light'
  return 'auto'
}

export function setThemeMode(mode) {
  localStorage.setItem(KEY, mode)
  localStorage.removeItem('darkMode')   // drop legacy key
  applyTheme()
}

export function isNightTime(d = new Date()) {
  const h = d.getHours()
  return h >= NIGHT_START || h < NIGHT_END
}

/** Returns true if dark should currently be active for the given mode. */
export function shouldBeDark(mode = getThemeMode()) {
  if (mode === 'dark') return true
  if (mode === 'light') return false
  return isNightTime()   // auto
}

/** Apply the dark/light class on <html> based on current mode + time. */
export function applyTheme() {
  const dark = shouldBeDark()
  document.documentElement.classList.toggle('dark', dark)
  return dark
}
