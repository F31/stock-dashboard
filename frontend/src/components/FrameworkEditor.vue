<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <!-- ── Header ── -->
      <div class="modal-header">
        <span class="modal-title">产业链矩阵配置</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="modal-body">
        <!-- ── Sidebar ── -->
        <div class="sidebar">
          <button class="btn-new" @click="openNew">+ 新增产业链</button>
          <div v-for="fw in frameworks" :key="fw.id"
               class="fw-item" :class="{ selected: editing?.id === fw.id }"
               @click="selectFw(fw)">
            <div class="fw-item-name">{{ fw.name }}</div>
            <div class="fw-item-meta">
              <span v-if="fw.is_active" class="badge-active">活跃</span>
              <span class="badge-counts">{{ fwLayerCount(fw) }}层 · {{ fwCoCount(fw) }}企业</span>
            </div>
          </div>
          <div v-if="!frameworks.length && !loading" class="sidebar-empty">暂无产业链</div>
          <div v-if="loading" class="sidebar-empty">加载中…</div>
        </div>

        <!-- ── Editor ── -->
        <div class="editor" v-if="editing">
          <!-- Topbar -->
          <div class="editor-topbar">
            <div class="editor-meta">
              <input v-model="editing.name" class="name-input" placeholder="产业链名称" />
              <input v-model="editing.description" class="desc-input" placeholder="描述（可选）" />
            </div>
            <div class="editor-actions">
              <button v-if="!editing.is_active" class="btn-activate"
                      :disabled="saving || !editing.id" @click="doActivate">设为活跃</button>
              <button v-else class="btn-active-ind" disabled>● 当前活跃</button>
              <button class="btn-save" :disabled="saving" @click="doSave">
                {{ saving ? '保存中…' : '保存' }}
              </button>
              <button v-if="editing.id && !editing.is_active" class="btn-del"
                      :disabled="saving" @click="openDialog({ type: 'deleteFw' })">删除</button>
            </div>
          </div>
          <div v-if="saveError" class="save-error">{{ saveError }}</div>

          <!-- Tab bar -->
          <div class="tab-bar">
            <button class="tab-btn" :class="{ active: tab === 'canvas' }" @click="tab = 'canvas'">矩阵视图</button>
            <button class="tab-btn" :class="{ active: tab === 'keywords' }" @click="tab = 'keywords'">关键词词典</button>
          </div>

          <!-- ══════ WYSIWYG Canvas ══════ -->
          <div v-if="tab === 'canvas'" class="canvas-wrap">
            <div class="canvas-toolbar">
              <button class="btn-add-layer" @click="openDialog({ type: 'addLayer' })">
                <IcoPlus /> 添加层级
              </button>
              <span class="canvas-hint">层级从下往上构建（L1 在底部）；概念板块可拖动排序</span>
            </div>

            <div class="canvas-scroll">
              <div v-if="!layers.length" class="canvas-empty">
                点击"添加层级"开始构建矩阵
              </div>

              <div v-for="layer in reversedLayers" :key="layer.id"
                   class="layer-row"
                   @mouseenter="hovLay = layer.id"
                   @mouseleave="hovLay = null">

                <!-- Layer header -->
                <div class="layer-hdr">
                  <span class="layer-id-badge"
                        :class="layer.physical_bottleneck ? 'bn-badge' : 'norm-badge'">
                    {{ layer.id }}
                  </span>
                  <span class="layer-name">{{ layer.name }}</span>
                  <span v-if="layer.physical_bottleneck" class="bn-chip">★物理瓶颈</span>
                  <span class="layer-desc">{{ layer.description }}</span>
                  <!-- Floating layer buttons: edit + delete only -->
                  <div class="layer-acts" :class="{ show: hovLay === layer.id }">
                    <button class="icon-btn" title="编辑层级"
                            @click.stop="openDialog({ type: 'editLayer', layer })">
                      <IcoPencil />
                    </button>
                    <button class="icon-btn icon-btn-danger" title="删除层级"
                            @click.stop="openDialog({ type: 'deleteLayer', layer })">
                      <IcoTrash />
                    </button>
                  </div>
                </div>

                <!-- Sectors row (draggable) -->
                <div class="sectors-row"
                     @dragover.prevent
                     @drop="onDropLayer($event, layer)">
                  <div v-if="!layer.sectors?.length" class="sectors-empty">
                    悬停此层级 → 点击下方按钮添加概念板块
                  </div>
                  <div v-for="(sector, si) in layer.sectors" :key="sector.id"
                       class="sector-card"
                       :class="{ 'drop-here': dragOverLay === layer.id && dragOverIdx === si }"
                       draggable="true"
                       @dragstart="onDragStart($event, layer.id, si)"
                       @dragover.prevent="onDragOver($event, layer.id, si)"
                       @dragleave="dragOverLay = null; dragOverIdx = null"
                       @drop.stop="onDrop($event, layer, si)"
                       @mouseenter.stop="onSectorEnter($event, layer, sector, si)"
                       @mouseleave.stop="onSectorLeave">

                    <!-- Sector header (compact, no company list) -->
                    <div class="sector-hdr">
                      <span class="grip">⠿</span>
                      <div class="sector-info">
                        <span class="sector-name">{{ sector.name }}</span>
                        <span v-if="sector.physical_bottleneck" class="sector-bn">★</span>
                      </div>
                      <span class="co-count-badge">{{ sector.companies?.length || 0 }}企业</span>
                      <!-- Edit + delete only -->
                      <div class="sector-acts" :class="{ show: hovSec === sector.id }">
                        <button class="icon-btn icon-btn-sm" title="编辑概念板块"
                                @click.stop="openDialog({ type: 'editSector', layer, sector, si })">
                          <IcoPencil />
                        </button>
                        <button class="icon-btn icon-btn-sm icon-btn-danger" title="删除概念板块"
                                @click.stop="openDialog({ type: 'deleteSector', layer, sector, si })">
                          <IcoTrash />
                        </button>
                      </div>
                    </div>
                    <div v-if="sector.description" class="sector-desc">{{ sector.description }}</div>
                  </div>
                </div>

                <!-- Add concept sector button: bottom-center, visible on layer hover -->
                <div class="add-csector-bar" :class="{ show: hovLay === layer.id }">
                  <button class="btn-add-csector"
                          @click.stop="openDialog({ type: 'addSector', layer })">
                    <IcoPlus /> 添加概念板块
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- ══════ Keywords Tab ══════ -->
          <div v-if="tab === 'keywords'" class="tab-content kw-layout">
            <div class="kw-sidebar">
              <div v-for="item in kwLayerList" :key="item.id"
                   class="kw-item" :class="{ selected: kwSel === item.id }"
                   @click="kwSel = item.id">
                <span class="kw-badge" :class="item.type === 'layer' ? 'kw-layer' : 'kw-col'">
                  {{ item.type === 'layer' ? '层' : '列' }}
                </span>
                {{ item.id }} · {{ item.name }}
                <span class="kw-count">{{ (editing.keyword_dict[item.id] || []).length }}</span>
              </div>
            </div>
            <div class="kw-editor" v-if="kwSel">
              <div class="kw-editor-head">
                <strong>{{ kwSel }}</strong> 关键词
                <span class="hint">每行一个，大小写不敏感</span>
              </div>
              <textarea class="kw-textarea" :value="kwText" @input="onKwInput"
                        placeholder="每行一个关键词…" spellcheck="false"></textarea>
              <div class="kw-foot">共 {{ (editing.keyword_dict[kwSel] || []).length }} 个关键词</div>
            </div>
            <div v-else class="kw-editor kw-ph">← 选择左侧层/列编辑关键词</div>
          </div>
        </div>

        <div class="editor editor-empty" v-else-if="!loading">
          <span>← 选择左侧产业链开始编辑</span>
        </div>
      </div>
    </div>
  </div>

  <!-- ══ Enterprise popup (hover on sector) ══ -->
  <Teleport to="body">
    <div v-if="popupInfo"
         class="co-popup"
         :style="popupStyle"
         @mouseenter="onPopupEnter"
         @mouseleave="onPopupLeave">
      <div class="co-popup-hdr">
        <span class="co-popup-title">{{ popupInfo.sector.name }}</span>
        <button class="btn-add-co"
                @click="openDialog({ type: 'addCompany', layer: popupInfo.layer, sector: popupInfo.sector, si: popupInfo.si })">
          <IcoPlus /> 添加企业
        </button>
      </div>
      <div class="co-popup-body">
        <div v-if="!popupInfo.sector.companies?.length" class="co-popup-empty">
          暂无企业，点击右上角添加
        </div>
        <div v-for="(co, ci) in popupInfo.sector.companies" :key="ci"
             class="co-row"
             @click="openDialog({ type: 'editCompany', layer: popupInfo.layer, sector: popupInfo.sector, si: popupInfo.si, co, ci })">
          <div class="co-main">
            <span class="co-name">{{ co.name }}</span>
            <span class="co-code" v-if="co.symbol">{{ co.symbol }}</span>
            <span class="co-mkt" v-if="co.market">{{ co.market }}</span>
          </div>
          <button class="co-del"
                  @click.stop="openDialog({ type: 'deleteCompany', sector: popupInfo.sector, ci })">
            <IcoTrash />
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- ══ Dialogs ══ -->
  <Teleport to="body">
    <div v-if="dialog" class="dlg-overlay" @click.self="closeDialog">
      <div class="dlg-box" :class="dlgSize">

        <!-- ─ Add / Edit Layer ─ -->
        <template v-if="dialog.type === 'addLayer' || dialog.type === 'editLayer'">
          <div class="dlg-hdr">
            <span>{{ dialog.type === 'addLayer' ? '添加层级' : '编辑层级' }}</span>
            <button class="close-btn" @click="closeDialog">✕</button>
          </div>
          <div class="dlg-body">
            <div class="frow">
              <label>层级 ID <span class="req">*</span></label>
              <input v-model="form.id" class="finput mono" placeholder="如 L1, L2, L9…"
                     :readonly="dialog.type === 'editLayer'" />
            </div>
            <div class="frow">
              <label>名称 <span class="req">*</span></label>
              <input v-model="form.name" class="finput" placeholder="如 L1·能源" />
            </div>
            <div class="frow frow-check">
              <label><input type="checkbox" v-model="form.physical_bottleneck" /> ★ 物理瓶颈层</label>
            </div>
            <div class="frow">
              <label>描述</label>
              <input v-model="form.description" class="finput" placeholder="简短描述" />
            </div>
            <div v-if="formErr" class="ferr">{{ formErr }}</div>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-primary" @click="submitLayerForm">保存</button>
          </div>
        </template>

        <!-- ─ Add / Edit Sector (概念板块) ─ -->
        <template v-if="dialog.type === 'addSector' || dialog.type === 'editSector'">
          <div class="dlg-hdr">
            <span>{{ dialog.type === 'addSector' ? '添加概念板块' : '编辑概念板块' }}（{{ dialog.layer.id }}）</span>
            <button class="close-btn" @click="closeDialog">✕</button>
          </div>
          <div class="dlg-body">
            <div class="frow">
              <label>板块 ID <span class="req">*</span></label>
              <input v-model="form.id" class="finput mono" placeholder="如 s-L1-cloud" />
            </div>
            <div class="frow">
              <label>名称 <span class="req">*</span></label>
              <input v-model="form.name" class="finput" placeholder="如 核电+电网" />
            </div>
            <div class="frow frow-check">
              <label><input type="checkbox" v-model="form.physical_bottleneck" /> ★ 瓶颈板块</label>
            </div>
            <div class="frow">
              <label>描述</label>
              <input v-model="form.description" class="finput" placeholder="简短描述" />
            </div>
            <div v-if="formErr" class="ferr">{{ formErr }}</div>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-primary" @click="submitSectorForm">保存</button>
          </div>
        </template>

        <!-- ─ Add / Edit Company (企业) ─ -->
        <template v-if="dialog.type === 'addCompany' || dialog.type === 'editCompany'">
          <div class="dlg-hdr">
            <span>{{ dialog.type === 'addCompany' ? '添加企业' : '编辑企业' }}（{{ dialog.sector.name }}）</span>
            <button class="close-btn" @click="closeDialog">✕</button>
          </div>
          <div class="dlg-body">
            <div class="frow">
              <label>名称 <span class="req">*</span></label>
              <input v-model="form.name" class="finput" placeholder="如 英伟达" />
            </div>
            <div class="frow">
              <label>股票代码</label>
              <input v-model="form.symbol" class="finput mono" placeholder="如 NVDA、688256" />
            </div>
            <div class="frow">
              <label>市场</label>
              <select v-model="form.market" class="fselect">
                <option value="US">US（美股）</option>
                <option value="A">A（A股）</option>
                <option value="HK">HK（港股）</option>
                <option value="">未上市</option>
              </select>
            </div>
            <div class="frow">
              <label>别名（逗号分隔）</label>
              <input v-model="form.aliases" class="finput" placeholder="英伟达, NVIDIA, Nvidia" />
            </div>
            <div v-if="formErr" class="ferr">{{ formErr }}</div>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-primary" @click="submitCompanyForm">保存</button>
          </div>
        </template>

        <!-- ─ Delete Layer ─ -->
        <template v-if="dialog.type === 'deleteLayer'">
          <div class="dlg-hdr"><span>确认删除层级</span>
            <button class="close-btn" @click="closeDialog">✕</button></div>
          <div class="dlg-body">
            <p>确定删除层级 <strong>{{ dialog.layer.name }}</strong>？<br>
              其下所有概念板块和企业将一并删除，不可恢复。</p>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-danger" @click="doDeleteLayer">删除</button>
          </div>
        </template>

        <!-- ─ Delete Sector ─ -->
        <template v-if="dialog.type === 'deleteSector'">
          <div class="dlg-hdr"><span>确认删除概念板块</span>
            <button class="close-btn" @click="closeDialog">✕</button></div>
          <div class="dlg-body">
            <p>确定删除概念板块 <strong>{{ dialog.sector.name }}</strong>？<br>
              其下所有企业将一并删除，不可恢复。</p>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-danger" @click="doDeleteSector">删除</button>
          </div>
        </template>

        <!-- ─ Delete Company (企业) ─ -->
        <template v-if="dialog.type === 'deleteCompany'">
          <div class="dlg-hdr"><span>确认删除企业</span>
            <button class="close-btn" @click="closeDialog">✕</button></div>
          <div class="dlg-body">
            <p>确定删除企业 <strong>{{ dialog.sector.companies[dialog.ci]?.name }}</strong>？</p>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-danger" @click="doDeleteCompany">删除</button>
          </div>
        </template>

        <!-- ─ Delete Framework ─ -->
        <template v-if="dialog.type === 'deleteFw'">
          <div class="dlg-hdr"><span>确认删除产业链</span>
            <button class="close-btn" @click="closeDialog">✕</button></div>
          <div class="dlg-body">
            <p>确定删除产业链 <strong>{{ editing.name }}</strong>？此操作不可恢复。</p>
          </div>
          <div class="dlg-foot">
            <button class="btn-cancel" @click="closeDialog">取消</button>
            <button class="btn-danger" :disabled="saving" @click="doDeleteFw">
              {{ saving ? '删除中…' : '删除' }}
            </button>
          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue'
