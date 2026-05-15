<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <h3>添加自选股 / 板块</h3>

      <!-- Search input -->
      <div class="field">
        <label>搜索股票或板块</label>
        <div class="search-wrap">
          <input
            ref="searchInput"
            v-model="keyword"
            placeholder="输入代码或名称搜索，如 600519、BK0447、AAPL"
            @keydown.enter="onSearch"
            @keydown.down.prevent="onArrowDown"
            @keydown.up.prevent="onArrowUp"
            @input="onInputChange"
          />
          <span class="search-icon" v-if="searching">⟳</span>
        </div>

        <!-- Search results -->
        <div class="search-results" v-if="showResults && keyword.length >= 1">
          <div
            v-for="r in results"
            :key="r.code + r.market"
            class="search-item"
            :class="{ active: selectedIdx === results.indexOf(r) }"
            @click="selectResult(r)"
            @mouseenter="selectedIdx = results.indexOf(r)"
          >
            <div class="si-left">
              <div class="si-name">{{ r.name }}</div>
              <div class="si-code">{{ r.code }}</div>
            </div>
            <div class="si-right">
              <span :class="['si-badge', r.item_type === 'sector' ? 'si-sector' : 'si-' + (r.market || '').toLowerCase()]">
                {{ r.item_type === 'sector' ? '板块' : (marketLabel(r.market)) }}
              </span>
            </div>
          </div>
          <div class="search-empty" v-if="results.length === 0 && !searching">
            未找到匹配的股票或板块，请手动输入代码
          </div>
          <div class="search-more" v-if="results.length >= 10 && !searching">
            输入更多字符精确搜索...
          </div>
        </div>
      </div>

      <!-- Selected item preview -->
      <div class="selected-preview" v-if="pendingCode">
        <span class="sp-label">已选择：</span>
        <span class="sp-name">{{ pendingName }}</span>
        <span class="sp-code">{{ pendingCode }}</span>
        <span :class="['si-badge', pendingIsSector ? 'si-sector' : 'si-' + (pendingMarket || '').toLowerCase()]">
          {{ pendingIsSector ? '板块' : marketLabel(pendingMarket) }}
        </span>
      </div>

      <!-- Sector name override (shown when a BK sector is selected/entered) -->
      <div class="field sector-name-field" v-if="showSectorNameInput">
        <label>板块名称 <span class="hint-inline">（自动获取失败，可手动填写）</span></label>
        <input
          v-model="sectorName"
          placeholder="输入板块中文名称，如 光模块、半导体"
          @keydown.enter.prevent="submitManual"
        />
      </div>

      <!-- Manual entry -->
      <div class="field-sep">— 或手动输入 —</div>

      <div class="form-row">
        <div class="field form-col">
          <label>市场</label>
          <select v-model="market" class="sel">
            <option value="A">A股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
          </select>
        </div>
        <div class="field form-col form-col-wide">
          <label>代码</label>
          <input
            v-model="code"
            :placeholder="codePlaceholder"
            @keydown.enter="submitManual"
            @input="onCodeInput"
          />
        </div>
      </div>
      <p class="hint">板块代码如 BK0447 自动识别，无需选择市场</p>

      <div class="actions">
        <button class="btn btn-add" @click="submitManual" :disabled="!code.trim() || loading">
          {{ loading ? '添加中...' : '添加' }}
        </button>
        <button class="btn btn-cancel" type="button" @click="$emit('close')">取消</button>
      </div>

      <div class="error" v-if="error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useStockStore } from '../stores/stockStore'

const emit = defineEmits(['close', 'added'])
const store = useStockStore()

// Search
const searchInput = ref(null)
const keyword = ref('')
const results = ref([])
const selectedIdx = ref(-1)
const searching = ref(false)
const showResults = ref(false)

// Pending selection (filled from search, waiting for user to click "添加")
const pendingCode = ref('')
const pendingName = ref('')
const pendingMarket = ref('A')
const pendingIsSector = ref(false)

