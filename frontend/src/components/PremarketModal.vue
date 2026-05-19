<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <div class="header-left">
          <span class="title-icon">🤖</span>
          <div>
            <h2>AI产业链盘前分析</h2>
            <span class="subtitle" v-if="report">
              {{ report.report_date }} {{ report.report_time }}
              &nbsp;·&nbsp;
              <span :class="['status-dot', report.status]"></span>
              {{ statusLabel }}
            </span>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn btn-run" :disabled="running" @click="triggerRun">
            <span :class="['run-icon', { spinning: running }]">↻</span>
            {{ running ? '分析中...' : '立即运行' }}
          </button>
          <a v-if="reportUrl" :href="reportUrl" target="_blank" class="btn btn-view">查看完整报告 ↗</a>
          <button class="modal-close" @click="$emit('close')">✕</button>
        </div>
      </div>

      <!-- Initial loading -->
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- Running state -->
      <div v-else-if="running" class="running-state">
        <div class="running-header">
          <div class="spinner large-spinner"></div>
          <div class="running-info">
            <p class="running-title">AI 分析进行中</p>
            <p class="running-step">{{ runningSteps[runningStep] }}</p>
            <div class="step-track">
              <div
                v-for="(s, i) in runningSteps"
                :key="i"
                :class="['step-dot', i <= runningStep ? 'active' : '']"
              ></div>
            </div>
            <p class="running-hint">大模型分析通常需要 1-3 分钟，请耐心等待</p>
          </div>
        </div>
        <!-- LLM 流式输出 -->
        <div v-if="streamText" class="stream-box">
          <div class="stream-label">
            <span class="stream-dot" :class="{ done: streamDone }"></span>
            {{ streamDone ? '大模型输出完成' : '大模型实时输出' }}
          </div>
          <pre ref="streamRef" class="stream-content">{{ streamText }}</pre>
        </div>
      </div>

      <!-- No report -->
      <div v-else-if="!analysis" class="empty-state">
        <div class="empty-icon">📋</div>
        <p>暂无分析报告</p>
        <p class="empty-sub">点击「立即运行」生成今日盘前分析，或等待定时任务在每天早上 6:00 自动执行</p>
        <button class="btn btn-run large" @click="triggerRun">
          ☀ 立即运行
        </button>
      </div>

      <!-- Error -->
      <div v-else-if="analysis.error" class="error-banner">
        ⚠️ {{ analysis.error }}
        <div class="error-hint" v-if="analysis.error.includes('大模型')">
          请前往「系统 → 大模型配置」添加并设置默认模型。
        </div>
        <div class="error-hint" v-else-if="analysis.error.includes('提示词')">
          请前往「系统 → 提示词模板」启用或创建模板。
        </div>
      </div>

      <!-- Content -->
      <div v-else class="modal-body">
        <!-- Market Sentiment -->
        <div class="section">
          <div class="section-title">📊 市场情绪基调</div>
          <div class="sentiment-row">
            <span :class="['tone-badge', toneClass]">{{ analysis.market_sentiment?.tone }}</span>
            <p class="basis-text">{{ analysis.market_sentiment?.basis }}</p>
          </div>
        </div>

        <!-- US Futures -->
        <div class="section" v-if="usMarket">
          <div class="section-title">🌙 美股行情速览</div>
          <div class="market-grid">
            <div v-for="(info, sym) in allMarketItems" :key="sym"
                 :class="['market-card', info.vix_level ? 'vix-card' : '']">
              <div class="market-label">{{ info.label }}</div>
              <div class="market-price">{{ info.price != null ? info.price.toFixed(2) : 'N/A' }}</div>
              <div :class="['market-chg', chgClass(info.change_pct)]">
                {{ info.change_pct != null ? (info.change_pct >= 0 ? '+' : '') + info.change_pct.toFixed(2) + '%' : 'N/A' }}
              </div>
              <div v-if="info.vix_level" :class="['vix-level', vixLevelClass(info.vix_level)]">
                {{ info.vix_level }}
              </div>
            </div>
          </div>
        </div>

        <!-- Watchlist -->
        <div class="section">
          <div class="section-title">
            👁 观察清单
            <span class="count-badge">{{ analysis.watchlist?.length ?? 0 }} 个标的</span>
          </div>
          <div class="watchlist">
            <div v-for="(item, i) in analysis.watchlist" :key="i" class="watch-card">
              <div class="watch-header">
                <span class="watch-num">{{ i + 1 }}</span>
                <strong class="watch-name">{{ item.name }}</strong>
                <span :class="['layer-tag', layerClass(item.industry_layer)]">{{ item.industry_layer }}</span>
              </div>
              <div class="watch-body">
                <div class="watch-row"><span class="row-label">触发事件</span><span>{{ item.trigger_event }}</span></div>
                <div class="watch-row"><span class="row-label">隔夜表现</span><span>{{ item.overnight_performance }}</span></div>
                <div class="watch-row bull"><span class="row-label">看多</span><span>{{ item.bull_case }}</span></div>
                <div class="watch-row bear"><span class="row-label">看空</span><span>{{ item.bear_case }}</span></div>
                <div class="watch-row" v-if="item.follow_up">
                  <span class="row-label">跟进</span><span>{{ item.follow_up }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Premarket Outlook -->
        <div class="section" v-if="analysis.premarket_outlook">
          <div class="section-title">🎯 A股开盘前情景判断</div>
          <p class="outlook-summary">{{ analysis.premarket_outlook.summary }}</p>
          <div class="outlook-grid">
            <div class="outlook-box watch-box" v-if="analysis.premarket_outlook.key_watch_points?.length">
              <div class="box-title">🔍 重点关注</div>
              <ul>
                <li v-for="(p, i) in analysis.premarket_outlook.key_watch_points" :key="i">{{ p }}</li>
              </ul>
            </div>
            <div class="outlook-box uncertainty-box" v-if="analysis.premarket_outlook.uncertainties?.length">
              <div class="box-title">⚡ 主要不确定性</div>
              <ul>
                <li v-for="(u, i) in analysis.premarket_outlook.uncertainties" :key="i">{{ u }}</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Data Gaps -->
        <div class="section" v-if="analysis.data_gaps?.length">
          <div class="section-title">⚠️ 数据缺口</div>
          <ul class="gap-list">
            <li v-for="(g, i) in analysis.data_gaps" :key="i">{{ g }}</li>
          </ul>
        </div>

        <!-- Disclaimer -->
        <div class="disclaimer">
          本报告由 AI 自动生成，仅供参考，不构成投资建议。事实数据以代码采集为准，大模型仅做判断与解读。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { getLatestPremarket, triggerPremarket, getPremarketReport, getStreamText } from '../api'

const emit = defineEmits(['close'])

const loading = ref(true)
const running = ref(false)
const report = ref(null)
const analysis = ref(null)
const reportUrl = ref(null)
const usMarket = ref(null)

const streamText = ref('')
const streamDone = ref(false)
const streamRef = ref(null)

const runningSteps = [
  '正在采集新闻与市场数据...',
  '正在清洗过滤 AI 产业链信息...',
  '正在调用大模型进行分析...',
  '正在生成分析报告...',
]
const runningStep = ref(0)
let pollTimer = null
let stepTimer = null
let streamTimer = null

watch(streamText, () => {
  nextTick(() => {
    if (streamRef.value) streamRef.value.scrollTop = streamRef.value.scrollHeight
  })
})

const statusLabel = computed(() => {
  const map = { completed: '已完成', running: '运行中', failed: '失败' }
  return map[report.value?.status] ?? ''
})

const toneClass = computed(() => {
  const t = analysis.value?.market_sentiment?.tone ?? ''
  if (t.includes('乐观')) return 'tone-positive'
  if (t.includes('谨慎') || t.includes('悲观')) return 'tone-negative'
  return 'tone-neutral'
})

const allMarketItems = computed(() => {
  if (!usMarket.value) return {}
  return {
    ...(usMarket.value.indices || {}),
    ...(usMarket.value.futures || {}),
    ...(usMarket.value.commodities || {}),
  }
})

function chgClass(pct) {
  if (pct == null) return ''
  return pct >= 0 ? 'up' : 'down'
}

function vixLevelClass(level) {
  if (!level) return ''
  if (level.includes('极度恐慌') || level.includes('高恐慌')) return 'vix-danger'
  if (level.includes('偏高'))    return 'vix-warn'
  if (level.includes('正常'))    return 'vix-neutral'
  return 'vix-calm'
}

function layerClass(layer) {
  const map = {
    '算力层': 'layer-compute',
    '模型与平台层': 'layer-model',
    '应用层': 'layer-app',
    '配套基础设施': 'layer-infra',
  }
  return map[layer] ?? 'layer-default'
}

function applyReport(data) {
  report.value = data.report
  analysis.value = data.analysis || null
  reportUrl.value = data.report_url || null
  usMarket.value = data.analysis?._us_market || null
}

async function load() {
  loading.value = true
  try {
    const res = await getLatestPremarket()
    if (res.data.exists) {
      applyReport(res.data)
      // 如果最新记录是 running 状态（如服务重启后遗留），不自动轮询
    }
  } catch (e) {
    console.error('load error', e)
  } finally {
    loading.value = false
  }
}

async function triggerRun() {
  if (running.value) return
  running.value = true
  runningStep.value = 0
  report.value = null
  analysis.value = null
  streamText.value = ''
  streamDone.value = false

  // 步骤进度每 20s 前进一格（最多到倒数第二步）
  stepTimer = setInterval(() => {
    if (runningStep.value < runningSteps.length - 2) runningStep.value++
  }, 20000)

  try {
    const res = await triggerPremarket()
    const newId = res.data.id

    // 流式文本轮询：每 400ms 拉一次 LLM 输出快照
    streamTimer = setInterval(async () => {
      try {
        const s = await getStreamText(newId)
        const newText = s.data.text || ''
        if (newText.length > streamText.value.length) {
          streamText.value = newText
          // 收到首个 token → 推进到"调用大模型"步骤
          if (runningStep.value < 2) runningStep.value = 2
        }
        if (s.data.done && streamTimer) {
          clearInterval(streamTimer)
          streamTimer = null
          streamDone.value = true
          // 流式完成 → 推进到"生成报告"步骤
          if (runningStep.value < 3) runningStep.value = 3
        }
      } catch { /* ignore stream poll errors */ }
    }, 400)

    let attempts = 0
    pollTimer = setInterval(async () => {
      attempts++
      try {
        const r = await getPremarketReport(newId)
        const status = r.data.report?.status

        if (status === 'completed') {
          runningStep.value = runningSteps.length - 1
          stopTimers()
          running.value = false
          applyReport(r.data)
        } else if (status === 'failed') {
          stopTimers()
          running.value = false
          report.value = r.data.report
          analysis.value = { error: r.data.report?.error_msg || '分析失败，请查看服务日志' }
        }
      } catch (e) {
        console.error('poll error', e)
      }
      if (attempts > 72) {
        stopTimers()
        running.value = false
        if (!analysis.value) {
          analysis.value = { error: '等待超时，请刷新页面查看结果或重新运行' }
        }
      }
    }, 5000)
  } catch (e) {
    stopTimers()
    running.value = false
    analysis.value = { error: '触发失败：' + (e.response?.data?.detail || e.message) }
  }
}

function stopTimers() {
  if (pollTimer)  { clearInterval(pollTimer);  pollTimer  = null }
  if (stepTimer)  { clearInterval(stepTimer);  stepTimer  = null }
  if (streamTimer){ clearInterval(streamTimer); streamTimer = null }
}

onMounted(load)
onUnmounted(stopTimers)
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.5);
  z-index: 1000; display: flex; align-items: flex-start; justify-content: center;
  padding: 20px; overflow-y: auto;
}
.modal {
  background: #fff; border-radius: 16px; width: 100%; max-width: 860px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25); overflow: hidden;
}

