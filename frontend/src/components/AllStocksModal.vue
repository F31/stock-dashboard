<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <!-- Header -->
      <div class="modal-hdr">
        <h3>全部自选股 <span class="hdr-count">({{ sorted.length }})</span></h3>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <!-- Search bar -->
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          class="search-input"
          v-model="searchQuery"
          placeholder="搜索股票代码或名称..."
          @keydown.esc="searchQuery = ''"
        />
        <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">×</button>
      </div>

      <div class="modal-body" v-if="sorted.length">
        <!-- No results from search -->
        <div v-if="filteredList.length === 0" class="empty-modal">
          未找到匹配「{{ searchQuery }}」的股票
        </div>

        <table v-else class="stock-table">
          <thead>
            <tr>
              <th class="th-drag"></th>
              <th class="th-name">名称</th>
              <th class="th-price">最新价</th>
              <th class="th-change">涨跌幅</th>
              <th class="th-pe">PE(动态)</th>
              <th class="th-mc">总市值</th>
              <th class="th-vol">成交额</th>
              <th class="th-act">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(s, idx) in filteredList" :key="s.id">
              <!-- Divider before first hidden stock -->
              <tr v-if="s.hidden && (idx === 0 || !filteredList[idx - 1].hidden)" class="hidden-divider-row">
                <td colspan="8" class="hidden-divider">
                  已隐藏的股票（含分析报告，点「显示」可恢复到卡片）
                </td>
              </tr>
              <tr
                :class="{
                  'drag-over-top': dropIdx === idx && dropDir === 'before',
                  'drag-over-btm': dropIdx === idx && dropDir === 'after',
                  'dragging': dragIdx === idx,
                  'row-hidden': s.hidden,
                }"
                @dragover.prevent="onDragOver($event, idx)"
                @dragleave="onDragLeave(idx)"
                @drop="onDrop($event, idx)"
                @dragend="onDragEnd"
              >
                <td class="td-drag">
                  <span
                    v-if="!s.hidden && !searchQuery"
                    class="drag-handle"
                    draggable="true"
                    @dragstart.stop="onDragStart(idx)"
                    title="拖动排序"
                  >⠿</span>
                </td>
                <td class="td-name">
                  <div class="td-name-top td-name-link" @click="$emit('open-detail', s)">
                    {{ s.data?.stock_name || s.stock_name || s.stock_code }}
                  </div>
                  <div class="td-code">
                    {{ s.stock_code }}
                    <span :class="['mkt-badge', `mkt-${s.market.toLowerCase()}`]">{{ marketLabel(s.market) }}</span>
                  </div>
                </td>
                <td :class="['td-price', s.hidden ? '' : trendClass(s)]">
                  {{ s.data?.price != null ? fmtPrice(s.data.price, s.market) : '--' }}
                </td>
                <td :class="['td-change', s.hidden ? '' : trendClass(s)]">
                  {{ s.data?.change_pct != null ? fmtChange(s.data.change_pct) : '--' }}
                </td>
                <td class="td-num">{{ s.data?.pe != null ? s.data.pe.toFixed(1) : '--' }}</td>
                <td class="td-num">{{ s.data?.market_cap != null ? fmtCap(s.data.market_cap) : '--' }}</td>
                <td class="td-num">{{ s.data?.amount != null ? fmtCap(s.data.amount) : '--' }}</td>
                <td class="td-act">
                  <button v-if="s.hidden" class="show-btn" @click="$emit('show-stock', s.id)">显示</button>
                  <button v-else class="del-btn" @click="$emit('remove', s.id)">删除</button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-modal">暂无自选股</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useStockStore } from '../stores/stockStore'

const props = defineProps({ stocks: Array })
const emit = defineEmits(['close', 'remove', 'show-stock', 'open-detail'])

const store = useStockStore()

// ── Search ──
const searchQuery = ref('')

// ── Local list (for drag-reorder) ──
const localList = ref([])

function syncFromProps(val) {
  if (val) localList.value = [...val]
}

onMounted(() => syncFromProps(props.stocks))

// Sync whenever parent data changes, unless a drag is in progress
watch(() => props.stocks, (val) => {
  if (dragIdx.value === -1) syncFromProps(val)
}, { deep: true })

// ── Drag state ──
const dragIdx = ref(-1)
const dropIdx = ref(-1)
const dropDir = ref('')

// Visible stocks first, hidden at bottom
const sorted = computed(() => {
  const visible = localList.value.filter(s => !s.hidden)
  const hidden = localList.value.filter(s => s.hidden)
  return [...visible, ...hidden]
})

