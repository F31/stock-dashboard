<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="$emit('close')">
      <div class="modal">

        <!-- Header -->
        <div class="modal-hdr">
          <div class="hdr-left">
            <span class="stock-name">{{ displayName }}</span>
            <span class="stock-code">{{ stock.stock_code }}</span>
            <span :class="['badge', badgeClass]">{{ marketLabel }}</span>
          </div>
          <div class="hdr-right">
            <span v-if="quanScore" :class="['quan-badge', quanBadgeCls]">
              {{ quanScore.label }}<em>({{ Math.round(quanScore.percentile_score) }})</em>
            </span>
            <button class="close-btn" @click="$emit('close')">×</button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="tab-bar">
          <button
            v-for="tab in tabs" :key="tab.key"
            :class="['tab-btn', { active: activeTab === tab.key }]"
            @click="activeTab = tab.key"
          >{{ tab.label }}</button>
        </div>

        <!-- Tab: 基本信息 -->
        <div v-if="activeTab === 'info'" class="tab-body">
          <div v-if="data" class="info-grid">
            <div class="info-price-row">
              <span :class="['big-price', trend]">
                {{ market === 'US' ? '$' : '¥' }}{{ data.price?.toFixed(2) ?? '--' }}
              </span>
              <span :class="['price-tag', trend]">
                {{ data.change_pct != null ? (data.change_pct >= 0 ? '+' : '') + data.change_pct.toFixed(2) + '%' : '--' }}
              </span>
              <span :class="['price-abs', trend]" v-if="data.change != null">
                {{ data.change >= 0 ? '+' : '' }}{{ data.change.toFixed(2) }}
              </span>
            </div>
            <div class="metrics-grid">
              <div class="mg-item" v-for="m in metricsList" :key="m.label">
                <div class="mg-label">{{ m.label }}</div>
                <div class="mg-value" :class="m.cls">
                  <template v-if="m.isSignal && m.value !== '--'">
                    <span :class="['sig-badge', sigClass(m.value)]">{{ m.value }}</span>
                  </template>
                  <template v-else>{{ m.value }}</template>
                </div>
              </div>
            </div>
            <!-- Sector Top5 Constituents -->
            <div v-if="isSector" class="top5-section">
              <div class="sec-ttl">🏆 Top10 成分股（按市值）</div>
              <div v-if="top5Loading" class="empty-tip">加载中...</div>
              <div v-else-if="top5Data.length === 0" class="empty-tip">暂无数据</div>
              <div class="m-table-wrap">
                <table v-if="top5Data.length" class="top5-table">
                  <thead>
                    <tr>
                      <th>#</th><th>名称</th><th>价格</th><th>涨跌幅</th>
                      <th>PE动态</th><th>PEG</th><th>净利增速</th><th>总市值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in top5Data" :key="s.code">
                      <td class="t5-rank">{{ s.rank }}</td>
                      <td class="t5-name">{{ s.name }}</td>
                      <td class="t5-num">{{ s.price != null ? s.price.toFixed(2) : '--' }}</td>
                      <td :class="['t5-num', s.change_pct != null ? (s.change_pct >= 0 ? 'val-up' : 'val-down') : '']">
                        {{ s.change_pct != null ? (s.change_pct >= 0 ? '+' : '') + s.change_pct.toFixed(2) + '%' : '--' }}
                      </td>
                      <td class="t5-num">{{ s.pe != null ? s.pe.toFixed(1) + '×' : '--' }}</td>
                      <td class="t5-num">{{ s.peg != null ? s.peg.toFixed(2) : '--' }}</td>
                      <td :class="['t5-num', s.profit_growth_rate != null ? (s.profit_growth_rate >= 0 ? 'val-up' : 'val-down') : '']">
                        {{ s.profit_growth_rate != null ? (s.profit_growth_rate >= 0 ? '+' : '') + s.profit_growth_rate.toFixed(1) + '%' : '--' }}
                      </td>
                      <td class="t5-num">{{ fmtCap(s.market_cap) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Sparkline -->
            <div class="sparkline-wrap" v-if="data.chart_data?.length >= 2">
              <svg :viewBox="`0 0 500 80`" class="sparkline">
                <polyline :points="chartPoints" :fill="chartColor + '22'" :stroke="chartColor" stroke-width="2"/>
              </svg>
            </div>
          </div>
          <div v-else class="empty-tip">行情数据加载中...</div>
        </div>

        <!-- Tab: 研究笔记 -->
        <div v-if="activeTab === 'notes'" class="tab-body notes-body">
          <textarea
            class="notes-ta"
            v-model="editingNotes"
            placeholder="记录研究笔记、投资逻辑、目标价位..."
          ></textarea>
          <div class="notes-ftr">
            <span class="char-count">{{ editingNotes.length }} 字</span>
            <button class="btn btn-primary" @click="saveNotes" :disabled="savingNotes">
              {{ savingNotes ? '保存中...' : '保存笔记' }}
            </button>
          </div>
        </div>

        <!-- Tab: 最新资讯 (lazy-loaded on first tab visit) -->
        <div v-if="activeTab === 'news'" class="tab-body">
          <div v-if="newsLoading" class="empty-tip">加载中...</div>
          <div v-else-if="!isSector && newsData.length" class="news-list">
            <a
              v-for="(n, i) in newsData" :key="i"
              :href="n.url" target="_blank" rel="noopener"
              class="news-item"
            >
              <span class="news-item-title">{{ n.title }}</span>
              <span class="news-item-meta">{{ n.source }} · {{ n.time }}</span>
            </a>
          </div>
          <div v-else class="empty-tip">暂无最新资讯</div>
        </div>

        <!-- Tab: 分析报告 -->
        <div v-if="activeTab === 'reports'" class="tab-body reports-body">
          <!-- Action bar -->
          <div class="report-actions">
            <label class="btn btn-outline upload-label">
              <span>📎 上传文件</span>
              <input type="file" accept=".pdf,.ppt,.pptx,.doc,.docx,.html,.htm" @change="handleFileUpload" hidden>
            </label>
            <button class="btn btn-outline" @click="showLinkDialog = true">🔗 添加链接</button>
          </div>

          <!-- Link dialog -->
          <div class="link-dialog" v-if="showLinkDialog">
            <div class="ld-title">添加外部链接</div>
            <input class="ld-input" v-model="linkTitle" placeholder="报告标题" />
            <input class="ld-input" v-model="linkUrl" placeholder="https://..." />
            <div class="ld-actions">
              <button class="btn btn-ghost" @click="showLinkDialog = false">取消</button>
              <button class="btn btn-primary" @click="submitLink" :disabled="submittingLink">
                {{ submittingLink ? '添加中...' : '确认添加' }}
              </button>
            </div>
          </div>

          <!-- Upload progress -->
          <div class="upload-progress" v-if="uploading">
            <span>上传中...</span>
          </div>

          <!-- Reports list -->
          <div v-if="reportsLoading" class="empty-tip">加载中...</div>
          <div v-else-if="!reports.length" class="empty-tip">暂无分析报告，点击上方按钮添加</div>
          <div v-else class="report-list">
            <div class="report-item" v-for="r in reports" :key="r.id">
              <div class="ri-icon">{{ r.report_type === 'auto' ? fileIcon(r.file_name) : r.report_type === 'file' ? fileIcon(r.file_name) : '🔗' }}</div>
              <div class="ri-main">
                <a class="ri-title" :href="r.url" target="_blank" rel="noopener">{{ r.title }}</a>
                <div class="ri-meta">
                  <span v-if="r.report_type === 'auto'" class="badge-auto">AUTO</span>
                  {{ r.uploader_name }} · {{ r.created_at }}
                </div>
              </div>
              <button
                v-if="r.report_type !== 'auto' && canDelete(r)"
                class="ri-del"
                @click="removeReport(r)"
                title="删除"
              >×</button>
            </div>
          </div>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { updateNotes, listReports, uploadReport, addLinkReport, deleteReport, fetchSectorTop5, fetchStockNews, fetchStockFinancials } from '../api/index.js'

// Module-level Map cache: survives modal open/close within the same session
const _newsCache = new Map()   // "code:market" → { data: [], ts: number }
const _NEWS_TTL  = 3600_000   // 1 hour — matches backend CACHE_TTL_NEWS

const props = defineProps({
  stock: { type: Object, required: true },
  currentUser: { type: Object, default: null },
  initialTab: { type: String, default: 'info' },
  quanScore: { type: Object, default: null },
})

const quanBadgeCls = computed(() => {
  if (!props.quanScore) return ''
  const p = props.quanScore.percentile_score
  if (p >= 90) return 'qb-strong'
  if (p >= 75) return 'qb-buy'
  if (p >= 50) return 'qb-neutral'
  return 'qb-avoid'
})
const emit = defineEmits(['close', 'notes-saved'])

const activeTab = ref(props.initialTab)
const tabs = computed(() => [
  { key: 'info',    label: '📊 基本信息' },
  { key: 'news',    label: '📰 最新资讯', hide: isSector.value },
  { key: 'notes',   label: '📝 研究笔记' },
  { key: 'reports', label: '📁 分析报告' },
].filter(t => !t.hide))

// ── Derived ──
const data = computed(() => props.stock.data)
const market = computed(() => props.stock.market)
const isSector = computed(() => props.stock.item_type === 'sector')
const displayName = computed(() =>
  data.value?.stock_name || props.stock.stock_name || props.stock.stock_code
)
const marketLabel = computed(() => ({ A: 'A股', HK: '港股', US: '美股', SECTOR: '板块' }[market.value] ?? market.value))
const badgeClass = computed(() => ({ A: 'ba', HK: 'bh', US: 'bu', SECTOR: 'bs' }[market.value] ?? ''))
const trend = computed(() => {
  const v = data.value?.change ?? data.value?.change_pct
  if (v == null) return 'flat'
  return v >= 0 ? 'up' : 'down'
})

function fmt(v, digits = 2, suffix = '') {
  return v != null ? v.toFixed(digits) + suffix : '--'
}
function fmtCap(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  return (v / 1e4).toFixed(2) + '万'
}
function fmtVol(v) {
  if (v == null) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(0)
}

function fmtCapex(v) {
  if (v == null) return '--'
  if (v >= 1e12) return (v / 1e12).toFixed(1) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toFixed(0)
}
function fmtGrowth(v) {
  if (v == null) return '--'
  return (v > 0 ? '+' : '') + v.toFixed(1) + '%'
}
function sigClass(s) {
  if (s === '买入') return 'sig-buy'
  if (s === '关注') return 'sig-watch'
  if (s === '减仓') return 'sig-reduce'
  return 'sig-hold'
}

const metricsList = computed(() => {
  const d = data.value
  if (!d) return []
  if (isSector.value) return []

  const g = d.profit_growth_rate
  const r = d.roe
  const dr = finData.value?.debt_ratio ?? d.debt_ratio
  const cf = finData.value?.cash_profit_ratio ?? d.cash_profit_ratio

  return [
    // ── 行情 ──
    { label: '昨收',   value: fmt(d.prev_close) },
    { label: '今开',   value: fmt(d.open) },
    { label: '最高',   value: fmt(d.high) },
    { label: '最低',   value: fmt(d.low) },
    { label: '总市值', value: fmtCap(d.market_cap) },
    { label: '流通市值', value: fmtCap(d.float_market_cap) },
    { label: '换手率', value: fmt(d.turnover_rate, 2, '%') },
    // ── 估值 ──
    { label: 'PE(动态)', value: d.pe != null ? d.pe.toFixed(1) + '×' : '--' },
    { label: 'PEG',      value: d.peg != null ? d.peg.toFixed(2) : '--' },
    { label: '净利增速', value: fmtGrowth(g), cls: g != null ? (g >= 0 ? 'val-up' : 'val-down') : '' },
    // ── 基本面 ──
    { label: 'ROE',    value: r != null ? r.toFixed(1) + '%' : '--',  cls: r != null ? (r >= 15 ? 'val-hi' : r < 8 ? 'val-lo' : '') : '' },
    { label: '负债率', value: dr != null ? dr.toFixed(1) + '%' : (finLoading.value ? '…' : '--'), cls: dr != null && dr > 70 ? 'val-warn' : '' },
    { label: '现金质量', value: cf != null ? cf.toFixed(0) + '%' : (finLoading.value ? '…' : '--'), cls: cf != null ? (cf >= 80 ? 'val-hi' : cf < 30 ? 'val-warn' : '') : '' },
    { label: d.capex_period ? `Capex(${d.capex_period})` : 'Capex', value: fmtCapex(d.capex) },
  ]
})

// Sparkline
const chartColor = computed(() => trend.value === 'up' ? '#dc2626' : trend.value === 'down' ? '#16a34a' : '#6b7280')
const chartPoints = computed(() => {
  const cd = data.value?.chart_data
  if (!cd || cd.length < 2) return ''
  const min = Math.min(...cd), max = Math.max(...cd)
  const range = max - min || 1
  return cd.map((v, i) => {
    const x = (i / (cd.length - 1)) * 500
    const y = 80 - ((v - min) / range) * 72 - 4
    return `${x},${y}`
  }).join(' ')
})

// ── Sector Top5 ──
const top5Data = ref([])
const top5Loading = ref(false)

async function loadTop5() {
  if (!isSector.value) return
  top5Loading.value = true
  try {
    const res = await fetchSectorTop5(props.stock.stock_code)
    top5Data.value = res.data
  } catch {
    top5Data.value = []
  } finally {
    top5Loading.value = false
  }
}

watch(activeTab, v => { if (v === 'info' && isSector.value) loadTop5() })
onMounted(() => { if (activeTab.value === 'info' && isSector.value) loadTop5() })

// ── THS Financials: lazy-load on modal open (debt_ratio, cash_profit_ratio) ──
const finData    = ref(null)
const finLoading = ref(false)

async function loadFinancials() {
  if (isSector.value || finData.value !== null) return
  finLoading.value = true
  try {
    const res = await fetchStockFinancials(props.stock.stock_code, props.stock.market)
    finData.value = res.data ?? {}
  } catch {
    finData.value = {}
  } finally {
    finLoading.value = false
  }
}

onMounted(() => { if (!isSector.value) loadFinancials() })

// ── News: lazy-load on first tab visit ──
const newsData    = ref([])
const newsLoading = ref(false)
const newsLoaded  = ref(false)

async function loadNews() {
  if (isSector.value || newsLoaded.value) return
  const key = `${props.stock.stock_code}:${props.stock.market}`
  const hit = _newsCache.get(key)
  if (hit && Date.now() - hit.ts < _NEWS_TTL) {
    newsData.value = hit.data
    newsLoaded.value = true
    return
  }
  newsLoading.value = true
  try {
    const res = await fetchStockNews(props.stock.stock_code, props.stock.market)
    const list = Array.isArray(res.data) ? res.data : []
    _newsCache.set(key, { data: list, ts: Date.now() })
    newsData.value = list
    newsLoaded.value = true
  } catch {
    newsData.value = []
  } finally {
    newsLoading.value = false
  }
}

watch(activeTab, v => { if (v === 'news') loadNews() })
onMounted(() => { if (activeTab.value === 'news') loadNews() })

// ── Notes ──
const editingNotes = ref(props.stock.notes || '')
const savingNotes = ref(false)

watch(() => props.stock.notes, v => { editingNotes.value = v || '' })

async function saveNotes() {
  if (!props.stock.id) return  // synthetic stock from fund flow — no DB record
  savingNotes.value = true
  try {
    await updateNotes(props.stock.id, editingNotes.value)
    emit('notes-saved', props.stock.id, editingNotes.value)
  } finally {
    savingNotes.value = false
  }
}

// ── Reports ──
const reports = ref([])
const reportsLoading = ref(false)
const uploading = ref(false)
const showLinkDialog = ref(false)
const linkTitle = ref('')
const linkUrl = ref('')
const submittingLink = ref(false)

async function loadReports() {
  reportsLoading.value = true
  try {
    const res = await listReports(props.stock.stock_code, props.stock.market)
    reports.value = res.data
  } catch (e) {
    reports.value = []
  } finally {
    reportsLoading.value = false
  }
}

watch(activeTab, v => { if (v === 'reports') loadReports() })
onMounted(() => { if (activeTab.value === 'reports') loadReports() })

function fileIcon(name) {
  if (!name) return '📄'
  const ext = name.split('.').pop().toLowerCase()
  return { pdf: '📕', ppt: '📙', pptx: '📙', doc: '📘', docx: '📘', html: '🌐', htm: '🌐' }[ext] ?? '📄'
}

function canDelete(r) {
  if (!props.currentUser) return false
  return props.currentUser.role === 'admin' || r.uploader_id === props.currentUser.id
}

async function handleFileUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  const title = file.name.replace(/\.[^.]+$/, '')
  uploading.value = true
  try {
    const res = await uploadReport(props.stock.stock_code, props.stock.market, title, file)
    reports.value.unshift(res.data)
  } catch (err) {
    alert(err.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
    e.target.value = ''
  }
}

async function submitLink() {
  if (!linkTitle.value.trim() || !linkUrl.value.trim()) return
  submittingLink.value = true
  try {
    const res = await addLinkReport(props.stock.stock_code, props.stock.market, linkTitle.value, linkUrl.value)
    reports.value.unshift(res.data)
    linkTitle.value = ''
    linkUrl.value = ''
    showLinkDialog.value = false
  } catch (err) {
    alert(err.response?.data?.detail || '添加失败')
  } finally {
    submittingLink.value = false
  }
}

async function removeReport(r) {
  if (!confirm(`确认删除「${r.title}」？`)) return
  try {
    await deleteReport(r.id)
    reports.value = reports.value.filter(x => x.id !== r.id)
  } catch (err) {
    alert(err.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 600; padding: 16px;
}
.modal {
  background: #fff; border-radius: 14px;
  width: 100%; max-width: 680px; max-height: 90vh;
  display: flex; flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
  overflow: hidden;
}

/* Header */
.modal-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.hdr-left  { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
.hdr-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.quan-badge {
  font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 12px;
  display: inline-flex; align-items: center; gap: 3px; white-space: nowrap;
}
.quan-badge em { font-style: normal; font-weight: 500; font-size: 10px; }
.qb-strong { background: #dcfce7; color: #15803d; }
.qb-buy    { background: #d1fae5; color: #047857; }
.qb-neutral{ background: #dbeafe; color: #1d4ed8; }
.qb-avoid  { background: #fee2e2; color: #dc2626; }
.stock-name { font-size: 18px; font-weight: 800; color: #111827; }
.stock-code { font-size: 13px; color: #6b7280; }
.badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; }
.ba { background: #fef3c7; color: #92400e; }
.bh { background: #dbeafe; color: #1e40af; }
.bu { background: #ede9fe; color: #5b21b6; }
.bs { background: #fce7f3; color: #9d174d; }
.close-btn {
  background: none; border: none; font-size: 22px; color: #9ca3af;
  cursor: pointer; width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px; flex-shrink: 0;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* Tabs */
.tab-bar {
  display: flex; gap: 0; border-bottom: 1px solid #e5e7eb;
  padding: 0 16px; flex-shrink: 0; background: #f9fafb;
}
.tab-btn {
  background: none; border: none; cursor: pointer;
  padding: 10px 16px; font-size: 13px; font-weight: 600; color: #6b7280;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all .15s;
}
.tab-btn:hover { color: #374151; }
.tab-btn.active { color: #2563eb; border-bottom-color: #2563eb; }

/* Tab body */
.tab-body { flex: 1; overflow-y: auto; padding: 18px 20px; }

/* Info tab */
.info-price-row {
  display: flex; align-items: baseline; gap: 10px;
  margin-bottom: 16px;
}
.big-price { font-size: 30px; font-weight: 900; }
.big-price.up { color: #dc2626; }
.big-price.down { color: #16a34a; }
.big-price.flat { color: #374151; }
.price-tag {
  font-size: 14px; font-weight: 700; padding: 4px 10px; border-radius: 6px;
}
.price-tag.up { background: #fee2e2; color: #dc2626; }
.price-tag.down { background: #dcfce7; color: #16a34a; }
.price-tag.flat { background: #f3f4f6; color: #6b7280; }
.price-abs { font-size: 14px; color: #6b7280; }

.metrics-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 1px; background: #e5e7eb;
  border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;
  margin-bottom: 14px;
}
.mg-item { background: #fff; padding: 10px 8px; text-align: center; }
.mg-label { font-size: 10px; color: #9ca3af; letter-spacing: .3px; margin-bottom: 4px; }
.mg-value { font-size: 13px; font-weight: 700; color: #111827; }
.val-up   { color: #dc2626; }
.val-down { color: #16a34a; }
.val-hi   { color: #15803d; }
.val-lo   { color: #9ca3af; }
.val-warn { color: #dc2626; }
.sig-badge {
  display: inline-block; font-size: 11px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px; white-space: nowrap;
}
.sig-buy    { background: #dcfce7; color: #15803d; }
.sig-watch  { background: #dbeafe; color: #1d4ed8; }
.sig-hold   { background: #f3f4f6; color: #6b7280; }
.sig-reduce { background: #fee2e2; color: #dc2626; }

.sparkline-wrap { height: 70px; margin-bottom: 14px; border: 1px solid #f3f4f6; border-radius: 8px; overflow: hidden; }
.sparkline { width: 100%; height: 100%; }

.top5-section { margin-bottom: 14px; }
.top5-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;
}
.top5-table th {
  background: #f9fafb; color: #6b7280; font-weight: 600;
  padding: 7px 6px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid #e5e7eb;
}
.top5-table th:first-child,
.top5-table th:nth-child(2) { text-align: left; }
.top5-table td { padding: 7px 6px; border-bottom: 1px solid #f3f4f6; }
.top5-table tr:last-child td { border-bottom: none; }
.top5-table tr:hover td { background: #f8fafc; }
.t5-rank { color: #9ca3af; font-weight: 700; width: 20px; }
.t5-name { color: #111827; font-weight: 600; max-width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t5-num { text-align: right; color: #374151; font-variant-numeric: tabular-nums; }

.sec-ttl { font-size: 11px; font-weight: 700; color: #6b7280; letter-spacing: .5px; text-transform: uppercase; margin-bottom: 8px; }
.news-list { display: flex; flex-direction: column; gap: 2px; }
.news-item {
  display: flex; flex-direction: column; gap: 4px;
  padding: 10px 0; border-bottom: 1px solid #f3f4f6;
  text-decoration: none; color: inherit;
}
.news-item:last-child { border-bottom: none; }
.news-item:hover .news-item-title { color: #2563eb; }
.news-item-title { font-size: 13px; color: #111827; line-height: 1.5; }
.news-item-meta { font-size: 11px; color: #9ca3af; }

/* Notes tab */
.notes-body { display: flex; flex-direction: column; gap: 0; }
.notes-ta {
  flex: 1; min-height: 300px; width: 100%;
  border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 12px 14px; font-size: 14px; font-family: inherit;
  color: #111827; background: #f9fafb; resize: vertical; line-height: 1.7;
}
.notes-ta:focus { outline: none; border-color: #2563eb; background: #fff; box-shadow: 0 0 0 3px rgba(37,99,235,.1); }
.notes-ta::placeholder { color: #9ca3af; }
.notes-ftr {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: 12px;
}
.char-count { font-size: 12px; color: #9ca3af; }

/* Reports tab */
.reports-body { display: flex; flex-direction: column; gap: 12px; }
.report-actions { display: flex; gap: 8px; flex-shrink: 0; }
.upload-label { cursor: pointer; }

.link-dialog {
  border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 14px; background: #f9fafb;
  display: flex; flex-direction: column; gap: 8px;
}
.ld-title { font-size: 13px; font-weight: 600; color: #374151; }
.ld-input {
  border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px;
  font-size: 13px; font-family: inherit; color: #111827; background: #fff;
}
.ld-input:focus { outline: none; border-color: #2563eb; }
.ld-actions { display: flex; gap: 8px; justify-content: flex-end; }

.upload-progress { font-size: 13px; color: #6b7280; padding: 4px 0; }

.report-list { display: flex; flex-direction: column; gap: 6px; }
.report-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px;
  background: #fff; transition: background .15s;
}
.report-item:hover { background: #f8fafc; }
.ri-icon { font-size: 20px; flex-shrink: 0; }
.ri-main { flex: 1; min-width: 0; }
.ri-title {
  font-size: 14px; font-weight: 600; color: #111827; text-decoration: none;
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ri-title:hover { color: #2563eb; }
.ri-meta { font-size: 11px; color: #9ca3af; margin-top: 2px; display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.badge-auto {
  display: inline-block; font-size: 10px; font-weight: 700;
  padding: 1px 5px; border-radius: 3px;
  background: #e0f2fe; color: #0369a1; letter-spacing: .3px;
}
.ri-del {
  background: none; border: none; cursor: pointer; font-size: 18px;
  color: #d1d5db; width: 28px; height: 28px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.ri-del:hover { background: #fee2e2; color: #dc2626; }

.empty-tip { text-align: center; color: #9ca3af; font-size: 13px; padding: 30px 0; }

/* Buttons */
.btn {
  padding: 8px 16px; border-radius: 6px; font-size: 13px;
  cursor: pointer; font-weight: 600; border: none; transition: all .15s;
  white-space: nowrap;
}
.btn:disabled { opacity: .6; cursor: not-allowed; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-outline { background: #fff; color: #374151; border: 1px solid #d1d5db; }
.btn-outline:hover { background: #f3f4f6; border-color: #9ca3af; }
.btn-ghost { background: none; color: #6b7280; border: 1px solid transparent; }
.btn-ghost:hover { background: #f3f4f6; }

/* ── 移动端响应式 ── */
@media (max-width: 640px) {
  .modal-overlay { padding: 0; align-items: flex-end; }
  .modal {
    border-radius: 20px 20px 0 0; max-width: 100vw; width: 100%;
    max-height: 96dvh;
  }
  .modal-hdr { padding: 12px 14px; }
  .stock-name { font-size: 15px; }
  .hdr-right { gap: 5px; }
  /* Tab bar: horizontal scroll when tabs don't fit */
  .tab-bar {
    overflow-x: auto; -webkit-overflow-scrolling: touch;
    scrollbar-width: none; flex-wrap: nowrap; padding: 0 10px;
  }
  .tab-bar::-webkit-scrollbar { display: none; }
  .tab-btn { padding: 9px 12px; font-size: 12px; white-space: nowrap; flex-shrink: 0; }
  .tab-body { padding: 12px 14px; }
  .big-price { font-size: 24px; }
  .metrics-grid { grid-template-columns: repeat(2, 1fr); }
  .top5-table { font-size: 11px; }
  .btn { padding: 7px 12px; font-size: 12px; }
}
</style>
