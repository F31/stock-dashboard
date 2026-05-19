<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <!-- Header -->
      <div class="modal-hdr">
        <div class="hdr-left">
          <span class="hdr-icon">🤖</span>
          <h3>大模型配置</h3>
          <span class="hdr-count" v-if="configs.length">{{ configs.length }} 个</span>
        </div>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <div class="modal-body">
        <!-- Left: card list -->
        <div class="list-panel">
          <div class="list-scroll">
            <div v-if="loading" class="empty-tip">加载中...</div>
            <div v-else-if="!configs.length" class="empty-tip">
              暂无配置，点击右侧「新增」开始添加
            </div>
            <div
              v-for="c in configs"
              :key="c.id"
              :class="['config-card', { active: editId === c.id, 'is-default': c.is_default }]"
              @click="startEdit(c.id)"
            >
              <div class="card-top">
                <span class="provider-icon">{{ providerIcon(c.provider) }}</span>
                <div class="card-info">
                  <div class="card-name">
                    {{ c.name }}
                    <span v-if="c.is_default" class="default-badge">默认</span>
                  </div>
                  <div class="card-model">{{ c.model_name }}</div>
                </div>
                <div class="card-actions" @click.stop>
                  <button
                    class="act-btn"
                    :class="{ active: c.is_default }"
                    :title="c.is_default ? '当前默认' : '设为默认'"
                    @click="handleSetDefault(c)"
                  >⭐</button>
                  <button class="act-btn del" title="删除" @click="handleDelete(c)">🗑</button>
                </div>
              </div>
              <div class="card-url">{{ c.base_url }}</div>
              <div class="card-key">
                <span class="key-label">Key</span>
                <span class="key-val">{{ c.api_key_masked || '未设置' }}</span>
              </div>
            </div>
          </div>

          <button class="add-btn" @click="startNew">+ 新增配置</button>
        </div>

        <!-- Right: edit/create form -->
        <div class="form-panel">
          <div v-if="!formVisible" class="form-placeholder">
            <div class="placeholder-icon">🔧</div>
            <p>点击左侧卡片编辑，或点击「新增配置」添加</p>
          </div>

          <form v-else class="config-form" @submit.prevent="handleSubmit">
            <div class="form-title">{{ editId ? '编辑配置' : '新增配置' }}</div>

            <!-- Provider selector -->
            <div class="field">
              <label>服务商</label>
              <div class="provider-grid">
                <button
                  v-for="p in providers"
                  :key="p.id"
                  type="button"
                  :class="['provider-btn', { selected: form.provider === p.id }]"
                  @click="selectProvider(p)"
                >
                  <span class="pb-icon">{{ p.icon }}</span>
                  <span class="pb-label">{{ p.label }}</span>
                </button>
              </div>
            </div>

            <!-- Name -->
            <div class="field">
              <label>配置名称 <span class="req">*</span></label>
              <input v-model="form.name" placeholder="如：DeepSeek Chat 生产环境" required />
            </div>

            <!-- Base URL -->
            <div class="field">
              <label>Base URL <span class="req">*</span></label>
              <input v-model="form.base_url" placeholder="https://api.openai.com/v1" required />
            </div>

            <!-- Model Name -->
            <div class="field">
              <label>模型名称 <span class="req">*</span></label>
              <input v-model="form.model_name" :placeholder="modelPlaceholder" required />
            </div>

            <!-- API Key -->
            <div class="field">
              <label>API Key{{ editId ? '（留空则保留原有 Key）' : '' }}</label>
              <input
                v-model="form.api_key"
                type="password"
                :placeholder="editId ? '不修改请留空' : 'sk-...'"
                autocomplete="new-password"
              />
              <p class="field-hint">Key 仅存储于服务端，前端只展示前4位和后4位，不传输完整内容</p>
            </div>

            <!-- Description -->
            <div class="field">
              <label>备注</label>
              <textarea v-model="form.description" rows="2" placeholder="可选，用途说明等"></textarea>
            </div>

            <!-- Default toggle -->
            <div class="field field-row">
              <label>设为默认</label>
              <div
                :class="['toggle', { on: form.is_default }]"
                @click="form.is_default = !form.is_default"
              >
                <div class="toggle-knob"></div>
              </div>
            </div>

            <!-- Actions -->
            <div class="form-actions">
              <button type="button" class="btn-cancel" @click="cancelForm">取消</button>
              <button type="submit" class="btn-save" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>

            <div v-if="formError" class="form-error">{{ formError }}</div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  listLLMConfigs, getLLMConfig,
  createLLMConfig, updateLLMConfig,
  deleteLLMConfig, setDefaultLLMConfig,
} from '../api'

const emit = defineEmits(['close'])