// Apply search filter on top of sorted order
const filteredList = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return sorted.value
  return sorted.value.filter(s => {
    const name = (s.data?.stock_name || s.stock_name || '').toLowerCase()
    const code = s.stock_code.toLowerCase()
    return name.includes(q) || code.includes(q)
  })
})

// ── Formatters ──
function marketLabel(m) {
  return { A: 'A', HK: 'HK', US: 'US' }[m] ?? m
}

function trendClass(s) {
  const d = s.data
  if (!d || d.change == null) return ''
  return d.change >= 0 ? 'up' : 'down'
}

function fmtPrice(v, m) {
  return (m === 'US' ? '$' : '¥') + v.toFixed(2)
}

function fmtChange(pct) {
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function fmtCap(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  return (v / 1e4).toFixed(2) + '万'
}

function fmtVol(v) {
  if (v == null) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(0)
}

// ── Drag & Drop (only works on visible non-hidden items, disabled when searching) ──
function onDragStart(idx) {
  if (searchQuery.value || filteredList.value[idx]?.hidden) return
  dragIdx.value = idx
  dropIdx.value = -1
}

function onDragOver(e, idx) {
  if (searchQuery.value || dragIdx.value === -1 || dragIdx.value === idx || filteredList.value[idx]?.hidden) {
    dropIdx.value = -1
    return
  }
  const rect = e.currentTarget.getBoundingClientRect()
  dropDir.value = e.clientY < rect.top + rect.height / 2 ? 'before' : 'after'
  dropIdx.value = idx
}

function onDragLeave(idx) {
  if (dropIdx.value === idx) dropIdx.value = -1
}

function onDrop(e, idx) {
  if (dragIdx.value === -1 || dragIdx.value === idx) {
    dragIdx.value = -1; dropIdx.value = -1; return
  }

  // Work on visible-only list for reordering (hidden items stay fixed)
  const visibleList = localList.value.filter(s => !s.hidden)
  const hiddenList = localList.value.filter(s => s.hidden)

  const fromIdx = dragIdx.value
  const toIdx = idx

  const reordered = [...visibleList]
  const [moved] = reordered.splice(fromIdx, 1)
  const targetIdx = fromIdx < toIdx ? toIdx - 1 : toIdx
  const insertAt = Math.max(0, Math.min(
    dropDir.value === 'before' ? targetIdx : targetIdx + 1,
    reordered.length
  ))
  reordered.splice(insertAt, 0, moved)

  localList.value = [...reordered, ...hiddenList]

  // Persist — build full order from store
  const newIds = reordered.map(s => s.id)
  const fullList = store.watchlistWithData
  const currentVisibleIds = new Set(props.stocks.filter(s => !s.hidden).map(s => s.id))

  let fullNewOrder
  if (currentVisibleIds.size >= fullList.filter(s => !s.hidden).length) {
    fullNewOrder = [...newIds, ...hiddenList.map(s => s.id)]
  } else {
    let visIdx = 0
    fullNewOrder = fullList.map(s => {
      if (currentVisibleIds.has(s.id)) return newIds[visIdx++]
      return s.id
    })
  }

  store.reorder(fullNewOrder)
  dragIdx.value = -1; dropIdx.value = -1
}

function onDragEnd() {
  dragIdx.value = -1; dropIdx.value = -1
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}

.modal {
  background: #fff; border-radius: 12px;
  width: 90vw; max-width: 960px; max-height: 85vh;
  display: flex; flex-direction: column;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2);
}

