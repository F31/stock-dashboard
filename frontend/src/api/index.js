/** API client for stock dashboard. */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Inject JWT token into every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Handle 401 globally
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      window.dispatchEvent(new Event('auth:logout'))
      window.location.hash = '#/login'
    }
    return Promise.reject(err)
  },
)

export default api

// ── Auth ──

export function login(username, password) {
  return api.post('/auth/login', { username, password })
}

export function register(username, password) {
  return api.post('/auth/register', { username, password })
}

// ── Watchlist ──

export function listStocks() {
  return api.get('/stocks/list')
}

export function addStock(code, market, name) {
  return api.post('/stocks/add', { stock_code: code, market, stock_name: name })
}

export function removeStock(id) {
  return api.delete(`/stocks/${id}`)
}

export function updateNotes(id, notes) {
  return api.patch(`/stocks/${id}/notes`, { notes })
}

export function renameStock(id, stockName) {
  return api.patch(`/stocks/${id}/name`, { stock_name: stockName })
}

export function reorderStocks(order) {
  return api.post('/stocks/reorder', order)
}

export function showStock(id) {
  return api.patch(`/stocks/${id}/show`)
}

// ── Data ──

export function getStockDetail(id) {
  return api.get(`/stocks/${id}`)
}

/**
 * Batch-fetch realtime data for many stocks in ONE request.
 * @param {Array<{code:string, market:string}>} stocks
 * @returns {Promise<Array>}
 */
export function batchFetch(stocks) {
  return api.post('/stocks/batch', { stocks })
}

/**
 * Refresh all stocks in the watchlist (backend fetches your watchlist from DB).
 * Returns full detail (realtime + news + chart) for every stock.
 */
export function refreshAll() {
  return api.post('/stocks/refresh')
}

export function searchStocks(keyword) {
  return api.get(`/stocks/search/${encodeURIComponent(keyword)}`)
}

export function fetchMarketIntel() {
  return api.get('/market-intel')
}

export function fetchSectorCongestion() {
  return api.get('/sector-congestion')
}

export function fetchSectorTop5(code) {
  return api.get(`/sectors/${encodeURIComponent(code)}/top5`)
}

export function triggerCapexRefresh() {
  return api.post('/stocks/capex/refresh')
}

export function fetchMacroData() {
  return api.get('/macro')
}

export function refreshMacroData() {
  return api.post('/macro/refresh')
}

export function fetchIndustrialProfit() {
  return api.get('/macro/profit')
}

export function refreshIndustrialProfit() {
  return api.post('/macro/profit/refresh')
}

export function fetchIndustrialCharts() {
  return api.get('/macro/industrial-charts')
}

// ── Northbound (北向资金) ──
export function fetchNorthboundFlow() {
  return api.get('/macro/northbound')
}
export function refreshNorthboundFlow() {
  return api.post('/macro/northbound/refresh')
}

export function refreshIndustrialCharts() {
  return api.post('/macro/industrial-charts/refresh')
}

export function fetchIndustrialProfitHistory() {
  return api.get('/macro/profit-history')
}

export function refreshIndustrialProfitHistory() {
  return api.post('/macro/profit-history/refresh')
}

// ── Analysis Reports ──

export function listReports(stockCode, market) {
  return api.get('/reports', { params: { stock_code: stockCode, market } })
}

export function uploadReport(stockCode, market, title, file) {
  const fd = new FormData()
  fd.append('stock_code', stockCode)
  fd.append('market', market)
  fd.append('title', title)
  fd.append('file', file)
  return api.post('/reports/upload', fd)
}

export function addLinkReport(stockCode, market, title, url) {
  return api.post('/reports/link', { stock_code: stockCode, market, title, url })
}

export function deleteReport(id) {
  return api.delete(`/reports/${id}`)
}

// ── Admin / User Management ──

export function listUsers(page = 1, pageSize = 20) {
  return api.get('/admin/users', { params: { page, page_size: pageSize } })
}

export function createUser(username, password, role = 'user') {
  return api.post('/admin/users', { username, password, role })
}

export function updateUser(id, data) {
  return api.put(`/admin/users/${id}`, data)
}

export function deleteUser(id) {
  return api.delete(`/admin/users/${id}`)
}

// ── System Settings ──

export function getSystemSetting(key) {
  return api.get(`/admin/settings/${key}`)
}

export function updateSystemSetting(key, value) {
  return api.put(`/admin/settings/${key}`, { value })
}

// ── LLM Config ──

export function listLLMConfigs() {
  return api.get('/llm-configs')
}

export function getLLMConfig(id) {
  return api.get(`/llm-configs/${id}`)
}

export function createLLMConfig(data) {
  return api.post('/llm-configs', data)
}

