<template>
  <div class="monitor-section">
    <!-- Tab header -->
    <div class="tab-bar">
      <button
        v-for="tab in tabs" :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="switchTab(tab.key)"
      >{{ tab.label }}</button>
      <div class="tab-spacer" />
      <button v-if="activeTab === 'profit'" class="refresh-btn" :class="{ spinning: profitLoading }" @click="refreshProfit" title="刷新利润数据">↻</button>
      <button v-if="activeTab === 'charts'" class="refresh-btn" :class="{ spinning: chartsLoading }" @click="refreshCharts" title="刷新图表数据">↻</button>
    </div>

    <!-- ── Tab: 工业企业利润 ── -->
    <div v-if="activeTab === 'profit'">
      <div v-if="profitLoading && !profitRows.length" class="loading-tip">数据加载中...</div>
      <div v-else-if="profitError && !profitRows.length" class="error-tip">{{ profitError }}</div>
      <div v-else class="profit-body">
        <table class="profit-table">
          <thead>
            <tr>
              <th class="th-label">指标</th>
              <th v-for="p in profitPeriods" :key="p" class="th-period">{{ p }}</th>
            </tr>
          </thead>
          <tbody>
            <tr class="group-hdr-row">
              <td colspan="4" class="group-hdr">全部工业企业</td>
            </tr>
            <tr>
              <td class="td-label">利润总额（亿元）</td>
              <td v-for="d in profitRows" :key="d.period + 'tp'" class="td-val">{{ fmt(d.total_profit) }}</td>
            </tr>
            <tr>
              <td class="td-label td-sub">↳ 上年同期（亿元）</td>
              <td v-for="d in profitRows" :key="d.period + 'tprev'" class="td-val td-muted">{{ fmt(d.total_prev) }}</td>
            </tr>
            <tr>
              <td class="td-label">同比增长</td>
              <td v-for="d in profitRows" :key="d.period + 'ty'" class="td-val">
                <span :class="yoyClass(d.total_yoy)">{{ fmtPct(d.total_yoy) }}</span>
              </td>
            </tr>
            <tr class="group-hdr-row">
              <td colspan="4" class="group-hdr">计算机、通信和其他电子设备制造业</td>
            </tr>
            <tr>
              <td class="td-label">利润总额（亿元）</td>
              <td v-for="d in profitRows" :key="d.period + 'ep'" class="td-val">{{ fmt(d.elec_profit) }}</td>
            </tr>
            <tr>
              <td class="td-label td-sub">↳ 上年同期（亿元）</td>
              <td v-for="d in profitRows" :key="d.period + 'eprev'" class="td-val td-muted">{{ fmt(d.elec_prev) }}</td>
            </tr>
            <tr>
              <td class="td-label">同比增长</td>
              <td v-for="d in profitRows" :key="d.period + 'ey'" class="td-val">
                <span :class="yoyClass(d.elec_yoy)">{{ fmtPct(d.elec_yoy) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="data-source">数据来源：国家统计局</div>
      </div>
    </div>

    <!-- ── Tab: 工业经济图表 ── -->
    <div v-else-if="activeTab === 'charts'" class="charts-body">
      <div v-if="chartsLoading && !chartsData" class="loading-tip">图表数据加载中...</div>
      <div v-else-if="chartsError && !chartsData" class="error-tip">{{ chartsError }}</div>
      <template v-else-if="chartsData">
        <!-- 工业增加值 — 双折线图 -->
        <div v-if="chartsData.industrial_value_added" class="chart-block">
          <div class="chart-title">
            {{ chartsData.industrial_value_added.title }}
            <span class="chart-unit">（同比增长，%）</span>
          </div>
          <div class="canvas-wrap">
            <canvas ref="ivaCanvas"></canvas>
          </div>
        </div>
        <!-- 工业出口交货值 — 柱线组合图 -->
        <div v-if="chartsData.industrial_export" class="chart-block">
          <div class="chart-title">
            {{ chartsData.industrial_export.title }}
            <span class="chart-unit">（亿元 / 同比%）</span>
          </div>
          <div class="canvas-wrap">
            <canvas ref="expCanvas"></canvas>
          </div>
        </div>
        <div v-if="!chartsData.industrial_value_added && !chartsData.industrial_export" class="empty-tip">
          暂无数据（NBS接口仅在中国大陆服务器可访问）
        </div>
        <div class="data-source">数据来源：国家统计局</div>
      </template>
      <div v-else class="empty-tip">暂无数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import {
  Chart,
  LineController, LineElement,
  BarController, BarElement,
  PointElement, LinearScale, CategoryScale,
  Tooltip, Legend, Filler,
} from 'chart.js'
import { fetchIndustrialProfit, refreshIndustrialProfit, fetchIndustrialCharts, refreshIndustrialCharts } from '../api/index.js'

Chart.register(
  LineController, LineElement,
  BarController, BarElement,
  PointElement, LinearScale, CategoryScale,
  Tooltip, Legend, Filler,
)

const tabs = [
  { key: 'profit', label: '🏭 规模以上工业企业利润' },
  { key: 'charts', label: '📈 工业经济图表' },
]
const activeTab = ref('profit')

// ── Profit tab ──
const profitRows = ref([])
const profitLoading = ref(false)
const profitError = ref('')
const profitPeriods = computed(() => profitRows.value.map(r => r.period))

async function loadProfit() {
  profitLoading.value = true
  profitError.value = ''
  try {
    const resp = await fetchIndustrialProfit()
    profitRows.value = resp.data || []
  } catch {
    profitError.value = '数据获取失败'
  } finally {
    profitLoading.value = false
  }
}

async function refreshProfit() {
  profitLoading.value = true
  profitError.value = ''
  try {
    const resp = await refreshIndustrialProfit()
    profitRows.value = resp.data || []
  } catch {
    profitError.value = '刷新失败'
  } finally {
    profitLoading.value = false
  }
}

// ── Charts tab ──
const chartsData = ref(null)
const chartsLoading = ref(false)
const chartsError = ref('')
const ivaCanvas = ref(null)
const expCanvas = ref(null)
let ivaChart = null
let expChart = null

const PALETTE = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

function _allPeriods(indicator) {
  const set = new Set()
  for (const s of indicator.series) {
    for (const p of s.data) set.add(p.period)
  }
  return Array.from(set).sort()
}

// 工业增加值：双折线（两条同比/累计同比线，单Y轴）
function buildDualLineData(indicator) {
  const labels = _allPeriods(indicator)
  const datasets = indicator.series.map((s, i) => {
    const dataMap = new Map(s.data.map(p => [p.period, p.value]))
    return {
      label: s.name,
      data: labels.map(period => dataMap.get(period) ?? null),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length] + '18',
      borderWidth: 2,
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
    }
  })
  return { labels, datasets }
}

// 工业出口交货值：柱线组合（绝对值亿元=柱，同比%=折线，双Y轴）
function buildBarLineData(indicator) {
  const labels = _allPeriods(indicator)
  const datasets = indicator.series.map((s, i) => {
    const isYoy = s.series_type === 'yoy'
    const dataMap = new Map(s.data.map(p => [p.period, p.value]))
    return {
      type: isYoy ? 'line' : 'bar',
      label: s.name,
      data: labels.map(period => dataMap.get(period) ?? null),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: isYoy ? 'transparent' : PALETTE[i % PALETTE.length] + '66',
      borderWidth: isYoy ? 2 : 0,
      pointRadius: isYoy ? 2 : 0,
      pointHoverRadius: isYoy ? 4 : 0,
      tension: 0.3,
      yAxisID: isYoy ? 'y1' : 'y',
      order: isYoy ? 1 : 2,
    }
  })
  return { labels, datasets }
}

const _xScale = {
  ticks: { font: { size: 10 }, maxTicksLimit: 18, maxRotation: 45 },
  grid: { color: '#f3f4f6' },
}

function renderIndicatorChart(canvas, indicator, existingChart) {
  if (!canvas || !indicator?.series?.length) return existingChart
  if (existingChart) existingChart.destroy()

  const chartType = indicator.chart_type || 'dual_line'
  const isBarLine = chartType === 'bar_line'

  const commonPlugins = {
    legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 14, padding: 10 } },
    tooltip: {
      callbacks: {
        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y ?? '--'}`,
      },
    },
  }

  if (isBarLine) {
    return new Chart(canvas, {
      type: 'bar',
      data: buildBarLineData(indicator),
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: commonPlugins,
        scales: {
          x: _xScale,
          y: {
            type: 'linear',
            position: 'left',
            ticks: { font: { size: 10 } },
            grid: { color: '#f3f4f6' },
            title: { display: true, text: '亿元', font: { size: 10 }, color: '#9ca3af' },
          },
          y1: {
            type: 'linear',
            position: 'right',
            ticks: { font: { size: 10 } },
            grid: { drawOnChartArea: false },
            title: { display: true, text: '%', font: { size: 10 }, color: '#9ca3af' },
          },
        },
      },
    })
  }

  return new Chart(canvas, {
    type: 'line',
    data: buildDualLineData(indicator),
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: commonPlugins,
      scales: {
        x: _xScale,
        y: {
          ticks: { font: { size: 10 } },
          grid: { color: '#f3f4f6' },
        },
      },
    },
  })
}

async function loadCharts() {
  chartsLoading.value = true
  chartsError.value = ''
  try {
    const resp = await fetchIndustrialCharts()
    chartsData.value = resp.data || {}
    await nextTick()
    ivaChart = renderIndicatorChart(ivaCanvas.value, chartsData.value.industrial_value_added, ivaChart)
    expChart = renderIndicatorChart(expCanvas.value, chartsData.value.industrial_export, expChart)
  } catch {
    chartsError.value = '图表数据获取失败'
  } finally {
    chartsLoading.value = false
  }
}

async function refreshCharts() {
  chartsLoading.value = true
  chartsError.value = ''
  try {
    const resp = await refreshIndustrialCharts()
    chartsData.value = resp.data || {}
    await nextTick()
    ivaChart = renderIndicatorChart(ivaCanvas.value, chartsData.value.industrial_value_added, ivaChart)
    expChart = renderIndicatorChart(expCanvas.value, chartsData.value.industrial_export, expChart)
  } catch {
    chartsError.value = '刷新失败'
  } finally {
    chartsLoading.value = false
  }
}

function switchTab(key) {
  activeTab.value = key
  if (key === 'charts' && !chartsData.value) {
    loadCharts()
  } else if (key === 'charts') {
    nextTick(() => {
      ivaChart = renderIndicatorChart(ivaCanvas.value, chartsData.value.industrial_value_added, ivaChart)
      expChart = renderIndicatorChart(expCanvas.value, chartsData.value.industrial_export, expChart)
    })
  }
}

onMounted(loadProfit)
onUnmounted(() => {
  ivaChart?.destroy()
  expChart?.destroy()
})

// ── Formatters ──
function fmt(v) {
  if (v == null) return '--'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}
function fmtPct(v) {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(1) + '%'
}
function yoyClass(v) {
  if (v == null) return 'yoy-neutral'
  return v > 0 ? 'yoy-pos' : v < 0 ? 'yoy-neg' : 'yoy-neutral'
}
</script>

<style scoped>
.monitor-section { padding: 0 0 24px; }

/* ── Tabs ── */
.tab-bar {
  display: flex; align-items: center; gap: 2px;
  margin-bottom: 10px; border-bottom: 1px solid #e5e7eb;
  padding-bottom: 0;
}
.tab-btn {
  background: none; border: none; cursor: pointer;
  font-size: 0.82em; font-weight: 600; color: #6b7280;
  padding: 6px 12px; border-bottom: 2px solid transparent;
  margin-bottom: -1px; white-space: nowrap;
  transition: all 0.15s;
}
.tab-btn:hover { color: #2563eb; }
.tab-btn.active { color: #2563eb; border-bottom-color: #2563eb; }
.tab-spacer { flex: 1; }
.refresh-btn {
  background: none; border: 1px solid #e5e7eb; border-radius: 5px;
  color: #6b7280; font-size: 1em; cursor: pointer;
  width: 26px; height: 26px; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.refresh-btn:hover { border-color: #3b82f6; color: #3b82f6; }
.refresh-btn.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Shared ── */
.loading-tip, .error-tip, .empty-tip {
  padding: 20px; text-align: center; font-size: 0.82em; color: #9ca3af;
}
.error-tip { color: #ef4444; }
.data-source {
  padding: 6px 12px; font-size: 0.7em; color: #d1d5db; text-align: right;
  border-top: 1px solid #f3f4f6;
}

/* ── Profit table ── */
.profit-body { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
.profit-table { width: 100%; border-collapse: collapse; font-size: 0.8em; }
.profit-table th, .profit-table td {
  padding: 7px 12px; text-align: right; border-bottom: 1px solid #f3f4f6;
}
.th-label, .td-label { text-align: left; color: #374151; font-weight: 500; white-space: nowrap; }
.td-label.td-sub { color: #9ca3af; font-weight: 400; font-size: 0.92em; padding-left: 20px; }
.th-period { color: #6b7280; font-weight: 600; font-size: 0.9em; white-space: nowrap; }
.td-val { color: #111827; font-variant-numeric: tabular-nums; white-space: nowrap; }
.td-muted { color: #9ca3af; }
.group-hdr-row .group-hdr {
  background: #f9fafb; color: #6b7280; font-size: 0.82em; font-weight: 600;
  text-align: left; padding: 5px 12px; border-bottom: 1px solid #e5e7eb;
}
.yoy-pos { color: #dc2626; font-weight: 600; }
.yoy-neg { color: #16a34a; font-weight: 600; }
.yoy-neutral { color: #6b7280; }

/* ── Charts tab ── */
.charts-body { display: flex; flex-direction: column; gap: 16px; }
.chart-block { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
.chart-title {
  padding: 10px 14px 4px; font-size: 0.82em; font-weight: 700;
  color: #374151; border-bottom: 1px solid #f3f4f6;
}
.chart-unit { font-size: 0.88em; font-weight: 400; color: #9ca3af; }
.canvas-wrap { padding: 10px 14px 14px; height: 220px; position: relative; }
.canvas-wrap canvas { width: 100% !important; height: 100% !important; }
</style>
