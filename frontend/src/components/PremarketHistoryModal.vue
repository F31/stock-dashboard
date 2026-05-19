<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">盘前分析历史记录</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="state-center">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="error" class="state-center error-text">{{ error }}</div>

        <div v-else-if="reports.length === 0" class="state-center muted">暂无历史记录</div>

        <ul v-else class="report-list">
          <li
            v-for="r in reports"
            :key="r.id"
            class="report-item"
            :class="{ selected: selected && selected.id === r.id }"
            @click="select(r)"
          >
            <div class="report-main">
              <span class="report-date">{{ r.report_date }}</span>
              <span class="report-time">{{ r.report_time }}</span>
              <span class="status-badge" :class="r.status">{{ statusLabel(r.status) }}</span>
              <span v-if="isStuck(r)" class="stuck-badge" title="该任务超过20分钟仍未完成，将被自动清理">已超时</span>
              <span v-if="parsedTone(r)" :class="['tone-inline', toneClass(parsedTone(r))]">
                {{ parsedTone(r) }}
              </span>
            </div>
            <!-- 摘要：观察清单股票名 -->
            <div v-if="parsedWatchlist(r).length" class="report-summary">
              <span v-for="name in parsedWatchlist(r)" :key="name" class="stock-chip">{{ name }}</span>
            </div>
            <div class="report-meta">
              <span class="created-at">{{ r.created_at }}</span>
              <span v-if="isStuck(r)" class="stuck-hint">后台进程已中断，将在下次检查时自动删除</span>
            </div>
          </li>
        </ul>
      </div>

      <!-- Preview panel -->
      <div v-if="selected" class="preview-panel">
        <div class="preview-header">
          <span>{{ selected.report_date }} {{ selected.report_time }} — 分析摘要</span>
          <div class="preview-actions">
            <button v-if="selected.report_path" class="btn-sm btn-primary" @click="openReport">
              查看完整报告
            </button>
            <button class="btn-sm btn-ghost" @click="selected = null">关闭预览</button>
          </div>
        </div>

        <div v-if="loadingDetail" class="state-center"><div class="spinner"></div></div>
        <div v-else-if="analysis" class="preview-content">
          <!-- Sentiment -->
          <div class="preview-section">
            <div class="section-label">市场情绪</div>
            <span class="tone-badge" :class="toneClass(analysis.market_sentiment?.tone)">
              {{ analysis.market_sentiment?.tone || '—' }}
            </span>
            <p class="basis-text">{{ analysis.market_sentiment?.basis || '' }}</p>
          </div>

          <!-- Watchlist -->
          <div v-if="analysis.watchlist?.length" class="preview-section">
            <div class="section-label">观察清单（{{ analysis.watchlist.length }} 标的）</div>
            <div class="watch-chips">
              <span v-for="w in analysis.watchlist" :key="w.name" class="chip">
                {{ w.name }}
                <em>{{ w.industry_layer }}</em>
              </span>
            </div>
          </div>

          <!-- Premarket outlook -->
          <div v-if="analysis.premarket_outlook?.summary" class="preview-section">
            <div class="section-label">情景判断</div>
            <p class="outlook-text">{{ analysis.premarket_outlook.summary }}</p>
          </div>

          <!-- Error msg -->
          <div v-if="selected.error_msg" class="preview-section error-text">
            错误：{{ selected.error_msg }}
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { listPremarketReports, getPremarketReport } from '../api'

const emit = defineEmits(['close'])

const reports = ref([])
const loading = ref(true)
const error = ref('')
const selected = ref(null)
const analysis = ref(null)
const loadingDetail = ref(false)

