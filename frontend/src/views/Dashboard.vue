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

        <button class="btn btn-refresh" :disabled="loading" @click="refresh">
          <span :class="['refresh-icon', { spinning: loading }]">↻</span>
          {{ loading ? '更新中...' : '刷新' }}
        </button>
        <button class="btn btn-add" @click="showAddModal = true">+ 添加</button>
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
      <!-- Tab Bar -->
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
          <button class="tab-more" @click="showAllModal = true">
            <template v-if="currentStocks.length > MAX_VISIBLE">
              更多 ({{ currentStocks.length - MAX_VISIBLE }})
            </template>
            <template v-else>☰ 列表</template>
          </button>
        </div>
      </div>

      <!-- Stock Grid (fluid auto-fill, max 2 rows on desktop) -->
      <div class="stock-grid" @touchstart.passive="onTouchStart" @touchend.passive="onTouchEnd">
        <div
          v-for="(stock, idx) in visibleStocks"
          :key="stock.id"
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
            @remove="handleRemove(stock.id)"
            @update-notes="handleUpdateNotes"
            @rename="handleRename"
            @open-detail="handleOpenDetail"
          />
        </div>
      </div>

      <!-- Pagination Controls -->
      <div v-if="totalPages > 1" class="pagination">
        <button class="page-btn" :disabled="currentPage === 0" @click="prevPage">
          ‹ 上一页
        </button>
        <span class="page-info">{{ currentPage + 1 }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="currentPage >= totalPages - 1" @click="nextPage">
          下一页 ›
        </button>
      </div>

      <!-- Market Intelligence -->
      <MarketIntel />
      <!-- Congestion Monitor -->
      <CongestionMonitor />
      <!-- Macro Data Monitor -->
      <MacroMonitor />
      <!-- Industrial Profit Monitor -->
      <IndustrialProfitMonitor />
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
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useStockStore } from '../stores/stockStore'
import StockCard from '../components/StockCard.vue'
import AddStockModal from '../components/AddStockModal.vue'
import AllStocksModal from '../components/AllStocksModal.vue'
import MarketIntel from '../components/MarketIntel.vue'
import CongestionMonitor from '../components/CongestionMonitor.vue'
import UserManagement from '../components/UserManagement.vue'
import OperationLog from '../components/OperationLog.vue'
import LLMConfigModal from '../components/LLMConfigModal.vue'
import MacroMonitor from '../components/MacroMonitor.vue'
import IndustrialProfitMonitor from '../components/IndustrialProfitMonitor.vue'
import StockDetailModal from '../components/StockDetailModal.vue'
import PremarketModal from '../components/PremarketModal.vue'
import PremarketHistoryModal from '../components/PremarketHistoryModal.vue'
import ScheduledTaskConfig from '../components/ScheduledTaskConfig.vue'
import DataSourceConfig from '../components/DataSourceConfig.vue'
import WatchedTickerConfig from '../components/WatchedTickerConfig.vue'
import FrameworkEditor from '../components/FrameworkEditor.vue'
import PromptTemplateConfig from '../components/PromptTemplateConfig.vue'
import { useAuthStore } from '../stores/authStore.js'

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
const activeTab = ref('ALL')
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

// Mobile (1 col): show all; Desktop: max 2 rows per page
const MAX_VISIBLE = computed(() =>
  gridCols.value <= 1 ? 9999 : gridCols.value * 2
)

// ── Pagination ──
const currentPage = ref(0)
const totalPages = computed(() =>
  MAX_VISIBLE.value >= 9999 ? 1 : Math.max(1, Math.ceil(currentStocks.value.length / MAX_VISIBLE.value))
)
const pageStart = computed(() => currentPage.value * MAX_VISIBLE.value)
const pageEnd = computed(() => Math.min(pageStart.value + MAX_VISIBLE.value, currentStocks.value.length))

const visibleStocks = computed(() =>
  currentStocks.value.slice(pageStart.value, pageEnd.value)
)

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
const hkStocks = computed(() => visibleWatchlist.value.filter(s => s.market === 'HK'))
const usStocks = computed(() => visibleWatchlist.value.filter(s => s.market === 'US'))
const sectorStocks = computed(() => visibleWatchlist.value.filter(s => s.item_type === 'sector' || s.data?.item_type === 'sector'))

