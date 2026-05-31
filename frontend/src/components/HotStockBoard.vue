<template>
  <div class="hot-board">
    <!-- ── Header ── -->
    <div class="hb-header">
      <div class="hb-source-tabs">
        <button
          v-for="src in SOURCES" :key="src.key"
          :class="['hb-src-tab', { active: activeSource === src.key }]"
          @click="switchSource(src.key)"
        >{{ src.label }}</button>
      </div>

      <!-- Xueqiu time sub-tabs -->
      <div class="hb-time-tabs" v-if="activeSource === 'xueqiu'">
        <button
          v-for="t in XQ_TYPES" :key="t.value"
          :class="['hb-time-tab', { active: activeXqType === t.value }]"
          @click="switchXqType(t.value)"
        >{{ t.label }}</button>
      </div>

      <div class="hb-header-r">
        <span class="hb-top-label">Top20</span>
        <span class="hb-update" v-if="currentSlot.ts">{{ fmtTs(currentSlot.ts) }} 更新</span>
        <button
          class="hb-refresh"
          :class="{ spinning: currentSlot.loading }"
          :disabled="currentSlot.loading"
          title="刷新"
          @click="forceRefresh"
        >↻</button>
      </div>
    </div>

    <!-- ── Body ── -->
    <div v-if="currentSlot.loading && !currentSlot.data.length" class="hb-loading">
      <span class="hb-spin">↻</span> 加载中…
    </div>

    <div v-else-if="currentSlot.error" class="hb-empty">
      获取失败，请稍后重试
    </div>

    <div v-else-if="!currentSlot.data.length" class="hb-empty">
      暂无数据
    </div>

    <div v-else class="hb-grid">
      <div
        v-for="item in currentSlot.data"
        :key="item.code"
        class="hb-cell"
        @click="$emit('open-stock', { code: item.code, name: item.name, market: item.market || 'A' })"
      >
        <span class="hb-rank" :class="rankCls(item.rank)">{{ item.rank }}</span>
        <div class="hb-info">
          <span class="hb-name">{{ item.name }}</span>
          <span class="hb-code">
            {{ item.code }}
            <span v-if="item.market === 'HK'" class="hb-market-tag">HK</span>
          </span>
        </div>
        <div class="hb-right">
          <span :class="['hb-pct', pctCls(item.percent)]">
            {{ fmtPct(item.percent) }}
          </span>
          <!-- Xueqiu: 热度值 -->
          <span v-if="activeSource === 'xueqiu'" class="hb-hot">
            {{ item.hot != null ? '热' + fmtHot(item.hot) : '' }}
          </span>
          <!-- EM: 排名变化 -->
          <span v-else class="hb-delta" :class="deltaCls(item.rank_delta)">
            {{ item.rank_delta || '' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { fetchXueqiuHot, fetchEMHot } from '../api/index.js'

const emit = defineEmits(['open-stock'])

// ── Constants ─────────────────────────────────────────────────────────────────
const SOURCES = [
  { key: 'xueqiu',    label: '🔥 雪球热股榜' },
  { key: 'eastmoney', label: '📊 东方财富人气榜' },
]

const XQ_TYPES = [
  { value: 10, label: '近1小时' },
  { value: 11, label: '近24小时' },
  { value: 12, label: '近5天' },
]

const CACHE_TTL = 5 * 60 * 1000  // 5 min frontend cache

// ── State ─────────────────────────────────────────────────────────────────────
const activeSource = ref('xueqiu')
const activeXqType = ref(10)

// Each slot: { data, ts, loading, error }
function makeSlot() {
  return reactive({ data: [], ts: 0, loading: false, error: false })
}

const slots = {
  xueqiu: {
    10: makeSlot(),
    11: makeSlot(),
    12: makeSlot(),
  },
  eastmoney: {
    default: makeSlot(),
  },
}

const currentSlot = computed(() =>
  activeSource.value === 'xueqiu'
    ? slots.xueqiu[activeXqType.value]
    : slots.eastmoney.default
)

// ── Fetch logic ───────────────────────────────────────────────────────────────
async function loadIfNeeded(force = false) {
  const slot = currentSlot.value
  if (slot.loading) return
  if (!force && slot.data.length && Date.now() - slot.ts < CACHE_TTL) return

  slot.loading = true
  slot.error   = false
  try {
    let list = []
    if (activeSource.value === 'xueqiu') {
      const res = await fetchXueqiuHot(activeXqType.value)
      list = Array.isArray(res.data?.data) ? res.data.data : []
    } else {
      const res = await fetchEMHot()
      list = Array.isArray(res.data?.data) ? res.data.data : []
    }
    slot.data = list
    slot.ts   = Date.now()
    if (!list.length) slot.error = true
  } catch {
    slot.error = true
  } finally {
    slot.loading = false
  }
}

function forceRefresh() { loadIfNeeded(true) }

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchSource(key) {
  activeSource.value = key
}
function switchXqType(val) {
  activeXqType.value = val
}

// Load whenever current slot changes
watch(currentSlot, () => loadIfNeeded(), { immediate: true })

// ── Auto-refresh every 5 min ──────────────────────────────────────────────────
let _timer = null
onMounted(() => {
  _timer = setInterval(forceRefresh, CACHE_TTL)
})
onUnmounted(() => clearInterval(_timer))

// ── Formatters ────────────────────────────────────────────────────────────────
function fmtPct(v) {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}
function pctCls(v) {
  if (v == null) return ''
  return v > 0 ? 'up' : (v < 0 ? 'dn' : '')
}
function fmtHot(v) {
  if (v >= 10000) return (v / 10000).toFixed(1) + 'w'
  if (v >= 1000)  return (v / 1000).toFixed(1) + 'k'
  return String(v)
}
function deltaCls(d) {
  if (!d) return ''
  return d === '↑' ? 'up' : (d === '↓' ? 'dn' : '')
}
function rankCls(r) {
  return r <= 3 ? 'top3' : ''
}
function fmtTs(ts) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
</script>

<style scoped>
.hot-board {
  margin: 12px 0 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

/* ── Header ── */
.hb-header {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 12px;
  border-bottom: 1px solid #f3f4f6;
  min-height: 40px;
  flex-wrap: wrap;
  row-gap: 0;
}

.hb-source-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 0;
}
.hb-src-tab {
  padding: 4px 12px;
  border-radius: 6px;
  border: none;
  background: none;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}
.hb-src-tab:hover  { background: #f3f4f6; color: #111827; }
.hb-src-tab.active { background: #eff6ff; color: #2563eb; }

.hb-time-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: 8px;
  padding: 6px 0;
  border-left: 1px solid #e5e7eb;
  padding-left: 10px;
}
.hb-time-tab {
  padding: 3px 10px;
  border-radius: 5px;
  border: none;
  background: none;
  font-size: 12px;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}
.hb-time-tab:hover  { background: #f3f4f6; color: #111827; }
.hb-time-tab.active { background: #fef3c7; color: #d97706; font-weight: 600; }

.hb-header-r {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  font-size: 11px;
  color: #9ca3af;
  padding: 6px 0;
}
.hb-top-label {
  background: #f3f4f6;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  color: #6b7280;
}
.hb-update { white-space: nowrap; }
.hb-refresh {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 15px;
  color: #6b7280;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  padding: 0;
}
.hb-refresh:hover:not(:disabled) { background: #f3f4f6; color: #2563eb; }
.hb-refresh:disabled { opacity: 0.4; cursor: default; }
.hb-refresh.spinning { animation: spin 1s linear infinite; }

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ── Loading / Empty ── */
.hb-loading, .hb-empty {
  padding: 28px;
  text-align: center;
  font-size: 13px;
  color: #9ca3af;
}
.hb-spin { display: inline-block; animation: spin 1s linear infinite; }

/* ── Grid ── */
.hb-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: none;
}

.hb-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-right: 1px solid #f3f4f6;
  border-bottom: 1px solid #f3f4f6;
  cursor: pointer;
  transition: background 0.12s;
  min-width: 0;
}
.hb-cell:nth-child(4n) { border-right: none; }
.hb-cell:nth-last-child(-n+4) { border-bottom: none; }
.hb-cell:hover { background: #f9fafb; }

.hb-rank {
  flex-shrink: 0;
  width: 18px;
  font-size: 12px;
  font-weight: 700;
  color: #9ca3af;
  text-align: center;
}
.hb-rank.top3 { color: #ef4444; }

.hb-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.hb-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.hb-code {
  font-size: 10px;
  color: #9ca3af;
  line-height: 1.2;
}

.hb-right {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}
.hb-pct {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}
.hb-pct.up { color: #ef4444; }
.hb-pct.dn { color: #22c55e; }

.hb-market-tag {
  display: inline-block;
  font-size: 9px;
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #bbf7d0;
  border-radius: 3px;
  padding: 0 3px;
  margin-left: 2px;
  vertical-align: middle;
  line-height: 1.4;
}

.hb-hot {
  font-size: 10px;
  color: #9ca3af;
  line-height: 1.2;
}
.hb-delta {
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
}
.hb-delta.up { color: #ef4444; }
.hb-delta.dn { color: #22c55e; }

/* ── Responsive: 2-col on narrow screens ── */
@media (max-width: 768px) {
  .hb-grid { grid-template-columns: repeat(2, 1fr); }
  .hb-cell:nth-child(4n)  { border-right: 1px solid #f3f4f6; }
  .hb-cell:nth-child(2n)  { border-right: none; }
  .hb-cell:nth-last-child(-n+4) { border-bottom: 1px solid #f3f4f6; }
  .hb-cell:nth-last-child(-n+2) { border-bottom: none; }
}
</style>