/* Header */
.modal-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px 14px;
  border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.modal-hdr h3 { margin: 0; font-size: 1.05em; color: #1f2937; }
.hdr-count { font-size: 0.85em; color: #9ca3af; font-weight: 400; margin-left: 4px; }

.close-btn {
  background: none; border: none; font-size: 22px; color: #9ca3af;
  cursor: pointer; width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center; border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* Search bar */
.search-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 20px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0; background: #f9fafb;
}
.search-icon { font-size: 14px; flex-shrink: 0; color: #9ca3af; }
.search-input {
  flex: 1; border: 1px solid #e5e7eb; border-radius: 6px;
  padding: 6px 10px; font-size: 13px; font-family: inherit;
  color: #111827; background: #fff;
  outline: none; transition: border-color .15s;
}
.search-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,.12); }
.search-input::placeholder { color: #9ca3af; }
.search-clear {
  background: none; border: none; cursor: pointer;
  font-size: 16px; color: #9ca3af; width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px; flex-shrink: 0;
}
.search-clear:hover { background: #f3f4f6; color: #374151; }

/* Body */
.modal-body { flex: 1; overflow: auto; -webkit-overflow-scrolling: touch; }

.stock-table {
  width: 100%; min-width: 560px;
  border-collapse: collapse; font-size: 0.85em;
}

.stock-table th {
  position: sticky; top: 0;
  background: #f9fafb; padding: 10px 8px;
  text-align: left; font-weight: 600; color: #6b7280;
  border-bottom: 1px solid #e5e7eb; white-space: nowrap;
}

.stock-table td {
  padding: 10px 8px; border-bottom: 1px solid #f3f4f6;
  vertical-align: middle; transition: background 0.15s;
}

.th-drag { width: 36px; min-width: 36px; padding: 10px 4px !important; }
.td-drag { width: 36px; min-width: 36px; padding: 10px 4px !important; text-align: center; }

.drag-handle {
  display: inline-block; cursor: grab; color: #d1d5db;
  font-size: 16px; letter-spacing: 2px; padding: 4px 2px;
  border-radius: 4px; user-select: none; transition: color 0.15s;
}
.drag-handle:hover { color: #6b7280; background: #f3f4f6; }
.drag-handle:active { cursor: grabbing; }

.stock-table tbody tr { user-select: none; }
.stock-table tbody tr.dragging { opacity: 0.35; }
.stock-table tbody tr.drag-over-top td { border-top: 2px solid #3b82f6; }
.stock-table tbody tr.drag-over-btm td { border-bottom: 2px solid #3b82f6; }
.stock-table tbody tr:hover { background: #f9fafb; }

.th-name { min-width: 160px; }
.th-price { min-width: 90px; text-align: right; }
.th-change { min-width: 80px; text-align: right; }
.th-pe { min-width: 65px; text-align: right; }
.th-mc { min-width: 90px; text-align: right; }
.th-vol { min-width: 80px; text-align: right; }
.th-act { min-width: 60px; text-align: center; }

.td-name-top { font-weight: 700; color: #1f2937; font-size: 0.95em; }
.td-name-link { cursor: pointer; }
.td-name-link:hover { color: #2563eb; text-decoration: underline; }

.td-code {
  font-size: 0.8em; color: #9ca3af; margin-top: 2px;
  display: flex; align-items: center; gap: 4px;
}

.mkt-badge { font-size: 0.75em; padding: 1px 5px; border-radius: 4px; font-weight: 700; }
.mkt-a  { background: #fef3c7; color: #92400e; }
.mkt-hk { background: #dbeafe; color: #1e40af; }
.mkt-us { background: #ede9fe; color: #5b21b6; }

.td-price, .td-change, .td-num {
  text-align: right; font-weight: 600;
  font-family: 'SF Mono', 'Menlo', monospace;
}
.td-price { font-size: 1em; }
.up { color: #dc2626; }
.down { color: #16a34a; }

.td-act { text-align: center; }

.del-btn {
  padding: 4px 12px; border: 1px solid #e5e7eb; border-radius: 4px;
  background: #fff; color: #9ca3af; font-size: 0.82em; cursor: pointer;
}
.del-btn:hover { background: #fee2e2; border-color: #fecaca; color: #dc2626; }

.show-btn {
  padding: 4px 12px; border: 1px solid #bfdbfe; border-radius: 4px;
  background: #eff6ff; color: #2563eb; font-size: 0.82em;
  cursor: pointer; font-weight: 600;
}
.show-btn:hover { background: #dbeafe; border-color: #93c5fd; }

/* Hidden rows */
.row-hidden td { opacity: 0.5; }
.row-hidden .td-name-top { color: #6b7280; text-decoration: line-through; }
.row-hidden .show-btn { opacity: 1; }

/* Divider */
.hidden-divider-row td { padding: 0; border-bottom: none; }
.hidden-divider {
  font-size: 0.78em; color: #9ca3af; font-weight: 600; letter-spacing: .3px;
  padding: 14px 8px 4px !important;
  border-top: 2px dashed #e5e7eb !important;
}

.empty-modal { padding: 60px 24px; text-align: center; color: #9ca3af; }

/* Mobile */
@media (max-width: 640px) {
  .modal { width: 100vw; max-width: 100vw; height: 100vh; max-height: 100vh; border-radius: 0; }
  .modal-hdr { padding: 12px 14px; }
  .modal-hdr h3 { font-size: 0.9em; }
  .search-bar { padding: 8px 12px; }
  .stock-table { font-size: 0.75em; }
  .stock-table th, .stock-table td { padding: 6px 4px; }
  .th-name { min-width: 100px; }
  .td-name-top { font-size: 0.9em; }
  .td-code { font-size: 0.75em; }
  .th-drag, .td-drag { display: none; }
  .del-btn, .show-btn { padding: 2px 8px; font-size: 0.75em; }
}
</style>