const configs = ref([])
const loading = ref(false)
const saving = ref(false)
const formVisible = ref(false)
const editId = ref(null)
const formError = ref('')

const form = reactive({
  name: '',
  provider: 'openai',
  base_url: '',
  model_name: '',
  api_key: '',
  description: '',
  is_default: false,
})

const providers = [
  { id: 'openai',    label: 'OpenAI',    icon: '🟢', url: 'https://api.openai.com/v1',                          model: 'gpt-4o' },
  { id: 'anthropic', label: 'Anthropic', icon: '🟠', url: 'https://api.anthropic.com',                          model: 'claude-opus-4-7' },
  { id: 'deepseek',  label: 'DeepSeek',  icon: '🔵', url: 'https://api.deepseek.com',                           model: 'deepseek-chat' },
  { id: 'moonshot',  label: 'Moonshot',  icon: '🌙', url: 'https://api.moonshot.cn/v1',                         model: 'moonshot-v1-8k' },
  { id: 'qwen',      label: '通义千问',  icon: '☁️', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-turbo' },
  { id: 'zhipu',     label: '智谱',      icon: '🧠', url: 'https://open.bigmodel.cn/api/paas/v4',              model: 'glm-4' },
  { id: 'custom',    label: '自定义',    icon: '⚙️', url: '',                                                    model: '' },
]

const modelPlaceholder = computed(() => {
  const p = providers.find(x => x.id === form.provider)
  return p?.model || '如：gpt-4o'
})

function providerIcon(id) {
  return providers.find(p => p.id === id)?.icon || '⚙️'
}

async function loadConfigs() {
  loading.value = true
  try {
    const res = await listLLMConfigs()
    configs.value = res.data || []
  } catch {
    configs.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadConfigs)

function selectProvider(p) {
  form.provider = p.id
  if (p.url) form.base_url = p.url
  if (p.model && !form.model_name) form.model_name = p.model
}

function startNew() {
  editId.value = null
  Object.assign(form, {
    name: '', provider: 'openai', base_url: 'https://api.openai.com/v1',
    model_name: 'gpt-4o', api_key: '', description: '', is_default: false,
  })
  formError.value = ''
  formVisible.value = true
}

async function startEdit(id) {
  editId.value = id
  formError.value = ''
  formVisible.value = true
  try {
    const res = await getLLMConfig(id)
    const c = res.data
    Object.assign(form, {
      name: c.name,
      provider: c.provider || 'custom',
      base_url: c.base_url,
      model_name: c.model_name,
      api_key: '',            // 始终置空，编辑时留空 = 保留原有 Key
      description: c.description || '',
      is_default: c.is_default,
    })
  } catch {
    formError.value = '加载配置失败'
  }
}

function cancelForm() {
  formVisible.value = false
  editId.value = null
}

async function handleSubmit() {
  if (!form.name.trim() || !form.base_url.trim() || !form.model_name.trim()) {
    formError.value = '请填写名称、Base URL 和模型名称'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      name: form.name.trim(),
      provider: form.provider,
      base_url: form.base_url.trim(),
      model_name: form.model_name.trim(),
      description: form.description.trim(),
      is_default: form.is_default,
    }
    // 只在用户实际填写了新 Key 时才传输，留空则后端保留原值
    if (form.api_key.trim()) {
      payload.api_key = form.api_key.trim()
    }
    if (editId.value) {
      await updateLLMConfig(editId.value, payload)
    } else {
      await createLLMConfig(payload)
    }
    formVisible.value = false
    editId.value = null
    await loadConfigs()
  } catch (e) {
    formError.value = e.response?.data?.detail || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

async function handleSetDefault(c) {
  if (c.is_default) return
  try {
    await setDefaultLLMConfig(c.id)
    await loadConfigs()
  } catch {
    // ignore
  }
}

async function handleDelete(c) {
  if (!confirm(`确认删除「${c.name}」？`)) return
  try {
    await deleteLLMConfig(c.id)
    if (editId.value === c.id) cancelForm()
    await loadConfigs()
  } catch {
    // ignore
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 300;
}

.modal {
  background: #fff;
  border-radius: 14px;
  width: 92vw;
  max-width: 900px;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(0,0,0,0.18);
  overflow: hidden;
}

/* ── Header ── */
.modal-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.hdr-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hdr-icon { font-size: 1.2em; }

.modal-hdr h3 {
  margin: 0;
  font-size: 1.05em;
  color: #1f2937;
  font-weight: 700;
}

.hdr-count {
  font-size: 0.75em;
  background: #eff6ff;
  color: #3b82f6;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.close-btn {
  background: none; border: none;
  font-size: 22px; color: #9ca3af; cursor: pointer;
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 6px;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* ── Body layout ── */
.modal-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* ── List panel ── */
.list-panel {
  width: 300px;
  min-width: 260px;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-tip {
  padding: 32px 12px;
  text-align: center;
  font-size: 0.82em;
  color: #9ca3af;
  line-height: 1.6;
}

.config-card {
  background: #fff;
  border: 1.5px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.config-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 2px 8px rgba(59,130,246,0.08);
}

.config-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
}

.config-card.is-default {
  border-left: 3px solid #f59e0b;
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.provider-icon {
  font-size: 1.3em;
  flex-shrink: 0;
  margin-top: 1px;
}

.card-info { flex: 1; min-width: 0; }

.card-name {
  font-size: 0.88em;
  font-weight: 700;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.default-badge {
  font-size: 0.7em;
  background: #fef3c7;
  color: #92400e;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  flex-shrink: 0;
}

.card-model {
  font-size: 0.75em;
  color: #6b7280;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.act-btn {
  background: none; border: none;
  font-size: 0.9em; cursor: pointer;
  padding: 3px 5px; border-radius: 4px;
  opacity: 0.4;
  transition: all 0.15s;
}
.act-btn:hover { opacity: 1; background: #f3f4f6; }
.act-btn.active { opacity: 1; }
.act-btn.del:hover { background: #fee2e2; }

.card-url {
  font-size: 0.72em;
  color: #9ca3af;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.card-key {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75em;
}

.key-label {
  color: #9ca3af;
  font-size: 0.85em;
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 3px;
}

.key-val {
  font-family: 'SF Mono', 'Menlo', monospace;
  color: #6b7280;
  letter-spacing: 0.05em;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.add-btn {
  margin: 10px 12px;
  padding: 10px;
  border: 1.5px dashed #d1d5db;
  border-radius: 8px;
  background: none;
  color: #6b7280;
  font-size: 0.85em;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.add-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
  background: #eff6ff;
}

/* ── Form panel ── */
.form-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
}

.form-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 0.85em;
  text-align: center;
  gap: 10px;
}

.placeholder-icon { font-size: 2.5em; }

.config-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-title {
  font-size: 0.9em;
  font-weight: 700;
  color: #374151;
  padding-bottom: 10px;
  border-bottom: 1px solid #f3f4f6;
  margin-bottom: 2px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.field label {
  font-size: 0.78em;
  font-weight: 600;
  color: #6b7280;
}

.req { color: #ef4444; }

.field input, .field textarea {
  border: 1.5px solid #e5e7eb;
  border-radius: 7px;
  padding: 8px 10px;
  font-size: 0.85em;
  color: #1f2937;
  transition: border-color 0.15s;
  background: #fff;
  width: 100%;
  box-sizing: border-box;
}

.field input:focus, .field textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.field textarea { resize: vertical; font-family: inherit; }

.field-hint {
  font-size: 0.72em;
  color: #9ca3af;
  margin: 0;
}

/* Provider grid */
.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.provider-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 7px 4px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 0.8em;
}

.provider-btn:hover {
  border-color: #93c5fd;
  background: #eff6ff;
}

.provider-btn.selected {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
}

.pb-icon { font-size: 1.2em; }
.pb-label { font-size: 0.78em; white-space: nowrap; }

/* Toggle */
.toggle {
  width: 40px; height: 22px;
  border-radius: 11px;
  background: #e5e7eb;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
  flex-shrink: 0;
}

.toggle.on { background: #3b82f6; }

.toggle-knob {
  position: absolute;
  top: 3px; left: 3px;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}

.toggle.on .toggle-knob { transform: translateX(18px); }

/* Form actions */
.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding-top: 4px;
}

.btn-cancel {
  padding: 8px 18px;
  border: 1.5px solid #e5e7eb;
  border-radius: 7px;
  background: #fff;
  color: #6b7280;
  font-size: 0.85em;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-cancel:hover { background: #f3f4f6; }

.btn-save {
  padding: 8px 22px;
  border: none;
  border-radius: 7px;
  background: #3b82f6;
  color: #fff;
  font-size: 0.85em;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-save:hover:not(:disabled) { background: #2563eb; }
.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }

.form-error {
  font-size: 0.8em;
  color: #dc2626;
  background: #fee2e2;
  padding: 8px 12px;
  border-radius: 6px;
}

/* ── Responsive ── */
@media (max-width: 640px) {
  .modal {
    width: 100vw; max-width: 100vw;
    height: 100vh; max-height: 100vh;
    border-radius: 0;
  }

  .modal-body {
    flex-direction: column;
  }

  .list-panel {
    width: 100%;
    min-width: unset;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
    max-height: 40vh;
  }

  .form-panel {
    padding: 16px;
  }

  .provider-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
</style>
