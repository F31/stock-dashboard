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

    <!-- ── Tab: 工业企业利润（历史折线图）── -->
    <div v-if="activeTab === 'profit'">
      <div v-if="profitLoading && !profitHistory" class="loading-tip">数据加载中，首次可能需要 10-30 秒…</div>
      <div v-else-if="profitError && !profitHistory" class="error-tip">{{ profitError }}</div>
      <template v-else-if="profitHistory">
        <!-- Chart 1: Total industry -->
        <div class="chart-block">
          <div class="chart-header">
            <span class="chart-title-main">工业企业营业利润 累计同比增速 (%)</span>
            <span class="source-badge">国家统计局 · 最新{{ profitHistory.latest_period }}</span>
          </div>
          <div class="canvas-wrap">
            <canvas ref="totalCanvas"></canvas>
          </div>
          <div class="chart-caption">
            规模以上工业企业营业利润累计同比增速 · {{ profitDateRange('total') }} · 来源: 国家统计局月度数据 · 红虚线=零轴
          </div>
        </div>
        <!-- Chart 2: Electronics sub-industry -->
        <div v-if="profitHistory.elec?.length" class="chart-block">
          <div class="chart-header">
            <span class="chart-title-main">计算机、通信和其他电子设备制造业 营业利润 累计同比增速 (%)</span>
            <span class="source-badge source-badge--purple">国家统计局 · 最新{{ profitHistory.latest_period }}</span>
          </div>
          <div class="canvas-wrap">
            <canvas ref="elecCanvas"></canvas>
          </div>
          <div class="chart-caption">
            规模以上计算机、通信和其他电子设备制造业营业利润累计同比 · {{ profitDateRange('elec') }} · 来源: 国家统计局 · 注: 受低基数效应影响部分期间增速偏高
          </div>
        </div>
      </template>
      <div v-else class="empty-tip">暂无数据（NBS服务可能受网络限制）</div>
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
import {
  fetchIndustrialProfitHistory, refreshIndustrialProfitHistory,
  fetchIndustrialCharts, refreshIndustrialCharts,
} from '../api/index.js'

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

// ── Profit history tab ──
const profitHistory = ref(null)
const profitLoading = ref(false)
const profitError = ref('')
const totalCanvas = ref(null)
const elecCanvas = ref(null)
let totalChart = null
let elecChart = null

function profitDateRange(key) {
  const arr = profitHistory.value?.[key]
  if (!arr?.length) return ''
  return `${arr[0].period}至${arr[arr.length - 1].period}`
}

// "2024-02" → "24-02"
function toShortPeriod(p) { return p.slice(2) }

function buildProfitChartData(points, label, lineColor, fillColor) {
  const labels = points.map(p => toShortPeriod(p.period))
  return {
    labels,
    datasets: [
      {
        label,
        data: points.map(p => p.value),
        borderColor: lineColor,
        backgroundColor: fillColor,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.3,
        fill: true,
        order: 1,
      },
      {
        label: '',
        data: labels.map(() => 0),
        borderColor: 'rgba(239, 68, 68, 0.55)',
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        tension: 0,
        order: 2,
      },
    ],
  }
}

const _xScaleProfit = {
  ticks: { font: { size: 10 }, maxTicksLimit: 16, maxRotation: 45 },
  grid: { color: '#f3f4f6' },
}

function buildProfitChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          filter: item => item.text.length > 0,
          font: { size: 11 },
          boxWidth: 32,
          padding: 10,
        },
      },
      tooltip: {
        filter: item => item.dataset.label.length > 0,
        callbacks: {
          label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1) ?? '--'}%`,
        },
      },
    },
    scales: {
      x: _xScaleProfit,
      y: {
        ticks: {
          font: { size: 10 },
          callback: v => v + '%',
        },
        grid: { color: '#f3f4f6' },
      },
    },
  }
}

function renderProfitCharts() {
  if (profitHistory.value?.total?.length && totalCanvas.value) {
    totalChart?.destroy()
    totalChart = new Chart(totalCanvas.value, {
      type: 'line',
      data: buildProfitChartData(
        profitHistory.value.total,
        '工业营业利润累计同比(%)',
        '#2563eb',
        'rgba(37, 99, 235, 0.1)',
      ),
      options: buildProfitChartOptions(),
    })
  }
  if (profitHistory.value?.elec?.length && elecCanvas.value) {
    elecChart?.destroy()
    elecChart = new Chart(elecCanvas.value, {
      type: 'line',
      data: buildProfitChartData(
        profitHistory.value.elec,
        '计算机通信电子营业利润累计同比(%)',
        '#7c3aed',
        'rgba(124, 58, 237, 0.1)',
      ),
      options: buildProfitChartOptions(),
    })
  }
}

async function loadProfit() {
  profitLoading.value = true
  profitError.value = ''
  try {
    const resp = await fetchIndustrialProfitHistory()
    const data = resp.data
    profitHistory.value = (data?.total?.length) ? data : null
    await nextTick()
    renderProfitCharts()
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
    const resp = await refreshIndustrialProfitHistory()
    const data = resp.data
    profitHistory.value = (data?.total?.length) ? data : null
    await nextTick()
    renderProfitCharts()
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

  const isBarLine = (indicator.chart_type || 'dual_line') === 'bar_line'
  const commonPlugins = {
    legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 14, padding: 10 } },
    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y ?? '--'}` } },
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
            type: 'linear', position: 'left',
            ticks: { font: { size: 10 } }, grid: { color: '#f3f4f6' },
            title: { display: true, text: '亿元', font: { size: 10 }, color: '#9ca3af' },
          },
          y1: {
            type: 'linear', position: 'right',
            ticks: { font: { size: 10 } }, grid: { drawOnChartArea: false },
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
        y: { ticks: { font: { size: 10 } }, grid: { color: '#f3f4f6' } },
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
  if (key === 'profit' && !profitHistory.value) {
    loadProfit()
  } else if (key === 'profit') {
    nextTick(renderProfitCharts)
  } else if (key === 'charts' && !chartsData.value) {
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
  totalChart?.destroy()
  elecChart?.destroy()
  ivaChart?.destroy()
  expChart?.destroy()
})
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

/* ── Profit history charts ── */
.chart-block {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  overflow: hidden; margin-bottom: 14px;
}
.chart-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px; padding: 10px 14px 6px;
  border-bottom: 1px solid #f3f4f6;
}
.chart-title-main {
  font-size: 0.82em; font-weight: 700; color: #1f2937; line-height: 1.4;
}
.source-badge {
  flex-shrink: 0;
  font-size: 0.72em; font-weight: 500;
  color: #2563eb; background: #eff6ff;
  border: 1px solid #bfdbfe; border-radius: 20px;
  padding: 2px 9px; white-space: nowrap; margin-top: 1px;
}
.source-badge--purple {
  color: #7c3aed; background: #f5f3ff;
  border-color: #ddd6fe;
}
.canvas-wrap { padding: 10px 14px 14px; height: 220px; position: relative; }
.canvas-wrap canvas { width: 100% !important; height: 100% !important; }
.chart-caption {
  padding: 5px 14px 8px; font-size: 0.68em; color: #9ca3af;
  border-top: 1px solid #f9fafb; line-height: 1.5;
}

/* ── Charts tab ── */
.charts-body { display: flex; flex-direction: column; gap: 16px; }
.chart-title {
  padding: 10px 14px 4px; font-size: 0.82em; font-weight: 700;
  color: #374151; border-bottom: 1px solid #f3f4f6;
}
.chart-unit { font-size: 0.88em; font-weight: 400; color: #9ca3af; }
</style>
