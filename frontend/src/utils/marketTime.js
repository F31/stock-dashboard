/**
 * A股交易时间判断工具 — 动态交易日历版
 *
 * 交易日历从后端 API 动态获取（AKShare / Sina 财经），
 * 不使用任何硬编码的休假日列表。
 * 前端定期拉取 + localStorage 缓存，离线情况下回退到仅周末判断。
 *
 * 数据流:
 *   GET /api/macro/trade-calendar  →  {trade_dates, holiday_dates}
 *   前端缓存 trade_dates (所有交易日) 到 localStorage，
 *   判断逻辑：周末休市 + 不在交易日列表中 → 非交易时段
 *
 * 用法:
 *   import { isMarketOpen, initTradeCalendar } from '@/utils/marketTime'
 *   await initTradeCalendar()   // 在 app 启动时调用一次
 *   if (isMarketOpen()) { ... }
 */

const CACHE_KEY = 'hermes_trade_calendar_cache'
const CACHE_TTL_MS = 4 * 3600 * 1000  // 4 小时刷新一次

let _tradeSet = null   // Set<"YYYY-MM-DD"> — 所有交易日
let _lastFetch = 0     // 上次 fetch 时间戳

// ── 从缓存读取 ─────────────────────────────────────
function _loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const { tradeDates, ts } = JSON.parse(raw)
    if (Date.now() - ts > CACHE_TTL_MS) return null
    return new Set(tradeDates)
  } catch {
    return null
  }
}

function _saveCache(tradeDates) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      tradeDates,
      ts: Date.now(),
    }))
  } catch { /* quota exceeded — 忽略 */ }
}

// ── 从后端获取 ─────────────────────────────────────
async function _fetchTradeCalendar() {
  const base = window.location.origin
  const url = `${base}/api/macro/trade-calendar`
  const resp = await fetch(url, { signal: AbortSignal.timeout(10000) })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const data = await resp.json()
  if (!data.trade_dates || !Array.isArray(data.trade_dates)) {
    throw new Error('Invalid calendar response')
  }
  return data.trade_dates
}

/**
 * 初始化交易日历。在 app 启动时调用一次即可。
 * 会尝试从 localStorage 加载缓存；缓存未命中或过期时从后端获取。
 * 获取失败时静默降级（仅周末判断，无节假日识别）。
 */
export async function initTradeCalendar() {
  // 优先从缓存加载
  const cached = _loadCache()
  if (cached) {
    _tradeSet = cached
    _lastFetch = Date.now()
    return
  }

  // 从后端获取
  try {
    const tradeDates = await _fetchTradeCalendar()
    _tradeSet = new Set(tradeDates)
    _lastFetch = Date.now()
    _saveCache(tradeDates)
  } catch (e) {
    console.warn('[marketTime] Failed to fetch trade calendar, fallback to weekend-only:', e)
    _tradeSet = null
  }

  // 后台静默刷新（下次页面加载或调用此函数时触发）
}

// 从本地时间推断中国标准时间 (UTC+8)
function getChinaDate() {
  const now = new Date()
  const utc = now.getTime() + now.getTimezoneOffset() * 60000
  return new Date(utc + 8 * 3600000)
}

/**
 * 判断当前是否为 A 股交易时段
 * @returns {boolean}
 */
export function isMarketOpen() {
  const cst = getChinaDate()
  const dow = cst.getDay()          // 0=Sun, 6=Sat

  // 周末休市
  if (dow === 0 || dow === 6) return false

  // 从缓存判断：如果该日不在交易日列表中，则休市
  const dateStr = `${cst.getFullYear()}-${String(cst.getMonth() + 1).padStart(2, '0')}-${String(cst.getDate()).padStart(2, '0')}`
  if (_tradeSet && !_tradeSet.has(dateStr)) {
    return false  // 非交易日（春节/国庆等法定节假日）
  }

  const h = cst.getHours()
  const m = cst.getMinutes()
  const total = h * 60 + m

  // 上午 9:25 ~ 11:30（早 5 分钟预热）
  if (total >= 565 && total < 690) return true
  // 下午 13:00 ~ 15:00
  if (total >= 780 && total < 900) return true

  return false
}

/**
 * 获取下次开盘时间（毫秒）
 * 可用于 setTimeout 精确唤醒
 * @returns {number} ms
 */
export function msUntilNextOpen() {
  const cst = getChinaDate()
  const now = cst.getTime()
  const h = cst.getHours()
  const m = cst.getMinutes()
  const total = h * 60 + m

  // 如果在交易时段内 → 立即刷新
  if (isMarketOpen()) return 0

  // 上午盘前 (0:00 ~ 9:25) → 当天 9:25
  if (total < 565) {
    const next = new Date(cst)
    next.setHours(9, 25, 0, 0)
    return next.getTime() - now
  }

  // 午间休市 (11:30 ~ 13:00) → 当天 13:00
  if (total >= 690 && total < 780) {
    const next = new Date(cst)
    next.setHours(13, 0, 0, 0)
    return next.getTime() - now
  }

  // 下午收盘后 (15:00 ~ 24:00) → 下个交易日 9:25
  let daysToAdd = 1
  while (true) {
    const cand = new Date(cst.getTime() + daysToAdd * 86400000)
    const cdow = cand.getDay()
    // 周末跳过
    if (cdow === 0 || cdow === 6) {
      daysToAdd++
      continue
    }
    // 非交易日跳过（使用动态日历）
    const cDateStr = `${cand.getFullYear()}-${String(cand.getMonth() + 1).padStart(2, '0')}-${String(cand.getDate()).padStart(2, '0')}`
    if (_tradeSet && !_tradeSet.has(cDateStr)) {
      daysToAdd++
      continue
    }
    // 找到了下一个交易日
    cand.setHours(9, 25, 0, 0)
    return cand.getTime() - now
  }
}