// Manual entry
const market = ref('A')
const code = ref('')
const error = ref('')
const loading = ref(false)

// Sector name override — shown when a BK sector code is detected
const sectorName = ref('')

const RE_BK = /^BK\d{4}$/i

const isBKCodeEntered = computed(() => RE_BK.test(code.value.trim()))

const showSectorNameInput = computed(() => {
  // Show name input when a sector is pending or BK code is typed manually
  if (pendingIsSector.value) return true
  if (isBKCodeEntered.value) return true
  return false
})

const codePlaceholder = computed(() => {
  if (market.value === 'A') return '例 600519'
  if (market.value === 'HK') return '例 00700'
  return '例 AAPL'
})

function marketLabel(m) {
  if (m === 'A') return 'A股'
  if (m === 'HK') return '港股'
  if (m === 'US') return '美股'
  return m
}

async function onSearch() {
  const kw = keyword.value.trim()
  if (kw.length < 1) {
    results.value = []
    showResults.value = false
    return
  }

  // If results already shown, selecting the highlighted item
  if (showResults.value && results.value.length > 0 && selectedIdx.value >= 0) {
    selectResult(results.value[selectedIdx.value])
    return
  }

  searching.value = true
  showResults.value = true
  try {
    const res = await store.search(kw)
    results.value = res || []
    selectedIdx.value = results.value.length > 0 ? 0 : -1
  } catch {
    results.value = []
  } finally {
    searching.value = false
  }
}

function onArrowDown() {
  if (results.value.length > 0) {
    selectedIdx.value = (selectedIdx.value + 1) % results.value.length
  }
}

function onArrowUp() {
  if (results.value.length > 0) {
    selectedIdx.value = (selectedIdx.value - 1 + results.value.length) % results.value.length
  }
}

function onInputChange() {
  if (showResults.value) {
    showResults.value = false
  }
}

function selectResult(r) {
  // Fill into pending preview + manual fields (don't add yet)
  const marketVal = r.item_type === 'sector' ? 'SECTOR' : (r.market || 'A')
  pendingCode.value = r.code
  pendingName.value = r.name
  pendingMarket.value = marketVal
  pendingIsSector.value = r.item_type === 'sector'

  // Pre-fill sector name: use name from API if it's meaningful (not a code fallback)
  if (r.item_type === 'sector') {
    const isFallback = !r.name || RE_BK.test(r.name) || r.name.startsWith('板块')
    sectorName.value = isFallback ? '' : r.name
  }

  // Also fill manual entry fields
  code.value = r.code
  if (marketVal === 'A' || marketVal === 'HK' || marketVal === 'US') {
    market.value = marketVal
  }

  // Clear search
  keyword.value = ''
  results.value = []
  showResults.value = false
  selectedIdx.value = -1
  error.value = ''
}

function onCodeInput() {
  // Reset sector name when code changes
  if (!RE_BK.test(code.value.trim())) {
    sectorName.value = ''
    if (!pendingIsSector.value) return
    pendingIsSector.value = false
    pendingName.value = ''
    pendingCode.value = ''
  }
}

function submitManual() {
  const c = code.value.trim()
  if (!c) return

  loading.value = true
  error.value = ''

  const isSector = pendingIsSector.value || RE_BK.test(c)
  const finalMarket = isSector ? 'SECTOR' : market.value
  // Prefer user-typed sector name, then search result name (if not a fallback), then empty
  const finalName = sectorName.value.trim() || (pendingIsSector.value && !RE_BK.test(pendingName.value) && !pendingName.value?.startsWith('板块') ? pendingName.value : '') || ''

  store.addStock(c, finalMarket, finalName)
    .then(() => {
      emit('added')
    })
    .catch((e) => {
      error.value = e.message || '添加失败，请重试'
    })
    .finally(() => {
      loading.value = false
    })
}

