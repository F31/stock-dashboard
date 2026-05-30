<template>
  <div class="dashboard">
    <!-- Header -->
    <header class="header">
      <div class="header-l">
        <h1><span class="logo-icon">📈</span> 自选股看板</h1>
        <span class="update-time" v-if="lastUpdate">更新于 {{ lastUpdate }}</span>
      </div>

      <!-- Center: Premarket Analysis -->
      <div class="header-c">
        <button class="btn btn-premarket" @click="showPremarket = true">
          ☀ 今日盘前分析（人工智能产业链）
        </button>
        <button class="btn btn-premarket-hist" @click="showPremarketHist = true" title="历史记录">
          ···
        </button>
      </div>

      <div class="header-r">
        <span class="user-badge">{{ username }}</span>

        <!-- System Menu (admin only) -->
        <div class="sys-menu" v-if="isAdmin" @click.stop>
          <button class="btn btn-sys" @click="toggleSysMenu">⚙ 系统</button>
          <div class="sys-dropdown" v-if="showSysMenu" @click="showSysMenu = false">
            <button class="sys-item" @click="showUserMgmt = true">👥 用户维护</button>
            <button class="sys-item" @click="showOpLogs = true">📋 操作日志</button>
            <button class="sys-item" @click="showLLMConfig = true">🤖 大模型配置</button>
            <div class="sys-divider"></div>
            <button class="sys-item" @click="showScheduledTasks = true">⏰ 定时任务</button>
            <button class="sys-item" @click="showDataSources = true">📡 采集数据配置</button>
            <button class="sys-item" @click="showWatchedTickers = true">📈 行情监控标的</button>
            <button class="sys-item" @click="showPromptTemplates = true">📝 提示词模板</button>
            <div class="sys-divider"></div>
            <button class="sys-item" @click="showFrameworkEditor = true">🔬 产业链矩阵</button>
          </div>
        </div>

        <button class="btn btn-logout" @click="logout">退出</button>
      </div>
    </header>

    <!-- Error Toast -->
    <transition name="toast">
      <div v-if="error" class="error-toast">{{ error }}</div>
    </transition>

    <!-- Hide-instead-of-delete Toast -->
    <transition name="toast">
      <div v-if="hideToast" class="hide-toast">{{ hideToast }}</div>
    </transition>

    <!-- Main Content -->
    <main class="main" v-if="visibleWatchlist.length > 0 || watchlist.length > 0">

      <!-- ── Top-level Main Tabs ── -->
      <div class="main-tab-bar">
        <button :class="['main-tab', { active: mainTab === 'market' }]" @click="mainTab = 'market'">
          📈 板块/个股行情
        </button>
        <button :class="['main-tab', { active: mainTab === 'quan' }]" @click="mainTab = 'quan'">
          ⚡ 量化分析
        </button>
        <button :class="['main-tab', { active: mainTab === 'macro' }]" @click="mainTab = 'macro'">
          🌐 宏观经济数据
        </button>
        <button :class="['main-tab', { active: mainTab === 'risk' }]" @click="mainTab = 'risk'">
          🚨 风险预警
        </button>
      </div>

      <!-- ── Panel: 板块/个股行情 ── -->
      <div v-show="mainTab === 'market'">
        <!-- A-share index row -->
        <MarketIntel mode="indices" />

        <!-- Market sub-tabs: A股 / 港股 / 美股 / 板块行情监控 -->
        <div class="tab-bar-wrap">
          <div class="tab-bar">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              :class="['tab', { active: activeTab === tab.key }]"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
              <span class="tab-count">{{ tab.count }}</span>
            </button>
            <div class="tab-bar-r">
              <!-- SECTOR tab view mode toggle -->
              <template v-if="activeTab === 'SECTOR'">
                <button class="tab-action-btn" :class="{ 'tab-active': sectorViewMode === 'heatmap' }" @click="sectorViewMode = 'heatmap'">📊 热力图</button>
                <button class="tab-action-btn" :class="{ 'tab-active': sectorViewMode === 'list' }" @click="sectorViewMode = 'list'">📋 我的板块</button>
              </template>
              <select
                v-if="activeTab === 'A'"
                v-model="quanLabelFilter"
                class="signal-filter"
                :class="{ 'signal-filter--active': quanLabelFilter }"
                title="按量化评级筛选"
              >
                <option value="">全部评级</option>
                <option value="强烈推荐">强烈推荐</option>
                <option value="推荐">推荐</option>
                <option value="中性">中性</option>
                <option value="回避">回避</option>
              </select>
              <select
                v-if="hasQuanData && activeTab === 'A'"
                v-model="quanSort"
                class="signal-filter"
                :class="{ 'signal-filter--active': quanSort !== 'default' }"
                title="量化排序"
              >
                <option value="default">默认排序</option>
                <option value="quan_desc">量化↓高→低</option>
                <option value="quan_asc">量化↑低→高</option>
              </select>
              <button class="tab-action-btn tab-action-refresh" :disabled="loading" @click="refresh">
                <span :class="['refresh-icon', { spinning: loading }]">↻</span>
                {{ loading ? '更新中...' : '刷新' }}
              </button>
              <button class="tab-action-btn tab-action-add" @click="showAddModal = true">+ 添加</button>
              <button class="tab-more" @click="showAllModal = true">☰ 列表</button>
            </div>
          </div>
        </div>

        <!-- SECTOR tab: heatmap + sector fund flow (replaces stock grid) -->
        <template v-if="activeTab === 'SECTOR'">
          <div class="stock-flow-layout">
            <!-- Left: shared container for heatmap/list + floating TOP5 -->
            <div class="sector-heatmap-area">
              <template v-if="sectorViewMode === 'heatmap'">
                <SectorHeatmap @select-board="onSelectBoard" />
              </template>
              <template v-else>
                <div class="stock-grid" @touchstart.passive="onTouchStart" @touchend.passive="onTouchEnd">
                  <template v-for="(stock, idx) in visibleStocks" :key="stock.id">
                    <div v-if="stock._pad" class="card-wrap card-pad"></div>
                    <div v-else
                         v-memo="[stock.data?.price, stock.data?.change_pct, dragOverIdx === idx, stock.stock_name]"
                         class="card-wrap" :class="{ 'drag-over': dragOverIdx === idx }"
                         draggable="true" @dragstart="onDragStart(idx)" @dragover.prevent="onDragOver(idx)"
                         @dragleave="onDragLeave" @drop="onDrop($event, idx)" @dragend="onDragEnd">
                      <div class="drag-handle" title="拖动排序">⠿</div>
                      <StockCard :stock="stock" :quan-score="quanScoresMap[stock.stock_code] || null"
                                 @remove="handleRemove(stock.id)" @rename="handleRename"
                                 @open-detail="onSectorNameClick(stock)" />
                    </div>
                  </template>
                </div>
              </template>
              <!-- Floating TOP5 panel (shared: heatmap tile click OR list mode sector card dblclick) -->
              <div v-if="selectedBoard" class="sector-top5-overlay" @click.self="selectedBoard = null">
                <div class="sector-top5-card" :style="{ top: top5Pos + 'px' }">
                  <div class="st5-hdr">
                    <span class="st5-title">{{ selectedBoard.name }} <small>({{ selectedBoard.code }})</small></span>
                    <div class="st5-sort-group">
                      <button class="st5-sort-btn" :class="{ active: top5SortMode === 'change' }" @click="toggleTop5Sort">按涨幅</button>
                      <button class="st5-sort-btn" :class="{ active: top5SortMode === 'market_cap' }" @click="toggleTop5Sort">按市值</button>
                    </div>
                    <button class="st5-close" @click="selectedBoard = null">✕</button>
                  </div>
                  <div v-if="top5Loading" class="st5-loading">加载中...</div>
                  <div v-else class="st5-list">
                    <div class="st5-row st5-row-hdr">
                      <span class="st5-rank">#</span>
                      <span class="st5-code">代码</span>
                      <span class="st5-name">名称</span>
                      <span class="st5-chg">涨跌幅</span>
                      <span class="st5-price">现价</span>
                    </div>
                    <div v-for="s in top5Stocks" :key="s.code" class="st5-row st5-row-body" @click="$emit('open-detail', s.code)">
                      <span class="st5-rank">{{ s.rank }}</span>
                      <span class="st5-code">{{ s.code }}</span>
                      <span class="st5-name">{{ s.name }}</span>
                      <span :class="['st5-chg', s.change_pct >= 0 ? 'up' : 'dn']">{{ s.change_pct != null ? (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%' : '—' }}</span>
                      <span class="st5-price">{{ s.price != null ? s.price.toFixed(2) : '—' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- Right: SectorFundFlowPanel (always visible for SECTOR tab) -->
            <SectorFundFlowPanel />
          </div>
        </template>

        <!-- Non-SECTOR tabs: stock grid + FundFlowPanel -->
        <template v-if="activeTab !== 'SECTOR'">
        <div class="stock-flow-layout">
          <div class="stock-grid" @touchstart.passive="onTouchStart" @touchend.passive="onTouchEnd">
            <template v-for="(stock, idx) in visibleStocks" :key="stock.id">
              <!-- Padding card: invisible, just fills grid space to keep 3 equal rows -->
              <div v-if="stock._pad" class="card-wrap card-pad"></div>
              <!-- Real stock card: v-memo skips vdom diff when price/score/drag haven't changed -->
              <div
                v-else
                v-memo="[stock.data?.price, stock.data?.change_pct, quanScoresMap[stock.stock_code]?.percentile_score, dragOverIdx === idx, stock.stock_name]"
                class="card-wrap"
                :class="{ 'drag-over': dragOverIdx === idx }"
                draggable="true"
                @dragstart="onDragStart(idx)"
                @dragover.prevent="onDragOver(idx)"
                @dragleave="onDragLeave"
                @drop="onDrop($event, idx)"
                @dragend="onDragEnd"
              >
                <div class="drag-handle" title="拖动排序">⠿</div>
                <StockCard
                  :stock="stock"
                  :quan-score="quanScoresMap[stock.stock_code] || null"
                  @remove="handleRemove(stock.id)"
                  @rename="handleRename"
                  @open-detail="handleOpenDetail"
                />
              </div>
            </template>
          </div>
          <FundFlowPanel @open-detail="handleFundFlowDetail" />
        </div>
        </template>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="pagination">
          <button class="page-btn" :disabled="currentPage === 0" @click="prevPage">‹ 上一页</button>
          <span class="page-info">{{ currentPage + 1 }} / {{ totalPages }}</span>
          <button class="page-btn" :disabled="currentPage >= totalPages - 1" @click="nextPage">下一页 ›</button>
        </div>
      </div>

      <!-- ── Panel: 量化分析 ── 首次点击后渲染并保持挂载，避免重复拉取 -->
      <div v-if="visitedTabs.quan" v-show="mainTab === 'quan'" class="macro-panel">
        <QuantAnalysisMonitor
          :watchlist-codes="watchlistAStockCodes"
          :watchlist-stocks="aStocks"
          @add-to-watchlist="({ code, name }) => store.addStock(code, 'A', name)"
        />
      </div>

      <!-- ── Panel: 宏观经济数据 ── -->
      <div v-if="visitedTabs.macro" v-show="mainTab === 'macro'" class="macro-panel">
        <MacroMonitor />
        <IndustrialProfitMonitor />
      </div>

      <!-- ── Panel: 风险预警 ── -->
      <div v-if="visitedTabs.risk" v-show="mainTab === 'risk'" class="macro-panel">
        <RiskWarningPanel />
      </div>

    </main>

    <!-- Empty state -->
    <main class="main" v-else>
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <p>自选股列表为空</p>
        <p class="empty-sub">点击右上角 <strong>+ 添加</strong> 开始添加股票</p>
      </div>
    </main>

    <!-- Status Bar -->
    <footer class="status-bar">
      <span>{{ stockCount }} 只自选股 · {{ marketCount }} 个市场</span>
      <span v-if="loading" class="status-loading">数据更新中...</span>
    </footer>

    <!-- Add Stock Modal -->
    <AddStockModal
      v-if="showAddModal"
      @close="showAddModal = false"
      @added="handleAdded"
    />

    <!-- All Stocks Modal -->
    <AllStocksModal
      v-if="showAllModal"
      :stocks="allStocksForModal"
      @close="showAllModal = false"
      @remove="handleRemove"
      @show-stock="handleShowStock"
      @open-detail="handleOpenDetail"
    />

    <!-- User Management Modal -->
    <UserManagement
      v-if="showUserMgmt"
      @close="showUserMgmt = false"
    />

    <!-- Operation Log Modal -->
    <OperationLog
      v-if="showOpLogs"
      @close="showOpLogs = false"
    />

    <!-- LLM Config Modal -->
    <LLMConfigModal
      v-if="showLLMConfig"
      @close="showLLMConfig = false"
    />

    <!-- Stock Detail Modal -->
    <StockDetailModal
      v-if="detailStock"
      :stock="detailStock"
      :initialTab="detailInitialTab"
      :currentUser="currentUserObj"
      :quanScore="quanScoresMap[detailStock?.stock_code] || null"
      @close="detailStock = null; detailInitialTab = 'info'"
      @notes-saved="handleNotesSaved"
    />

    <!-- Premarket Analysis Modal -->
    <PremarketModal
      v-if="showPremarket"
      @close="showPremarket = false"
    />

    <!-- Premarket History Modal -->
    <PremarketHistoryModal
      v-if="showPremarketHist"
      @close="showPremarketHist = false"
    />

    <!-- Scheduled Tasks Config -->
    <ScheduledTaskConfig
      v-if="showScheduledTasks"
      @close="showScheduledTasks = false"
    />

    <!-- Data Source Config -->
    <DataSourceConfig
      v-if="showDataSources"
      @close="showDataSources = false"
    />

    <!-- Watched Ticker Config -->
    <WatchedTickerConfig
      v-if="showWatchedTickers"
      @close="showWatchedTickers = false"
    />

    <!-- Prompt Template Config -->
    <PromptTemplateConfig
      v-if="showPromptTemplates"
      @close="showPromptTemplates = false"
    />

    <!-- Framework Editor -->
    <FrameworkEditor
      v-if="showFrameworkEditor"
      @close="showFrameworkEditor = false"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { useStockStore } from '../stores/stockStore'
import { useAuthStore } from '../stores/authStore.js'
import { isMarketOpen, msUntilNextOpen, initTradeCalendar } from '../utils/marketTime'
import { fetchQuanScores, fetchSectorTop5ByChange, fetchSectorTop5, fetchStockPreview } from '../api/index.js'

// ── Always on first paint ───────────────────────────────────────────────────
import StockCard      from '../components/StockCard.vue'
import MarketIntel    from '../components/MarketIntel.vue'
import FundFlowPanel  from '../components/FundFlowPanel.vue'
import SectorHeatmap      from '../components/SectorHeatmap.vue'
import SectorFundFlowPanel from '../components/SectorFundFlowPanel.vue'

// ── Lazy: shown only after a user action (modal / tab switch) ───────────────
const AddStockModal      = defineAsyncComponent(() => import('../components/AddStockModal.vue'))
const AllStocksModal     = defineAsyncComponent(() => import('../components/AllStocksModal.vue'))
const StockDetailModal   = defineAsyncComponent(() => import('../components/StockDetailModal.vue'))
const CongestionMonitor  = defineAsyncComponent(() => import('../components/CongestionMonitor.vue'))

// Heavy tab panels — loaded only when the user clicks the tab
const QuantAnalysisMonitor   = defineAsyncComponent(() => import('../components/QuantAnalysisMonitor.vue'))
const MacroMonitor           = defineAsyncComponent(() => import('../components/MacroMonitor.vue'))
const IndustrialProfitMonitor = defineAsyncComponent(() => import('../components/IndustrialProfitMonitor.vue'))
const RiskWarningPanel       = defineAsyncComponent(() => import('../components/RiskWarningPanel.vue'))

// Premarket — triggered by header button
const PremarketModal        = defineAsyncComponent(() => import('../components/PremarketModal.vue'))
const PremarketHistoryModal = defineAsyncComponent(() => import('../components/PremarketHistoryModal.vue'))

// Admin-only system modals — rarely opened
const UserManagement      = defineAsyncComponent(() => import('../components/UserManagement.vue'))
const OperationLog        = defineAsyncComponent(() => import('../components/OperationLog.vue'))
const LLMConfigModal      = defineAsyncComponent(() => import('../components/LLMConfigModal.vue'))
const ScheduledTaskConfig = defineAsyncComponent(() => import('../components/ScheduledTaskConfig.vue'))
const DataSourceConfig    = defineAsyncComponent(() => import('../components/DataSourceConfig.vue'))
const WatchedTickerConfig = defineAsyncComponent(() => import('../components/WatchedTickerConfig.vue'))
const FrameworkEditor     = defineAsyncComponent(() => import('../components/FrameworkEditor.vue'))
const PromptTemplateConfig = defineAsyncComponent(() => import('../components/PromptTemplateConfig.vue'))

const router = useRouter()
const store = useStockStore()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const username = ref(localStorage.getItem('username') || 'User')
const showAddModal = ref(false)
const showAllModal = ref(false)
const showUserMgmt = ref(false)
const showOpLogs = ref(false)
const showLLMConfig = ref(false)
const showSysMenu = ref(false)
const showPremarket = ref(false)
const showPremarketHist = ref(false)
const showScheduledTasks = ref(false)
const showDataSources = ref(false)
const showWatchedTickers   = ref(false)
const showFrameworkEditor  = ref(false)
const showPromptTemplates = ref(false)
const mainTab = ref('market')   // 'market' | 'quan' | 'macro' | 'risk'
// 记录已访问过的 Tab，确保非首页 Tab 在首次点击后才渲染（分次装载），
// 之后保持挂载（v-show）避免切回时重复拉取数据。
const visitedTabs = reactive({ market: true, quan: false, macro: false, risk: false })

// Quan scores map: stock_code -> { percentile_score, label }
const quanScoresMap = ref({})
const quanSort = ref('default')
const hasQuanData = computed(() => Object.keys(quanScoresMap.value).length > 0)

// ── Sector tab state ──
const sectorViewMode = ref('heatmap')  // 'heatmap' | 'list'
const selectedBoard = ref(null)        // {code, name} when a heatmap tile is clicked
const top5Stocks = ref([])
const top5Loading = ref(false)
const top5Pos = ref(0)
const top5SortMode = ref('change')     // 'change' | 'market_cap'

// 前端缓存：key = `${code}:${sortMode}`，TTL 1 min，避免重复点击重复请求
const _top10Cache = new Map()
const _TOP5_TTL = 60000

async function loadTop5(code, sortMode) {
  const cacheKey = `${code}:${sortMode}`
  const hit = _top10Cache.get(cacheKey)
  if (hit && Date.now() - hit.ts < _TOP5_TTL) {
    top5Stocks.value = hit.data
    return
  }
  top5Loading.value = true
  top5Stocks.value = []
  try {
    const fn = sortMode === 'change' ? fetchSectorTop5ByChange : fetchSectorTop5
    const res = await fn(code)
    const data = Array.isArray(res.data) ? res.data : []
    _top10Cache.set(cacheKey, { data, ts: Date.now() })
    top5Stocks.value = data
  } catch (e) {
    console.error('Failed to load sector top5', e)
  } finally {
    top5Loading.value = false
  }
}

async function onSelectBoard(board) {
  selectedBoard.value = board
  top5SortMode.value = 'change'
  top5Pos.value = Math.min(window.innerHeight * 0.15, 120)
  await loadTop5(board.code, 'change')
}

function toggleTop5Sort() {
  const next = top5SortMode.value === 'change' ? 'market_cap' : 'change'
  top5SortMode.value = next
  if (selectedBoard.value) {
    loadTop5(selectedBoard.value.code, next)
  }
}

/** StockCard emits open-detail when clicking sector name — route to TOP5 for sectors */
function onSectorNameClick(stock) {
  if (stock.item_type === 'sector' || stock.data?.item_type === 'sector') {
    selectedBoard.value = { code: stock.stock_code, name: stock.stock_name || stock.data?.stock_name }
    top5SortMode.value = 'market_cap'
    top5Pos.value = Math.min(window.innerHeight * 0.15, 120)
    loadTop5(selectedBoard.value.code, 'market_cap')
  } else {
    handleOpenDetail(stock)
  }
}

async function loadQuanScores() {
  try {
    const res = await fetchQuanScores({ model: 'factor', min_percentile: 0 })
    const map = {}
    for (const row of (res.data.scores || [])) {
      map[row.stock_code] = { percentile_score: row.percentile_score, label: row.label }
    }
    quanScoresMap.value = map
  } catch {
    // quan model may not be trained yet — silently ignore
  }
}
const activeTab = ref('A')
const quanLabelFilter = ref('')
const detailStock = ref(null)

// Decode JWT to get current user id and role (no extra network call needed)
const currentUserObj = computed(() => {
  const token = localStorage.getItem('token')
  if (!token) return null
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return { id: parseInt(payload.sub), username: payload.username, role: payload.role }
  } catch {
    return null
  }
})
const lastUpdate = ref('')
const dragIdx = ref(-1)
const dragOverIdx = ref(-1)
let refreshTimer = null
let _autoRefreshTick = 0  // counts 30s ticks; every 10th tick triggers a full refresh

// ── Responsive grid: track window width to compute visible card count ──
const windowWidth = ref(window.innerWidth)
function handleResize() { windowWidth.value = window.innerWidth }

// Mirror the CSS auto-fill formula: minmax(280px, 1fr), gap clamp(8,1.5vw,14)
const gridCols = computed(() => {
  const w = windowWidth.value
  const pad = Math.min(32, Math.max(12, w * 0.03)) * 2
  const gap = Math.min(14, Math.max(8, w * 0.015))
  const avail = w - pad
  return Math.min(5, Math.max(1, Math.floor((avail + gap) / (280 + gap))))
})

// Mobile: cap at 20 cards to bound DOM size; Desktop: exactly 3 rows × 3 cols = 9 cards
const MAX_VISIBLE = computed(() =>
  gridCols.value <= 1 ? 20 : 9
)

const filteredStocks = computed(() => {
  let stocks = currentStocks.value
  if (quanLabelFilter.value) {
    const map = quanScoresMap.value
    stocks = stocks.filter(s => map[s.stock_code]?.label === quanLabelFilter.value)
  }
  if (quanSort.value !== 'default') {
    const map = quanScoresMap.value
    stocks = [...stocks].sort((a, b) => {
      const pa = map[a.stock_code]?.percentile_score ?? -1
      const pb = map[b.stock_code]?.percentile_score ?? -1
      return quanSort.value === 'quan_desc' ? pb - pa : pa - pb
    })
  }
  return stocks
})

// ── Pagination ──
const currentPage = ref(0)
const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredStocks.value.length / MAX_VISIBLE.value))
)
const pageStart = computed(() => currentPage.value * MAX_VISIBLE.value)
const pageEnd = computed(() => Math.min(pageStart.value + MAX_VISIBLE.value, filteredStocks.value.length))

const visibleStocks = computed(() => {
  const sliced = filteredStocks.value.slice(pageStart.value, pageEnd.value)
  // Desktop dual-panel: pad to exactly 9 so the grid always has 3 full rows.
  // This keeps 港股/美股/概念板块 cards the same height as A股 cards
  // and prevents single-row stretching when there are fewer than 9 items.
  if (gridCols.value > 1 && sliced.length < MAX_VISIBLE.value) {
    const pads = []
    for (let i = sliced.length; i < MAX_VISIBLE.value; i++) {
      pads.push({ id: `__pad_${i}`, _pad: true })
    }
    return [...sliced, ...pads]
  }
  return sliced
})

const watchlist = computed(() => store.watchlistWithData)
// Only non-hidden items for display in the grid and counts
const visibleWatchlist = computed(() => watchlist.value.filter(s => !s.hidden))
const loading = computed(() => store.loading)
const error = computed(() => store.error)

const stockCount = computed(() => visibleWatchlist.value.length)
const marketCount = computed(() => {
  const markets = new Set(visibleWatchlist.value.map(s => s.market))
  return markets.size
})

const aStocks = computed(() => visibleWatchlist.value.filter(s => s.market === 'A'))
const watchlistAStockCodes = computed(() => aStocks.value.map(s => s.stock_code).filter(Boolean))
const hkStocks = computed(() => visibleWatchlist.value.filter(s => s.market === 'HK'))
const usStocks = computed(() => visibleWatchlist.value.filter(s => s.market === 'US'))
const sectorStocks = computed(() => visibleWatchlist.value.filter(s => s.item_type === 'sector' || s.data?.item_type === 'sector'))

// Used for the grid — non-hidden only
const currentStocks = computed(() => {
  if (activeTab.value === 'A') return aStocks.value
  if (activeTab.value === 'HK') return hkStocks.value
  if (activeTab.value === 'US') return usStocks.value
  if (activeTab.value === 'SECTOR') return sectorStocks.value
  return visibleWatchlist.value
})

// Used for AllStocksModal — full list including hidden (modal sorts hidden to bottom)
const allStocksForModal = computed(() => {
  const visible = currentStocks.value
  const hidden = watchlist.value.filter(s => s.hidden && (
    (activeTab.value === 'A' && s.market === 'A') ||
    (activeTab.value === 'HK' && s.market === 'HK') ||
    (activeTab.value === 'US' && s.market === 'US') ||
    (activeTab.value === 'SECTOR' && (s.item_type === 'sector' || s.data?.item_type === 'sector'))
  ))
  return [...visible, ...hidden]
})

const tabs = computed(() => {
  const items = []
  if (aStocks.value.length) items.push({ key: 'A', label: 'A股', count: aStocks.value.length })
  if (hkStocks.value.length) items.push({ key: 'HK', label: '港股', count: hkStocks.value.length })
  if (usStocks.value.length) items.push({ key: 'US', label: '美股', count: usStocks.value.length })
  if (sectorStocks.value.length) items.push({ key: 'SECTOR', label: '概念板块', count: sectorStocks.value.length })
  if (items.length && !items.find(t => t.key === activeTab.value)) {
    activeTab.value = items[0].key
  }
  return items
})

function fmtTime() {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${now.getHours()}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

function onDragStart(idx) {
  if (quanLabelFilter.value || quanSort.value !== 'default') return
  dragIdx.value = idx
}

function onDragOver(idx) {
  if (dragIdx.value !== idx) dragOverIdx.value = idx
}

function onDragLeave() {
  dragOverIdx.value = -1
}

function onDrop(e, idx) {
  if (dragIdx.value === -1 || dragIdx.value === idx) {
    dragOverIdx.value = -1
    return
  }

  // Convert page-relative indices to absolute indices within currentStocks
  const absFrom = pageStart.value + dragIdx.value
  const absTo = pageStart.value + idx

  const list = currentStocks.value
  if (!list || list.length < 2) {
    dragIdx.value = -1; dragOverIdx.value = -1
    return
  }

  const newList = [...list]
  const [moved] = newList.splice(absFrom, 1)
  newList.splice(absTo, 0, moved)

  const newIds = newList.map(s => s.id)

  const fullList = watchlist.value
  const currentIdSet = new Set(list.map(s => s.id))
  let filteredIdx = 0
  const fullNewOrder = fullList.map(s => {
    if (currentIdSet.has(s.id)) {
      return newIds[filteredIdx++]
    }
    return s.id
  })

  store.reorder(fullNewOrder)
  dragIdx.value = -1
  dragOverIdx.value = -1
}

function onDragEnd() {
  dragIdx.value = -1
  dragOverIdx.value = -1
}

async function refresh() {
  try {
    _autoRefreshTick = 0  // reset so next full refresh is another 5 min away
    await store.refreshStocks()
    lastUpdate.value = fmtTime()
  } catch (e) {
    if (e?.response?.status === 401) {
      if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
    }
  }
}

const hideToast = ref('')
let hideToastTimer = null

async function handleRemove(id) {
  const result = await store.removeStock(id)
  if (result === 'hidden') {
    if (hideToastTimer) clearTimeout(hideToastTimer)
    hideToast.value = '该股票已有分析报告，已隐藏而非删除，可在「更多」列表中恢复显示'
    hideToastTimer = setTimeout(() => { hideToast.value = '' }, 4000)
  }
}

function handleShowStock(id) {
  store.showStock(id)
}

function handleRename(id, name) {
  store.renameStock(id, name)
}

const detailInitialTab = ref('info')

function handleOpenDetail(stock, tab = 'info') {
  detailInitialTab.value = tab
  detailStock.value = stock
}

async function handleFundFlowDetail(item) {
  // If already in watchlist AND data is loaded, reuse it directly
  const inWatchlist = store.stocks.find(
    s => s.stock_code === item.stock_code && s.market === 'A'
  )
  if (inWatchlist?.data) {
    handleOpenDetail(inWatchlist)
    return
  }

  // Open modal immediately with fund flow data, then enrich with full data
  detailInitialTab.value = 'info'
  detailStock.value = {
    id:         null,
    stock_code: item.stock_code,
    stock_name: item.stock_name,
    market:     'A',
    item_type:  'stock',
    notes:      '',
    data: {
      stock_name: item.stock_name,
      price:      item.price,
      change_pct: item.change_pct,
    },
  }

  try {
    const res = await fetchStockPreview(item.stock_code, 'A')
    const d = res.data
    // Replace detailStock.value entirely so Vue re-renders with full data
    if (detailStock.value?.stock_code === item.stock_code) {
      detailStock.value = {
        id:         null,
        stock_code: item.stock_code,
        stock_name: d.stock_name || item.stock_name,
        market:     'A',
        item_type:  'stock',
        notes:      '',
        data: {
          stock_name:         d.stock_name,
          price:              d.price,
          change:             d.change,
          change_pct:         d.change_pct,
          prev_close:         d.prev_close,
          open:               d.open,
          high:               d.high,
          low:                d.low,
          volume:             d.volume,
          amount:             d.amount,
          turnover_rate:      d.turnover_rate,
          pe:                 d.pe,
          pe_ttm:             d.pe_ttm ?? null,
          market_cap:         d.market_cap,
          float_market_cap:   d.float_market_cap,
          amplitude:          d.amplitude,
          news:               d.news || [],
          chart_data:         d.chart_data || [],
          item_type:          'stock',
          profit_growth_rate: d.profit_growth_rate ?? null,
          roe:                d.roe ?? null,
          debt_ratio:         d.debt_ratio ?? null,
          cash_profit_ratio:  d.cash_profit_ratio ?? null,
          peg:                d.peg ?? null,
          signal:             d.signal ?? null,
          capex:              d.capex ?? null,
          capex_period:       d.capex_period ?? '',
        },
      }
    }
  } catch (e) {
    console.error('Failed to load stock preview', e)
  }
}

function handleNotesSaved(id, notes) {
  store.updateStockNotesLocal(id, notes)
}

function handleAdded() {
  showAddModal.value = false
  // Card already added to local state by store.addStock (optimistic).
  // Real-time data is being fetched in background by store.addStock -> refreshStocks.
}

function prevPage() {
  if (currentPage.value > 0) currentPage.value--
}

function nextPage() {
  if (currentPage.value < totalPages.value - 1) currentPage.value++
}

// ── Touch swipe to paginate ──
let touchStartX = 0
let touchStartY = 0

function onTouchStart(e) {
  touchStartX = e.touches[0].clientX
  touchStartY = e.touches[0].clientY
}

function onTouchEnd(e) {
  if (totalPages.value <= 1) return
  const dx = e.changedTouches[0].clientX - touchStartX
  const dy = e.changedTouches[0].clientY - touchStartY
  // Only trigger on predominantly horizontal swipes with enough distance
  if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy)) return
  if (dx < 0) nextPage()
  else prevPage()
}

