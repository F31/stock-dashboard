<template>
  <div class="congestion-section">
    <div class="congestion-hdr">
      <span class="congestion-ttl">🔥 AI板块监控</span>
      <span class="congestion-sub" v-if="sectors.length">
        {{ upCount }}涨 · {{ downCount }}跌 · {{ sectors.length }}板块
      </span>
      <div class="hdr-right">
        <span class="update-hint" v-if="lastUpdate">{{ lastUpdate }}</span>
      </div>
    </div>

    <!-- Summary bar -->
    <div class="summary-bar" v-if="sectors.length">
      <div class="summary-item">
        <span class="summary-label">均涨跌幅</span>
        <span :class="['summary-val', avgTrend]">{{ fmtPct(avgChangePct) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">主力合计净流入</span>
        <span :class="['summary-val', totalFlow > 0 ? 'up' : totalFlow < 0 ? 'down' : '']">
          {{ fmtFlow(totalFlow) }}
        </span>
      </div>
      <div class="summary-item">
        <span class="summary-label">上涨板块</span>
        <span class="summary-val" :class="upCount > downCount ? 'up' : 'down'">
          {{ upCount }} / {{ sectors.length }}
        </span>
      </div>
    </div>

    <!-- Live sector cards -->
    <div class="sector-grid" v-if="sectors.length">
      <div
        v-for="s in sectors"
        :key="s.code"
        :class="['sector-card', trendClass(s)]"
      >
        <div class="sc-name">{{ s.name }}</div>
        <div class="sc-code">{{ s.code }}</div>
        <div :class="['sc-chg', trendClass(s)]">{{ fmtPct(s.change_pct) }}</div>
        <div class="sc-fund" :class="flowClass(s.fund_flow)">
          <span class="sc-fund-label">主力</span>{{ fmtFlow(s.fund_flow) }}
        </div>
        <div class="sc-turnover" v-if="s.turnover_rate != null">
          换手 {{ s.turnover_rate.toFixed(2) }}%
        </div>
      </div>
    </div>

    <div class="loading-tip" v-else-if="loading">板块数据加载中...</div>
    <div class="no-data" v-else>
      暂无板块数据，请先在自选股中添加 BK 板块，或等待数据刷新
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchSectorCongestion } from '../api'

const sectors = ref([])
const loading = ref(false)
const lastUpdate = ref('')
let timer = null

async function load() {
  loading.value = true
  try {
    const res = await fetchSectorCongestion()
    sectors.value = res.data || []
    const now = new Date()
    lastUpdate.value = `${now.getHours()}:${String(now.getMinutes()).padStart(2,'0')} 更新`
  } catch {
    // silently fail
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// ── Computed stats ──
const upCount = computed(() => sectors.value.filter(s => (s.change_pct ?? 0) >= 0).length)
const downCount = computed(() => sectors.value.filter(s => (s.change_pct ?? 0) < 0).length)

const avgChangePct = computed(() => {
  const valid = sectors.value.filter(s => s.change_pct != null)
  if (!valid.length) return null
  return valid.reduce((sum, s) => sum + s.change_pct, 0) / valid.length
})

const totalFlow = computed(() =>
  sectors.value.reduce((sum, s) => sum + (s.fund_flow || 0), 0)
)

const avgTrend = computed(() => {
  const v = avgChangePct.value
  return v == null ? '' : v >= 0 ? 'up' : 'down'
})

// ── Formatters ──
function trendClass(s) {
  if (!s || s.change_pct == null) return 'flat'
  return s.change_pct >= 0 ? 'up' : 'down'
}

function flowClass(v) {
  if (v == null) return ''
  return v > 0 ? 'up' : v < 0 ? 'down' : ''
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

</script>

<style scoped>
.congestion-section {
  padding: 0 0 20px;
}

/* ── Header ── */
.congestion-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.congestion-ttl {
  font-size: 0.88em;
  font-weight: 700;
  color: #374151;
  letter-spacing: 0.3px;
}

.congestion-sub {
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

/* ── Summary bar ── */
.summary-bar {
  display: flex;
  gap: 20px;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82em;
}

.summary-label {
  color: #6b7280;
}

.summary-val {
  font-weight: 700;
  font-size: 1em;
}

.summary-val.up { color: #dc2626; }
.summary-val.down { color: #16a34a; }

/* ── Sector grid ── */
.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.sector-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 10px 8px;
  transition: box-shadow 0.15s;
}

.sector-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.sector-card.up  { border-left: 3px solid #dc2626; }
.sector-card.down { border-left: 3px solid #16a34a; }
.sector-card.flat { border-left: 3px solid #e5e7eb; }

.sc-name {
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.3;
  margin-bottom: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sc-code {
  font-size: 10px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.sc-chg {
  font-size: 18px;
  font-weight: 900;
  line-height: 1;
  margin-bottom: 4px;
}

.sc-chg.up   { color: #dc2626; }
.sc-chg.down { color: #16a34a; }
.sc-chg.flat { color: #6b7280; }

.sc-fund {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 2px;
}

.sc-fund-label {
  font-weight: 400;
  color: #9ca3af;
  margin-right: 2px;
}

.sc-fund.up   { color: #dc2626; }
.sc-fund.down { color: #16a34a; }
.sc-fund:not(.up):not(.down) { color: #6b7280; }

.sc-turnover {
  font-size: 10px;
  color: #9ca3af;
}

/* ── Empty states ── */
.loading-tip, .no-data {
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
  .sector-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 6px;
  }
  .sc-chg { font-size: 16px; }
  .summary-bar { gap: 12px; padding: 6px 10px; }
  .congestion-table { font-size: 0.75em; min-width: 420px; }
  .congestion-table th, .congestion-table td { padding: 6px 8px; }
}
</style>
