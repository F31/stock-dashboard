<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">定时任务配置</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="toolbar">
        <button class="btn-add" @click="openAdd">+ 新增任务</button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="state-center"><div class="spinner"></div></div>
        <div v-else-if="error" class="state-center error-text">{{ error }}</div>
        <div v-else-if="tasks.length === 0" class="state-center muted">暂无定时任务</div>

        <table v-else class="data-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>任务类型</th>
              <th>执行时间</th>
              <th>状态</th>
              <th>上次执行</th>
              <th>下次执行</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tasks" :key="t.id">
              <td class="col-name">{{ t.name }}</td>
              <td><span class="type-badge">{{ typeLabel(t.task_type) }}</span></td>
              <td class="col-time">{{ t.schedule_time }}</td>
              <td>
                <span class="status-dot" :class="t.enabled ? 'enabled' : 'disabled'">
                  {{ t.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td class="col-run">{{ t.last_run || '—' }}</td>
              <td class="col-run">{{ t.next_run || '—' }}</td>
              <td class="col-ops">
                <button class="op-btn toggle" @click="toggleEnabled(t)">
                  {{ t.enabled ? '停用' : '启用' }}
                </button>
                <button class="op-btn edit" @click="openEdit(t)">编辑</button>
                <button class="op-btn del" @click="confirmDelete(t)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Add/Edit dialog -->
      <div v-if="showForm" class="dialog-overlay" @click.self="showForm = false">
        <div class="dialog-box">
          <div class="dialog-header">
            <span>{{ editingId ? '编辑定时任务' : '新增定时任务' }}</span>
            <button class="close-btn" @click="showForm = false">✕</button>
          </div>
          <div class="dialog-body">
            <div class="form-row">
              <label>任务名称 <span class="req">*</span></label>
              <input v-model="form.name" class="form-input" placeholder="如 AI产业链盘前分析" />
            </div>
            <div class="form-row">
              <label>任务类型 <span class="req">*</span></label>
              <select v-model="form.task_type" class="form-select">
                <option value="premarket_analysis">盘前分析</option>
              </select>
            </div>
            <div class="form-row">
              <label>
                执行时间 <span class="req">*</span>
                <span class="hint">（24小时制 HH:MM，每天定时执行）</span>
              </label>
              <input v-model="form.schedule_time" class="form-input" placeholder="06:00" maxlength="5" />
            </div>
            <div class="form-row">
              <label>状态</label>
              <select v-model="form.enabled" class="form-select">
                <option :value="true">启用</option>
                <option :value="false">停用</option>
              </select>
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
            <p>确定删除任务 <strong>{{ deleteTarget.name }}</strong>？</p>
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
  listScheduledTasks, createScheduledTask, updateScheduledTask, deleteScheduledTask,
} from '../api'

const emit = defineEmits(['close'])

const tasks = ref([])
const loading = ref(true)
const error = ref('')

const showForm = ref(false)
const editingId = ref(null)
const form = ref({ name: '', task_type: 'premarket_analysis', schedule_time: '06:00', enabled: true })
const formError = ref('')
const saving = ref(false)

const deleteTarget = ref(null)
const deleting = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listScheduledTasks()
    tasks.value = res.data
  } catch (e) {
    error.value = '加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editingId.value = null
  form.value = { name: '', task_type: 'premarket_analysis', schedule_time: '06:00', enabled: true }
  formError.value = ''
  showForm.value = true
}

function openEdit(t) {
  editingId.value = t.id
  form.value = {
    name: t.name,
    task_type: t.task_type,
    schedule_time: t.schedule_time,
    enabled: t.enabled,
  }
  formError.value = ''
  showForm.value = true
}

async function toggleEnabled(t) {
  try {
    await updateScheduledTask(t.id, { enabled: !t.enabled })
    await load()
  } catch (e) {
    alert('操作失败：' + (e.response?.data?.detail || e.message))
  }
}

async function save() {
  formError.value = ''
  if (!form.value.name.trim()) { formError.value = '名称不能为空'; return }
  const timeRe = /^([01]\d|2[0-3]):[0-5]\d$/
  if (!timeRe.test(form.value.schedule_time)) { formError.value = '时间格式应为 HH:MM（如 06:00）'; return }
  saving.value = true
  try {
    if (editingId.value) {
      await updateScheduledTask(editingId.value, form.value)
    } else {
      await createScheduledTask(form.value)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

function confirmDelete(t) { deleteTarget.value = t }

async function doDelete() {
  deleting.value = true
  try {
    await deleteScheduledTask(deleteTarget.value.id)
    deleteTarget.value = null
    await load()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.detail || e.message))
  } finally {
    deleting.value = false
  }
}

function typeLabel(type) {
  return { premarket_analysis: '盘前分析' }[type] || type
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.modal-box {
  background: #fff; border-radius: 12px;
  width: 900px; max-width: 97vw; max-height: 88vh;
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

.modal-body { flex: 1; overflow-y: auto; min-height: 0; }

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

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
  position: sticky; top: 0;
  padding: 10px 12px; background: #f9fafb; color: #6b7280;
  font-weight: 600; text-align: left; border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}
.data-table td { padding: 9px 12px; color: #374151; border-bottom: 1px solid #f3f4f6; }
.data-table tr:hover td { background: #f9fafb; }

.col-name { font-weight: 500; color: #1f2937; }
.col-time { font-family: monospace; color: #2563eb; font-weight: 500; }
.col-run  { color: #9ca3af; font-size: 12px; }
.col-ops  { white-space: nowrap; }

.type-badge { font-size: 11px; background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 10px; }

.status-dot { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-dot.enabled  { background: #dcfce7; color: #166534; }
.status-dot.disabled { background: #e5e7eb; color: #6b7280; }

.op-btn {
  font-size: 12px; padding: 3px 10px; border-radius: 5px;
  border: 1px solid #d1d5db; cursor: pointer; margin-right: 4px;
  background: #fff; color: #374151; transition: all .15s;
}
.op-btn.toggle:hover { border-color: #6b7280; background: #f3f4f6; }
.op-btn.edit:hover   { border-color: #2563eb; color: #2563eb; }
.op-btn.del:hover    { border-color: #dc2626; color: #dc2626; background: #fef2f2; }

/* Dialog */
.dialog-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center; z-index: 10;
}
.dialog-box {
  background: #fff; border-radius: 10px;
  width: 460px; max-width: 94vw;
  box-shadow: 0 8px 30px rgba(0,0,0,.15);
}
.dialog-sm { width: 360px; }
.dialog-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid #e5e7eb;
  font-size: 14px; font-weight: 600; color: #1f2937;
}
.dialog-body { padding: 18px; }
.dialog-footer {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 18px; border-top: 1px solid #e5e7eb;
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

@media (max-width: 640px) {
  .modal-overlay { padding: 0; align-items: flex-end; }
  .modal-box {
    width: 100% !important; max-width: 100% !important;
    border-radius: 16px 16px 0 0; max-height: 92dvh;
  }
  .modal-body { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .data-table { min-width: 580px; font-size: 12px; }
  .data-table th, .data-table td { padding: 7px 8px; }
  .dialog-overlay { padding: 0; align-items: flex-end; }
  .dialog-box {
    width: 100% !important; max-width: 100% !important;
    border-radius: 16px 16px 0 0; max-height: 85dvh; overflow-y: auto;
  }
  .dialog-sm { width: 100%; }
}
</style>
