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
              <span v-if="ttsState !== 'idle'" class="tts-reading-badge">
                &nbsp;·&nbsp;{{ ttsState === 'loading' ? '合成中' : ttsState === 'playing' ? '朗读中' : '已暂停' }}
              </span>
            </span>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn btn-run" :disabled="running" @click="triggerRun">
            <span :class="['run-icon', { spinning: running }]">↻</span>
            {{ running ? '分析中...' : '立即运行' }}
          </button>
          <template v-if="analysis && !analysis.error">
            <select v-if="ttsState === 'idle'" v-model="selectedVoice" class="voice-select" title="选择朗读声音">
              <option v-for="v in ttsVoices" :key="v.value" :value="v.value">{{ v.label }}</option>
            </select>
            <button class="btn btn-tts" :disabled="ttsState === 'loading'" @click="toggleTTS" :title="ttsBtnTitle">
              <span v-if="ttsState === 'loading'" class="tts-loading-dot"></span>
              {{ ttsState === 'idle' ? '🔊 朗读' : ttsState === 'loading' ? '合成中…' : ttsState === 'playing' ? '⏸ 暂停' : '▶ 继续' }}
            </button>
            <button v-if="ttsState !== 'idle'" class="btn btn-tts-stop" @click="stopTTS" title="停止朗读">⏹</button>
          </template>
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

        <!-- News Briefing -->
        <div class="section" v-if="newsItems.length">
          <div class="section-title">
            📰 资讯简报
            <span class="count-badge">{{ newsItems.length }} 条</span>
            <button class="toggle-news-btn" @click="newsExpanded = !newsExpanded">
              {{ newsExpanded ? '收起 ▲' : '展开 ▼' }}
            </button>
          </div>
          <div v-if="newsExpanded" class="news-list">
            <div v-for="(item, i) in newsItems" :key="i"
                 :class="['news-item', `news-${item.signal_strength}`]">
              <div class="news-title-row">
                <span :class="['signal-pill', `signal-${item.signal_strength}`]">
                  {{ item.signal_strength === 'high' ? '高' : item.signal_strength === 'medium' ? '中' : '低' }}
                </span>
                <a v-if="item.url" :href="item.url" target="_blank" rel="noopener"
                   class="news-link">{{ item.title }}</a>
                <span v-else class="news-title-plain">{{ item.title }}</span>
              </div>
              <div class="news-meta">
                <span>{{ item.source }}</span>
                <span>{{ item.published_at }}</span>
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

        <!-- TTS Error -->
        <div v-if="ttsError" class="tts-error-tip">⚠️ {{ ttsError }}</div>

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
import { getLatestPremarket, triggerPremarket, getPremarketReport, getStreamText, synthesizeTTS } from '../api'

const emit = defineEmits(['close'])

// ── TTS — HTMLAudioElement + 分块流式朗读 ────────────────────────────────────
// 核心策略：
// 1. 用 HTMLAudioElement 取代 AudioContext —— iOS Safari 对 <audio> 的支持
//    远比 WebAudio API 稳定，pause/play 语义清晰，不存在 suspend 后无法 resume 的问题。
// 2. 全文切成 700 字块，超前预取 LOOKAHEAD 块 —— 第一块 5~8 s 内到达，
//    完全在 iOS 用户手势上下文有效期内，解决"长请求导致手势超时"问题。
// 3. Blob URL 生命周期管理：播完即 revoke，避免内存泄漏。

const CHUNK_MAX = 700
const LOOKAHEAD = 2

const ttsState  = ref('idle')  // 'idle' | 'loading' | 'playing' | 'paused'
const ttsError  = ref('')
const ttsChunkProgress = ref({ cur: 0, total: 0 })

let _audio    = null   // HTMLAudioElement（在用户手势中创建）
let _chunks   = []     // string[]
let _playIdx  = 0
let _buffers  = {}     // idx → blob URL
let _fetching = {}     // idx → true（请求进行中）
let _session  = 0      // 每次 start/stop 自增，使过期回调失效

