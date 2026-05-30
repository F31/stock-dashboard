<template>
  <div class="fund-flow-panel">
    <div class="ff-hdr">
      <span class="ff-title">💹 主力净流入 TOP 20</span>
      <span class="ff-sub" v-if="updateTime"> {{ updateTime }}</span>
      <button class="ff-refresh" :class="{ spinning: loading }" @click="load(true)" title="刷新">↻</button>
    </div>
    <div v-if="loading && !items.length" class="ff-loading">加载中...</div>
    <div v-else-if="error && !items.length" class="ff-error">{{ error }}</div>
    <div v-else class="ff-list">
      <div class="ff-row ff-row-hdr">
        <span class="ff-rank">#</span>
        <span class="ff-name">名称</span>
        <span class="ff-chg">涨跌</span>
        <span class="ff-inflow">净流入</span>
        <span class="ff-ratio hide-mobile">占比</span>
      </div>
      <div
        v-for="(item, i) in items"
        :key="item.stock_code"
        class="ff-row ff-row-body"
        :class="{ 'ff-top3': i < 3 }"
        @click="$emit('open-detail', item)"
      >
        <span class="ff-rank">{{ rankIcon(i) }}</span>
        <span class="ff-name">{{ item.stock_name }}</span>
        <span :class="['ff-chg', chgCls(item.change_pct)]">{{ fmtPct(item.change_pct) }}</span>
        <span :class="['ff-inflow', inflowCls(item.net_inflow)]">{{ fmtInflow(item.net_inflow) }}</span>
        <span class="ff-ratio hide-mobile">{{ item.net_ratio ? item.net_ratio.toFixed(1) + '%' : '—' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchFundFlowTop20 } from '../api'

defineEmits(['open-detail'])

const items = ref([])
const loading = ref(false)
const error = ref('')
const updateTime = ref('')

async function load(forced = false) {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchFundFlowTop20()
    items.value = res.data.items || []
    if (res.data.update_time) {
      const d = new Date(res.data.update_time * 1000)
      updateTime.value = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
  } catch (e) {
    error.value = '获取失败，点击↻重试'
    console.error('Fund flow error', e)
  } finally {
    loading.value = false
  }
}

function rankIcon(i) {
  if (i === 0) return '🥇'
  if (i === 1) return '🥈'
  if (i === 2) return '🥉'
  return `#${i + 1}`
}

function chgCls(v) { return v == null ? '' : v >= 0 ? 'up' : 'dn' }
function inflowCls(v) { return v == null ? '' : v >= 0 ? 'inflow-pos' : 'inflow-neg' }
function fmtPct(v) {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}
function fmtInflow(v) {
  if (v == null || v === 0) return '—'
  return (v > 0 ? '+' : '') + v.toFixed(1) + '亿'
}

onMounted(() => load())
</script>

<style scoped>
.fund-flow-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  min-width: 280px;
  max-width: 340px;
  position: sticky;
  top: 8px;
  max-height: calc(100vh - 40px);
  overflow-y: auto;
}

.ff-hdr {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.ff-title { font-size: 0.82em; font-weight: 700; color: #111827; white-space: nowrap; }
.ff-sub   { font-size: 0.7em; color: #9ca3af; }
.ff-refresh {
  margin-left: auto; background: none; border: 1px solid #d1d5db;
  border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.8em;
}
.ff-refresh.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.ff-loading, .ff-error { font-size: 0.78em; color: #9ca3af; padding: 20px 0; text-align: center; }
.ff-error { color: #dc2626; }

.ff-list { display: flex; flex-direction: column; gap: 2px; }

.ff-row {
  display: grid;
  grid-template-columns: 30px 1fr 72px 72px 60px;
  align-items: center;
  padding: 5px 6px;
  border-radius: 6px;
  font-size: 0.75em;
  gap: 4px;
}
.ff-row-hdr {
  color: #9ca3af;
  font-weight: 600;
  font-size: 0.7em;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 6px;
  margin-bottom: 2px;
}
.ff-row-body { cursor: pointer; transition: background 0.12s; }
.ff-row-body:hover { background: #f3f4f6; }
.ff-top3 { background: #fffbeb; }
.ff-top3:hover { background: #fef3c7; }

.ff-rank  { font-weight: 700; color: #6b7280; text-align: center; }
.ff-name  { font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ff-chg   { text-align: right; font-weight: 700; font-family: monospace; }
.ff-chg.up { color: #dc2626; }
.ff-chg.dn { color: #16a34a; }
.ff-inflow { text-align: right; font-weight: 700; font-family: monospace; }
.inflow-pos { color: #dc2626; }
.inflow-neg { color: #16a34a; }
.ff-ratio  { text-align: right; color: #6b7280; font-weight: 500; }

@media (max-width: 768px) {
  .fund-flow-panel { max-width: 100%; min-width: 0; position: static; max-height: none; }
  .hide-mobile { display: none; }
  .ff-row { grid-template-columns: 30px 1fr 72px 72px; }
}
</style>
