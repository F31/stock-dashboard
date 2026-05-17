<template>
  <div class="card" :class="{ 'card-loading': !stock.data }">
    <!-- Card Header -->
    <div class="card-hdr">
      <div class="card-hdr-l">
        <div v-if="!renamingName" class="sname">
          <span class="sname-text" @click.stop="$emit('open-detail', stock)">{{ stock.data?.stock_name || stock.stock_name || stock.stock_code }}</span>
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
        <span :class="['badge', badgeClass]" v-else>{{ marketLabel }}</span>
        <button class="del-btn" @click="$emit('remove')" title="删除">×</button>
      </div>
    </div>

    <!-- Sector: sub-type line (行业/概念) -->
    <div class="sector-sub" v-if="isSector && stock.data?.board_type">
      {{ stock.data.board_type === 'concept' ? '概念板块' : '行业板块' }}
    </div>

    <!-- Price Area -->
    <div class="price-area">
      <!-- Sector: show change_pct if available; fallback to "no data" -->
      <template v-if="isSector">
        <div v-if="stock.data?.price != null" class="price-row">
          <div :class="['cprice', priceTrend]">{{ fmtSectorIndex(stock.data.price) }}</div>
          <span :class="['ctag', priceTrend]">{{ fmtChangePct(stock.data.change_pct) }}</span>
        </div>
        <div v-else-if="stock.data?.change_pct != null" class="sector-chg-only">
          <span :class="['chg-pct-big', priceTrend]">{{ fmtChangePct(stock.data.change_pct) }}</span>
          <span class="chg-hint">今日涨跌</span>
        </div>
        <div v-else class="no-data-notice">
          行情数据加载中...
        </div>
        <div class="prev-close" v-if="stock.data?.prev_close">
          昨收 {{ fmtSectorIndex(stock.data.prev_close) }}
        </div>
      </template>
      <!-- Regular stock -->
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

    <!-- Chart Area -->
    <div class="chart-wrap" v-if="!isSector">
      <svg v-if="stock.data?.chart_data && stock.data.chart_data.length >= 2"
        :viewBox="`0 0 ${chartW} ${chartH}`" class="sparkline">
        <polyline
          :points="chartPoints"
          :fill="chartColor + '22'"
          :stroke="chartColor"
          stroke-width="1.5"
        />
      </svg>
      <div v-else class="chart-ph">暂无历史数据</div>
    </div>

    <!-- Metrics Row (stock: PE/mktcap/turnover; sector: up/down counts) -->
    <div class="metrics" v-if="!isSector">
      <div class="met">
        <div class="met-l">市盈率 PE</div>
        <div class="met-v">{{ stock.data?.pe != null ? stock.data.pe.toFixed(1) + '×' : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">总市值</div>
        <div class="met-v">{{ stock.data?.market_cap != null ? fmtMarketCap(stock.data.market_cap) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">换手率</div>
        <div class="met-v">{{ stock.data?.turnover_rate != null ? stock.data.turnover_rate.toFixed(2) + '%' : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">今日波动</div>
        <div class="met-v met-v-sm">
          {{ stock.data?.high != null ? fmtPrice(stock.data.high) : '--' }}<br>
          {{ stock.data?.low != null ? fmtPrice(stock.data.low) : '--' }}
        </div>
      </div>
    </div>

    <!-- Sector Metrics: constituent stock counts -->
    <div class="metrics" v-if="isSector">
      <div class="met">
        <div class="met-l">上涨家数</div>
        <div class="met-v up">{{ stock.data?.up_count != null ? stock.data.up_count : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">下跌家数</div>
        <div class="met-v down">{{ stock.data?.down_count != null ? stock.data.down_count : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">总市值</div>
        <div class="met-v">{{ stock.data?.market_cap != null ? fmtMarketCap(stock.data.market_cap) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">成交额</div>
        <div class="met-v">{{ stock.data?.amount != null ? fmtAmount(stock.data.amount) : '--' }}</div>
      </div>
    </div>

    <!-- Extra Metrics Row (only for stocks) -->
    <div class="metrics metrics-extra" v-if="!isSector">
      <div class="met">
        <div class="met-l">成交量</div>
        <div class="met-v">{{ stock.data?.volume != null ? fmtVolume(stock.data.volume) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">成交额</div>
        <div class="met-v">{{ stock.data?.amount != null ? fmtAmount(stock.data.amount) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">流通市值</div>
        <div class="met-v">{{ stock.data?.float_market_cap != null ? fmtMarketCap(stock.data.float_market_cap) : '--' }}</div>
      </div>
      <div class="met">
        <div class="met-l">振幅</div>
        <div class="met-v">{{ stock.data?.amplitude != null ? stock.data.amplitude.toFixed(2) + '%' : '--' }}</div>
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

    <!-- Notes Area -->
    <div class="notes-area">
      <div class="sec-ttl-row">
        <div class="sec-ttl">📝 研究笔记</div>
        <button class="btn-enlarge" @click="openNotesModal" title="放大编辑">⛶</button>
      </div>
      <textarea
        class="notes-ta"
        :placeholder="notesPlaceholder"
        :value="stock.notes"
        @change="updateNotes"
      ></textarea>
    </div>

    <!-- Notes Editor Modal -->
    <Teleport to="body">
      <div class="notes-modal-overlay" v-if="showNotesModal" @click.self="closeNotesModal">
        <div class="notes-modal">
          <div class="notes-modal-hdr">
            <h3>📝 {{ notesModalTitle }} 研究笔记</h3>
            <button class="close-btn" @click="closeNotesModal">×</button>
          </div>
          <div class="notes-modal-body">
            <textarea
              ref="notesTextareaRef"
              class="notes-modal-ta"
              :value="editingNotes"
              @input="editingNotes = $event.target.value"
              placeholder="记录研究笔记、投资逻辑、目标价位..."
            ></textarea>
          </div>
          <div class="notes-modal-ftr">
            <span class="notes-char-count">{{ editingNotes.length }} 字</span>
            <div class="notes-modal-actions">
              <button class="btn btn-cancel" @click="closeNotesModal">取消</button>
              <button class="btn btn-save" @click="saveNotes">保存</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const props = defineProps({ stock: Object })
const emit = defineEmits(['remove', 'update-notes', 'rename', 'open-detail'])

// Notes editor modal
const showNotesModal = ref(false)
const editingNotes = ref('')
const notesTextareaRef = ref(null)

// Inline rename (for sector cards)
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

const notesModalTitle = computed(() => {
  return props.stock.data?.stock_name || props.stock.stock_name || props.stock.stock_code
})

function openNotesModal() {
  editingNotes.value = props.stock.notes || ''
  showNotesModal.value = true
  nextTick(() => {
    notesTextareaRef.value?.focus()
  })
}

function closeNotesModal() {
  showNotesModal.value = false
  editingNotes.value = ''
}

function saveNotes() {
  emit('update-notes', props.stock.id, editingNotes.value)
  showNotesModal.value = false
  editingNotes.value = ''
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
  // For sectors, change may be null but change_pct is available
  const val = d.change ?? d.change_pct
  if (val == null) return 'flat'
  return val >= 0 ? 'up' : 'down'
})

const notesPlaceholder = computed(() => {
  const name = props.stock.data?.stock_name || props.stock.stock_name || props.stock.stock_code
  return `记录${name}的研究笔记、投资逻辑、目标价位...`
})

const isSector = computed(() => {
  return props.stock.item_type === 'sector' || props.stock.data?.item_type === 'sector'
})

// Sparkline
const chartW = 360
const chartH = 60

const chartColor = computed(() => {
  const d = props.stock.data
  if (!d || d.change == null) return '#6b7280'
  return d.change >= 0 ? '#dc2626' : '#16a34a'
})

const chartPoints = computed(() => {
  const data = props.stock.data?.chart_data
  if (!data || data.length < 2) return ''
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const stepX = chartW / (data.length - 1)
  return data
    .map((v, i) => {
      const x = i * stepX
      const y = chartH - ((v - min) / range) * (chartH - 8) - 4
      return `${x},${y}`
    })
    .join(' ')
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
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  return (v / 1e4).toFixed(2) + '万'
}

function fmtVolume(v) {
  if (v == null) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(0)
}

function fmtAmount(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

function updateNotes(e) {
  emit('update-notes', props.stock.id, e.target.value)
}
</script>

<style scoped>
.card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06);
  overflow: hidden;
  transition: box-shadow .2s;
}
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

.rename-btn {
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: #9ca3af; padding: 0 2px;
  line-height: 1; opacity: 0.6;
  flex-shrink: 0;
}
.rename-btn:hover { color: #3b82f6; opacity: 1; }

.rename-row { display: flex; align-items: center; gap: 4px; }
.rename-input {
  flex: 1; min-width: 0;
  font-size: 13px; font-weight: 700; color: #111827;
  border: 1px solid #3b82f6; border-radius: 4px;
  padding: 2px 6px; background: #eff6ff;
  font-family: inherit;
}
.rename-input:focus { outline: none; }
.rename-save, .rename-cancel {
  background: none; border: none; cursor: pointer;
  font-size: 14px; padding: 0 3px; line-height: 1;
  flex-shrink: 0;
}
.rename-save { color: #16a34a; }
.rename-save:hover { color: #15803d; }
.rename-cancel { color: #9ca3af; }
.rename-cancel:hover { color: #dc2626; }

.card-hdr-r { display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: 6px; }

.badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; }
.ba { background: #fef3c7; color: #92400e; }
.bh { background: #dbeafe; color: #1e40af; }
.bu { background: #ede9fe; color: #5b21b6; }
.badge-sector { background: #fce7f3; color: #9d174d; }

.sector-sub {
  padding: 0 12px 4px;
  font-size: 11px;
  color: #9ca3af;
}

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

.sector-chg-only {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 4px 0 2px;
}
.chg-pct-big {
  font-size: 28px;
  font-weight: 900;
  line-height: 1;
}
.chg-pct-big.up { color: #dc2626; }
.chg-pct-big.down { color: #16a34a; }
.chg-pct-big.flat { color: #6b7280; }
.chg-hint {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
}
.no-data-notice {
  padding: 8px 0 4px;
  font-size: 13px;
  font-weight: 500;
  color: #9ca3af;
}

.chart-wrap { padding: 0 12px 6px; height: 54px; }
.chart-ph {
  height: 100%; display: flex; align-items: center; justify-content: center;
  font-size: 12px; color: #9ca3af;
}
.sparkline { width: 100%; height: 100%; }

.metrics {
  display: flex;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}
.met { flex: 1; padding: 6px 2px; text-align: center; }
.met + .met { border-left: 1px solid #e5e7eb; }
.met-l { font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: .3px; margin-bottom: 3px; }
.met-v { font-size: 13px; font-weight: 700; color: #111827; }
.met-v-sm { font-size: 11px; line-height: 1.4; }

.metrics-extra {
  border-top: none;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}
.metrics-extra .met { padding: 4px 2px; }
.metrics-extra .met-l { font-size: 9px; }
.metrics-extra .met-v { font-size: 11px; }

.news-area, .notes-area { padding: 8px 12px; }
.notes-area { padding-bottom: 10px; border-top: 1px solid #e5e7eb; }

/* Section title row with enlarge button */
.sec-ttl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sec-ttl { font-size: 11px; font-weight: 700; color: #6b7280; letter-spacing: .5px; text-transform: uppercase; }

.btn-enlarge {
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  color: #9ca3af;
  font-size: 13px;
  cursor: pointer;
  padding: 1px 6px;
  line-height: 1.2;
  transition: all 0.15s;
}
.btn-enlarge:hover {
  background: #f3f4f6;
  border-color: #3b82f6;
  color: #3b82f6;
}

.ni { padding: 6px 0; border-bottom: 1px solid #e5e7eb; }
.ni:last-child { border-bottom: none; }
.ni-t a {
  font-size: 13px; line-height: 1.45; color: #111827;
  text-decoration: none;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.ni-t a:hover { color: #3b82f6; }
.ni-m { font-size: 11px; color: #9ca3af; margin-top: 2px; }

.notes-ta {
  width: 100%; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 8px 10px; font-size: 13px; font-family: inherit;
  color: #111827; background: #f0f2f5; resize: vertical;
  min-height: 44px; max-height: 100px; line-height: 1.5;
}
.notes-ta:focus { outline: none; border-color: #3b82f6; background: #fff; box-shadow: 0 0 0 3px rgba(59,130,246,.1); }
.notes-ta::placeholder { color: #9ca3af; }

/* ── Notes Editor Modal ── */
.notes-modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
}
.notes-modal {
  background: #fff;
  border-radius: 12px;
  width: 90vw;
  max-width: 720px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2);
}
.notes-modal-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}
.notes-modal-hdr h3 {
  margin: 0;
  font-size: 1em;
  color: #1f2937;
  font-weight: 700;
}
.notes-modal-body {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
}
.notes-modal-ta {
  width: 100%;
  min-height: 250px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 14px;
  font-family: inherit;
  color: #1f2937;
  background: #f9fafb;
  resize: vertical;
  line-height: 1.7;
  box-sizing: border-box;
}
.notes-modal-ta:focus {
  outline: none;
  border-color: #3b82f6;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(59,130,246,.1);
}
.notes-modal-ta::placeholder { color: #9ca3af; }
.notes-modal-ftr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid #e5e7eb;
  flex-shrink: 0;
}
.notes-char-count {
  font-size: 0.82em;
  color: #9ca3af;
}
.notes-modal-actions {
  display: flex;
  gap: 8px;
}
.btn-cancel {
  padding: 8px 20px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #6b7280;
  font-size: 0.88em;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.15s;
}
.btn-cancel:hover {
  background: #f3f4f6;
}
.btn-save {
  padding: 8px 24px;
  border: none;
  border-radius: 6px;
  background: #2563eb;
  color: #fff;
  font-size: 0.88em;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s;
}
.btn-save:hover {
  background: #1d4ed8;
}
.close-btn {
  background: none; border: none;
  font-size: 22px; color: #9ca3af;
  cursor: pointer;
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* ── Responsive: Mobile ── */
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
  .chart-wrap { height: 44px; }
  .metrics { flex-wrap: wrap; }
  .met { padding: 5px 2px; min-width: 25%; }
  .met-l { font-size: 9px; }
  .met-v { font-size: 12px; }
  .news-area { padding: 6px 10px; display: none; }
  .notes-area { padding: 8px 10px 10px; }
  .notes-ta { min-height: 40px; font-size: 13px; }
  .btn-enlarge { font-size: 12px; padding: 2px 6px; min-height: 28px; }
  .metrics-extra .met { min-width: 25%; }
  .metrics-extra .met-l { font-size: 8px; }
  .metrics-extra .met-v { font-size: 11px; }
  .prev-close { font-size: 11px; }
}

/* ── Tablet: 2 columns, show news ── */
@media (min-width: 641px) and (max-width: 960px) {
  .card-hdr { padding: 10px 12px 4px; }
  .sname { font-size: 13px; }
}
</style>
