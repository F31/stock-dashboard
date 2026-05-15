<template>
  <div class="congestion-section">
    <div class="congestion-hdr">
      <span class="congestion-ttl">🔥 AI板块拥挤度监控</span>
      <span class="congestion-sub" v-if="sectors.length">
        {{ upCount }}涨 · {{ downCount }}跌 · {{ sectors.length }}板块
      </span>
      <div class="hdr-right">
        <span class="update-hint" v-if="lastUpdate">{{ lastUpdate }}</span>
        <button class="detail-toggle" @click="showAssessment = !showAssessment">
          {{ showAssessment ? '收起评估' : '展开拥挤度评估' }}
        </button>
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

    <!-- Qualitative assessment (collapsible) -->
    <transition name="slide">
      <div class="assessment-section" v-show="showAssessment">
        <div class="assessment-title">📊 拥挤度综合评估（研究判断，非实时数据）</div>
        <div class="congestion-table-wrap">
          <table class="congestion-table">
            <thead>
              <tr>
                <th class="col-dim">维度</th>
                <th class="col-reading">当前状态</th>
                <th class="col-level">风险等级</th>
                <th class="col-desc">解读</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in assessments" :key="item.id">
                <td class="col-dim">{{ item.dimension }}</td>
                <td class="col-reading">{{ item.reading }}</td>
                <td class="col-level">
                  <span :class="['level-badge', levelClass(item.level)]">{{ item.level }}</span>
                </td>
                <td class="col-desc">{{ item.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchSectorCongestion } from '../api'

const sectors = ref([])
const loading = ref(false)
const showAssessment = ref(false)
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

function levelClass(level) {
  if (level.startsWith('✓')) return 'level-low'
  if (level.startsWith('⚠')) return 'level-mid'
  if (level.startsWith('✗')) return 'level-high'
  return ''
}

// ── Static qualitative assessments ──
const assessments = [
  {
    id: 'fund_holding',
    dimension: '公募基金持仓',
    reading: '头部基金高配',
    level: '⚠ 中',
    description: '主动权益基金对光模块、AI芯片配置比例处于历史高位，但尚未出现"断崖式重仓"。',
  },
  {
    id: 'northbound',
    dimension: '北向资金',
    reading: '仍在净流入',
    level: '✓ 低',
    description: '外资持续买入算力链龙头，与2021年抱团末期"内热外冷"特征不同，风险信号较低。',
  },
  {
    id: 'etf_issue',
    dimension: '新发基金主题',
    reading: 'AI主题密集',
    level: '⚠ 中高',
    description: '2026年以来AI主题ETF与主动基金密集发行，是阶段4后段的典型行为，需保持警惕。',
  },
  {
    id: 'valuation',
    dimension: '估值历史分位',
    reading: '龙头分化',
    level: '✓ 中',
    description: '龙头PE处于历史70–90分位，PEG因业绩高增长仍合理；二三线高估值标的分位数已接近95+。',
  },
  {
    id: 'story_stocks',
    dimension: '"故事股"信号',
    reading: '↑ 活跃度上升',
    level: '✗ 中高',
    description: '未盈利主题概念股交易活跃度上升，是拥挤度进入第5阶段的早期信号，建议压缩此类敞口。',
  },
  {
    id: 'margin_debt',
    dimension: '融资余额',
    reading: '抬升中',
    level: '⚠ 中',
    description: '杠杆资金参与度上升，放大双向波动，但绝对水平尚未到危险区间。',
  },
]
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

.detail-toggle {
  padding: 3px 12px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  background: #fff;
  color: #6b7280;
  font-size: 0.78em;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.detail-toggle:hover {
  background: #f3f4f6;
  border-color: #2563eb;
  color: #2563eb;
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

/* ── Qualitative assessment ── */
.assessment-section {
  margin-top: 8px;
}

.assessment-title {
  font-size: 0.78em;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
  padding: 0 2px;
}

.congestion-table-wrap {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.congestion-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82em;
}

.congestion-table th {
  background: #f9fafb;
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}

.congestion-table td {
  padding: 9px 12px;
  border-bottom: 1px solid #f3f4f6;
  vertical-align: top;
  line-height: 1.5;
  color: #374151;
}

.congestion-table tbody tr:last-child td {
  border-bottom: none;
}

.congestion-table tbody tr:hover {
  background: #f9fafb;
}

.col-dim     { width: 120px; min-width: 100px; font-weight: 600; color: #1f2937; }
.col-reading { width: 100px; min-width: 80px; }
.col-level   { width: 70px; min-width: 60px; }
.col-desc    { color: #6b7280; }

.level-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8em;
  font-weight: 700;
  white-space: nowrap;
}

.level-low  { background: #dcfce7; color: #15803d; }
.level-mid  { background: #fef9c3; color: #a16207; }
.level-high { background: #fee2e2; color: #b91c1c; }

/* ── Transition ── */
.slide-enter-active, .slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to, .slide-leave-from {
  opacity: 1;
  max-height: 1000px;
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
