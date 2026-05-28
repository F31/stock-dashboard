<template>
  <div class="heatmap-section">
    <div class="heatmap-hdr">
      <span class="heatmap-ttl">📊 概念板块热力图</span>
      <span class="heatmap-sub" v-if="boards.length">
        {{ boards.length }} 板块
      </span>
      <div class="hdr-right">
        <span class="update-hint" v-if="updateTime">{{ updateTime }}</span>
        <span class="loading-spinner" v-if="loading">⟳</span>
      </div>
    </div>

    <div class="heatmap-grid" v-if="boards.length">
      <div
        v-for="b in boards"
        :key="b.code"
        class="heatmap-tile"
        :style="tileStyle(b.change_pct)"
        @click="emit('select-board', { code: b.code, name: b.name })"
      >
        <span class="tile-name">{{ b.name }}</span>
        <span class="tile-pct">{{ fmtPct(b.change_pct) }}</span>
        <div class="tile-tooltip">
          <div class="tt-name">{{ b.name }}</div>
          <div class="tt-chg">涨跌幅 {{ fmtPct(b.change_pct) }}</div>
          <div class="tt-flow" v-if="b.fund_flow != null">主力净流入 {{ fmtFlow(b.fund_flow) }}</div>
          <div class="tt-flow" v-else>主力净流入 --</div>
        </div>
      </div>
    </div>

    <div class="loading-tip" v-else-if="loading">热力图数据加载中...</div>
    <div class="no-data" v-else>暂无概念板块数据</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchSectorHeatmap } from '../api'
import { isMarketOpen, msUntilNextOpen } from '../utils/marketTime'

const emit = defineEmits(['select-board'])
const boards = ref([])
const updateTime = ref('')
const loading = ref(false)
let refreshTimer = null

async function load() {
  loading.value = true
  try {
    const res = await fetchSectorHeatmap()
    boards.value = res.data.boards || []
    if (res.data.update_time) {
      updateTime.value = res.data.update_time
    }
  } catch (e) {
    console.error('SectorHeatmap load error', e)
  } finally {
    loading.value = false
  }
}

function tileStyle(pct) {
  let bg = '#d1d5db'
  let color = '#1f2937'

  if (pct == null) {
    bg = '#d1d5db'
    color = '#1f2937'
  } else if (pct >= 5) {
    bg = '#dc2626'
    color = '#ffffff'
  } else if (pct >= 2) {
    bg = '#ef4444'
    color = '#ffffff'
  } else if (pct >= 0) {
    bg = '#fecaca'
    color = '#6b7280'
  } else if (pct >= -2) {
    bg = '#bbf7d0'
    color = '#6b7280'
  } else if (pct >= -5) {
    bg = '#4ade80'
    color = '#ffffff'
  } else {
    bg = '#16a34a'
    color = '#ffffff'
  }

  return { background: bg, color }
}

function fmtPct(v) {
  if (v == null) return '--'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function fmtFlow(v) {
  if (v == null) return '--'
  const sign = v >= 0 ? '+' : ''
  const abs = Math.abs(v)
  if (abs >= 1e8) return `${sign}${(v / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${sign}${(v / 1e4).toFixed(0)}万`
  if (abs > 0)    return `${sign}${v.toFixed(0)}`
  return '--'
}

function scheduleRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (isMarketOpen()) {
    refreshTimer = setInterval(() => {
      load()
      if (!isMarketOpen()) {
        clearInterval(refreshTimer)
        refreshTimer = null
      }
    }, 30000)
  } else {
    const ms = msUntilNextOpen()
    refreshTimer = setTimeout(() => {
      load()
      scheduleRefresh()
    }, Math.min(ms, 3600000))
  }
}

onMounted(() => {
  load()
  scheduleRefresh()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.heatmap-section {
  padding: 0 0 20px;
}

/* ── Header ── */
.heatmap-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.heatmap-ttl {
  font-size: 0.88em;
  font-weight: 700;
  color: #374151;
  letter-spacing: 0.3px;
}

.heatmap-sub {
  font-size: 0.78em;
  color: #6b7280;
}

.hdr-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.update-hint {
  font-size: 0.72em;
  color: #9ca3af;
}

.loading-spinner {
  font-size: 0.82em;
  color: #9ca3af;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Grid ── */
.heatmap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 6px;
  max-height: 580px;
  overflow-y: auto;
  padding-right: 4px;
}

.heatmap-grid::-webkit-scrollbar {
  width: 4px;
}
.heatmap-grid::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 2px;
}
.heatmap-grid::-webkit-scrollbar-track {
  background: transparent;
}

/* ── Tile ── */
.heatmap-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.7em;
  min-height: 52px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  text-align: center;
  overflow: hidden;
}

.heatmap-tile:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
  z-index: 2;
}

.tile-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  line-height: 1.3;
  margin-bottom: 2px;
  font-size: 1.1em;
}

.tile-pct {
  font-weight: 800;
  font-size: 1.1em;
  line-height: 1;
}

/* ── Tooltip ── */
.tile-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) scale(0.9);
  background: #1f2937;
  color: #f9fafb;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 1.1em;
  line-height: 1.4;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.18s ease, transform 0.18s ease;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.tile-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  margin-left: -5px;
  border: 5px solid transparent;
  border-top-color: #1f2937;
}

.heatmap-tile:hover .tile-tooltip {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}

.tt-name {
  font-weight: 700;
  margin-bottom: 2px;
}

.tt-chg,
.tt-flow {
  font-size: 0.92em;
  color: #d1d5db;
}

/* ── Empty states ── */
.loading-tip,
.no-data {
  padding: 16px;
  text-align: center;
  font-size: 0.82em;
  color: #9ca3af;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 10px;
}

/* ── Responsive ── */
@media (max-width: 640px) {
  .heatmap-grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 5px;
    max-height: 420px;
  }
  .heatmap-tile {
    padding: 6px;
    min-height: 44px;
  }
}
</style>