const ttsBtnTitle = computed(() => {
  const m = { idle: '朗读报告', loading: '正在合成语音…', playing: '暂停朗读', paused: '继续朗读' }
  return m[ttsState.value] ?? '朗读报告'
})

const ttsVoices = [
  { label: '小晓 (女声)', value: 'zh-CN-XiaoxiaoNeural' },
  { label: '云杨 (男声)', value: 'zh-CN-YunyangNeural'  },
  { label: '云希 (男声)', value: 'zh-CN-YunxiNeural'    },
]
const selectedVoice = ref('zh-CN-XiaoxiaoNeural')

function buildSpeechText() {
  if (!analysis.value) return ''
  const parts = []
  const sent = analysis.value.market_sentiment
  if (sent?.tone) parts.push(`市场情绪基调：${sent.tone}。${sent.basis || ''}`)
  const list = analysis.value.watchlist
  if (list?.length) {
    parts.push(`以下是观察清单，共${list.length}个标的。`)
    list.forEach((item, i) => {
      const layer = item.industry_layer ? `，${item.industry_layer}` : ''
      parts.push(`第${i + 1}个标的：${item.name}${layer}。`)
      if (item.trigger_event)         parts.push(`触发事件：${item.trigger_event}。`)
      if (item.overnight_performance) parts.push(`隔夜表现：${item.overnight_performance}。`)
      if (item.bull_case)             parts.push(`看多理由：${item.bull_case}。`)
      if (item.bear_case)             parts.push(`看空理由：${item.bear_case}。`)
      if (item.follow_up)             parts.push(`跟进问题：${item.follow_up}。`)
    })
  }
  const outlook = analysis.value.premarket_outlook
  if (outlook?.summary) {
    parts.push(`A股开盘前情景判断：${outlook.summary}`)
    if (outlook.key_watch_points?.length)
      parts.push(`重点关注：${outlook.key_watch_points.join('；')}。`)
    if (outlook.uncertainties?.length)
      parts.push(`主要不确定性：${outlook.uncertainties.join('；')}。`)
  }
  return parts.join('\n')
}

// 按句子边界切块，每块最多 CHUNK_MAX 字
function _buildChunks(text) {
  const chunks = []
  let t = text.trim()
  while (t.length > 0) {
    if (t.length <= CHUNK_MAX) { chunks.push(t); break }
    let cut = CHUNK_MAX
    for (let i = Math.min(CHUNK_MAX, t.length - 1); i > CHUNK_MAX * 0.5; i--) {
      const c = t[i]
      if (c === '。' || c === '！' || c === '？' || c === '\n') { cut = i + 1; break }
      if ((c === '；' || c === '，') && i > CHUNK_MAX * 0.75) { cut = i + 1; break }
    }
    chunks.push(t.slice(0, cut).trim())
    t = t.slice(cut).trim()
  }
  return chunks.filter(c => c.length > 0)
}

// 异步预取一块并缓存为 Blob URL
async function _fetchChunk(idx) {
  if (idx < 0 || idx >= _chunks.length) return
  if (_buffers[idx] !== undefined || _fetching[idx]) return
  const mySid = _session
  _fetching[idx] = true
  try {
    const res = await synthesizeTTS(_chunks[idx], selectedVoice.value)
    if (_session !== mySid) return           // 已停止，丢弃
    _buffers[idx] = URL.createObjectURL(res.data)
    delete _fetching[idx]
    // 若此时正等待这一块，立即播放
    if (ttsState.value === 'loading' && idx === _playIdx) _playChunk(idx)
  } catch (e) {
    if (_session !== mySid) return
    delete _fetching[idx]
    if (ttsState.value === 'loading' && idx === _playIdx) {
      ttsState.value = 'idle'
      ttsError.value = `第 ${idx + 1} 段合成失败，请检查网络后重试`
    }
  }
}

function _prefetch() {
  for (let i = 0; i < LOOKAHEAD; i++) _fetchChunk(_playIdx + i)
}

