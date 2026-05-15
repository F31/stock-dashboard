<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-hdr">
        <h3>全部自选股 ({{ sorted.length }})</h3>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <div class="modal-body" v-if="sorted.length">
        <table class="stock-table">
          <thead>
            <tr>
              <th class="th-drag"></th>
              <th class="th-name">名称</th>
              <th class="th-price">最新价</th>
              <th class="th-change">涨跌幅</th>
              <th class="th-pe">市盈率</th>
              <th class="th-mc">总市值</th>
              <th class="th-vol">成交量</th>
              <th class="th-act">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(s, idx) in sorted"
              :key="s.id"
              :class="{
                'drag-over-top': dropIdx === idx && dropDir === 'before',
                'drag-over-btm': dropIdx === idx && dropDir === 'after',
                'dragging': dragIdx === idx,
              }"
              @dragover.prevent="onDragOver($event, idx)"
              @dragleave="onDragLeave(idx)"
              @drop="onDrop($event, idx)"
              @dragend="onDragEnd"
            >
              <td class="td-drag">
                <span class="drag-handle" draggable="true"
                      @dragstart.stop="onDragStart(idx)"
                      title="拖动排序">⠿</span>
              </td>
              <td class="td-name">
                <div class="td-name-top">
                  {{ s.data?.stock_name || s.stock_name || s.stock_code }}
                </div>
                <div class="td-code">
                  {{ s.stock_code }}
                  <span :class="['mkt-badge', `mkt-${s.market.toLowerCase()}`]">{{ marketLabel(s.market) }}</span>
                </div>
              </td>
              <td :class="['td-price', trendClass(s)]">
                {{ s.data?.price != null ? fmtPrice(s.data.price, s.market) : '--' }}
              </td>
              <td :class="['td-change', trendClass(s)]">
                {{ s.data?.change_pct != null ? fmtChange(s.data.change_pct) : '--' }}
              </td>
              <td class="td-num">
                {{ s.data?.pe != null ? s.data.pe.toFixed(1) : '--' }}
              </td>
              <td class="td-num">
                {{ s.data?.market_cap != null ? fmtCap(s.data.market_cap) : '--' }}
              </td>
              <td class="td-num">
                {{ s.data?.volume != null ? fmtVol(s.data.volume) : '--' }}
              </td>
              <td class="td-act">
                <button class="del-btn" @click="$emit('remove', s.id)" title="从自选股删除">删除</button>
              </td>
            </tr>
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
const emit = defineEmits(['close', 'remove'])

const store = useStockStore()

// Local copy of stocks for drag reorder + display.
// Sync'd from props on mount and whenever props change (e.g. after delete).
const localList = ref([])

onMounted(() => {
  localList.value = props.stocks ? [...props.stocks] : []
})

// Sync when parent data changes (delete/add), but skip during drag
watch(() => props.stocks, (val) => {
  if (dragIdx.value === -1 && val) {
    localList.value = [...val]
  }
}, { deep: false })

// Drag state
const dragIdx = ref(-1)
const dropIdx = ref(-1)
const dropDir = ref('')

// Sorted local list
const sorted = computed(() => localList.value)

function marketLabel(m) {
  if (m === 'A') return 'A'
  if (m === 'HK') return 'HK'
  if (m === 'US') return 'US'
  return m
}

function trendClass(s) {
  const d = s.data
  if (!d || d.change == null) return ''
  return d.change >= 0 ? 'up' : 'down'
}

