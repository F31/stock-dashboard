<template>
  <div class="intel-section" v-if="items.length">
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
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchMarketIntel } from '../api'

const items = ref([])
let timer = null

async function load() {
  try {
    const res = await fetchMarketIntel()
    items.value = res.data || []
  } catch {
    // silently fail
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 60000) // refresh every 60s
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
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
</style>