// 播放指定块（已在 _buffers 中）
function _playChunk(idx) {
  if (!_audio || _buffers[idx] === undefined) return
  const mySid = _session
  const oldSrc = _audio.src
  _audio.pause()          // 确保停止静音解锁音频或上一块
  _audio.src = _buffers[idx]
  // 释放上一块的 Blob URL
  if (oldSrc && oldSrc.startsWith('blob:')) { try { URL.revokeObjectURL(oldSrc) } catch {} }

  _audio.onended = () => {
    if (_session !== mySid || ttsState.value !== 'playing') return
    delete _buffers[idx]
    _playIdx++
    ttsChunkProgress.value = { cur: _playIdx + 1, total: _chunks.length }
    if (_playIdx >= _chunks.length) { ttsState.value = 'idle'; return }
    _prefetch()
    if (_buffers[_playIdx] !== undefined) _playChunk(_playIdx)
    else ttsState.value = 'loading'   // 等待下一块到达
  }

  _audio.play()
    .then(() => {
      ttsState.value = 'playing'
      ttsChunkProgress.value = { cur: idx + 1, total: _chunks.length }
    })
    .catch(e => {
      if (_session !== mySid) return
      ttsState.value = 'idle'
      ttsError.value = '播放失败，请重试'
      console.error('TTS play error', e)
    })
}

function _revokeAll() {
  Object.values(_buffers).forEach(url => { if (url) try { URL.revokeObjectURL(url) } catch {} })
  _buffers = {}
  _fetching = {}
}

async function toggleTTS() {
  if (ttsState.value === 'loading') return

  if (ttsState.value === 'idle') {
    const text = buildSpeechText()
    if (!text) return

    // iOS Safari: 在用户手势栈中同步创建并 play 一次静音音频，解锁 HTMLAudioElement。
    // 此后异步调用 play() 仍可正常播放（元素已信任）。
    if (!_audio) {
      _audio = new Audio()
      _audio.preload = 'auto'
    }
    const SILENT = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA'
    _audio.src = SILENT
    try { await _audio.play(); _audio.pause() } catch { /* 忽略自动播放策略拒绝 */ }

    _chunks  = _buildChunks(text)
    if (!_chunks.length) return

    _session++
    _playIdx = 0
    _revokeAll()
    ttsError.value = ''
    ttsState.value = 'loading'
    ttsChunkProgress.value = { cur: 0, total: _chunks.length }

    _prefetch()

  } else if (ttsState.value === 'playing') {
    _audio.pause()
    ttsState.value = 'paused'

  } else if (ttsState.value === 'paused') {
    try {
      await _audio.play()
      ttsState.value = 'playing'
    } catch {
      ttsState.value = 'idle'
      ttsError.value = '恢复播放失败，请重新点击朗读'
    }
  }
}

function stopTTS() {
  _session++
  if (_audio) {
    _audio.pause()
    const oldSrc = _audio.src
    _audio.src = ''
    _audio.onended = null
    if (oldSrc && oldSrc.startsWith('blob:')) { try { URL.revokeObjectURL(oldSrc) } catch {} }
  }
  _revokeAll()
  ttsState.value = 'idle'
  ttsError.value = ''
  ttsChunkProgress.value = { cur: 0, total: 0 }
}

const loading = ref(true)
const running = ref(false)
const report = ref(null)
const analysis = ref(null)
const reportUrl = ref(null)
const usMarket = ref(null)
const newsExpanded = ref(false)