/* Header */
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 24px; background: linear-gradient(135deg,#1e3a8a,#2563eb); color: #fff;
  flex-wrap: wrap; gap: 10px;
}
.header-left { display: flex; align-items: center; gap: 14px; }
.title-icon { font-size: 1.6rem; }
.modal-header h2 { font-size: 1.1rem; font-weight: 700; margin: 0; }
.subtitle { font-size: 12px; opacity: .8; }
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
.status-dot.completed { background: #86efac; }
.status-dot.running { background: #fde68a; animation: pulse 1s infinite; }
.status-dot.failed { background: #fca5a5; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn { padding: 7px 16px; border-radius: 8px; border: none; font-size: 13px; cursor: pointer;
       font-weight: 600; transition: all .15s; white-space: nowrap; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-run { background: rgba(255,255,255,.2); color: #fff; border: 1px solid rgba(255,255,255,.3); }
.btn-run:hover:not(:disabled) { background: rgba(255,255,255,.3); }
.btn-run.large { background: #2563eb; color: #fff; padding: 10px 24px; font-size: 14px; margin-top: 12px; }
.btn-view { background: #fff; color: #2563eb; text-decoration: none; }
.btn-view:hover { background: #dbeafe; }
.run-icon { display: inline-block; margin-right: 4px; }
.run-icon.spinning { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.modal-close { background: rgba(255,255,255,.15); border: none; color: #fff; width: 32px;
               height: 32px; border-radius: 8px; cursor: pointer; font-size: 14px; }

/* States */
.loading-state, .empty-state { text-align: center; padding: 60px 24px; color: #6b7280; }
.spinner { width: 36px; height: 36px; border: 3px solid #e5e7eb; border-top-color: #2563eb;
           border-radius: 50%; animation: spin .8s linear infinite; margin: 0 auto 16px; }
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
.empty-sub { font-size: 13px; color: #9ca3af; max-width: 400px; margin: 8px auto 20px; line-height: 1.6; }
.error-banner { margin: 16px; padding: 14px 18px; background: #fef2f2;
                border: 1px solid #fecaca; border-radius: 8px; color: #dc2626; font-size: 13px; }
.error-hint { margin-top: 8px; font-size: 12px; color: #9ca3af; }

/* Running state */
.running-state {
  padding: 32px 24px 28px;
  background: linear-gradient(180deg, #eff6ff 0%, #fff 100%);
}
.running-header { display: flex; align-items: flex-start; gap: 20px; margin-bottom: 20px; }
.large-spinner {
  width: 44px; height: 44px; border: 4px solid #dbeafe; border-top-color: #2563eb;
  border-radius: 50%; animation: spin .9s linear infinite; flex-shrink: 0; margin-top: 4px;
}
.running-info { flex: 1; }
.running-title { font-size: 16px; font-weight: 700; color: #1e3a8a; margin: 0 0 6px; }
.running-step  { font-size: 13px; color: #2563eb; margin: 0 0 14px; min-height: 20px; }
.step-track    { display: flex; gap: 8px; margin-bottom: 10px; }
.step-dot      { width: 8px; height: 8px; border-radius: 50%; background: #dbeafe; transition: background .4s; }
.step-dot.active { background: #2563eb; }
.running-hint  { font-size: 12px; color: #9ca3af; margin: 0; }

/* Stream output */
.stream-box {
  border: 1px solid #dbeafe; border-radius: 10px; overflow: hidden; background: #f8faff;
}
.stream-label {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 14px; font-size: 12px; color: #6b7280;
  background: #eff6ff; border-bottom: 1px solid #dbeafe;
}
.stream-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #2563eb;
  animation: pulse 1s infinite; flex-shrink: 0;
}
.stream-dot.done { background: #16a34a; animation: none; }
.stream-content {
  margin: 0; padding: 12px 14px; font-size: 12px; line-height: 1.6;
  color: #1f2937; white-space: pre-wrap; word-break: break-all;
  max-height: 320px; overflow-y: auto; font-family: 'SFMono-Regular', Consolas, monospace;
}

/* Body */
.modal-body { padding: 20px 24px; max-height: calc(100vh - 200px); overflow-y: auto; }
.section { margin-bottom: 22px; }
.section-title { font-size: 13px; font-weight: 700; color: #1e3a8a; margin-bottom: 12px;
                 display: flex; align-items: center; gap: 8px; }
.count-badge { background: #dbeafe; color: #2563eb; border-radius: 12px;
               padding: 1px 8px; font-size: 11px; font-weight: 600; }

/* Sentiment */
.sentiment-row { display: flex; align-items: flex-start; gap: 14px; }
.tone-badge { padding: 4px 14px; border-radius: 20px; font-weight: 700; font-size: 13px;
              white-space: nowrap; flex-shrink: 0; }
.tone-positive { background: #dcfce7; color: #16a34a; }
.tone-negative { background: #fee2e2; color: #dc2626; }
.tone-neutral { background: #dbeafe; color: #2563eb; }
.basis-text { font-size: 13px; color: #374151; line-height: 1.7; }

/* Market grid */
.market-grid { display: flex; gap: 10px; flex-wrap: wrap; }
.market-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
               padding: 10px 14px; min-width: 100px; text-align: center; }
.market-label { font-size: 11px; color: #6b7280; margin-bottom: 4px; }
.market-price { font-size: 14px; font-weight: 700; }
.market-chg { font-size: 12px; font-weight: 600; margin-top: 2px; }
.up { color: #dc2626; } .down { color: #16a34a; }

/* VIX semantic label */
.vix-card { min-width: 120px; }
.vix-level {
  margin-top: 4px; font-size: 11px; font-weight: 600;
  padding: 1px 7px; border-radius: 8px; display: inline-block;
}
.vix-calm    { background: #dcfce7; color: #166534; }
.vix-neutral { background: #dbeafe; color: #1d4ed8; }
.vix-warn    { background: #fef3c7; color: #92400e; }
.vix-danger  { background: #fee2e2; color: #991b1b; }

/* Watchlist */
.watch-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px;
              padding: 16px; margin-bottom: 12px; }
.watch-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.watch-num { width: 24px; height: 24px; border-radius: 50%; background: #1e3a8a;
             color: #fff; font-size: 12px; font-weight: 700; display: flex;
             align-items: center; justify-content: center; flex-shrink: 0; }
.watch-name { font-size: 15px; font-weight: 700; color: #111827; }
.layer-tag { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.layer-compute { background: #dbeafe; color: #2563eb; }
.layer-model { background: #ede9fe; color: #7c3aed; }
.layer-app { background: #dcfce7; color: #16a34a; }
.layer-infra { background: #fef3c7; color: #d97706; }
.layer-default { background: #f3f4f6; color: #6b7280; }
.watch-body { font-size: 13px; }
.watch-row { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px solid #e5e7eb; line-height: 1.5; }
.watch-row:last-child { border-bottom: none; }
.row-label { color: #6b7280; min-width: 60px; flex-shrink: 0; }
.watch-row.bull .row-label { color: #16a34a; font-weight: 600; }
.watch-row.bear .row-label { color: #dc2626; font-weight: 600; }

/* Outlook */
.outlook-summary { font-size: 13px; color: #374151; line-height: 1.8; margin-bottom: 12px; }
.outlook-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media(max-width:600px){.outlook-grid{grid-template-columns:1fr;}}
.outlook-box { padding: 12px 16px; border-radius: 8px; }
.box-title { font-size: 12px; font-weight: 700; margin-bottom: 8px; }
.watch-box { background: #fffbeb; border: 1px solid #fde68a; }
.watch-box .box-title { color: #92400e; }
.uncertainty-box { background: #fef2f2; border: 1px solid #fecaca; }
.uncertainty-box .box-title { color: #991b1b; }
.outlook-box ul { margin: 0; padding-left: 16px; }
.outlook-box li { font-size: 13px; color: #374151; margin: 4px 0; }

.gap-list { margin: 0; padding-left: 18px; }
.gap-list li { font-size: 13px; color: #6b7280; margin: 4px 0; }

.disclaimer { font-size: 11px; color: #9ca3af; text-align: center;
              padding-top: 16px; border-top: 1px solid #f3f4f6; margin-top: 8px; }
</style>