// Used for the grid — non-hidden only
const currentStocks = computed(() => {
  if (activeTab.value === 'ALL') return visibleWatchlist.value
  if (activeTab.value === 'A') return aStocks.value
  if (activeTab.value === 'HK') return hkStocks.value
  if (activeTab.value === 'US') return usStocks.value
  if (activeTab.value === 'SECTOR') return sectorStocks.value
  return []
})

// Used for AllStocksModal — full list including hidden (modal sorts hidden to bottom)
const allStocksForModal = computed(() => {
  const visible = currentStocks.value
  const hidden = watchlist.value.filter(s => s.hidden && (
    activeTab.value === 'ALL' ||
    (activeTab.value === 'A' && s.market === 'A') ||
    (activeTab.value === 'HK' && s.market === 'HK') ||
    (activeTab.value === 'US' && s.market === 'US') ||
    (activeTab.value === 'SECTOR' && (s.item_type === 'sector' || s.data?.item_type === 'sector'))
  ))
  return [...visible, ...hidden]
})

const tabs = computed(() => {
  const items = [{ key: 'ALL', label: '全部', count: watchlist.value.length }]
  if (aStocks.value.length) items.push({ key: 'A', label: 'A股', count: aStocks.value.length })
  if (hkStocks.value.length) items.push({ key: 'HK', label: '港股', count: hkStocks.value.length })
  if (usStocks.value.length) items.push({ key: 'US', label: '美股', count: usStocks.value.length })
  if (sectorStocks.value.length) items.push({ key: 'SECTOR', label: '板块行情监控', count: sectorStocks.value.length })
  if (!items.find(t => t.key === activeTab.value)) {
    activeTab.value = 'ALL'
  }
  return items
})

function fmtTime() {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${now.getHours()}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

function onDragStart(idx) {
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

  let fullNewOrder
  if (activeTab.value === 'ALL') {
    fullNewOrder = newIds
  } else {
    const fullList = watchlist.value
    const currentIdSet = new Set(list.map(s => s.id))
    let filteredIdx = 0
    fullNewOrder = fullList.map(s => {
      if (currentIdSet.has(s.id)) {
        return newIds[filteredIdx++]
      }
      return s.id
    })
  }

  store.reorder(fullNewOrder)
  dragIdx.value = -1
  dragOverIdx.value = -1
}

function onDragEnd() {
  dragIdx.value = -1
  dragOverIdx.value = -1
}

async function refresh() {
  await store.refreshStocks()
  lastUpdate.value = fmtTime()
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

function handleUpdateNotes(id, notes) {
  store.updateStockNotes(id, notes)
}

function handleRename(id, name) {
  store.renameStock(id, name)
}

const detailInitialTab = ref('info')

function handleOpenDetail(stock, tab = 'info') {
  detailInitialTab.value = tab
  detailStock.value = stock
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

// Reset to first page when switching tabs or when page count shrinks below current page
watch(activeTab, () => { currentPage.value = 0 })
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

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await store.loadWatchlist()
  await refresh()
  refreshTimer = setInterval(refresh, 30000)
  document.addEventListener('click', closeSysMenu)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (refreshTimer) clearInterval(refreshTimer)
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

.btn-refresh {
  background: rgba(255,255,255,0.15);
  color: #fff;
}
.btn-refresh:hover:not(:disabled) { background: rgba(255,255,255,0.25); }

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

/* ── Tab Bar ── */
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
.stock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: clamp(8px, 1.5vw, 14px);
  padding: 4px 0 16px;
  touch-action: pan-y;
}

/* ── "列表" button in tab bar ── */
.tab-more {
  margin-left: auto;
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
  flex-shrink: 0;
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
@media (min-width: 1800px) {
  .stock-grid { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
}

/* ── Phone portrait: single column ── */
@media (max-width: 400px) {
  .stock-grid { grid-template-columns: 1fr; }
}

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
  .header {
    padding: 8px clamp(10px, 3vw, 16px);
    gap: 6px;
  }
  .header h1 { font-size: 0.95em; }
  .header-l { gap: 8px; }
  .header-r { gap: 4px; }
  .update-time { display: none; }
  .user-badge { display: none; }
  .btn { padding: 6px 10px; font-size: 0.78em; }
  .btn-sys { padding: 6px 10px; font-size: 0.78em; }
  /* Show icon-only for logout on very small screens */
  .btn-logout .btn-text { display: none; }

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
  .tab-more {
    padding: 4px 10px;
    font-size: 0.75em;
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
}
</style>
