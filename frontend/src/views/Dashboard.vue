<template>
  <div class="dashboard">
    <!-- Header -->
    <header class="header">
      <div class="header-l">
        <h1><span class="logo-icon">📈</span> 自选股看板</h1>
        <span class="update-time" v-if="lastUpdate">更新于 {{ lastUpdate }}</span>
      </div>
      <div class="header-r">
        <span class="user-badge">{{ username }}</span>

        <!-- System Menu -->
        <div class="sys-menu" @click.stop>
          <button class="btn btn-sys" @click="toggleSysMenu">⚙ 系统</button>
          <div class="sys-dropdown" v-if="showSysMenu" @click="showSysMenu = false">
            <button class="sys-item" @click="showUserMgmt = true">👥 用户维护</button>
            <button class="sys-item" @click="showOpLogs = true">📋 操作日志</button>
            <button class="sys-item" @click="showLLMConfig = true">🤖 大模型配置</button>
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

    <!-- Main Content -->
    <main class="main" v-if="watchlist.length > 0">
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
      <div class="stock-grid">
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
          />
        </div>
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
      :stocks="currentStocks"
      @close="showAllModal = false"
      @remove="handleRemove"
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
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

const router = useRouter()
const store = useStockStore()

const username = ref(localStorage.getItem('username') || 'User')
const showAddModal = ref(false)
const showAllModal = ref(false)
const showUserMgmt = ref(false)
const showOpLogs = ref(false)
const showLLMConfig = ref(false)
const showSysMenu = ref(false)
const activeTab = ref('ALL')
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

// Mobile (1 col): show all; Desktop: max 2 rows
const MAX_VISIBLE = computed(() =>
  gridCols.value <= 1 ? 9999 : gridCols.value * 2
)
const visibleStocks = computed(() =>
  currentStocks.value.slice(0, MAX_VISIBLE.value)
)

const watchlist = computed(() => store.watchlistWithData)
const loading = computed(() => store.loading)
const error = computed(() => store.error)

const stockCount = computed(() => watchlist.value.length)
const marketCount = computed(() => {
  const markets = new Set(watchlist.value.map(s => s.market))
  return markets.size
})

const aStocks = computed(() => watchlist.value.filter(s => s.market === 'A'))
const hkStocks = computed(() => watchlist.value.filter(s => s.market === 'HK'))
const usStocks = computed(() => watchlist.value.filter(s => s.market === 'US'))
const sectorStocks = computed(() => watchlist.value.filter(s => s.item_type === 'sector' || s.data?.item_type === 'sector'))

const currentStocks = computed(() => {
  if (activeTab.value === 'ALL') return watchlist.value
  if (activeTab.value === 'A') return aStocks.value
  if (activeTab.value === 'HK') return hkStocks.value
  if (activeTab.value === 'US') return usStocks.value
  if (activeTab.value === 'SECTOR') return sectorStocks.value
  return []
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

  const list = currentStocks.value
  if (!list || list.length < 2) {
    dragIdx.value = -1; dragOverIdx.value = -1
    return
  }

  const newList = [...list]
  const [moved] = newList.splice(dragIdx.value, 1)
  newList.splice(idx, 0, moved)

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

function handleRemove(id) {
  store.removeStock(id)
}

function handleUpdateNotes(id, notes) {
  store.updateStockNotes(id, notes)
}

function handleRename(id, name) {
  store.renameStock(id, name)
}

function handleAdded() {
  showAddModal.value = false
  // Card already added to local state by store.addStock (optimistic).
  // Real-time data is being fetched in background by store.addStock -> refreshStocks.
}

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