onMounted(() => {
  nextTick(() => searchInput.value?.focus())
})
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: #fff;
  border-radius: 12px;
  padding: 28px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 8px 30px rgba(0,0,0,0.15);
}
h3 { margin: 0 0 20px; font-size: 1.1em; color: #1f2937; }

.field { margin-bottom: 16px; }
.field label {
  display: block;
  font-size: 0.82em;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 5px;
}
.field-sep {
  text-align: center;
  font-size: 0.78em;
  color: #9ca3af;
  margin: 16px 0;
  position: relative;
}
.field-sep::before, .field-sep::after {
  content: '';
  display: inline-block;
  width: 60px;
  height: 1px;
  background: #e5e7eb;
  vertical-align: middle;
  margin: 0 10px;
}

.form-row {
  display: flex;
  gap: 10px;
}
.form-col { flex: 0 0 100px; }
.form-col-wide { flex: 1; }

.sel, .field input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.95em;
  color: #1f2937;
  background: #f9fafb;
  box-sizing: border-box;
  font-family: inherit;
}
.sel:focus, .field input:focus {
  outline: none;
  border-color: #2563eb;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}
.hint { margin: 4px 0 0; font-size: 0.75em; color: #9ca3af; }
.hint-inline { font-weight: 400; color: #9ca3af; font-size: 0.9em; }
.sector-name-field { margin-bottom: 0; }

/* Search */
.search-wrap { position: relative; }
.search-icon {
  position: absolute; right: 12px; top: 50%;
  transform: translateY(-50%);
  font-size: 1em; color: #9ca3af;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { from { transform: translateY(-50%) rotate(0deg); } to { transform: translateY(-50%) rotate(360deg); } }

.search-results {
  border: 1px solid #d1d5db;
  border-top: none;
  border-radius: 0 0 8px 8px;
  max-height: 280px;
  overflow-y: auto;
  background: #fff;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.search-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f3f4f6;
  transition: background 0.1s;
}
.search-item:last-child { border-bottom: none; }
.search-item:hover, .search-item.active { background: #eff6ff; }
.si-left { flex: 1; min-width: 0; }
.si-name { font-size: 0.88em; font-weight: 600; color: #1f2937; }
.si-code { font-size: 0.78em; color: #9ca3af; margin-top: 1px; }
.si-right { flex-shrink: 0; margin-left: 10px; }
.si-badge {
  font-size: 0.75em;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 700;
  white-space: nowrap;
}
.si-a { background: #fef3c7; color: #92400e; }
.si-hk { background: #dbeafe; color: #1e40af; }
.si-us { background: #ede9fe; color: #5b21b6; }
.si-sector { background: #fce7f3; color: #9d174d; }

.search-empty, .search-more {
  padding: 10px 12px;
  text-align: center;
  font-size: 0.82em;
  color: #9ca3af;
}

/* Selected preview */
.selected-preview {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f0f7ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  font-size: 0.85em;
}
.sp-label { color: #6b7280; }
.sp-name { font-weight: 700; color: #1f2937; }
.sp-code { color: #6b7280; font-family: monospace; }

.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 16px;
}
.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 0.9em;
  cursor: pointer;
  font-weight: 500;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-add { background: #2563eb; color: #fff; }
.btn-add:hover:not(:disabled) { background: #1d4ed8; }
.btn-cancel { background: #e5e7eb; color: #4b5563; }
.btn-cancel:hover { background: #d1d5db; }

.error {
  margin-top: 12px;
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #dc2626;
  font-size: 0.85em;
}

/* ── Responsive: Mobile ── */
@media (max-width: 640px) {
  .modal {
    width: 100vw;
    max-width: 100vw;
    height: 100vh;
    max-height: 100vh;
    border-radius: 0;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
  }
  h3 { font-size: 1em; margin-bottom: 16px; flex-shrink: 0; }
  .search-results { max-height: 200px; }
  .form-row { flex-direction: column; gap: 0; }
  .form-col { flex: 1; }
  .hint { font-size: 0.72em; }
}
</style>