function fmtPrice(v, m) {
  const prefix = m === 'US' ? '$' : '¥'
  return prefix + v.toFixed(2)
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

// ── Drag & Drop ──

function onDragStart(idx) {
  dragIdx.value = idx
  dropIdx.value = -1
}

function onDragOver(e, idx) {
  if (dragIdx.value === -1 || dragIdx.value === idx) {
    dropIdx.value = -1
    return
  }
  // Determine if the cursor is in the top or bottom half of the row
  const rect = e.currentTarget.getBoundingClientRect()
  const midY = rect.top + rect.height / 2
  dropDir.value = e.clientY < midY ? 'before' : 'after'
  dropIdx.value = idx
}

function onDragLeave(idx) {
  // Only clear if we're leaving THIS row (not moving into a child)
  if (dropIdx.value === idx) {
    dropIdx.value = -1
  }
}

function onDrop(e, idx) {
  if (dragIdx.value === -1 || dragIdx.value === idx) {
    dragIdx.value = -1
    dropIdx.value = -1
    return
  }

  const list = [...localList.value]
  const [moved] = list.splice(dragIdx.value, 1)

  // After removal, the target index shifts if the source was before it
  const targetIdx = dragIdx.value < idx ? idx - 1 : idx

  let insertAt
  if (dropDir.value === 'before') {
    insertAt = targetIdx
  } else {
    insertAt = targetIdx + 1
  }
  insertAt = Math.max(0, Math.min(insertAt, list.length))
  list.splice(insertAt, 0, moved)

  // Update local display immediately
  localList.value = list

  // Build new full ID order (respecting any tab filter)
  const newIds = list.map(s => s.id)
  const fullList = store.watchlistWithData
  const currentIdSet = new Set(props.stocks.map(s => s.id))

  let fullNewOrder
  if (currentIdSet.size >= fullList.length) {
    // ALL tab — fullList matches props.stocks exactly
    fullNewOrder = newIds
  } else {
    // Filtered tab — merge filtered order back into full order
    let filteredIdx = 0
    fullNewOrder = fullList.map(s => {
      if (currentIdSet.has(s.id)) {
        return newIds[filteredIdx++]
      }
      return s.id
    })
  }

  // Persist to backend
  store.reorder(fullNewOrder)

  dragIdx.value = -1
  dropIdx.value = -1
}

function onDragEnd() {
  dragIdx.value = -1
  dropIdx.value = -1
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal {
  background: #fff;
  border-radius: 12px;
  width: 90vw;
  max-width: 960px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2);
}

.modal-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.modal-hdr h3 {
  margin: 0;
  font-size: 1.05em;
  color: #1f2937;
}

.close-btn {
  background: none;
  border: none;
  font-size: 22px;
  color: #9ca3af;
  cursor: pointer;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

.modal-body {
  flex: 1;
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  padding: 0;
}

.stock-table {
  width: 100%;
  min-width: 560px;
  border-collapse: collapse;
  font-size: 0.85em;
}

.stock-table th {
  position: sticky;
  top: 0;
  background: #f9fafb;
  padding: 10px 8px;
  text-align: left;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}

.stock-table td {
  padding: 10px 8px;
  border-bottom: 1px solid #f3f4f6;
  vertical-align: middle;
  transition: background 0.15s;
}

/* Drag handle column */
.th-drag { width: 36px; min-width: 36px; padding: 10px 4px !important; }
.td-drag { width: 36px; min-width: 36px; padding: 10px 4px !important; text-align: center; }

.drag-handle {
  display: inline-block;
  cursor: grab;
  color: #d1d5db;
  font-size: 16px;
  letter-spacing: 2px;
  padding: 4px 2px;
  border-radius: 4px;
  user-select: none;
  transition: color 0.15s;
}
.drag-handle:hover {
  color: #6b7280;
  background: #f3f4f6;
}
.drag-handle:active {
  cursor: grabbing;
}

/* Drag feedback */
.stock-table tbody tr { user-select: none; }
.stock-table tbody tr.dragging { opacity: 0.35; }
.stock-table tbody tr.drag-over-top td { border-top: 2px solid #3b82f6; }
.stock-table tbody tr.drag-over-btm td { border-bottom: 2px solid #3b82f6; }

.stock-table tbody tr:hover {
  background: #f9fafb;
}

.th-name { min-width: 160px; }
.th-price { min-width: 90px; text-align: right; }
.th-change { min-width: 80px; text-align: right; }
.th-pe { min-width: 65px; text-align: right; }
.th-mc { min-width: 90px; text-align: right; }
.th-vol { min-width: 80px; text-align: right; }
.th-act { min-width: 50px; text-align: center; }

.td-name-top {
  font-weight: 700;
  color: #1f2937;
  font-size: 0.95em;
}

.td-code {
  font-size: 0.8em;
  color: #9ca3af;
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.mkt-badge {
  font-size: 0.75em;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 700;
}
.mkt-a { background: #fef3c7; color: #92400e; }
.mkt-hk { background: #dbeafe; color: #1e40af; }
.mkt-us { background: #ede9fe; color: #5b21b6; }

.td-price, .td-change, .td-num {
  text-align: right;
  font-weight: 600;
  font-family: 'SF Mono', 'Menlo', monospace;
}

.td-price { font-size: 1em; }

.up { color: #dc2626; }
.down { color: #16a34a; }

.td-act { text-align: center; }

.del-btn {
  padding: 4px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  color: #9ca3af;
  font-size: 0.82em;
  cursor: pointer;
}
.del-btn:hover {
  background: #fee2e2;
  border-color: #fecaca;
  color: #dc2626;
}

.empty-modal {
  padding: 60px 24px;
  text-align: center;
  color: #9ca3af;
}

/* ── Responsive: Mobile ── */
@media (max-width: 640px) {
  .modal {
    width: 100vw; max-width: 100vw;
    height: 100vh; max-height: 100vh;
    border-radius: 0;
  }
  .modal-hdr { padding: 12px 14px; }
  .modal-hdr h3 { font-size: 0.9em; }
  .stock-table { font-size: 0.75em; }
  .stock-table th, .stock-table td { padding: 6px 4px; }
  .th-name { min-width: 100px; }
  .td-name-top { font-size: 0.9em; }
  .td-code { font-size: 0.75em; }
  .th-drag, .td-drag { display: none; }
  .col-act { width: 40px; }
  .del-btn { padding: 2px 8px; font-size: 0.75em; }
  .pagination { padding: 8px 14px; gap: 6px; }
  .page-btn { padding: 3px 10px; font-size: 0.85em; }
  .page-info { font-size: 0.78em; }
}
</style>
