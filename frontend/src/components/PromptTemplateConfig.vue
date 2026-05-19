<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">提示词模板配置</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="toolbar">
        <button class="btn-add" @click="openAdd">+ 新增模板</button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="state-center"><div class="spinner"></div></div>
        <div v-else-if="error" class="state-center error-text">{{ error }}</div>
        <div v-else-if="templates.length === 0" class="state-center muted">暂无模板</div>

        <div v-else class="template-list">
          <div
            v-for="t in templates"
            :key="t.id"
            class="template-card"
            :class="{ default: t.is_default }"
          >
            <div class="card-top">
              <div class="card-title-row">
                <span class="t-name">{{ t.name }}</span>
                <span v-if="t.is_default" class="default-badge">默认</span>
                <span class="status-dot" :class="t.status">{{ t.status === 'active' ? '启用' : '停用' }}</span>
              </div>
              <p class="t-preview">{{ preview(t.content) }}</p>
            </div>
            <div class="card-actions">
              <button v-if="!t.is_default" class="op-btn set-default" @click="setDefault(t)">设为默认</button>
              <button class="op-btn edit" @click="openEdit(t)">编辑</button>
              <button v-if="!t.is_default" class="op-btn del" @click="confirmDelete(t)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Add/Edit dialog -->
      <div v-if="showForm" class="dialog-overlay" @click.self="showForm = false">
        <div class="dialog-box">
          <div class="dialog-header">
            <span>{{ editingId ? '编辑模板' : '新增模板' }}</span>
            <button class="close-btn" @click="showForm = false">✕</button>
          </div>
          <div class="dialog-body">
            <div class="form-row">
              <label>模板名称 <span class="req">*</span></label>
              <input v-model="form.name" class="form-input" placeholder="如 AI产业链盘前分析" />
            </div>
            <div class="form-row">
              <label>状态</label>
              <select v-model="form.status" class="form-select">
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
            </div>
            <div class="form-row">
              <label>
                提示词内容 <span class="req">*</span>
                <span class="hint">（可用变量：{{news_json}} {{earnings_events_json}} {{macro_json}} {{us_market_json}} {{futures_json}}）</span>
              </label>
              <textarea v-model="form.content" class="form-textarea" rows="16" spellcheck="false"></textarea>
            </div>
            <div v-if="formError" class="form-error">{{ formError }}</div>
          </div>
          <div class="dialog-footer">
            <button class="btn-cancel" @click="showForm = false">取消</button>
            <button class="btn-save" :disabled="saving" @click="save">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Delete confirm -->
      <div v-if="deleteTarget" class="dialog-overlay" @click.self="deleteTarget = null">
        <div class="dialog-box dialog-sm">
          <div class="dialog-header">
            <span>确认删除</span>
            <button class="close-btn" @click="deleteTarget = null">✕</button>
          </div>
          <div class="dialog-body">
            <p>确定删除模板 <strong>{{ deleteTarget.name }}</strong>？</p>
          </div>
          <div class="dialog-footer">
            <button class="btn-cancel" @click="deleteTarget = null">取消</button>
            <button class="btn-danger" :disabled="deleting" @click="doDelete">
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  listPromptTemplates, createPromptTemplate, updatePromptTemplate,
  deletePromptTemplate, setDefaultPromptTemplate,
} from '../api'

const emit = defineEmits(['close'])

const templates = ref([])
const loading = ref(true)
const error = ref('')

const showForm = ref(false)
const editingId = ref(null)
const form = ref({ name: '', content: '', status: 'active' })
const formError = ref('')
const saving = ref(false)

const deleteTarget = ref(null)
const deleting = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listPromptTemplates()
    templates.value = res.data
  } catch (e) {
    error.value = '加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editingId.value = null
  form.value = { name: '', content: '', status: 'active' }
  formError.value = ''
  showForm.value = true
}

function openEdit(t) {
  editingId.value = t.id
  form.value = { name: t.name, content: t.content, status: t.status }
  formError.value = ''
  showForm.value = true
}

