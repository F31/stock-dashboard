<template>
  <div class="radar-wrap">
    <div class="radar-hdr">
      <span class="radar-title clickable-title" @click="rulesModal = true" title="点击查看维度说明">📡 风险雷达</span>
      <span class="radar-composite" :class="radar?.risk_level">
        {{ radar?.composite ?? '—' }}
        <span class="radar-label-txt">{{ radar?.risk_label ?? '' }}</span>
      </span>
      <span class="radar-date">{{ radar?.date || '' }}</span>
    </div>

    <div v-if="loading && !radar" class="radar-loading">风险雷达加载中...</div>
    <div v-else-if="error && !radar" class="radar-error">{{ error }}</div>

    <div v-else class="radar-body">
      <div class="radar-canvas-wrap">
        <canvas ref="canvasEl"></canvas>
      </div>

      <div class="radar-dims">
        <div
          v-for="(score, dim) in radar?.scores"
          :key="dim"
          class="radar-dim-row"
        >
          <span class="rdim-name">{{ dim }}</span>
          <div class="rdim-bar-wrap">
            <div class="rdim-bar" :style="{ width: score + '%', background: dimColor(score) }"></div>
          </div>
          <span class="rdim-score" :class="dimClass(score)">{{ score }}</span>
        </div>
      </div>
    </div>

    <!-- ── 维度说明弹窗 ── -->
    <div v-if="rulesModal" class="modal-overlay" @click.self="rulesModal = false">
      <div class="modal rules-modal">
        <div class="modal-hdr">
          <span class="modal-title">📡 风险雷达说明</span>
          <a href="/risk-radar-rules.html" target="_blank" class="rules-ext-link" title="在新标签页打开">↗ 独立页面</a>
          <button class="close-btn" @click="rulesModal = false">×</button>
        </div>
        <div class="rules-iframe-wrap">
          <iframe src="/risk-radar-rules.html" class="rules-iframe" title="风险雷达说明"></iframe>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  Chart,
  RadarController, RadialLinearScale,
  PointElement, LineElement,
  Filler, Tooltip, Legend,
} from 'chart.js'
import { fetchRiskRadar } from '../api/index.js'

Chart.register(RadarController, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

const canvasEl   = ref(null)
const radar      = ref(null)
const loading    = ref(false)
const error      = ref('')
const rulesModal = ref(false)
let chartInstance = null

const DIMS = ['情绪温度', '杠杆水位', '宏观金融', '技术超买', '曲线斜率', '期权波动率']

function dimColor(score) {
  if (score >= 75) return '#dc2626'
  if (score >= 55) return '#f59e0b'
  if (score >= 35) return '#6b7280'
  return '#16a34a'
}

function dimClass(score) {
  if (score >= 75) return 'dim-danger'
  if (score >= 55) return 'dim-warning'
  if (score >= 35) return 'dim-neutral'
  return 'dim-safe'
}

function buildChart() {
  if (!canvasEl.value || !radar.value?.scores) return

  const scores = DIMS.map(d => radar.value.scores[d] ?? 50)

  if (chartInstance) {
    chartInstance.data.datasets[0].data = scores
    chartInstance.update()
    return
  }

  chartInstance = new Chart(canvasEl.value, {
    type: 'radar',
    data: {
      labels: DIMS,
      datasets: [
        {
          label: '风险评分',
          data: scores,
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          borderColor: 'rgba(239, 68, 68, 0.8)',
          borderWidth: 2,
          pointBackgroundColor: scores.map(s =>
            s >= 75 ? '#dc2626' : s >= 55 ? '#f59e0b' : s >= 35 ? '#6b7280' : '#16a34a'
          ),
          pointRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `风险: ${ctx.raw}`,
          },
        },
      },
      scales: {
        r: {
          min: 0,
          max: 100,
          ticks: {
            stepSize: 25,
            font: { size: 9 },
            color: '#9ca3af',
            backdropColor: 'transparent',
          },
          pointLabels: {
            font: { size: 11 },
            color: '#374151',
          },
          grid: { color: 'rgba(0,0,0,0.08)' },
          angleLines: { color: 'rgba(0,0,0,0.08)' },
        },
      },
    },
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchRiskRadar()
    radar.value = res.data
    await nextTick()
    buildChart()
  } catch (e) {
    error.value = '风险雷达数据加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
onUnmounted(() => { chartInstance?.destroy() })
</script>

<style scoped>
.radar-wrap {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 14px;
}

.radar-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.radar-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.clickable-title {
  cursor: pointer;
  border-radius: 4px;
  padding: 1px 4px;
  transition: background 0.15s;
}
.clickable-title:hover { background: #f3f4f6; }

.radar-composite {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.radar-composite.danger  { color: #dc2626; }
.radar-composite.warning { color: #d97706; }
.radar-composite.normal  { color: #6b7280; }
.radar-composite.safe    { color: #16a34a; }

.radar-label-txt {
  font-size: 13px;
  font-weight: 500;
}

.radar-date {
  margin-left: auto;
  font-size: 11px;
  color: #9ca3af;
}

.radar-loading,
.radar-error {
  text-align: center;
  color: #9ca3af;
  padding: 24px 0;
  font-size: 13px;
}

.radar-body {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.radar-canvas-wrap {
  flex: 0 0 220px;
  max-width: 220px;
}

.radar-dims {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.radar-dim-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.rdim-name {
  font-size: 11px;
  color: #374151;
  flex: 0 0 68px;
  text-align: right;
}

.rdim-bar-wrap {
  flex: 1;
  background: #f3f4f6;
  border-radius: 3px;
  height: 8px;
  overflow: hidden;
}

.rdim-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.rdim-score {
  font-size: 12px;
  font-weight: 600;
  flex: 0 0 30px;
  text-align: right;
}
.dim-danger  { color: #dc2626; }
.dim-warning { color: #d97706; }
.dim-neutral { color: #6b7280; }
.dim-safe    { color: #16a34a; }


@media (max-width: 600px) {
  .radar-body {
    flex-direction: column;
  }
  .radar-canvas-wrap {
    flex: unset;
    max-width: 100%;
    width: 100%;
  }
}

/* ── 说明弹窗 ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rules-modal {
  background: #fff;
  border-radius: 12px;
  width: min(860px, 96vw);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
}

.modal-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.rules-ext-link {
  margin-left: auto;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
  background: #f3f4f6;
  color: #374151;
  text-decoration: none;
  border: 1px solid #e5e7eb;
}
.rules-ext-link:hover { background: #e0e7ff; }

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #6b7280;
  line-height: 1;
  padding: 0 4px;
}
.close-btn:hover { color: #111827; }

.rules-iframe-wrap {
  flex: 1;
  overflow: hidden;
}

.rules-iframe {
  width: 100%;
  height: 100%;
  min-height: 520px;
  border: none;
}

@media (max-width: 600px) {
  .rules-modal { border-radius: 0; max-height: 100dvh; max-width: 100vw; }
}
</style>