export function updateLLMConfig(id, data) {
  return api.put(`/llm-configs/${id}`, data)
}

export function setDefaultLLMConfig(id) {
  return api.post(`/llm-configs/${id}/set-default`)
}

export function deleteLLMConfig(id) {
  return api.delete(`/llm-configs/${id}`)
}

// ── Admin / Operation Logs ──

export function listLogs(page = 1, pageSize = 20, filters = {}) {
  return api.get('/admin/logs', {
    params: { page, page_size: pageSize, ...filters },
  })
}

// ── Data Sources ──
export function listDataSources() { return api.get('/datasources') }
export function createDataSource(data) { return api.post('/datasources', data) }
export function updateDataSource(id, data) { return api.put(`/datasources/${id}`, data) }
export function deleteDataSource(id) { return api.delete(`/datasources/${id}`) }

// ── Prompt Templates ──
export function listPromptTemplates() { return api.get('/prompt-templates') }
export function createPromptTemplate(data) { return api.post('/prompt-templates', data) }
export function updatePromptTemplate(id, data) { return api.put(`/prompt-templates/${id}`, data) }
export function deletePromptTemplate(id) { return api.delete(`/prompt-templates/${id}`) }
export function setDefaultPromptTemplate(id) { return api.post(`/prompt-templates/${id}/set-default`) }

// ── Scheduled Tasks ──
export function listScheduledTasks() { return api.get('/scheduled-tasks') }
export function createScheduledTask(data) { return api.post('/scheduled-tasks', data) }
export function updateScheduledTask(id, data) { return api.put(`/scheduled-tasks/${id}`, data) }
export function deleteScheduledTask(id) { return api.delete(`/scheduled-tasks/${id}`) }

// ── Watched Tickers ──
export function listWatchedTickers() { return api.get('/watched-tickers') }
export function createWatchedTicker(data) { return api.post('/watched-tickers', data) }
export function updateWatchedTicker(id, data) { return api.put(`/watched-tickers/${id}`, data) }
export function deleteWatchedTicker(id) { return api.delete(`/watched-tickers/${id}`) }

// ── Analysis Frameworks ──
export function listFrameworks() { return api.get('/analysis-frameworks') }
export function getFramework(id) { return api.get(`/analysis-frameworks/${id}`) }
export function createFramework(data) { return api.post('/analysis-frameworks', data) }
export function updateFramework(id, data) { return api.put(`/analysis-frameworks/${id}`, data) }
export function deleteFramework(id) { return api.delete(`/analysis-frameworks/${id}`) }
export function setActiveFramework(id) { return api.post(`/analysis-frameworks/${id}/set-active`) }

// ── Premarket Analysis ──
export function triggerPremarket() { return api.post('/premarket/run') }
export function getLatestPremarket() { return api.get('/premarket/latest') }
export function listPremarketReports(limit = 20, offset = 0) { return api.get('/premarket/reports', { params: { limit, offset } }) }
export function getPremarketReport(id) { return api.get(`/premarket/reports/${id}`) }
export function getStreamText(id) { return api.get(`/premarket/stream-text/${id}`) }
export function synthesizeTTS(text, voice = 'zh-CN-XiaoxiaoNeural', rate = '-5%') {
  return api.post('/premarket/tts', { text, voice, rate }, { responseType: 'blob', timeout: 120000 })
}

// ── Quantitative Analysis ──
export function fetchQuanScores(params = {}) { return api.get('/quan/scores', { params }) }
export function fetchQuanTop(n = 20, tradeDate = null, model = 'factor') {
  return api.get('/quan/top', { params: { n, trade_date: tradeDate, model } })
}
export function fetchQuanStockScore(stockCode, model = 'factor', tradeDate = null) {
  return api.get(`/quan/scores/${stockCode}`, { params: { model, trade_date: tradeDate } })
}
export function fetchQuanDates(model = 'factor', limit = 30) {
  return api.get('/quan/dates', { params: { model, limit } })
}
export function fetchQuanChainFilters() { return api.get('/quan/chain-filters') }
export function fetchQuanThemeScores(params = {}) { return api.get('/quan/theme-scores', { params }) }

// ── Pipeline ──
export function triggerPipeline(trade_date = null, expand = false) {
  return api.post('/pipeline/trigger', { trade_date, expand })
}
export function fetchPipelineStatus() { return api.get('/pipeline/status') }
export function fetchPipelineLog(lines = 100) { return api.get('/pipeline/log', { params: { lines } }) }
export function fetchPoolStats() { return api.get('/pipeline/pool-stats') }
// qlib subprocess cold-start can take 40 s; override the 30 s global timeout
export function fetchQuanStockLevels(stockCode) {
  return api.get(`/quan/scores/${stockCode}/levels`, { timeout: 90000 })
}