const newsItems = computed(() => analysis.value?._news_items || [])

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
onUnmounted(() => {
  stopTimers()
  stopTTS()
})
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
.voice-select {
  background: rgba(255,255,255,.15); color: #fff; border: 1px solid rgba(255,255,255,.3);
  border-radius: 7px; padding: 6px 8px; font-size: 12px; cursor: pointer; outline: none;
  font-family: inherit;
}
.voice-select option { background: #1e3a8a; color: #fff; }
.btn-tts { background: rgba(255,255,255,.15); color: #fff; border: 1px solid rgba(255,255,255,.3);
           display: flex; align-items: center; gap: 5px; }
.btn-tts:hover:not(:disabled) { background: rgba(255,255,255,.28); }
.btn-tts:disabled { opacity: .55; cursor: not-allowed; }
.btn-tts-stop { background: rgba(255,255,255,.1); color: #fff; border: 1px solid rgba(255,255,255,.2);
                padding: 7px 10px; min-width: unset; }
.btn-tts-stop:hover { background: rgba(255,255,255,.22); }
.tts-reading-badge { color: #fde68a; font-size: 11px; animation: pulse 1.5s infinite; }
.tts-loading-dot {
  width: 10px; height: 10px; border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .7s linear infinite; flex-shrink: 0;
}
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

/* News briefing */
.toggle-news-btn {
  margin-left: auto; background: none; border: 1px solid #dbeafe; color: #2563eb;
  border-radius: 6px; padding: 2px 10px; font-size: 11px; cursor: pointer;
  font-weight: 600; transition: background .15s;
}
.toggle-news-btn:hover { background: #eff6ff; }

.news-list { display: flex; flex-direction: column; gap: 0; }

.news-item {
  padding: 8px 12px; border-bottom: 1px solid #f3f4f6;
  display: flex; flex-direction: column; gap: 4px;
}
.news-item:last-child { border-bottom: none; }
.news-item.news-high   { border-left: 3px solid #ef4444; }
.news-item.news-medium { border-left: 3px solid #f59e0b; }
.news-item.news-low    { border-left: 3px solid #9ca3af; }

.news-title-row { display: flex; align-items: flex-start; gap: 7px; }

.signal-pill {
  flex-shrink: 0; padding: 1px 6px; border-radius: 8px; font-size: 10px;
  font-weight: 700; margin-top: 1px;
}
.signal-high   { background: #fef2f2; color: #dc2626; }
.signal-medium { background: #fffbeb; color: #d97706; }
.signal-low    { background: #f0fdf4; color: #16a34a; }

.news-link {
  font-size: 13px; color: #111827; font-weight: 500; line-height: 1.5;
  text-decoration: none; border-bottom: 1px solid #d1d5db; transition: color .15s;
}
.news-link:hover { color: #2563eb; border-bottom-color: #2563eb; }
.news-title-plain { font-size: 13px; color: #374151; line-height: 1.5; }

.news-meta { display: flex; gap: 10px; font-size: 11px; color: #9ca3af; padding-left: 27px; }

.tts-error-tip { font-size: 12px; color: #d97706; background: #fffbeb; border: 1px solid #fde68a;
                 border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; }
.disclaimer { font-size: 11px; color: #9ca3af; text-align: center;
              padding-top: 16px; border-top: 1px solid #f3f4f6; margin-top: 8px; }

/* ── 移动端响应式 ── */
@media (max-width: 640px) {
  .modal-overlay { padding: 0; align-items: flex-end; }
  .modal {
    border-radius: 20px 20px 0 0; max-width: 100vw;
    max-height: 96dvh; display: flex; flex-direction: column;
  }
  .modal-header { padding: 12px 14px; gap: 6px; }
  .modal-header h2 { font-size: 0.95rem; }
  .title-icon { font-size: 1.2rem; }
  .header-actions { gap: 5px; }
  .btn { padding: 6px 10px; font-size: 12px; }
  /* 移动端隐藏"查看完整报告"按钮（已在历史弹窗中提供） */
  .btn-view { display: none; }
  /* 声音选择下拉收窄 */
  .voice-select { max-width: 90px; font-size: 11px; padding: 4px 6px; }
  .modal-body { padding: 14px 14px; max-height: unset; flex: 1; overflow-y: auto; }
  .running-state { padding: 20px 14px 16px; }
  .running-header { flex-direction: column; gap: 12px; }
  .market-grid { gap: 6px; }
  .market-card { min-width: 80px; padding: 8px 10px; }
  .watch-grid { grid-template-columns: 1fr; }
  .stream-content { font-size: 11px; max-height: 200px; }
  .sentiment-row { flex-direction: column; gap: 8px; }
}
</style>
