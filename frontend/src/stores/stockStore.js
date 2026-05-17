/** Pinia store for stock watchlist data. */
import { defineStore } from 'pinia'
import {
  listStocks,
  addStock,
  removeStock,
  updateNotes,
  renameStock,
  reorderStocks,
  batchFetch,
  refreshAll,
  searchStocks,
} from '../api'

export const useStockStore = defineStore('stocks', {
  state: () => ({
    stocks: [],            // watchlist items [{id, stock_code, market, stock_name, notes}]
    realtime: {},          // keyed by "market:code" → {price, change, ...}
    loading: false,
    error: '',
  }),

  getters: {
    /** Merge watchlist with realtime data into an ordered array for rendering. */
    watchlistWithData: (state) => {
      return state.stocks.map((s) => ({
        ...s,
        data: state.realtime[`${s.market}:${s.stock_code}`] || null,
      }))
    },
  },

  actions: {
    async loadWatchlist() {
      try {
        const res = await listStocks()
        this.stocks = res.data
      } catch (e) {
        this.error = 'Failed to load watchlist'
      }
    },

    async addStock(code, market, name = '') {
      // 1. Optimistic: add to local state immediately so card shows instantly
      const tempItem = {
        id: -Date.now(),  // temporary id, replaced after API response
        stock_code: code,
        market: market,
        stock_name: name || code,
        notes: '',
        sort_order: this.stocks.length,
        item_type: market === 'SECTOR' ? 'sector' : 'stock',
      }
      this.stocks.push(tempItem)

      // 2. Save to backend
      try {
        const res = await addStock(code, market, name)
        // Replace temp id with real id from server
        tempItem.id = res.data.id
      } catch (e) {
        // Rollback on failure
        const idx = this.stocks.indexOf(tempItem)
        if (idx !== -1) this.stocks.splice(idx, 1)
        delete this.realtime[`${market}:${code}`]
        throw new Error(e.response?.data?.detail || 'Failed to add stock')
      }

      // 3. Background refresh to fill real-time data (don't await — non-blocking)
      this.refreshStocks()
    },

    async removeStock(id) {
      try {
        await removeStock(id)
        // Clean realtime cache for the removed stock
        const item = this.stocks.find((s) => s.id === id)
        if (item) delete this.realtime[`${item.market}:${item.stock_code}`]
        this.stocks = this.stocks.filter((s) => s.id !== id)
      } catch (e) {
        this.error = 'Failed to remove stock'
      }
    },

    /**
     * Reorder stocks by sending the new ID order to the backend.
     * Also updates local state immediately.
     */
    async reorder(newOrder) {
      // newOrder is an array of stock IDs in the new order
      try {
        await reorderStocks(newOrder)
        // Reorder local stocks array to match
        const idMap = {}
        this.stocks.forEach((s) => { idMap[s.id] = s })
        this.stocks = newOrder.map((id) => idMap[id]).filter(Boolean)
      } catch (e) {
        this.error = 'Failed to save order'
      }
    },

    /**
     * Update notes for a stock.
     */
    async updateStockNotes(id, notes) {
      try {
        await updateNotes(id, notes)
        const stock = this.stocks.find((s) => s.id === id)
        if (stock) stock.notes = notes
      } catch (e) {
        this.error = 'Failed to update notes'
      }
    },

    updateStockNotesLocal(id, notes) {
      const stock = this.stocks.find((s) => s.id === id)
      if (stock) stock.notes = notes
    },

    async renameStock(id, name) {
      try {
        await renameStock(id, name)
        const stock = this.stocks.find((s) => s.id === id)
        if (stock) {
          stock.stock_name = name
          const key = `${stock.market}:${stock.stock_code}`
          if (this.realtime[key]) this.realtime[key].stock_name = name
        }
      } catch (e) {
        this.error = 'Failed to rename'
        throw e
      }
    },

    /**
     * Refresh all stock data in ONE batch API call.
     * Uses the server-side /stocks/refresh endpoint which fetches
     * realtime + financial data + news + chart data for all stocks in parallel.
     */
    async refreshStocks() {
      if (this.stocks.length === 0) return
      this.loading = true
      this.error = ''

      try {
        const res = await refreshAll()
        for (const item of res.data) {
          this.realtime[`${item.market}:${item.stock_code}`] = {
            stock_name: item.stock_name,
            price: item.price,
            change: item.change,
            change_pct: item.change_pct,
            prev_close: item.prev_close,
            open: item.open,
            high: item.high,
            low: item.low,
            volume: item.volume,
            amount: item.amount,
            turnover_rate: item.turnover_rate,
            pe: item.pe,
            market_cap: item.market_cap,
            float_market_cap: item.float_market_cap,
            amplitude: item.amplitude,
            news: item.news || [],
            chart_data: item.chart_data || [],
            item_type: item.item_type || 'stock',
            board_type: item.board_type || '',
            up_count: item.up_count,
            down_count: item.down_count,
          }
          // Sync stock_name into local stocks array for cards that rely on stock.stock_name
          const local = this.stocks.find(s => s.id === item.id)
          if (local && item.stock_name && !local.stock_name) {
            local.stock_name = item.stock_name
          }
        }
      } catch (e) {
        this.error = 'Failed to refresh stock data'
      } finally {
        this.loading = false
      }
    },

    async search(keyword) {
      try {
        const res = await searchStocks(keyword)
        return res.data
      } catch {
        return []
      }
    },
  },
})