onMounted(async () => {
  try {
    const res = await listPremarketReports(50)
    reports.value = res.data
  } catch (e) {
    error.value = '加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
})

async function select(r) {
  selected.value = r
  analysis.value = null
  if (r.status !== 'completed') return
  loadingDetail.value = true
  try {
    const res = await getPremarketReport(r.id)
    analysis.value = res.data.analysis || {}
  } catch {
    analysis.value = {}
  } finally {
    loadingDetail.value = false
  }
}

function openReport() {
  if (selected.value?.report_path) {
    window.open('/reports/' + selected.value.report_path, '_blank')
  }
}

function statusLabel(s) {
  return { completed: '已完成', running: '运行中', failed: '失败', pending: '等待' }[s] || s
}

function isStuck(r) {
  if (r.status !== 'running') return false
  if (!r.created_at) return false
  // created_at 格式 "YYYY-MM-DD HH:MM"
  const created = new Date(r.created_at.replace(' ', 'T'))
  return (Date.now() - created.getTime()) > 20 * 60 * 1000
}

function toneClass(tone) {
  if (!tone) return ''
  if (tone.includes('乐观')) return 'positive'
  if (tone.includes('谨慎') || tone.includes('悲观')) return 'negative'
  return 'neutral'
}

function _parseAnalysis(r) {
  try { return r.analysis_json ? JSON.parse(r.analysis_json) : null } catch { return null }
}

function parsedTone(r) {
  return _parseAnalysis(r)?.market_sentiment?.tone || ''
}

function parsedWatchlist(r) {
  return (_parseAnalysis(r)?.watchlist || []).map(w => w.name).filter(Boolean)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.modal-box {
  background: #fff; border-radius: 12px;
  width: 680px; max-width: 96vw; max-height: 88vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 8px 30px rgba(0,0,0,.2);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.modal-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.close-btn {
  background: none; border: none; color: #9ca3af; font-size: 18px;
  cursor: pointer; padding: 4px 8px; border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

.modal-body { flex: 1; overflow-y: auto; padding: 0; min-height: 0; }

.state-center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px; gap: 12px;
  color: #9ca3af; font-size: 14px;
}
.error-text { color: #dc2626; }
.muted { color: #9ca3af; }

.spinner {
  width: 28px; height: 28px; border: 3px solid #e5e7eb;
  border-top-color: #2563eb; border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.report-list { list-style: none; margin: 0; padding: 0; }
.report-item {
  padding: 12px 20px; cursor: pointer; border-bottom: 1px solid #f3f4f6;
  transition: background .15s;
}
.report-item:hover { background: #f9fafb; }
.report-item.selected { background: #eff6ff; border-left: 3px solid #2563eb; }

.report-main { display: flex; align-items: center; gap: 10px; }
.report-date { font-size: 14px; font-weight: 600; color: #1f2937; }
.report-time { font-size: 13px; color: #6b7280; }
.report-meta { margin-top: 3px; }
.created-at { font-size: 12px; color: #9ca3af; }

.status-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.status-badge.completed { background: #dcfce7; color: #166534; }
.status-badge.running   { background: #dbeafe; color: #1d4ed8; }
.status-badge.failed    { background: #fee2e2; color: #dc2626; }
.status-badge.pending   { background: #fef9c3; color: #854d0e; }

.stuck-badge {
  font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 500;
  background: #fef3c7; color: #92400e; border: 1px solid #fde68a;
}
.stuck-hint { font-size: 11px; color: #d97706; margin-left: 8px; }

.tone-inline {
  font-size: 10px; padding: 1px 7px; border-radius: 8px; font-weight: 600;
}
.tone-inline.positive { background: #dcfce7; color: #166534; }
.tone-inline.negative { background: #fee2e2; color: #dc2626; }
.tone-inline.neutral  { background: #dbeafe; color: #1d4ed8; }

.report-summary {
  display: flex; flex-wrap: wrap; gap: 4px; margin: 5px 0 2px;
}
.stock-chip {
  font-size: 11px; background: #f3f4f6; color: #374151;
  padding: 1px 7px; border-radius: 8px; border: 1px solid #e5e7eb;
}

/* Preview panel */
.preview-panel {
  border-top: 1px solid #e5e7eb; background: #f9fafb;
  max-height: 300px; overflow-y: auto; flex-shrink: 0;
}
.preview-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 20px; border-bottom: 1px solid #e5e7eb;
  font-size: 13px; color: #6b7280;
}
.preview-actions { display: flex; gap: 8px; }

.btn-sm {
  font-size: 12px; padding: 4px 12px; border-radius: 6px;
  border: none; cursor: pointer; font-weight: 500;
}
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover { background: #1d4ed8; }
.btn-ghost { background: #fff; color: #6b7280; border: 1px solid #d1d5db; }
.btn-ghost:hover { background: #f3f4f6; }

.preview-content { padding: 12px 20px; }
.preview-section { margin-bottom: 14px; }
.section-label {
  font-size: 11px; color: #9ca3af; text-transform: uppercase;
  letter-spacing: .05em; margin-bottom: 6px;
}

.tone-badge {
  display: inline-block; font-size: 13px; font-weight: 600;
  padding: 3px 12px; border-radius: 12px; margin-bottom: 6px;
}
.tone-badge.positive { background: #dcfce7; color: #166534; }
.tone-badge.negative { background: #fee2e2; color: #dc2626; }
.tone-badge.neutral  { background: #dbeafe; color: #1d4ed8; }

.basis-text { font-size: 12px; color: #6b7280; line-height: 1.5; margin: 0; }
.outlook-text { font-size: 13px; color: #374151; line-height: 1.6; margin: 0; }

.watch-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 12px; background: #e5e7eb; color: #374151;
  padding: 3px 10px; border-radius: 12px; display: flex; align-items: center; gap: 5px;
}
.chip em { font-style: normal; color: #9ca3af; font-size: 11px; }
</style>