// 首次切换到某个主 Tab 时，标记为已访问（触发 v-if 渲染该 Tab 的组件）
watch(mainTab, tab => { visitedTabs[tab] = true })

// Reset to first page when switching tabs or filter; shrink page if needed
watch(activeTab, () => { currentPage.value = 0; quanLabelFilter.value = ''; quanSort.value = 'default' })
watch(quanLabelFilter, () => { currentPage.value = 0 })
watch(totalPages, (newTotal) => {
  if (currentPage.value >= newTotal) currentPage.value = Math.max(0, newTotal - 1)
})

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}

function toggleSysMenu() {
  showSysMenu.value = !showSysMenu.value
}

function closeSysMenu(e) {
  if (!e.target.closest('.sys-menu')) {
    showSysMenu.value = false
  }
}

function stopRefreshTimer() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

/** 交易时段感知的自动刷新调度器
 *  每 30 秒运行一次价格刷新（快速），每 10 个 tick（约 5 分钟）运行一次完整刷新（含新闻）。
 */
function scheduleNextRefresh() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  if (isMarketOpen()) {
    refreshTimer = setInterval(() => {
      _autoRefreshTick++
      if (_autoRefreshTick % 10 === 0) {
        refresh()  // 完整刷新（含新闻）约每 5 分钟一次
      } else {
        store.refreshPriceOnly()  // 仅价格刷新，快速，不阻塞 UI
      }
      if (!isMarketOpen()) stopRefreshTimer()
    }, 30000)
  } else {
    // 非交易时段: 等到下次开盘再启动
    const ms = msUntilNextOpen()
    refreshTimer = setTimeout(() => {
      refresh()
      scheduleNextRefresh()
    }, Math.min(ms, 3600000))  // 最多少 1 小时检查一次
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('auth:logout', stopRefreshTimer)
  await store.loadWatchlist()
  await refresh()
  loadQuanScores()  // fire-and-forget, may have no data yet
  scheduleNextRefresh()
  document.addEventListener('click', closeSysMenu)
  initTradeCalendar()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('auth:logout', stopRefreshTimer)
  stopRefreshTimer()
  document.removeEventListener('click', closeSysMenu)
})
</script>

