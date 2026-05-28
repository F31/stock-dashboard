<template>
  <!-- Compact index bar (板块/个股行情 top) -->
  <div v-if="mode === 'indices'" class="index-bar" v-show="indexItems.length">
    <div
      v-for="item in indexItems"
      :key="item.id"
      :class="['idx-pill', `dir-${item.direction}`]"
    >
      <span class="idx-name">{{ item.title }}</span>
      <span :class="['idx-val', `dir-${item.direction}`]">{{ item.value }}</span>
      <span :class="['idx-chg', `dir-${item.direction}`]">{{ item.subtitle }}</span>
    </div>
  </div>

  <!-- Full market intel grid (宏观经济数据 panel) -->
  <div v-else class="intel-section" v-if="items.length">
    <div class="intel-hdr">
      <span class="intel-ttl">📊 市场情报</span>
    </div>
    <div class="intel-grid">
      <div
        v-for="item in items"
        :key="item.id"
        :class="['intel-card', `dir-${item.direction}`]"
      >
        <div :class="['intel-val', `dir-${item.direction}`]">{{ item.value }}</div>
        <div class="intel-tt">{{ item.title }}</div>
        <div class="intel-sub">{{ item.subtitle }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchMarketIntel } from '../api'
import { isMarketOpen, msUntilNextOpen, initTradeCalendar } from '../utils/marketTime'

const props = defineProps({ mode: { type: String, default: '' } })

const INDEX_IDS = new Set(['sh000001', 'sz399001', 'sz399006', 'sh000688'])
const items = ref([])
const indexItems = computed(() => items.value.filter(i => INDEX_IDS.has(i.id)))

let timer = null

async function load() {
  try {
    const res = await fetchMarketIntel()
    items.value = res.data || []
  } catch {
    // silently fail
  }
}

function scheduleRefresh() {
  if (timer) { clearInterval(timer); timer = null }
  if (isMarketOpen()) {
    timer = setInterval(() => {
      load()
      if (!isMarketOpen()) { clearInterval(timer); timer = null }
    }, 60000)
  } else {
    const ms = msUntilNextOpen()
    timer = setTimeout(() => {
      load()
      scheduleRefresh()
    }, Math.min(ms, 3600000))
  }
}

onMounted(() => {
  initTradeCalendar()
  load()
  scheduleRefresh()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
/* ── Index bar (compact horizontal row) ── */
.index-bar {
  display: flex;
  gap: 10px;
  padding: 10px 0 12px;
  flex-wrap: wrap;
}

.idx-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 14px;
  min-width: 180px;
  flex: 1;
}

.idx-name {
  font-size: 12px;
  color: #6b7280;
  font-weight: 600;
  white-space: nowrap;
}

.idx-val {
  font-size: 16px;
  font-weight: 900;
  font-family: 'SF Mono', 'Menlo', monospace;
  margin-left: auto;
}
.idx-val.dir-up  { color: #dc2626; }
.idx-val.dir-down { color: #16a34a; }

.idx-chg {
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  padding: 2px 6px;
  border-radius: 4px;
}
.idx-chg.dir-up   { background: #fee2e2; color: #dc2626; }
.idx-chg.dir-down { background: #dcfce7; color: #16a34a; }

/* ── Full intel grid ── */
.intel-section {
  padding: 0 0 16px;
}

.intel-hdr {
  margin-bottom: 10px;
}

.intel-ttl {
  font-size: 0.88em;
  font-weight: 700;
  color: #374151;
  letter-spacing: 0.3px;
}

.intel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.intel-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  transition: box-shadow 0.2s;
}
.intel-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.intel-val {
  font-size: 22px;
  font-weight: 900;
  line-height: 1.2;
  margin-bottom: 4px;
  font-family: 'SF Mono', 'Menlo', monospace;
}
.intel-val.dir-up { color: #dc2626; }
.intel-val.dir-down { color: #16a34a; }
.intel-val:not(.dir-up):not(.dir-down) { color: #2563eb; }

.intel-tt {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  line-height: 1.3;
  margin-bottom: 2px;
}

.intel-sub {
  font-size: 11px;
  color: #6b7280;
  line-height: 1.3;
}

@media (max-width: 640px) {
  .idx-pill { min-width: 140px; padding: 7px 10px; }
  .intel-grid { grid-template-columns: 1fr; }
}
</style>
