<template>
  <div class="profit-section">
    <div class="profit-hdr">
      <span class="profit-ttl">🏭 规模以上工业企业利润</span>
      <span class="profit-sub">（累计值，亿元）</span>
    </div>

    <div v-if="loading && !rows.length" class="loading-tip">数据加载中...</div>
    <div v-else-if="error && !rows.length" class="error-tip">{{ error }}</div>

    <div v-else class="profit-body">
      <table class="profit-table">
        <thead>
          <tr>
            <th class="th-label">指标</th>
            <th v-for="p in periods" :key="p" class="th-period">{{ p }}</th>
          </tr>
        </thead>
        <tbody>
          <!-- Total industrial profit -->
          <tr class="group-hdr-row">
            <td colspan="4" class="group-hdr">全部工业企业</td>
          </tr>
          <tr>
            <td class="td-label">利润总额（亿元）</td>
            <td v-for="d in rows" :key="d.period + 'tp'" class="td-val">
              {{ fmt(d.total_profit) }}
            </td>
          </tr>
          <tr>
            <td class="td-label td-sub">↳ 上年同期（亿元）</td>
            <td v-for="d in rows" :key="d.period + 'tprev'" class="td-val td-muted">
              {{ fmt(d.total_prev) }}
            </td>
          </tr>
          <tr>
            <td class="td-label">同比增长</td>
            <td v-for="d in rows" :key="d.period + 'ty'" class="td-val">
              <span :class="yoyClass(d.total_yoy)">{{ fmtPct(d.total_yoy) }}</span>
            </td>
          </tr>

          <!-- Electronics sector -->
          <tr class="group-hdr-row">
            <td colspan="4" class="group-hdr">计算机、通信和其他电子设备制造业</td>
          </tr>
          <tr>
            <td class="td-label">利润总额（亿元）</td>
            <td v-for="d in rows" :key="d.period + 'ep'" class="td-val">
              {{ fmt(d.elec_profit) }}
            </td>
          </tr>
          <tr>
            <td class="td-label td-sub">↳ 上年同期（亿元）</td>
            <td v-for="d in rows" :key="d.period + 'eprev'" class="td-val td-muted">
              {{ fmt(d.elec_prev) }}
            </td>
          </tr>
          <tr>
            <td class="td-label">同比增长</td>
            <td v-for="d in rows" :key="d.period + 'ey'" class="td-val">
              <span :class="yoyClass(d.elec_yoy)">{{ fmtPct(d.elec_yoy) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="data-source">数据来源：国家统计局</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchIndustrialProfit } from '../api/index.js'

const rows = ref([])
const loading = ref(false)
const error = ref('')

const periods = computed(() => rows.value.map(r => r.period))

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
  if (v > 0) return 'yoy-pos'
  if (v < 0) return 'yoy-neg'
  return 'yoy-neutral'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetchIndustrialProfit()
    rows.value = resp.data || []
  } catch (e) {
    error.value = '数据获取失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.profit-section {
  padding: 0 0 24px;
}

.profit-hdr {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 10px;
}
.profit-ttl {
  font-size: 0.88em;
  font-weight: 700;
  color: #374151;
  letter-spacing: 0.3px;
}
.profit-sub {
  font-size: 0.75em;
  color: #9ca3af;
}

.loading-tip,
.error-tip {
  padding: 20px;
  text-align: center;
  font-size: 0.82em;
  color: #9ca3af;
}
.error-tip { color: #ef4444; }

.profit-body {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
}

.profit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8em;
}

.profit-table th,
.profit-table td {
  padding: 7px 12px;
  text-align: right;
  border-bottom: 1px solid #f3f4f6;
}

.th-label,
.td-label {
  text-align: left;
  color: #374151;
  font-weight: 500;
  white-space: nowrap;
}
.td-label.td-sub {
  color: #9ca3af;
  font-weight: 400;
  font-size: 0.92em;
  padding-left: 20px;
}

.th-period {
  color: #6b7280;
  font-weight: 600;
  font-size: 0.9em;
  white-space: nowrap;
}

.td-val {
  color: #111827;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.td-muted {
  color: #9ca3af;
}

.group-hdr-row .group-hdr {
  background: #f9fafb;
  color: #6b7280;
  font-size: 0.82em;
  font-weight: 600;
  text-align: left;
  padding: 5px 12px;
  border-bottom: 1px solid #e5e7eb;
}

.yoy-pos { color: #dc2626; font-weight: 600; }
.yoy-neg { color: #16a34a; font-weight: 600; }
.yoy-neutral { color: #6b7280; }

.data-source {
  padding: 6px 12px;
  font-size: 0.7em;
  color: #d1d5db;
  text-align: right;
  border-top: 1px solid #f3f4f6;
}
</style>
