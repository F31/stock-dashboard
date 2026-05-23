<template>
  <div class="card" :class="{ 'card-loading': !stock.data }">
    <!-- Card Header -->
    <div class="card-hdr">
      <div class="card-hdr-l">
        <div v-if="!renamingName" class="sname">
          <span v-if="!isSector" :class="['mkt-tag', badgeClass]">{{ marketLabel }}</span>
          <span class="sname-text" @click.stop="$emit('open-detail', stock)">{{ stock.data?.stock_name || stock.stock_name || stock.stock_code }}</span>
          <button class="report-btn" @click.stop="$emit('open-detail', stock, 'reports')" title="查看分析报告">分析报告</button>
          <button v-if="isSector" class="rename-btn" @click.stop="startRename" title="修改名称">✎</button>
        </div>
        <div v-else class="rename-row">
          <input
            ref="renameInputRef"
            class="rename-input"
            v-model="renameValue"
            @keydown.enter="saveRename"
            @keydown.esc="cancelRename"
            placeholder="输入板块名称"
          />
          <button class="rename-save" @click="saveRename">✓</button>
          <button class="rename-cancel" @click="cancelRename">✕</button>
        </div>
        <div class="scode">{{ stock.stock_code }}</div>
      </div>
      <div class="card-hdr-r">
        <span v-if="isSector" class="badge badge-sector">板块</span>
        <span v-if="!isSector && quanScore" :class="['sig-badge', quanBadgeCls]">
          {{ quanScore.label }}
          <em>({{ Math.round(quanScore.percentile_score) }})</em>
        </span>
        <button class="del-btn" @click="$emit('remove')" title="删除">×</button>
      </div>
    </div>

    <!-- Sector: sub-type line -->
    <div class="sector-sub" v-if="isSector && stock.data?.board_type">
      {{ stock.data.board_type === 'concept' ? '概念板块' : '行业板块' }}
    </div>

    <!-- Price Area -->
    <div class="price-area">
      <template v-if="isSector">
        <div v-if="stock.data?.price != null" class="price-row">
          <div :class="['cprice', priceTrend]">{{ fmtSectorIndex(stock.data.price) }}</div>
          <span :class="['ctag', priceTrend]">{{ fmtChangePct(stock.data.change_pct) }}</span>
        </div>
        <div v-else-if="stock.data?.change_pct != null" class="sector-chg-only">
          <span :class="['chg-pct-big', priceTrend]">{{ fmtChangePct(stock.data.change_pct) }}</span>
          <span class="chg-hint">今日涨跌</span>
        </div>
        <div v-else class="no-data-notice">行情数据加载中...</div>
        <div class="prev-close" v-if="stock.data?.prev_close">
          昨收 {{ fmtSectorIndex(stock.data.prev_close) }}
        </div>
      </template>
      <template v-else>
        <div class="price-row" v-if="stock.data">
          <div :class="['cprice', priceTrend]">
            {{ stock.data.price != null ? fmtPrice(stock.data.price) : '--' }}
          </div>
          <span :class="['ctag', priceTrend]">
            {{ stock.data.change != null ? fmtChange(stock.data.change_pct, stock.data.change) : '--' }}
          </span>
        </div>
        <div class="price-row" v-else>
          <div class="cprice flat">--</div>
          <span class="ctag flat">--</span>
        </div>
        <div class="prev-close" v-if="stock.data?.prev_close">
          昨收 {{ fmtPrice(stock.data.prev_close) }}
        </div>
      </template>
    </div>

    <!-- Stock Metrics: PE(动态) | PEG | 净利增速 | 总市值 -->
    <div class="metrics" v-if="!isSector">
      <div class="met">
        <div class="met-l">PE(动态)</div>
        <div class="met-v">{{ stock.data?.pe != null ? stock.data.pe.toFixed(1) + '×' : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">PEG</div>
        <div class="met-v">{{ stock.data?.peg != null ? stock.data.peg.toFixed(2) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">净利增速</div>
        <div class="met-v" :class="growthClass">{{ stock.data?.profit_growth_rate != null ? (stock.data.profit_growth_rate > 0 ? '+' : '') + stock.data.profit_growth_rate.toFixed(1) + '%' : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">总市值</div>
        <div class="met-v">{{ stock.data?.market_cap != null ? fmtMarketCap(stock.data.market_cap) : '--' }}</div>
      </div>
    </div>

    <!-- Financial Fundamentals: ROE | 负债率 | 现金质量 | Capex -->
    <div class="metrics fin-row" v-if="!isSector && (stock.data?.roe != null || stock.data?.debt_ratio != null || stock.data?.cash_profit_ratio != null || stock.data?.capex != null)">
      <div class="met">
        <div class="met-l">ROE</div>
        <div class="met-v" :class="stock.data?.roe >= 15 ? 'roe-hi' : stock.data?.roe >= 8 ? '' : 'roe-lo'">
          {{ stock.data?.roe != null ? stock.data.roe.toFixed(1) + '%' : '--' }}
        </div>
      </div>
      <div class="met">
        <div class="met-l">负债率</div>
        <div class="met-v" :class="stock.data?.debt_ratio > 70 ? 'debt-hi' : ''">
          {{ stock.data?.debt_ratio != null ? stock.data.debt_ratio.toFixed(1) + '%' : '--' }}
        </div>
      </div>
      <div class="met">
        <div class="met-l">现金质量</div>
        <div class="met-v" :class="stock.data?.cash_profit_ratio >= 80 ? 'cf-hi' : stock.data?.cash_profit_ratio < 30 ? 'cf-lo' : ''">
          {{ stock.data?.cash_profit_ratio != null ? stock.data.cash_profit_ratio.toFixed(0) + '%' : '--' }}
        </div>
      </div>
      <div class="met">
        <div class="met-l">{{ stock.data?.capex_period ? `Capex(${stock.data.capex_period})` : 'Capex' }}</div>
        <div class="met-v">{{ fmtCapex(stock.data?.capex) }}</div>
      </div>
    </div>

    <!-- News Area -->
    <div class="news-area" v-if="!isSector && stock.data?.news && stock.data.news.length">
      <div class="sec-ttl">📰 最新资讯</div>
      <div class="ni" v-for="(item, i) in stock.data.news.slice(0, 4)" :key="i">
        <div class="ni-t">
          <a :href="item.url" target="_blank" rel="noopener">{{ item.title }}</a>
        </div>
        <div class="ni-m">{{ item.source }} · {{ item.time }}</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const props = defineProps({
  stock: Object,
  quanScore: { type: Object, default: null },  // { percentile_score, label }
})
const emit = defineEmits(['remove', 'rename', 'open-detail'])

const renamingName = ref(false)
const renameValue = ref('')
const renameInputRef = ref(null)

function startRename() {
  renameValue.value = props.stock.data?.stock_name || props.stock.stock_name || ''
  renamingName.value = true
  nextTick(() => renameInputRef.value?.focus())
}

function saveRename() {
  const name = renameValue.value.trim()
  if (name) emit('rename', props.stock.id, name)
  renamingName.value = false
}

function cancelRename() {
  renamingName.value = false
}

const marketLabel = computed(() => {
  const m = props.stock.market
  if (m === 'A') return 'A股'
  if (m === 'HK') return '港股'
  if (m === 'US') return '美股'
  return m
})

const badgeClass = computed(() => {
  const m = props.stock.market
  if (m === 'A') return 'ba'
  if (m === 'HK') return 'bh'
  if (m === 'US') return 'bu'
  return ''
})

const priceTrend = computed(() => {
  const d = props.stock.data
  if (!d) return 'flat'
  const val = d.change ?? d.change_pct
  if (val == null) return 'flat'
  return val >= 0 ? 'up' : 'down'
})

const quanBadgeCls = computed(() => {
  if (!props.quanScore) return ''
  const p = props.quanScore.percentile_score
  if (p >= 90) return 'sig-strong'
  if (p >= 75) return 'sig-buy'
  if (p >= 50) return 'sig-neutral'
  return 'sig-avoid'
})

const quanBadgeClass = computed(() => {
  if (!props.quanScore) return ''
  const p = props.quanScore.percentile_score
  if (p >= 90) return 'qb-strong'
  if (p >= 75) return 'qb-buy'
  if (p >= 50) return 'qb-neutral'
  return 'qb-avoid'
})

const growthClass = computed(() => {
  const g = props.stock.data?.profit_growth_rate
  if (g == null) return ''
  return g >= 0 ? 'up' : 'down'
})

const isSector = computed(() => {
  return props.stock.item_type === 'sector' || props.stock.data?.item_type === 'sector'
})

function fmtPrice(v) {
  const m = props.stock.market
  if (m === 'US') return `$${v.toFixed(2)}`
  return `¥${v.toFixed(2)}`
}

function fmtSectorIndex(v) {
  if (v == null) return '--'
  return v.toFixed(2)
}

function fmtChangePct(pct) {
  if (pct == null) return '--'
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function fmtChange(pct, abs) {
  const sign = pct >= 0 ? '+' : ''
  if (abs == null) return `${sign}${pct.toFixed(2)}%`
  return `${sign}${pct.toFixed(2)}% (${sign}${abs.toFixed(2)})`
}

function fmtMarketCap(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(1) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(1) + '万'
  return v.toFixed(0)
}

function fmtAmount(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

function fmtCapex(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(1) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toFixed(0)
}

</script>

<style scoped>
.card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06);
  overflow: hidden;
  position: relative;
  transition: box-shadow .2s;
}

/* Quantitative score corner badge */
.quan-corner {
  position: absolute; top: 0; right: 0;
  font-size: 9px; font-weight: 800;
  padding: 2px 5px 2px 6px;
  border-radius: 0 12px 0 8px;
  line-height: 1.4; pointer-events: none; z-index: 1;
}
.qb-strong { background: #dcfce7; color: #15803d; }
.qb-buy    { background: #d1fae5; color: #047857; }
.qb-neutral{ background: #f3f4f6; color: #6b7280; }
.qb-avoid  { background: #fee2e2; color: #dc2626; }
.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.1); }
.card-loading { opacity: .5; pointer-events: none; }

.card-hdr {
  padding: 10px 12px 4px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.card-hdr-l { flex: 1; min-width: 0; }
.sname { font-size: 14px; font-weight: 800; line-height: 1.2; color: #111827; display: flex; align-items: center; gap: 4px; }
.sname-text { cursor: pointer; }
.sname-text:hover { color: #2563eb; text-decoration: underline; }
.scode { font-size: 11px; color: #6b7280; margin-top: 1px; }

.report-btn {
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  cursor: pointer;
  font-size: 10px;
  color: #6b7280;
  padding: 1px 5px;
  line-height: 1.4;
  flex-shrink: 0;
  transition: all .15s;
}
.report-btn:hover { background: #eff6ff; border-color: #93c5fd; color: #2563eb; }
.rename-btn {
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: #9ca3af; padding: 0 2px;
  line-height: 1; opacity: 0.6; flex-shrink: 0;
}
.rename-btn:hover { color: #3b82f6; opacity: 1; }

.rename-row { display: flex; align-items: center; gap: 4px; }
.rename-input {
  flex: 1; min-width: 0;
  font-size: 13px; font-weight: 700; color: #111827;
  border: 1px solid #3b82f6; border-radius: 4px;
  padding: 2px 6px; background: #eff6ff; font-family: inherit;
}
.rename-input:focus { outline: none; }
.rename-save, .rename-cancel {
  background: none; border: none; cursor: pointer;
  font-size: 14px; padding: 0 3px; line-height: 1; flex-shrink: 0;
}
.rename-save { color: #16a34a; }
.rename-save:hover { color: #15803d; }
.rename-cancel { color: #9ca3af; }
.rename-cancel:hover { color: #dc2626; }

.card-hdr-r { display: flex; align-items: center; gap: 5px; flex-shrink: 0; margin-left: 6px; }

.badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; }
.badge-sector { background: #fce7f3; color: #9d174d; }

/* Market tag inline before stock name */
.mkt-tag {
  font-size: 10px; font-weight: 700;
  padding: 1px 5px; border-radius: 8px;
  flex-shrink: 0; white-space: nowrap; line-height: 1.6;
}
.ba { background: #fef3c7; color: #92400e; }
.bh { background: #dbeafe; color: #1e40af; }
.bu { background: #ede9fe; color: #5b21b6; }

.sector-sub { padding: 0 12px 4px; font-size: 11px; color: #9ca3af; }

.del-btn {
  background: none; border: none; cursor: pointer;
  font-size: 16px; color: #9ca3af;
  width: 24px; height: 24px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; line-height: 1;
}
.del-btn:hover { background: #fee2e2; color: #dc2626; }

.price-area { padding: 4px 12px 6px; }
.price-row { display: flex; align-items: flex-end; gap: 8px; }
.cprice { font-size: 24px; font-weight: 900; line-height: 1; }
.cprice.up { color: #dc2626; }
.cprice.down { color: #16a34a; }
.cprice.flat { color: #6b7280; }

.ctag { font-size: 13px; font-weight: 700; padding: 4px 9px; border-radius: 6px; white-space: nowrap; }
.ctag.up { color: #dc2626; background: #fee2e2; }
.ctag.down { color: #16a34a; background: #dcfce7; }
.ctag.flat { color: #6b7280; background: #f3f4f6; }

.prev-close { font-size: 12px; color: #6b7280; margin-top: 3px; }

.sector-chg-only { display: flex; align-items: baseline; gap: 10px; padding: 4px 0 2px; }
.chg-pct-big { font-size: 28px; font-weight: 900; line-height: 1; }
.chg-pct-big.up { color: #dc2626; }
.chg-pct-big.down { color: #16a34a; }
.chg-pct-big.flat { color: #6b7280; }
.chg-hint { font-size: 11px; color: #9ca3af; font-weight: 500; }
.no-data-notice { padding: 8px 0 4px; font-size: 13px; font-weight: 500; color: #9ca3af; }

.metrics {
  display: flex;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}
.met { flex: 1; padding: 6px 2px; text-align: center; }
.met + .met { border-left: 1px solid #e5e7eb; }
.met-l { font-size: 9.5px; color: #6b7280; letter-spacing: .2px; margin-bottom: 3px; }
.met-v { font-size: 13px; font-weight: 700; color: #111827; }
.met-v.up { color: #dc2626; }
.met-v.down { color: #16a34a; }

/* Quant rating badge (replaces signal badge) */
.sig-badge {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 11px; font-weight: 700;
  padding: 2px 7px; border-radius: 10px; white-space: nowrap;
}
.sig-badge em { font-style: normal; font-weight: 500; font-size: 10px; opacity: 0.85; }
.sig-strong { background: #dcfce7; color: #15803d; }
.sig-buy    { background: #d1fae5; color: #047857; }
.sig-neutral{ background: #dbeafe; color: #1d4ed8; }
.sig-avoid  { background: #fee2e2; color: #dc2626; }

/* Financial fundamentals row */
.fin-row { background: #f9fafb; }
.roe-hi  { color: #15803d; }
.roe-lo  { color: #9ca3af; }
.debt-hi { color: #dc2626; }
.cf-hi   { color: #15803d; }
.cf-lo   { color: #f59e0b; }


.news-area { padding: 8px 12px; }
.sec-ttl { font-size: 11px; font-weight: 700; color: #6b7280; letter-spacing: .5px; text-transform: uppercase; }

.ni { padding: 6px 0; border-bottom: 1px solid #e5e7eb; }
.ni:last-child { border-bottom: none; }
.ni-t a {
  font-size: 13px; line-height: 1.45; color: #111827;
  text-decoration: none;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.ni-t a:hover { color: #3b82f6; }
.ni-m { font-size: 11px; color: #9ca3af; margin-top: 2px; }

.close-btn {
  background: none; border: none; font-size: 22px; color: #9ca3af;
  cursor: pointer; width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center; border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

@media (max-width: 640px) {
  .card { border-radius: 8px; }
  .card-hdr { padding: 10px 10px 2px; }
  .sname { font-size: 13px; }
  .scode { font-size: 10px; }
  .del-btn { width: 32px; height: 32px; font-size: 18px; }
  .price-area { padding: 4px 10px 6px; }
  .cprice { font-size: 22px; }
  .ctag { font-size: 12px; padding: 3px 8px; }
  .chg-pct-big { font-size: 24px; }
  .metrics { flex-wrap: wrap; }
  .met { padding: 5px 2px; min-width: 25%; }
  .met-l { font-size: 9px; }
  .met-v { font-size: 12px; }
  .news-area { padding: 6px 10px; display: none; }
  .prev-close { font-size: 11px; }
}

@media (min-width: 641px) and (max-width: 960px) {
  .card-hdr { padding: 10px 12px 4px; }
  .sname { font-size: 13px; }
}
</style>