async function save() {
  formError.value = ''
  if (!form.value.name.trim())    { formError.value = '名称不能为空'; return }
  if (!form.value.content.trim()) { formError.value = '内容不能为空'; return }
  saving.value = true
  try {
    if (editingId.value) {
      await updatePromptTemplate(editingId.value, form.value)
    } else {
      await createPromptTemplate(form.value)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

async function setDefault(t) {
  try {
    await setDefaultPromptTemplate(t.id)
    await load()
  } catch (e) {
    alert('操作失败：' + (e.response?.data?.detail || e.message))
  }
}

function confirmDelete(t) { deleteTarget.value = t }

async function doDelete() {
  deleting.value = true
  try {
    await deletePromptTemplate(deleteTarget.value.id)
    deleteTarget.value = null
    await load()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.detail || e.message))
  } finally {
    deleting.value = false
  }
}

function preview(content) {
  return content ? content.slice(0, 120).replace(/\n/g, ' ') + '…' : ''
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.modal-box {
  background: #fff; border-radius: 12px;
  width: 780px; max-width: 97vw; max-height: 88vh;
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

.toolbar { padding: 10px 20px; border-bottom: 1px solid #e5e7eb; }
.btn-add {
  background: #2563eb; color: #fff; border: none; border-radius: 7px;
  padding: 7px 16px; font-size: 13px; cursor: pointer; font-weight: 500;
}
.btn-add:hover { background: #1d4ed8; }

.modal-body { flex: 1; overflow-y: auto; padding: 16px 20px; min-height: 0; }

.state-center {
  display: flex; align-items: center; justify-content: center;
  padding: 40px; color: #9ca3af; font-size: 14px; gap: 12px;
}
.error-text { color: #dc2626; }
.muted { color: #9ca3af; }

.spinner {
  width: 26px; height: 26px; border: 3px solid #e5e7eb;
  border-top-color: #2563eb; border-radius: 50%; animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.template-list { display: flex; flex-direction: column; gap: 12px; }
.template-card {
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 14px 16px;
}
.template-card.default { border-color: #2563eb; background: #eff6ff; }
.card-top { margin-bottom: 10px; }
.card-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.t-name { font-size: 14px; font-weight: 600; color: #1f2937; }
.default-badge { font-size: 11px; background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 10px; }

.status-dot { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-dot.active   { background: #dcfce7; color: #166534; }
.status-dot.inactive { background: #e5e7eb; color: #6b7280; }

.t-preview {
  font-size: 12px; color: #6b7280; line-height: 1.5;
  margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.card-actions { display: flex; gap: 6px; }
.op-btn {
  font-size: 12px; padding: 4px 12px; border-radius: 5px;
  border: 1px solid #d1d5db; cursor: pointer; background: #fff;
  color: #374151; transition: all .15s;
}
.op-btn.set-default:hover { border-color: #2563eb; color: #2563eb; }
.op-btn.edit:hover { border-color: #2563eb; color: #2563eb; }
.op-btn.del:hover  { border-color: #dc2626; color: #dc2626; background: #fef2f2; }

/* Dialog */
.dialog-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
.dialog-box {
  background: #fff; border-radius: 10px;
  width: 680px; max-width: 94vw; max-height: 90vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 8px 30px rgba(0,0,0,.15);
}
.dialog-sm { width: 360px; }
.dialog-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid #e5e7eb;
  font-size: 14px; font-weight: 600; color: #1f2937; flex-shrink: 0;
}
.dialog-body { padding: 18px; overflow-y: auto; flex: 1; min-height: 0; }
.dialog-footer {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 18px; border-top: 1px solid #e5e7eb; flex-shrink: 0;
}

.form-row { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
.form-row label { font-size: 12px; color: #6b7280; font-weight: 500; }
.req { color: #dc2626; }
.hint { color: #9ca3af; margin-left: 8px; font-size: 11px; }
.form-input, .form-select {
  background: #fff; border: 1px solid #d1d5db; border-radius: 6px;
  color: #1f2937; padding: 7px 10px; font-size: 13px; outline: none;
}
.form-input:focus, .form-select:focus { border-color: #2563eb; box-shadow: 0 0 0 2px #dbeafe; }
.form-textarea {
  background: #f9fafb; border: 1px solid #d1d5db; border-radius: 6px;
  color: #1f2937; padding: 10px; font-size: 12px; line-height: 1.6;
  font-family: 'Courier New', monospace; outline: none; resize: vertical; width: 100%;
  box-sizing: border-box;
}
.form-textarea:focus { border-color: #2563eb; box-shadow: 0 0 0 2px #dbeafe; }
.form-error { color: #dc2626; font-size: 12px; margin-top: 4px; }

.btn-cancel {
  background: #fff; color: #6b7280; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 7px 16px; cursor: pointer; font-size: 13px;
}
.btn-cancel:hover { background: #f3f4f6; }
.btn-save {
  background: #2563eb; color: #fff; border: none; border-radius: 6px;
  padding: 7px 18px; cursor: pointer; font-size: 13px; font-weight: 500;
}
.btn-save:hover:not(:disabled) { background: #1d4ed8; }
.btn-save:disabled { opacity: .6; cursor: not-allowed; }
.btn-danger {
  background: #dc2626; color: #fff; border: none; border-radius: 6px;
  padding: 7px 18px; cursor: pointer; font-size: 13px;
}
.btn-danger:hover:not(:disabled) { background: #b91c1c; }
.btn-danger:disabled { opacity: .6; cursor: not-allowed; }
.dialog-body p { color: #374151; font-size: 13px; margin: 0; }
.dialog-body strong { color: #1f2937; }
</style>
