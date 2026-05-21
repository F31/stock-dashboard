<template>
  <div class="macro-section">
    <!-- Header -->
    <div class="macro-hdr">
      <span class="macro-ttl">🌐 宏观数据监控</span>
      <div class="hdr-right">
        <span class="update-hint" v-if="lastUpdate">{{ lastUpdate }}</span>
        <button class="refresh-btn" :class="{ spinning: loading }" @click="forceRefresh" title="强制刷新">↻</button>
      </div>
    </div>

    <div v-if="loading && !hasData" class="loading-tip">宏观数据加载中...</div>

    <div v-else class="macro-body">
      <!-- ── 国债收益率 ── -->
      <div class="yield-row">
        <!-- 美国国债 -->
        <div class="yield-card">
          <div class="ycard-hdr">
            <span class="flag">🇺🇸</span>
            <span class="ycard-title">美国国债收益率</span>
            <span class="ycard-date" v-if="yields.date">{{ yields.date }}</span>
          </div>
          <div v-if="yields.us?.length" class="yield-list">
            <div v-for="y in yields.us" :key="y.term" class="yield-item">
              <span class="y-term">{{ y.term }}</span>
              <span class="y-bar-wrap">
                <span class="y-bar us-bar" :style="barStyle(y.value, 0, 6)"></span>
              </span>
              <span class="y-val">{{ y.value.toFixed(2) }}%</span>
            </div>
          </div>
          <div v-else class="no-yield">暂无数据</div>
        </div>

        <!-- 中国国债 -->
        <div class="yield-card">
          <div class="ycard-hdr">
            <span class="flag">🇨🇳</span>
            <span class="ycard-title">中国国债收益率</span>
            <span class="ycard-date" v-if="yields.date">{{ yields.date }}</span>
          </div>
          <div v-if="yields.cn?.length" class="yield-list">
            <div v-for="y in yields.cn" :key="y.term" class="yield-item">
              <span class="y-term">{{ y.term }}</span>
              <span class="y-bar-wrap">
                <span class="y-bar cn-bar" :style="barStyle(y.value, 0, 4)"></span>
              </span>
              <span class="y-val">{{ y.value.toFixed(2) }}%</span>
            </div>
          </div>
          <div v-else class="no-yield">暂无数据</div>
        </div>
      </div>

      <!-- 中美利差 -->
      <div class="spread-row" v-if="yields.spread_10y != null">
        <span class="spread-label">中美利差（10Y）</span>
        <span :class="['spread-val', yields.spread_10y < 0 ? 'neg' : 'pos']">
          {{ yields.spread_10y > 0 ? '+' : '' }}{{ yields.spread_10y.toFixed(2) }}%
        </span>
        <span class="spread-desc">{{ yields.spread_10y < 0 ? '中债收益率低于美债' : '中债收益率高于美债' }}</span>
      </div>

      <!-- ── 中国经济指标 ── -->
      <div class="section-title">🇨🇳 中国经济指标</div>
      <div class="indicator-row">
        <!-- CPI -->
        <div class="ind-card">
          <div class="ind-hdr">
            <span class="ind-icon">📊</span>
            <span class="ind-label">中国 CPI</span>
            <span class="ind-period">{{ cpi.period || '--' }}</span>
          </div>
          <div class="ind-main" :class="cpiClass">
            <span class="ind-big">{{ fmtPct(cpi.yoy) }}</span>
            <span class="ind-unit">同比</span>
          </div>
          <div class="ind-sub" v-if="cpi.prev != null">
            前值 {{ fmtPct(cpi.prev) }}
          </div>
          <div class="ind-tag" :class="cpiClass">{{ cpiTag }}</div>
        </div>

        <!-- PPI -->
        <div class="ind-card">
          <div class="ind-hdr">
            <span class="ind-icon">🏭</span>
            <span class="ind-label">中国 PPI</span>
            <span class="ind-period">{{ ppi.period || '--' }}</span>
          </div>
          <div class="ind-main" :class="ppiClass">
            <span class="ind-big">{{ fmtPct(ppi.yoy) }}</span>
            <span class="ind-unit">同比</span>
          </div>
          <div class="ind-sub" v-if="ppi.prev != null">
            前值 {{ fmtPct(ppi.prev) }}
          </div>
          <div class="ind-tag" :class="ppiClass">{{ ppiTag }}</div>
        </div>

        <!-- 制造业 PMI -->
        <div class="ind-card">
          <div class="ind-hdr">
            <span class="ind-icon">🔩</span>
            <div class="ind-label-wrap">
              <span class="ind-label">制造业 PMI</span>
              <span class="ind-source" v-if="pmi.mfg_source">{{ pmi.mfg_source }}</span>
            </div>
            <span class="ind-period">{{ pmi.mfg_period || '--' }}</span>
          </div>
          <div class="ind-main" :class="mfgPmiClass">
            <span class="ind-big">{{ fmtNum(pmi.mfg_value) }}</span>
            <span class="ind-threshold">荣枯线 50</span>
          </div>
          <div class="ind-sub" v-if="pmi.mfg_prev != null">
            前值 {{ fmtNum(pmi.mfg_prev) }}
          </div>
          <div class="ind-tag" :class="mfgPmiClass">{{ mfgPmiTag }}</div>
        </div>

        <!-- 非制造业 PMI -->
        <div class="ind-card" v-if="pmi.svc_value != null">
          <div class="ind-hdr">
            <span class="ind-icon">🏢</span>
            <span class="ind-label">非制造业 PMI</span>
            <span class="ind-period">{{ pmi.svc_period || '--' }}</span>
          </div>
          <div class="ind-main" :class="svcPmiClass">
            <span class="ind-big">{{ fmtNum(pmi.svc_value) }}</span>
            <span class="ind-threshold">荣枯线 50</span>
          </div>
          <div class="ind-sub" v-if="pmi.svc_prev != null">
            前值 {{ fmtNum(pmi.svc_prev) }}
          </div>
          <div class="ind-tag" :class="svcPmiClass">{{ svcPmiTag }}</div>
        </div>
      </div>

      <!-- ── 美国经济指标（FRED） ── -->
      <div class="section-title" v-if="usFred && Object.keys(usFred).length">🇺🇸 美国经济指标 <span class="fred-badge">FRED</span></div>
      <div class="indicator-row us-row" v-if="usFred && Object.keys(usFred).length">
        <div class="ind-card" v-for="(item, key) in usFred" :key="key">
          <div class="ind-hdr">
            <span class="ind-icon">{{ usFredIcon(key) }}</span>
            <span class="ind-label">{{ item.label }}</span>
            <span class="ind-period">{{ fmtFredPeriod(item.period) }}</span>
          </div>
          <div class="ind-main" :class="usFredClass(key, item.value)">
            <span class="ind-big us-big">{{ item.value }}</span>
          </div>
          <div class="ind-sub" v-if="item.previous">前值 {{ item.previous }}</div>
          <div class="ind-tag" :class="usFredClass(key, item.value)">{{ usFredTag(key, item.value) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchMacroData, refreshMacroData } from '../api'

const macro = ref({})
const loading = ref(false)
const lastUpdate = ref('')
let timer = null

// Shortcuts to nested data
const yields = computed(() => macro.value.yields || {})
const cpi    = computed(() => macro.value.cn_cpi || {})
const ppi    = computed(() => macro.value.cn_ppi || {})
const pmi    = computed(() => macro.value.cn_pmi || {})
const usFred = computed(() => macro.value.us_fred || {})

const hasData = computed(() =>
  yields.value.us?.length || cpi.value.yoy != null || ppi.value.yoy != null
    || Object.keys(usFred.value).length > 0
)

async function load(forced = false) {
  loading.value = true
  try {
    const res = forced ? await refreshMacroData() : await fetchMacroData()
    macro.value = res.data || {}
    const now = new Date()
    lastUpdate.value = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')} 更新`
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function forceRefresh() { load(true) }

onMounted(() => {
  load()
  timer = setInterval(load, 60 * 60 * 1000)  // hourly refresh
})
onUnmounted(() => { if (timer) clearInterval(timer) })

// ── Formatters ──
function fmtPct(v) {
  if (v == null) return '--'
  const s = v >= 0 ? '+' : ''
  return `${s}${v.toFixed(2)}%`
}
function fmtNum(v) {
  if (v == null) return '--'
  return v.toFixed(1)
}
function barStyle(value, lo, hi) {
  const pct = Math.min(96, Math.max(4, ((value - lo) / (hi - lo)) * 100))
  return { width: `${pct}%` }
}

// ── CPI ──
const cpiClass = computed(() => {
  const v = cpi.value.yoy
  if (v == null) return 'neutral'
  if (v < 0)   return 'deflation'
  if (v > 3)   return 'hot'
  if (v < 0.5) return 'weak'
  return 'normal'
})
const cpiTag = computed(() => {
  const v = cpi.value.yoy
  if (v == null) return '--'
  if (v < 0)    return '通缩压力'
  if (v < 0.5)  return '温和偏低'
  if (v <= 3)   return '温和正常'
  return '偏高注意'
})

// ── PPI ──
const ppiClass = computed(() => {
  const v = ppi.value.yoy
  if (v == null) return 'neutral'
  if (v < -3)  return 'deflation'
  if (v < 0)   return 'weak'
  if (v > 5)   return 'hot'
  return 'normal'
})
const ppiTag = computed(() => {
  const v = ppi.value.yoy
  if (v == null) return '--'
  if (v < -3)  return '深度通缩'
  if (v < 0)   return '温和通缩'
  if (v <= 3)  return '温和正常'
  return '上游通胀'
})

// ── PMI helpers ──
function pmiClass(v) {
  if (v == null) return 'neutral'
  if (v >= 52)  return 'hot'
  if (v >= 50)  return 'normal'
  if (v >= 48)  return 'weak'
  return 'deflation'
}
function pmiTag(v) {
  if (v == null) return '--'
  if (v >= 52)  return '较强扩张'
  if (v >= 50)  return '温和扩张'
  if (v >= 49)  return '轻微收缩'
  return '明显收缩'
}

const mfgPmiClass = computed(() => pmiClass(pmi.value.mfg_value))
const mfgPmiTag   = computed(() => pmiTag(pmi.value.mfg_value))
const svcPmiClass = computed(() => pmiClass(pmi.value.svc_value))
const svcPmiTag   = computed(() => pmiTag(pmi.value.svc_value))

// ── US FRED helpers ──
function fmtFredPeriod(p) {
  if (!p) return '--'
  return p.length >= 7 ? p.slice(0, 7) : p
}

const _fredIcons = {
  fed_rate: '🏦', cpi: '📊', ppi: '🏭',
  non_farm: '👷', unemployment: '📉', initial_jobless: '📋',
  retail_sales: '🛒',
}
function usFredIcon(key) { return _fredIcons[key] || '📌' }

function _parseNum(val) {
  if (val == null) return null
  const s = String(val).replace('%', '').replace('千人', '').replace('万人', '').trim()
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

function usFredClass(key, val) {
  const n = _parseNum(val)
  if (n == null) return 'neutral'
  if (key === 'fed_rate')       return n > 4 ? 'hot' : n > 2 ? 'normal' : 'weak'
  if (key === 'cpi')            return n > 4 ? 'hot' : n > 2 ? 'normal' : n < 0 ? 'deflation' : 'weak'
  if (key === 'ppi')            return n > 5 ? 'hot' : n > 0 ? 'normal' : 'deflation'
  if (key === 'non_farm')       return n > 200 ? 'hot' : n > 100 ? 'normal' : n > 0 ? 'weak' : 'deflation'
  if (key === 'unemployment')   return n > 5 ? 'hot' : n < 4 ? 'normal' : 'weak'
  if (key === 'retail_sales')   return n > 0.5 ? 'normal' : n > 0 ? 'weak' : 'deflation'
  return 'neutral'
}

function usFredTag(key, val) {
  const n = _parseNum(val)
  if (n == null) return '--'
  if (key === 'fed_rate')       return n > 4 ? '偏紧' : n > 2 ? '中性' : '宽松'
  if (key === 'cpi')            return n > 4 ? '通胀偏热' : n > 2 ? '温和' : n < 0 ? '通缩' : '偏低'
  if (key === 'ppi')            return n > 5 ? '上游通胀' : n > 0 ? '温和' : '通缩'
  if (key === 'non_farm')       return n > 200 ? '强劲' : n > 100 ? '稳健' : n > 0 ? '偏弱' : '收缩'
  if (key === 'unemployment')   return n > 5 ? '偏高' : n < 4 ? '低位' : '正常'
  if (key === 'initial_jobless') return n < 15 ? '偏低' : n < 25 ? '正常' : '偏高'
  if (key === 'retail_sales')   return n > 0.5 ? '强劲' : n > 0 ? '温和' : '走弱'
  return '--'
}
</script>

<style scoped>
.macro-section { padding: 0 0 24px; }

/* ── Header ── */
.macro-hdr {
  display: flex; align-items: center;
  justify-content: space-between; margin-bottom: 10px;
}
.macro-ttl { font-size: 0.88em; font-weight: 700; color: #374151; letter-spacing: 0.3px; }
.hdr-right { display: flex; align-items: center; gap: 8px; }
.update-hint { font-size: 0.72em; color: #9ca3af; }
.refresh-btn {
  background: none; border: 1px solid #e5e7eb; border-radius: 5px;
  color: #6b7280; font-size: 1em; cursor: pointer;
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.refresh-btn:hover { border-color: #3b82f6; color: #3b82f6; background: #eff6ff; }
.refresh-btn.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.loading-tip { padding: 20px; text-align: center; font-size: 0.82em; color: #9ca3af; }
.macro-body { display: flex; flex-direction: column; gap: 10px; }

/* ── Yield cards ── */
.yield-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

.yield-card {
  background: #fff; border: 1px solid #e5e7eb;
  border-radius: 10px; padding: 12px 14px;
}
.ycard-hdr { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; }
.flag { font-size: 1.1em; }
.ycard-title { font-size: 0.82em; font-weight: 700; color: #374151; flex: 1; }
.ycard-date { font-size: 0.7em; color: #9ca3af; }

.yield-list { display: flex; flex-direction: column; gap: 7px; }
.yield-item { display: flex; align-items: center; gap: 8px; font-size: 0.8em; }
.y-term { width: 28px; color: #6b7280; font-weight: 600; flex-shrink: 0; }
.y-bar-wrap {
  flex: 1; height: 6px; background: #f3f4f6;
  border-radius: 3px; overflow: hidden;
}
.y-bar { display: block; height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.us-bar { background: linear-gradient(90deg, #93c5fd, #2563eb); }
.cn-bar { background: linear-gradient(90deg, #6ee7b7, #059669); }
.y-val {
  width: 48px; text-align: right;
  font-family: 'SF Mono', 'Menlo', monospace;
  font-weight: 700; color: #1f2937; font-size: 0.92em;
}
.no-yield { font-size: 0.78em; color: #9ca3af; padding: 8px 0; text-align: center; }

/* ── Spread row ── */
.spread-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 14px; background: #f8fafc;
  border: 1px solid #e5e7eb; border-radius: 8px; font-size: 0.8em;
  flex-wrap: wrap;
}
.spread-label { color: #6b7280; font-weight: 600; flex-shrink: 0; }
.spread-val { font-family: 'SF Mono', 'Menlo', monospace; font-weight: 700; }
.spread-val.neg { color: #7c3aed; }
.spread-val.pos { color: #059669; }
.spread-desc { color: #9ca3af; font-size: 0.88em; }

/* ── Indicator cards ── */
.indicator-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}
.ind-card {
  background: #fff; border: 1px solid #e5e7eb;
  border-radius: 10px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 4px;
}
.ind-hdr { display: flex; align-items: flex-start; gap: 5px; margin-bottom: 4px; }
.ind-icon { font-size: 0.95em; flex-shrink: 0; margin-top: 1px; }
.ind-label-wrap { display: flex; flex-direction: column; gap: 1px; flex: 1; }
.ind-label { font-size: 0.78em; font-weight: 700; color: #374151; }
.ind-source { font-size: 0.65em; color: #9ca3af; }
.ind-period { font-size: 0.68em; color: #9ca3af; white-space: nowrap; margin-left: auto; }

.ind-main { display: flex; align-items: baseline; gap: 4px; }
.ind-big {
  font-size: 1.6em; font-weight: 900;
  font-family: 'SF Mono', 'Menlo', monospace; line-height: 1;
}
.ind-unit { font-size: 0.7em; color: #9ca3af; }
.ind-threshold { font-size: 0.68em; color: #9ca3af; }
.ind-sub { font-size: 0.72em; color: #6b7280; }
.ind-tag {
  font-size: 0.68em; font-weight: 600;
  padding: 2px 7px; border-radius: 4px;
  display: inline-block; align-self: flex-start; margin-top: 2px;
}

/* ── Color themes ── */
.ind-main.normal    .ind-big { color: #059669; }
.ind-main.hot       .ind-big { color: #dc2626; }
.ind-main.weak      .ind-big { color: #d97706; }
.ind-main.deflation .ind-big { color: #7c3aed; }
.ind-main.neutral   .ind-big { color: #6b7280; }

.ind-tag.normal    { background: #dcfce7; color: #15803d; }
.ind-tag.hot       { background: #fee2e2; color: #b91c1c; }
.ind-tag.weak      { background: #fef3c7; color: #92400e; }
.ind-tag.deflation { background: #ede9fe; color: #6d28d9; }
.ind-tag.neutral   { background: #f3f4f6; color: #6b7280; }

/* ── Section title ── */
.section-title {
  font-size: 0.78em; font-weight: 700; color: #374151;
  padding: 4px 0 2px; letter-spacing: 0.3px;
  display: flex; align-items: center; gap: 6px;
}
.fred-badge {
  font-size: 0.72em; background: #dbeafe; color: #2563eb;
  padding: 1px 6px; border-radius: 4px; font-weight: 600;
}

/* US FRED row — slightly smaller number to fit value+unit */
.us-big { font-size: 1.3em !important; }

/* ── Responsive ── */
@media (max-width: 640px) {
  .yield-row { grid-template-columns: 1fr; }
  .indicator-row { grid-template-columns: 1fr 1fr; }
  .ind-big { font-size: 1.3em; }
  .spread-row { gap: 6px; }
}
</style>
