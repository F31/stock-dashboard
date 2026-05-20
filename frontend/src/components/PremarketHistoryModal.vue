<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">盘前分析历史记录</span>
        <span v-if="total > 0" class="modal-total">共 {{ total }} 条</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="state-center">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="error" class="state-center error-text">{{ error }}</div>

        <div v-else-if="reports.length === 0" class="state-center muted">暂无历史记录</div>

        <template v-else>
          <ul class="report-list">
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
                <button
                  v-if="r.report_path"
                  class="row-report-btn"
                  @click.stop="openReportModal(r)"
                >查看完整报告</button>
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

          <!-- 分页控件 -->
          <div v-if="totalPages > 1" class="pagination">
            <button class="page-btn" :disabled="page === 1" @click="goPage(page - 1)">← 上一页</button>
            <div class="page-info">
              <span class="page-current">第 {{ page }} 页</span>
              <span class="page-sep">/</span>
              <span class="page-total">共 {{ totalPages }} 页</span>
            </div>
            <button class="page-btn" :disabled="page === totalPages" @click="goPage(page + 1)">下一页 →</button>
          </div>
        </template>
      </div>

      <!-- Preview panel -->
      <div v-if="selected" class="preview-panel">
        <div class="preview-header">
          <span>{{ selected.report_date }} {{ selected.report_time }} — 分析摘要</span>
          <div class="preview-actions">
            <button v-if="selected.report_path" class="btn-sm btn-primary" @click="openReportModal(selected)">
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

  <!-- 完整报告弹窗 — teleport 到 body 避免事件冒泡关闭列表弹窗 -->
  <Teleport to="body">
    <div v-if="reportUrl" class="report-viewer-overlay" @click.self="reportUrl = null">
      <div class="report-viewer-box">
        <div class="report-viewer-header">
          <span class="report-viewer-title">{{ reportTitle }}</span>
          <div class="report-viewer-actions">
            <button class="btn-sm btn-share" :class="{ copied: copyDone }" @click="copyLink">
              {{ copyDone ? '链接已复制 ✓' : '复制分享链接' }}
            </button>
            <a :href="reportUrl" target="_blank" class="btn-sm btn-ghost">在新标签页打开</a>
            <button class="close-btn" @click="reportUrl = null">✕</button>
          </div>
        </div>
        <iframe :src="reportUrl" class="report-iframe" frameborder="0"></iframe>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listPremarketReports, getPremarketReport } from '../api'

const emit = defineEmits(['close'])

const PAGE_SIZE = 20

const reports = ref([])
const loading = ref(true)
const error = ref('')
const total = ref(0)
const page = ref(1)

const selected = ref(null)
const analysis = ref(null)
const loadingDetail = ref(false)

const reportUrl = ref(null)
const reportTitle = ref('')
const copyDone = ref(false)

const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE) || 1)

onMounted(() => loadPage(1))

async function loadPage(n) {
  loading.value = true
  error.value = ''
  selected.value = null
  analysis.value = null
  try {
    const res = await listPremarketReports(PAGE_SIZE, (n - 1) * PAGE_SIZE)
    total.value = res.data.total
    reports.value = res.data.items
    page.value = n
  } catch (e) {
    error.value = '加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function goPage(n) {
  if (n < 1 || n > totalPages.value) return
  loadPage(n)
}

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

function openReportModal(r) {
  if (!r?.report_path) return
  reportUrl.value = '/reports/' + r.report_path
  reportTitle.value = `${r.report_date} ${r.report_time} 完整报告`
  copyDone.value = false
}

let copyTimer = null
async function copyLink() {
  const url = window.location.origin + reportUrl.value
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    // fallback for environments without clipboard API
    const ta = document.createElement('textarea')
    ta.value = url
    ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copyDone.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copyDone.value = false }, 2500)
}

function statusLabel(s) {
  return { completed: '已完成', running: '运行中', failed: '失败', pending: '等待' }[s] || s
}

function isStuck(r) {
  if (r.status !== 'running') return false
  if (!r.created_at) return false
  // created_at 是 UTC 时间，拼接 Z 让浏览器正确解析（否则按本地时间解析会偏差8小时）
  const created = new Date(r.created_at.replace(' ', 'T') + 'Z')
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
  display: flex; align-items: center; gap: 8px;
  padding: 16px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.modal-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.modal-total { font-size: 12px; color: #9ca3af; margin-right: auto; }
.close-btn {
  background: none; border: none; color: #9ca3af; font-size: 18px;
  cursor: pointer; padding: 4px 8px; border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

.modal-body { flex: 1; overflow-y: auto; padding: 0; min-height: 0; display: flex; flex-direction: column; }

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

.report-list { list-style: none; margin: 0; padding: 0; flex: 1; }
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

/* 行内"查看完整报告"按钮：默认隐藏，hover/selected 时显示 */
.row-report-btn {
  margin-left: auto;
  font-size: 11px; padding: 2px 10px; border-radius: 8px; font-weight: 500;
  background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe;
  white-space: nowrap; flex-shrink: 0; cursor: pointer;
  opacity: 0; transition: opacity .15s;
}
.report-item:hover .row-report-btn,
.report-item.selected .row-report-btn { opacity: 1; }
.row-report-btn:hover { background: #dbeafe; }

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

/* 分页控件 */
.pagination {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 12px 20px; border-top: 1px solid #f3f4f6; flex-shrink: 0;
}
.page-btn {
  font-size: 12px; padding: 5px 14px; border-radius: 8px; font-weight: 500;
  background: #fff; color: #374151; border: 1px solid #d1d5db; cursor: pointer;
  transition: background .15s, border-color .15s;
}
.page-btn:hover:not(:disabled) { background: #f3f4f6; border-color: #9ca3af; }
.page-btn:disabled { opacity: .35; cursor: default; }
.page-info { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.page-current { font-weight: 600; color: #1f2937; }
.page-sep { color: #d1d5db; }
.page-total { color: #6b7280; }

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
  border: none; cursor: pointer; font-weight: 500; text-decoration: none;
  display: inline-flex; align-items: center;
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

/* 完整报告弹窗 */
.report-viewer-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.65);
  display: flex; align-items: center; justify-content: center; z-index: 3000;
}
.report-viewer-box {
  background: #fff; border-radius: 12px;
  width: 90vw; height: 88vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 12px 48px rgba(0,0,0,.35);
}
.report-viewer-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.report-viewer-title { font-size: 14px; font-weight: 600; color: #1f2937; }
.report-viewer-actions { display: flex; align-items: center; gap: 10px; }
.report-iframe { flex: 1; width: 100%; border: none; }

.btn-share {
  background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0;
  transition: background .15s, color .15s, border-color .15s;
}
.btn-share:hover { background: #dcfce7; }
.btn-share.copied { background: #dcfce7; color: #15803d; border-color: #86efac; cursor: default; }
</style>