import {
  listFrameworks, createFramework, updateFramework,
  deleteFramework, setActiveFramework,
} from '../api'

// ── Icon components — render functions (no template compiler needed) ──────────
const IcoPencil = () => h('svg', {
  width: '13', height: '13', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2',
  'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  style: 'display:block;flex-shrink:0',
}, [
  h('path', { d: 'M12 20h9' }),
  h('path', { d: 'M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z' }),
])

const IcoTrash = () => h('svg', {
  width: '13', height: '13', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2',
  'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  style: 'display:block;flex-shrink:0',
}, [
  h('polyline', { points: '3 6 5 6 21 6' }),
  h('path', { d: 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2' }),
])

const IcoPlus = () => h('svg', {
  width: '13', height: '13', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.5', 'stroke-linecap': 'round',
  style: 'display:block;flex-shrink:0',
}, [
  h('line', { x1: '12', y1: '5', x2: '12', y2: '19' }),
  h('line', { x1: '5', y1: '12', x2: '19', y2: '12' }),
])

const emit = defineEmits(['close'])

// ── State ──────────────────────────────────────────────────────────────────

const frameworks = ref([])
const loading    = ref(true)
const editing    = ref(null)
const tab        = ref('canvas')
const saving     = ref(false)
const saveError  = ref('')

// canvas hover / drag
const hovLay      = ref(null)
const hovSec      = ref(null)
const dragSrcLay  = ref(null)
const dragSrcIdx  = ref(null)
const dragOverLay = ref(null)
const dragOverIdx = ref(null)

// enterprise popup (hover on sector card)
const popupInfo  = ref(null)  // { sector, layer, si, rect }
let   popupTimer = null

// dialog
const dialog  = ref(null)
const form    = ref({})
const formErr = ref('')

// keyword tab
const kwSel = ref('')

// ── Computed ────────────────────────────────────────────────────────────────

const layers         = computed(() => editing.value?.framework_data?.layers || [])
const reversedLayers = computed(() => [...layers.value].reverse())

const dlgSize = computed(() => {
  const t = dialog.value?.type
  return (t && (t.startsWith('delete') || t === 'deleteFw')) ? 'dlg-sm' : ''
})

const kwLayerList = computed(() => {
  const ls   = layers.value.map(l => ({ id: l.id, type: 'layer',  name: l.name }))
  const cols = [
    { id: 'cloud',       type: 'column', name: '云侧' },
    { id: 'edge',        type: 'column', name: '端侧' },
    { id: 'physical_ai', type: 'column', name: '物理AI' },
  ]
  return [...ls, ...cols]
})

const kwText = computed(() => {
  if (!kwSel.value || !editing.value) return ''
  return (editing.value.keyword_dict[kwSel.value] || []).join('\n')
})

// Position the enterprise popup relative to the hovered sector card
const popupStyle = computed(() => {
  if (!popupInfo.value) return {}
  const { rect } = popupInfo.value
  const winW = window.innerWidth
  const winH = window.innerHeight
  const minW = Math.max(rect.width, 240)
  const left = Math.max(8, Math.min(rect.left, winW - minW - 8))

  const style = {
    position: 'fixed',
    left:     left + 'px',
    minWidth: minW + 'px',
    maxWidth: '300px',
    zIndex:   '2500',
  }
  // show below unless too close to bottom
  if (rect.bottom + 260 < winH) {
    style.top = (rect.bottom + 5) + 'px'
  } else {
    style.bottom = (winH - rect.top + 5) + 'px'
  }
  return style
})

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(load)

// ── Load / Select ────────────────────────────────────────────────────────────

async function load() {
  loading.value = true
  try {
    const res = await listFrameworks()
    frameworks.value = res.data
  } finally {
    loading.value = false
  }
}

function fwLayerCount(fw) {
  return fw.framework_data?.layers?.length
    ?? (fw.layer_definition || []).filter(d => d.type === 'layer').length
}
function fwCoCount(fw) {
  if (fw.framework_data?.layers) {
    return fw.framework_data.layers.reduce(
      (s, l) => s + (l.sectors || []).reduce((s2, sec) => s2 + (sec.companies || []).length, 0), 0)
  }
  return (fw.entity_matrix || []).length
}

function selectFw(fw) {
  const clone = JSON.parse(JSON.stringify(fw))
  if (!clone.framework_data?.layers?.length
      && (clone.layer_definition?.length || clone.entity_matrix?.length)) {
    clone.framework_data = buildFdFromFlat(clone)
  }
  if (!clone.framework_data)  clone.framework_data  = { layers: [] }
  if (!clone.keyword_dict)    clone.keyword_dict    = {}
  editing.value = clone
  tab.value = 'canvas'
  kwSel.value = ''
  saveError.value = ''
}

function openNew() {
  editing.value = {
    id: null, name: '', description: '', is_active: 0,
    framework_data: { layers: [] }, keyword_dict: {},
    layer_definition: [], entity_matrix: [],
  }
  tab.value = 'canvas'
  saveError.value = ''
}

function buildFdFromFlat(fw) {
  const layerDefs = (fw.layer_definition || []).filter(d => d.type === 'layer')
  const entities  = fw.entity_matrix || []
  return {
    layers: layerDefs.map(ld => {
      const cos = entities.filter(e => (e.layers || []).includes(ld.id))
      return {
        id: ld.id, name: ld.name,
        physical_bottleneck: ld.physical_bottleneck || false,
        description: ld.description || '',
        sectors: cos.length ? [{
          id: `s-${ld.id}-all`,
          name: ld.name.replace(/^L\d+·?/, '') || ld.id,
          physical_bottleneck: ld.physical_bottleneck || false,
          description: '',
          companies: cos.map(co => ({
            name: co.name, symbol: co.symbol, market: co.market,
            aliases: co.aliases || [co.name], columns: co.columns || [],
          })),
        }] : [],
      }
    }),
  }
}

// ── Dialog helpers ────────────────────────────────────────────────────────────

function openDialog(opts) {
  // Close the company popup whenever a dialog opens
  popupInfo.value = null
  clearTimeout(popupTimer)
  formErr.value = ''
  dialog.value = opts

  if (opts.type === 'addLayer') {
    form.value = { id: '', name: '', physical_bottleneck: false, description: '' }
  } else if (opts.type === 'editLayer') {
    form.value = { ...opts.layer }
  } else if (opts.type === 'addSector') {
    form.value = { id: '', name: '', physical_bottleneck: false, description: '' }
  } else if (opts.type === 'editSector') {
    form.value = { ...opts.sector }
  } else if (opts.type === 'addCompany') {
    form.value = { name: '', symbol: '', market: 'US', aliases: '' }
  } else if (opts.type === 'editCompany') {
    const co = opts.co
    form.value = {
      name:    co.name,
      symbol:  co.symbol  || '',
      market:  co.market  || '',
      aliases: (co.aliases || []).join(', '),
    }
  }
}

function closeDialog() {
  dialog.value = null
  formErr.value = ''
}

// ── Layer CRUD ────────────────────────────────────────────────────────────────

function submitLayerForm() {
  const f = form.value
  if (!f.id.trim())   { formErr.value = 'ID不能为空';  return }
  if (!f.name.trim()) { formErr.value = '名称不能为空'; return }
  const ls = editing.value.framework_data.layers
  if (dialog.value.type === 'addLayer') {
    if (ls.find(l => l.id === f.id.trim())) { formErr.value = `ID "${f.id}" 已存在`; return }
    ls.push({ id: f.id.trim(), name: f.name.trim(),
              physical_bottleneck: !!f.physical_bottleneck,
              description: f.description || '', sectors: [] })
  } else {
    const layer = dialog.value.layer
    layer.name = f.name.trim()
    layer.physical_bottleneck = !!f.physical_bottleneck
    layer.description = f.description || ''
  }
  closeDialog()
}

function doDeleteLayer() {
  const ls  = editing.value.framework_data.layers
  const idx = ls.indexOf(dialog.value.layer)
  if (idx !== -1) ls.splice(idx, 1)
  closeDialog()
}

// ── Sector CRUD ───────────────────────────────────────────────────────────────

function submitSectorForm() {
  const f = form.value
  if (!f.id.trim())   { formErr.value = 'ID不能为空';  return }
  if (!f.name.trim()) { formErr.value = '名称不能为空'; return }
  const layer = dialog.value.layer
  if (dialog.value.type === 'addSector') {
    if (layer.sectors.find(s => s.id === f.id.trim())) { formErr.value = `ID "${f.id}" 已存在`; return }
    layer.sectors.push({ id: f.id.trim(), name: f.name.trim(),
                         physical_bottleneck: !!f.physical_bottleneck,
                         description: f.description || '', companies: [] })
  } else {
    const sec = dialog.value.sector
    sec.id = f.id.trim(); sec.name = f.name.trim()
    sec.physical_bottleneck = !!f.physical_bottleneck
    sec.description = f.description || ''
  }
  closeDialog()
}

function doDeleteSector() {
  dialog.value.layer.sectors.splice(dialog.value.si, 1)
  closeDialog()
}

// ── Company CRUD ──────────────────────────────────────────────────────────────

function submitCompanyForm() {
  const f = form.value
  if (!f.name.trim()) { formErr.value = '名称不能为空'; return }
  const aliases = f.aliases.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  if (!aliases.length) aliases.push(f.name.trim())
  const co = {
    name:    f.name.trim(),
    symbol:  f.symbol.trim() || null,
    market:  f.market || null,
    aliases,
    columns: [],
  }
  const { sector, ci } = dialog.value
  if (dialog.value.type === 'addCompany') {
    sector.companies.push(co)
  } else {
    co.columns = sector.companies[ci]?.columns || []
    sector.companies[ci] = co
  }
  closeDialog()
}

function doDeleteCompany() {
  dialog.value.sector.companies.splice(dialog.value.ci, 1)
  closeDialog()
}

// ── Enterprise popup ──────────────────────────────────────────────────────────

function onSectorEnter(e, layer, sector, si) {
  clearTimeout(popupTimer)
  hovSec.value = sector.id
  const rect = e.currentTarget.getBoundingClientRect()
  popupInfo.value = { sector, layer, si, rect }
}

function onSectorLeave() {
  hovSec.value = null
  popupTimer = setTimeout(() => { popupInfo.value = null }, 140)
}

function onPopupEnter() {
  clearTimeout(popupTimer)
}

function onPopupLeave() {
  popupTimer = setTimeout(() => { popupInfo.value = null }, 140)
}

// ── Drag & Drop ───────────────────────────────────────────────────────────────

function onDragStart(e, layId, si) {
  dragSrcLay.value = layId; dragSrcIdx.value = si
  e.dataTransfer.effectAllowed = 'move'
}
function onDragOver(e, layId, si) {
  dragOverLay.value = layId; dragOverIdx.value = si
}
function onDropLayer(e, layer) {
  dragOverLay.value = null; dragOverIdx.value = null
}
function onDrop(e, layer, targetIdx) {
  e.preventDefault()
  const fromIdx = dragSrcIdx.value
  if (dragSrcLay.value !== layer.id || fromIdx === targetIdx || fromIdx === null) {
    dragSrcLay.value = dragSrcIdx.value = dragOverLay.value = dragOverIdx.value = null
    return
  }
  const [moved] = layer.sectors.splice(fromIdx, 1)
  layer.sectors.splice(targetIdx, 0, moved)
  dragSrcLay.value = dragSrcIdx.value = dragOverLay.value = dragOverIdx.value = null
}

// ── Keyword tab ───────────────────────────────────────────────────────────────

function onKwInput(e) {
  const lines = e.target.value.split('\n').map(l => l.trim()).filter(Boolean)
  editing.value.keyword_dict[kwSel.value] = lines
}

// ── Save / Activate / Delete ─────────────────────────────────────────────────

async function doSave() {
  saveError.value = ''
  if (!editing.value.name.trim()) { saveError.value = '产业链名称不能为空'; return }
  saving.value = true
  try {
    const payload = {
      name:             editing.value.name.trim(),
      description:      editing.value.description || '',
      framework_data:   editing.value.framework_data,
      keyword_dict:     editing.value.keyword_dict,
      layer_definition: [],
      entity_matrix:    [],
    }
    const res = editing.value.id
      ? await updateFramework(editing.value.id, payload)
      : await createFramework(payload)
    const saved = JSON.parse(JSON.stringify(res.data))
    if (!saved.framework_data) saved.framework_data = editing.value.framework_data
    editing.value = saved
    await load()
  } catch (e) {
    saveError.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

async function doActivate() {
  saving.value = true
  try {
    await setActiveFramework(editing.value.id)
    editing.value.is_active = 1
    await load()
  } catch (e) {
    saveError.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

async function doDeleteFw() {
  saving.value = true
  try {
    await deleteFramework(editing.value.id)
    closeDialog(); editing.value = null
    await load()
  } catch (e) {
    saveError.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* ── Modal shell ── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.modal-box {
  background: #fff; border-radius: 12px;
  width: 1180px; max-width: 98vw; height: 90vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 8px 40px rgba(0,0,0,.24);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.modal-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.close-btn {
  background: none; border: none; color: #9ca3af; font-size: 18px;
  cursor: pointer; padding: 4px 8px; border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* ── Body ── */
.modal-body { display: flex; flex: 1; min-height: 0; }

/* ── Sidebar ── */
.sidebar {
  width: 195px; flex-shrink: 0; border-right: 1px solid #e5e7eb;
  display: flex; flex-direction: column; overflow-y: auto;
  padding: 10px 8px; gap: 4px;
}
.btn-new {
  background: #2563eb; color: #fff; border: none; border-radius: 7px;
  padding: 7px 10px; font-size: 12px; cursor: pointer; font-weight: 500; margin-bottom: 8px;
}
.btn-new:hover { background: #1d4ed8; }
.fw-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; transition: background .12s; }
.fw-item:hover { background: #f3f4f6; }
.fw-item.selected { background: #eff6ff; border: 1px solid #bfdbfe; }
.fw-item-name { font-size: 13px; font-weight: 600; color: #1f2937; }
.fw-item-meta { font-size: 11px; color: #9ca3af; margin-top: 3px; display: flex; gap: 6px; align-items: center; }
.badge-active { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: #dcfce7; color: #166534; font-weight: 600; }
.sidebar-empty { font-size: 13px; color: #9ca3af; padding: 20px 10px; text-align: center; }

/* ── Editor ── */
.editor { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.editor-empty { align-items: center; justify-content: center; color: #9ca3af; font-size: 14px; }

/* ── Topbar ── */
.editor-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0; gap: 12px;
}
.editor-meta { display: flex; gap: 8px; flex: 1; min-width: 0; }
.name-input {
  font-size: 14px; font-weight: 600; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 5px 10px; width: 160px; outline: none;
}
.desc-input {
  font-size: 12px; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 5px 10px; flex: 1; min-width: 0; outline: none;
}
.name-input:focus, .desc-input:focus { border-color: #2563eb; }
.editor-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.btn-save {
  background: #2563eb; color: #fff; border: none; border-radius: 6px;
  padding: 6px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.btn-save:hover:not(:disabled) { background: #1d4ed8; }
.btn-save:disabled { opacity: .6; cursor: not-allowed; }
.btn-activate {
  background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;
  border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer;
}
.btn-activate:hover:not(:disabled) { background: #dcfce7; }
.btn-active-ind { background: #dcfce7; color: #166534; border: none; border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: default; }
.btn-del {
  background: #fff; color: #dc2626; border: 1px solid #fca5a5;
  border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer;
}
.btn-del:hover:not(:disabled) { background: #fef2f2; }
.save-error { padding: 4px 16px; font-size: 12px; color: #dc2626; flex-shrink: 0; }

/* ── Tabs ── */
.tab-bar {
  display: flex; border-bottom: 1px solid #e5e7eb; padding: 0 16px;
  flex-shrink: 0; background: #fafafa;
}
.tab-btn {
  padding: 8px 18px; font-size: 13px; background: none; border: none;
  border-bottom: 2px solid transparent; color: #6b7280; cursor: pointer; margin-bottom: -1px;
}
.tab-btn:hover { color: #374151; }
.tab-btn.active { color: #2563eb; border-bottom-color: #2563eb; font-weight: 600; }

/* ══ WYSIWYG Canvas ══ */
.canvas-wrap { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.canvas-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; border-bottom: 1px solid #e5e7eb; flex-shrink: 0; background: #fafafa;
}
.btn-add-layer {
  display: inline-flex; align-items: center; gap: 5px;
  background: #2563eb; color: #fff; border: none; border-radius: 6px;
  padding: 5px 14px; font-size: 12px; font-weight: 500; cursor: pointer;
}
.btn-add-layer:hover { background: #1d4ed8; }
.canvas-hint { font-size: 11px; color: #9ca3af; }
.canvas-scroll { flex: 1; overflow-y: auto; padding: 14px 16px; }
.canvas-empty { color: #9ca3af; font-size: 14px; text-align: center; padding: 40px 0; }

/* ── SVG icon buttons ── */
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px; border: 1px solid #e5e7eb;
  background: #fff; color: #6b7280; cursor: pointer; transition: all .12s;
  flex-shrink: 0;
}
.icon-btn:hover { background: #f3f4f6; color: #374151; border-color: #d1d5db; }
.icon-btn-danger:hover { background: #fef2f2; color: #dc2626; border-color: #fca5a5; }
.icon-btn-sm { width: 24px; height: 24px; border-radius: 5px; }

/* ── Layer row ── */
.layer-row {
  position: relative;
  border: 1px solid #e5e7eb; border-radius: 10px;
  margin-bottom: 14px; background: #fafafa;
  transition: border-color .15s;
  overflow: visible;
}
.layer-row:hover { border-color: #93c5fd; }

.layer-hdr {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-bottom: 1px solid #f3f4f6; flex-wrap: wrap;
}
.layer-id-badge {
  font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
  font-family: monospace; flex-shrink: 0;
}
.norm-badge { background: #ede9fe; color: #6d28d9; }
.bn-badge   { background: #fee2e2; color: #991b1b; }
.layer-name { font-size: 13px; font-weight: 600; color: #1f2937; }
.bn-chip {
  font-size: 10px; padding: 1px 7px; border-radius: 8px;
  background: #fef3c7; color: #92400e; font-weight: 600; flex-shrink: 0;
}
.layer-desc { font-size: 11px; color: #9ca3af; flex: 1; }
.layer-acts {
  display: flex; gap: 4px; align-items: center; flex-shrink: 0;
  opacity: 0; pointer-events: none; transition: opacity .15s;
}
.layer-acts.show { opacity: 1; pointer-events: all; }

/* ── Sectors row ── */
.sectors-row {
  display: flex; flex-wrap: nowrap; gap: 8px;
  padding: 8px 10px; overflow-x: auto; min-height: 58px; align-items: flex-start;
}
.sectors-empty {
  font-size: 11px; color: #d1d5db; align-self: center; padding: 0 4px;
}

/* ── Sector card (compact) ── */
.sector-card {
  position: relative;
  min-width: 130px; max-width: 200px; flex-shrink: 0;
  border: 1px solid #e5e7eb; border-radius: 8px; background: #fff;
  cursor: grab; transition: box-shadow .12s, border-color .12s; user-select: none;
}
.sector-card:hover { border-color: #93c5fd; box-shadow: 0 2px 8px rgba(37,99,235,.1); }
.sector-card.drop-here { border-color: #2563eb; border-style: dashed; }

.sector-hdr {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 8px; border-radius: 8px;
}
.grip { color: #d1d5db; font-size: 14px; cursor: grab; flex-shrink: 0; }
.sector-info { flex: 1; min-width: 0; display: flex; align-items: center; gap: 4px; overflow: hidden; }
.sector-name {
  font-size: 12px; font-weight: 600; color: #1e3a8a;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sector-bn { color: #b45309; font-size: 11px; flex-shrink: 0; }
.co-count-badge {
  font-size: 10px; color: #6b7280; background: #f3f4f6;
  padding: 1px 6px; border-radius: 8px; flex-shrink: 0; white-space: nowrap;
}
.sector-acts {
  display: flex; gap: 2px; flex-shrink: 0;
  opacity: 0; pointer-events: none; transition: opacity .12s;
}
.sector-acts.show { opacity: 1; pointer-events: all; }

.sector-desc {
  font-size: 10px; color: #9ca3af; padding: 0 8px 5px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ── Add concept sector button (bottom-center of layer) ── */
.add-csector-bar {
  display: flex; justify-content: center;
  padding: 3px 0 8px;
  opacity: 0; pointer-events: none; transition: opacity .15s;
}
.add-csector-bar.show { opacity: 1; pointer-events: all; }
.btn-add-csector {
  display: inline-flex; align-items: center; gap: 5px;
  background: #eff6ff; color: #1d4ed8; border: 1px dashed #93c5fd;
  border-radius: 20px; padding: 4px 16px; font-size: 12px; cursor: pointer;
  font-weight: 500; transition: all .12s;
}
.btn-add-csector:hover { background: #dbeafe; border-color: #2563eb; }

/* ══ Enterprise popup ══ */
.co-popup {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0,0,0,.14); overflow: hidden;
}
.co-popup-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; background: #f8faff; border-bottom: 1px solid #e5e7eb;
}
.co-popup-title { font-size: 12px; font-weight: 700; color: #1e3a8a; }
.btn-add-co {
  display: inline-flex; align-items: center; gap: 4px;
  background: #2563eb; color: #fff; border: none; border-radius: 5px;
  padding: 4px 10px; font-size: 11px; font-weight: 500; cursor: pointer;
}
.btn-add-co:hover { background: #1d4ed8; }
.co-popup-body { padding: 4px 0; max-height: 240px; overflow-y: auto; }
.co-popup-empty { font-size: 12px; color: #9ca3af; padding: 12px 14px; text-align: center; }
.co-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; cursor: pointer; transition: background .1s;
}
.co-row:hover { background: #f0f9ff; }
.co-main { display: flex; align-items: center; gap: 5px; flex: 1; min-width: 0; }
.co-name { font-size: 12px; font-weight: 600; color: #1f2937; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.co-code { font-family: monospace; font-size: 10px; color: #1e40af; background: #eff6ff; padding: 1px 4px; border-radius: 3px; flex-shrink: 0; }
.co-mkt  { font-size: 10px; color: #6b7280; flex-shrink: 0; }
.co-del  {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 4px; border: none;
  background: none; color: #d1d5db; cursor: pointer; flex-shrink: 0;
  opacity: 0; transition: opacity .1s;
}
.co-row:hover .co-del { opacity: 1; }
.co-del:hover { background: #fef2f2; color: #dc2626; }

/* ══ Keywords Tab ══ */
.tab-content { flex: 1; overflow-y: auto; min-height: 0; }
.kw-layout { display: flex; gap: 0; padding: 0; overflow: hidden; }
.kw-sidebar {
  width: 215px; flex-shrink: 0; border-right: 1px solid #e5e7eb;
  overflow-y: auto; padding: 8px;
}
.kw-item {
  display: flex; align-items: center; gap: 6px; padding: 7px 8px;
  border-radius: 6px; cursor: pointer; font-size: 12px; color: #374151; transition: background .12s;
}
.kw-item:hover { background: #f3f4f6; }
.kw-item.selected { background: #eff6ff; color: #1d4ed8; }
.kw-badge { font-size: 10px; padding: 1px 5px; border-radius: 6px; font-weight: 600; flex-shrink: 0; }
.kw-layer { background: #ede9fe; color: #6d28d9; }
.kw-col   { background: #fef3c7; color: #92400e; }
.kw-count {
  margin-left: auto; font-size: 10px; background: #e5e7eb; color: #6b7280;
  border-radius: 10px; padding: 0 6px; min-width: 18px; text-align: center;
}
.kw-editor { flex: 1; display: flex; flex-direction: column; padding: 12px 16px; overflow: hidden; }
.kw-editor-head {
  display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px;
  font-size: 13px; font-weight: 600; color: #1f2937;
}
.hint { font-size: 11px; color: #9ca3af; font-weight: 400; }
.kw-textarea {
  flex: 1; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px 10px;
  font-size: 13px; color: #374151; resize: none; outline: none;
  font-family: ui-monospace, monospace; line-height: 1.6;
}
.kw-textarea:focus { border-color: #2563eb; }
.kw-foot { font-size: 11px; color: #9ca3af; margin-top: 6px; }
.kw-ph { align-items: center; justify-content: center; color: #9ca3af; font-size: 13px; }

/* ══ Dialogs ══ */
.dlg-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center; z-index: 3000;
}
.dlg-box {
  background: #fff; border-radius: 10px;
  width: 480px; max-width: 96vw; max-height: 90vh; overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0,0,0,.2);
}
.dlg-sm { width: 380px; }
.dlg-hdr {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid #e5e7eb;
  font-size: 14px; font-weight: 600; color: #1f2937;
}
.dlg-body { padding: 16px 18px; }
.dlg-body p { color: #374151; font-size: 13px; margin: 0; line-height: 1.6; }
.dlg-body strong { color: #1f2937; }
.dlg-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 18px; border-top: 1px solid #e5e7eb;
}
.frow { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.frow label { font-size: 12px; color: #6b7280; font-weight: 500; }
.frow-check { flex-direction: row; align-items: center; }
.frow-check label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #374151; }
.req { color: #dc2626; }
.finput, .fselect {
  border: 1px solid #d1d5db; border-radius: 6px; padding: 7px 10px;
  font-size: 13px; color: #374151; outline: none; background: #fff;
}
.finput:focus, .fselect:focus { border-color: #2563eb; }
.mono { font-family: ui-monospace, monospace; font-weight: 600; }
.ferr { color: #dc2626; font-size: 12px; margin-top: 4px; }
.btn-cancel {
  background: #fff; color: #6b7280; border: 1px solid #d1d5db;
  border-radius: 6px; padding: 7px 16px; cursor: pointer; font-size: 13px;
}
.btn-cancel:hover { background: #f3f4f6; }
.btn-primary {
  background: #2563eb; color: #fff; border: none; border-radius: 6px;
  padding: 7px 18px; cursor: pointer; font-size: 13px; font-weight: 500;
}
.btn-primary:hover { background: #1d4ed8; }
.btn-danger {
  background: #dc2626; color: #fff; border: none; border-radius: 6px;
  padding: 7px 18px; cursor: pointer; font-size: 13px;
}
.btn-danger:hover:not(:disabled) { background: #b91c1c; }
.btn-danger:disabled { opacity: .6; cursor: not-allowed; }
</style>
