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

export function fetchMacroData() {
  return api.get('/macro')
}

export function refreshMacroData() {
  return api.post('/macro/refresh')
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