<style scoped>
/* ── Layout ── */
.dashboard {
  min-height: 100vh;
  background: #f0f2f5;
  color: #1f2937;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: linear-gradient(135deg, #1e3a5f, #2563eb);
  color: #fff;
  flex-wrap: wrap;
  gap: 10px;
  position: sticky;
  top: 0;
  z-index: 50;
}

.header-l {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.header h1 {
  font-size: 1.2em;
  margin: 0;
  font-weight: 700;
}

.logo-icon {
  margin-right: 4px;
}

.update-time {
  font-size: 0.78em;
  color: rgba(255,255,255,0.7);
}

.header-r {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-badge {
  font-size: 0.8em;
  padding: 3px 10px;
  background: rgba(255,255,255,0.15);
  border-radius: 12px;
  color: rgba(255,255,255,0.9);
}

.btn {
  padding: 7px 16px;
  border: none;
  border-radius: 6px;
  font-size: 0.85em;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-add {
  background: #fff;
  color: #2563eb;
  font-weight: 600;
}
.btn-add:hover { background: #e0e7ff; }

.refresh-icon { display: inline-block; margin-right: 4px; }
.refresh-icon.spinning { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.btn-logout {
  background: transparent;
  color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.25);
}
.btn-logout:hover { background: rgba(255,255,255,0.1); color: #fff; }

/* ── System Menu ── */
.sys-menu { position: relative; }
.btn-sys {
  padding: 7px 16px;
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: 6px;
  font-size: 0.85em;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  background: transparent;
  color: rgba(255,255,255,0.7);
}
.btn-sys:hover { background: rgba(255,255,255,0.1); color: #fff; }
.sys-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.12);
  min-width: 150px;
  z-index: 300;
  overflow: hidden;
}
.sys-item {
  display: block;
  width: 100%;
  padding: 9px 16px;
  border: none;
  background: none;
  color: #374151;
  font-size: 0.85em;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}
.sys-item:hover { background: #f3f4f6; color: #2563eb; }
.sys-item + .sys-item { border-top: 1px solid #f3f4f6; }
.sys-divider { height: 1px; background: #e5e7eb; margin: 2px 0; }

/* ── Header Center (Premarket) ── */
.header-c {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  justify-content: center;
  min-width: 0;
}

.btn-premarket {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: #fff;
  font-weight: 600;
  font-size: 0.82em;
  padding: 7px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(245,158,11,0.35);
}
.btn-premarket:hover { background: linear-gradient(135deg, #d97706, #b45309); }

.btn-premarket-hist {
  background: rgba(255,255,255,0.15);
  color: rgba(255,255,255,0.85);
  font-size: 1em;
  font-weight: 700;
  letter-spacing: .08em;
  padding: 5px 10px;
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.btn-premarket-hist:hover { background: rgba(255,255,255,0.25); }

/* ── Error Toast ── */
.error-toast {
  position: fixed;
  top: 70px;
  left: 50%;
  transform: translateX(-50%);
  background: #dc2626;
  color: #fff;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 0.85em;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  z-index: 200;
}
.toast-enter-active, .toast-leave-active { transition: all 0.3s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-10px); }

.hide-toast {
  position: fixed;
  top: 70px;
  left: 50%;
  transform: translateX(-50%);
  background: #92400e;
  color: #fef3c7;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 0.85em;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  z-index: 200;
  max-width: 480px;
  text-align: center;
}

/* ── Main ── */
.main {
  flex: 1;
  padding: 0 clamp(12px, 3vw, 32px);
  max-width: 1800px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

/* ── Main Tabs (板块/个股行情 | 宏观经济数据) ── */
.main-tab-bar {
  display: flex;
  gap: 8px;
  padding: 16px 0 0;
  border-bottom: 2px solid #e5e7eb;
  margin-bottom: 0;
}

.main-tab {
  padding: 10px 22px;
  border: none;
  border-bottom: 3px solid transparent;
  background: none;
  font-size: 0.95em;
  font-weight: 700;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: -2px;
  border-radius: 6px 6px 0 0;
  white-space: nowrap;
}

.main-tab:hover {
  color: #374151;
  background: #f3f4f6;
}

.main-tab.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  background: #fff;
}

.macro-panel {
  padding-top: 16px;
}

/* ── Market Sub-Tab Bar ── */
.tab-bar-wrap {
  padding: 16px 0 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
}

.tab-bar {
  display: flex;
  align-items: center;
  gap: 2px;
}

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  background: #e5e7eb;
  border: none;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #6b7280;
  font-size: 0.88em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab:hover {
  background: #d1d5db;
  color: #374151;
}

.tab.active {
  background: #fff;
  color: #2563eb;
  font-weight: 700;
  box-shadow: 0 -1px 3px rgba(0,0,0,0.05);
}

.tab-count {
  font-size: 0.75em;
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(0,0,0,0.08);
  color: inherit;
}

.tab.active .tab-count {
  background: rgba(37,99,235,0.12);
  color: #2563eb;
}

/* ── Stock Grid (fluid: auto-fill, min card 280px) ── */
/* ── Stock Grid (inside dual layout or standalone) ── */
.stock-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: clamp(8px, 1.5vw, 14px);
  padding: 4px 0 16px;
  touch-action: pan-y;
}

/* ── Stock Grid + Fund Flow dual layout ── */
.stock-flow-layout {
  display: flex;
  gap: 14px;
  align-items: stretch;
}
.stock-flow-layout .stock-grid {
  flex: 1;
  min-width: 0;
  align-items: stretch;
  grid-auto-rows: 1fr;
}
.stock-flow-layout .card-wrap {
  display: flex;
  flex-direction: column;
  min-height: 70px;
}
.stock-flow-layout .card-wrap > .card {
  flex: 1;
}

/* Padding card: invisible, occupies grid cell to maintain 3 equal rows */
.card-pad {
  visibility: hidden;
  pointer-events: none;
  min-height: 0;
}

/* ── Sector heatmap area ── */
.sector-heatmap-area {
  flex: 1;
  min-width: 0;
  position: relative;
}

/* ── Sector TOP5 floating overlay ── */
.sector-top5-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  background: rgba(0,0,0,0.15);
  border-radius: 10px;
  display: flex;
  justify-content: center;
}
.sector-top5-card {
  position: absolute;
  width: 380px;
  max-width: 90%;
  max-height: 70vh;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.15);
  padding: 14px;
  z-index: 21;
}
.st5-hdr {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.st5-title {
  font-size: 0.9em;
  font-weight: 700;
  color: #111827;
}
.st5-title small {
  font-weight: 400;
  color: #9ca3af;
  font-size: 0.8em;
}
.st5-close {
  margin-left: auto;
  background: none;
  border: none;
  font-size: 1em;
  cursor: pointer;
  color: #9ca3af;
  padding: 2px 6px;
  border-radius: 4px;
}
.st5-close:hover { background: #f3f4f6; color: #374151; }

/* ── TOP5 sort toggle buttons ── */
.st5-sort-group {
  display: flex;
  gap: 4px;
  margin-left: auto;
  margin-right: 8px;
}
.st5-sort-btn {
  background: transparent;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 0.72em;
  cursor: pointer;
  color: #6b7280;
  transition: all 0.12s;
}
.st5-sort-btn:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}
.st5-sort-btn.active {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}
.st5-sort-btn.active:hover {
  background: #1d4ed8;
}

.st5-loading {
  text-align: center;
  color: #9ca3af;
  padding: 20px;
  font-size: 0.82em;
}
.st5-list { display: flex; flex-direction: column; gap: 2px; }
.st5-row {
  display: grid;
  grid-template-columns: 28px 76px 1fr 72px 72px;
  align-items: center;
  padding: 5px 6px;
  border-radius: 6px;
  font-size: 0.75em;
  gap: 4px;
}
.st5-row-hdr {
  color: #9ca3af;
  font-weight: 600;
  font-size: 0.7em;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 6px;
  margin-bottom: 2px;
}
.st5-row-body { cursor: pointer; transition: background 0.12s; }
.st5-row-body:hover { background: #f3f4f6; }
.st5-rank  { font-weight: 700; color: #6b7280; text-align: center; }
.st5-code  { font-family: monospace; color: #6b7280; font-size: 0.9em; }
.st5-name  { font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st5-chg   { text-align: right; font-weight: 700; font-family: monospace; }
.st5-chg.up { color: #dc2626; }
.st5-chg.dn { color: #16a34a; }
.st5-price { text-align: right; font-family: monospace; color: #374151; font-weight: 600; }

/* ── Sector view mode toggle active state ── */
.tab-active {
  background: #2563eb !important;
  color: #fff !important;
  border-color: #2563eb !important;
}

/* Desktop dual-panel: fix exactly 3 rows so cards are always equal height */
@media (min-width: 1201px) {
  .stock-flow-layout .stock-grid {
    grid-template-rows: repeat(3, 1fr);
    grid-auto-rows: 0;
  }
}

@media (max-width: 1200px) {
  .stock-flow-layout { flex-direction: column; }
}
@media (max-width: 768px) {
  .stock-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 400px) {
  .stock-grid { grid-template-columns: 1fr; }
}

/* ── Tab bar right-side action group ── */
.tab-bar-r {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.tab-action-btn {
  padding: 5px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  font-size: 0.82em;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.tab-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.tab-action-refresh {
  color: #374151;
}
.tab-action-refresh:hover:not(:disabled) {
  background: #f3f4f6;
  border-color: #6b7280;
}

.tab-action-add {
  color: #2563eb;
  font-weight: 600;
  border-color: #bfdbfe;
}
.tab-action-add:hover {
  background: #eff6ff;
  border-color: #2563eb;
}

/* ── Signal filter dropdown ── */
.signal-filter {
  padding: 5px 6px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  font-size: 0.82em;
  font-weight: 500;
  color: #374151;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s, background 0.15s;
  max-width: 76px;
  appearance: auto;
}
.signal-filter:hover { border-color: #6b7280; }
.signal-filter:focus { border-color: #2563eb; }
.signal-filter--active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}

/* ── "列表" button in tab bar ── */
.tab-more {
  padding: 5px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #6b7280;
  font-size: 0.82em;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.tab-more:hover {
  background: #f3f4f6;
  border-color: #2563eb;
  color: #2563eb;
}

/* ── Pagination ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 4px 0 16px;
}

.page-btn {
  padding: 7px 20px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #374151;
  font-size: 0.88em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.page-btn:hover:not(:disabled) {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.page-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.85em;
  color: #6b7280;
  min-width: 52px;
  text-align: center;
}

/* ── Empty State ── */
.empty-state {
  text-align: center;
  padding: 100px 24px;
  color: #9ca3af;
}

.empty-icon {
  font-size: 3em;
  margin-bottom: 16px;
}

.empty-state p {
  margin: 6px 0;
  font-size: 1em;
}

.empty-sub {
  font-size: 0.85em !important;
  color: #b0b7c3;
}

/* ── Status Bar ── */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 24px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
  font-size: 0.78em;
  color: #9ca3af;
  position: sticky;
  bottom: 0;
}

.status-loading {
  color: #2563eb;
}

/* ── Ultrawide cap ── */
/* ── Drag-and-Drop ── */
.card-wrap {
  position: relative;
  transition: transform 0.15s, box-shadow 0.15s;
}

.card-wrap:active {
  cursor: grabbing;
}

.card-wrap.drag-over {
  transform: scale(1.02);
  z-index: 10;
}

.card-wrap.drag-over > .card {
  box-shadow: 0 4px 20px rgba(37,99,235,0.25);
  border-color: #2563eb;
}

.drag-handle {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 5;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #c0c4cc;
  cursor: grab;
  border-radius: 4px;
  user-select: none;
  opacity: 0;
  transition: opacity 0.2s;
}

.card-wrap:hover .drag-handle {
  opacity: 1;
}

.drag-handle:hover {
  background: #e5e7eb;
  color: #6b7280;
}

/* ── Responsive: Mobile ── */
@media (max-width: 640px) {
  /* 两行布局：
     行1: 标题(左) + 操作按钮(右)
     行2: 盘前分析按钮(全宽) */
  .header {
    padding: 8px 12px;
    gap: 0;
    row-gap: 7px;
    align-items: center;
  }

  /* 行1: 标题撑满剩余空间 */
  .header-l {
    flex: 1 1 0;
    min-width: 0;
    gap: 8px;
  }
  .header h1 { font-size: 0.92em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .update-time { display: none; }
  .user-badge  { display: none; }

  /* 行1: 按钮组靠右紧凑排列 */
  .header-r {
    flex: 0 0 auto;
    gap: 5px;
  }
  .btn        { padding: 6px 9px; font-size: 0.76em; }
  .btn-sys    { padding: 6px 9px; font-size: 0.76em; }

  /* 行2: 盘前分析区 — order 靠后强制换行，宽度撑满 */
  .header-c {
    order: 10;
    flex: 0 0 100%;
    width: 100%;
    justify-content: stretch;
    gap: 5px;
  }
  .btn-premarket {
    flex: 1 1 0;
    min-width: 0;
    font-size: 0.78em;
    padding: 7px 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .btn-premarket-hist {
    flex: 0 0 auto;
    padding: 6px 10px;
  }

  .tab-bar-wrap {
    padding: 10px 0 0;
    margin-bottom: 10px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .tab-bar {
    flex-wrap: nowrap;
    min-width: min-content;
    padding-bottom: 2px;
  }
  .tab {
    padding: 7px 12px;
    font-size: 0.8em;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .tab-count { font-size: 0.7em; padding: 0 5px; }
  .tab-action-btn {
    padding: 4px 9px;
    font-size: 0.75em;
  }
  .tab-more {
    padding: 4px 10px;
    font-size: 0.75em;
  }
  .signal-filter {
    padding: 4px 4px;
    font-size: 0.75em;
    max-width: 64px;
  }

  .stock-grid {
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
    gap: 8px;
    padding: 2px 0 12px;
  }

  .status-bar {
    padding: 6px clamp(10px, 3vw, 16px);
    font-size: 0.72em;
  }

  .error-toast {
    top: 60px;
    padding: 8px 16px;
    font-size: 0.78em;
    width: 90%;
    text-align: center;
  }

  .drag-handle { display: none; }

  /* Main tabs: horizontal scroll on small screens */
  .main-tab-bar {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    flex-wrap: nowrap;
  }
  .main-tab-bar::-webkit-scrollbar { display: none; }
  .main-tab { flex-shrink: 0; font-size: 0.82em; padding: 8px 14px; }
}
</style>
