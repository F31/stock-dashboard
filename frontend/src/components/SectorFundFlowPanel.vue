<template>
  <div class="sff-panel">
    <div class="sff-hdr">
      <span class="sff-title">🏷️ 概念板块主力净流入 TOP10</span>
      <button class="sff-refresh" :class="{ spinning: loading }" @click="load(true)" title="刷新">↻</button>
    </div>
    <div v-if="loading && !items.length" class="sff-loading">加载中...</div>
    <div v-else class="sff-list">
      <div class="sff-row sff-row-hdr">
        <span class="sff-rank">#</span>
        <span class="sff-name">板块</span>
        <span class="sff-chg">涨跌</span>
        <span class="sff-inflow">净流入</span>
      </div>
      <div v-for="(item, i) in items" :key="item.code" class="sff-row sff-row-body" :class="{ 'sff-top3': i < 3 }">
        <span class="sff-rank">{{ rankIcon(i) }}</span>
        <span class="sff-name" :title="item.name">{{ item.name }}</span>
        <span :class="['sff-chg', chgCls(item.change_pct)]">{{ fmtPct(item.change_pct) }}</span>
        <span :class="['sff-inflow', inflowCls(item.fund_flow)]">{{ fmtInflow(item.fund_flow) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchSectorFundFlowTop10 } from '../api'

const items = ref([])
const loading = ref(false)

async function load(forced = false) {
  loading.value = true
  try {
    const res = await fetchSectorFundFlowTop10()
    items.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    console.error('Sector fund flow error', e)
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
  if (v == null) return '—'
  const yi = v / 1e8
  if (yi === 0) return '—'
  return (yi > 0 ? '+' : '') + yi.toFixed(2) + '亿'
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.sff-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  min-width: 280px;
  max-width: 340px;
}

.sff-hdr {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.sff-title { font-size: 0.82em; font-weight: 700; color: #111827; white-space: nowrap; }
.sff-refresh {
  margin-left: auto; background: none; border: 1px solid #d1d5db;
  border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.8em;
}
.sff-refresh.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.sff-loading { font-size: 0.78em; color: #9ca3af; padding: 20px 0; text-align: center; }

.sff-list { display: flex; flex-direction: column; gap: 2px; }

.sff-row {
  display: grid;
  grid-template-columns: 30px 1fr 72px 80px;
  align-items: center;
  padding: 5px 6px;
  border-radius: 6px;
  font-size: 0.75em;
  gap: 4px;
}
.sff-row-hdr {
  color: #9ca3af;
  font-weight: 600;
  font-size: 0.7em;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 6px;
  margin-bottom: 2px;
}
.sff-row-body { transition: background 0.12s; }
.sff-row-body:hover { background: #f3f4f6; }
.sff-top3 { background: #fffbeb; }
.sff-top3:hover { background: #fef3c7; }

.sff-rank  { font-weight: 700; color: #6b7280; text-align: center; }
.sff-name  { font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sff-chg   { text-align: right; font-weight: 700; font-family: monospace; }
.sff-chg.up { color: #dc2626; }
.sff-chg.dn { color: #16a34a; }
.sff-inflow { text-align: right; font-weight: 700; font-family: monospace; }
.inflow-pos { color: #dc2626; }
.inflow-neg { color: #16a34a; }

@media (max-width: 768px) {
  .sff-panel { max-width: 100%; min-width: 0; }
  .sff-row { grid-template-columns: 30px 1fr 72px; }
  .sff-inflow { display: none; }
}
</style>
