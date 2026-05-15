<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-hdr">
        <h3>👥 用户维护</h3>
        <div class="hdr-actions">
          <button class="btn btn-sm btn-primary" @click="openCreate">+ 新增用户</button>
          <button class="close-btn" @click="$emit('close')">×</button>
        </div>
      </div>

      <div class="modal-body">
        <!-- User Table -->
        <table class="user-table" v-if="users.length">
          <thead>
            <tr>
              <th class="col-id">ID</th>
              <th class="col-name">用户名</th>
              <th class="col-role">角色</th>
              <th class="col-date">创建时间</th>
              <th class="col-act">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td class="col-id">{{ u.id }}</td>
              <td class="col-name">{{ u.username }}</td>
              <td class="col-role">
                <span :class="['role-badge', u.role === 'admin' ? 'role-admin' : 'role-user']">
                  {{ u.role === 'admin' ? '管理员' : '用户' }}
                </span>
              </td>
              <td class="col-date">{{ u.created_at }}</td>
              <td class="col-act">
                <button class="act-btn act-edit" @click="openEdit(u)">编辑</button>
                <button class="act-btn act-del" @click="confirmDelete(u)" :disabled="u.id === currentUserId">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无用户数据</div>

        <!-- Pagination -->
        <div class="pagination" v-if="totalPages > 1">
          <button :disabled="page <= 1" @click="goPage(page - 1)" class="page-btn">‹</button>
          <span class="page-info">{{ page }} / {{ totalPages }}</span>
          <button :disabled="page >= totalPages" @click="goPage(page + 1)" class="page-btn">›</button>
        </div>
      </div>

      <!-- Create / Edit Modal -->
      <Teleport to="body">
        <div class="sub-modal-overlay" v-if="showForm" @click.self="closeForm">
          <div class="sub-modal">
            <div class="sub-modal-hdr">
              <h3>{{ isEdit ? '编辑用户' : '新增用户' }}</h3>
              <button class="close-btn" @click="closeForm">×</button>
            </div>
            <div class="sub-modal-body">
              <div class="field">
                <label>用户名</label>
                <input v-model="form.username" placeholder="登录用户名" />
              </div>
              <div class="field">
                <label>密码 {{ isEdit ? '(留空不修改)' : '' }}</label>
                <input v-model="form.password" type="password" :placeholder="isEdit ? '留空则不修改密码' : '设置密码'" />
              </div>
              <div class="field">
                <label>角色</label>
                <select v-model="form.role">
                  <option value="user">普通用户</option>
                  <option value="admin">管理员</option>
                </select>
              </div>
              <div class="form-error" v-if="formError">{{ formError }}</div>
            </div>
            <div class="sub-modal-ftr">
              <button class="btn btn-cancel" @click="closeForm">取消</button>
              <button class="btn btn-save" :disabled="formSubmitting" @click="submitForm">
                {{ formSubmitting ? '提交中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- Delete Confirm -->
      <Teleport to="body">
        <div class="sub-modal-overlay" v-if="showDeleteConfirm" @click.self="showDeleteConfirm = false">
          <div class="sub-modal sub-modal-sm">
            <div class="sub-modal-hdr">
              <h3>确认删除</h3>
            </div>
            <div class="sub-modal-body">
              <p>确定要删除用户 <strong>{{ deleteTarget?.username }}</strong> 吗？此操作不可恢复。</p>
              <div class="form-error" v-if="deleteError">{{ deleteError }}</div>
            </div>
            <div class="sub-modal-ftr">
              <button class="btn btn-cancel" @click="showDeleteConfirm = false">取消</button>
              <button class="btn btn-danger" :disabled="deleteSubmitting" @click="doDelete">
                {{ deleteSubmitting ? '删除中...' : '确认删除' }}
              </button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listUsers, createUser, updateUser, deleteUser } from '../api'

const emit = defineEmits(['close'])

const users = ref([])
const page = ref(1)
const total = ref(0)
const pageSize = 20

const currentUserId = computed(() => {
  // Parse JWT to get current user id
  const token = localStorage.getItem('token')
  if (!token) return -1
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return parseInt(payload.sub) || -1
  } catch { return -1 }
})

const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)

// Form state
const showForm = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const form = ref({ username: '', password: '', role: 'user' })
const formError = ref('')
const formSubmitting = ref(false)

// Delete state
const showDeleteConfirm = ref(false)
const deleteTarget = ref(null)
const deleteError = ref('')
const deleteSubmitting = ref(false)

async function fetchData() {
  try {
    const res = await listUsers(page.value, pageSize)
    users.value = res.data.items || []
    total.value = res.data.total || 0
  } catch {
    users.value = []
  }
}

function goPage(p) {
  page.value = p
  fetchData()
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  form.value = { username: '', password: '', role: 'user' }
  formError.value = ''
  showForm.value = true
}

function openEdit(u) {
  isEdit.value = true
  editingId.value = u.id
  form.value = { username: u.username, password: '', role: u.role || 'user' }
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  formError.value = ''
}

async function submitForm() {
  formError.value = ''
  if (!form.value.username.trim()) {
    formError.value = '请输入用户名'
    return
  }
  if (!isEdit.value && !form.value.password) {
    formError.value = '请输入密码'
    return
  }

  formSubmitting.value = true
  try {
    if (isEdit.value) {
      const data = {}
      if (form.value.username.trim() !== '') data.username = form.value.username.trim()
      if (form.value.password) data.password = form.value.password
      data.role = form.value.role
      await updateUser(editingId.value, data)
    } else {
      await createUser(form.value.username.trim(), form.value.password, form.value.role)
    }
    closeForm()
    fetchData()
  } catch (e) {
    formError.value = e.response?.data?.detail || '操作失败，请重试'
  } finally {
    formSubmitting.value = false
  }
}

function confirmDelete(u) {
  deleteTarget.value = u
  deleteError.value = ''
  showDeleteConfirm.value = true
}

async function doDelete() {
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    await deleteUser(deleteTarget.value.id)
    showDeleteConfirm.value = false
    deleteTarget.value = null
    fetchData()
  } catch (e) {
    deleteError.value = e.response?.data?.detail || '删除失败'
  } finally {
    deleteSubmitting.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal {
  background: #fff;
  border-radius: 12px;
  width: 90vw;
  max-width: 800px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2);
}
.modal-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}
.modal-hdr h3 { margin: 0; font-size: 1em; color: #1f2937; }
.hdr-actions { display: flex; align-items: center; gap: 8px; }
.close-btn {
  background: none; border: none;
  font-size: 22px; color: #9ca3af; cursor: pointer;
  width: 30px; height: 30px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

.modal-body { flex: 1; overflow-y: auto; padding: 0; }

.btn { padding: 7px 16px; border-radius: 6px; font-size: 0.85em; cursor: pointer; font-weight: 500; border: none; transition: all 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 5px 12px; font-size: 0.82em; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover { background: #1d4ed8; }
.btn-cancel { background: #fff; color: #6b7280; border: 1px solid #d1d5db; }
.btn-cancel:hover { background: #f3f4f6; }
.btn-save { background: #2563eb; color: #fff; }
.btn-save:hover { background: #1d4ed8; }
.btn-danger { background: #dc2626; color: #fff; }
.btn-danger:hover { background: #b91c1c; }

/* User table */
.user-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.user-table th {
  position: sticky; top: 0; background: #f9fafb;
  padding: 10px 12px; text-align: left; font-weight: 600;
  color: #6b7280; border-bottom: 1px solid #e5e7eb; white-space: nowrap;
}
.user-table td { padding: 10px 12px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
.user-table tbody tr:hover { background: #f9fafb; }
.col-id { width: 50px; color: #9ca3af; font-family: monospace; }
.col-name { font-weight: 600; color: #1f2937; }
.col-role { width: 90px; }
.col-date { width: 140px; color: #6b7280; }
.col-act { width: 130px; text-align: center; }

.role-badge { font-size: 0.8em; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.role-admin { background: #ede9fe; color: #5b21b6; }
.role-user { background: #e5e7eb; color: #374151; }

.act-btn {
  padding: 3px 10px; border: 1px solid #d1d5db; border-radius: 4px;
  background: #fff; font-size: 0.82em; cursor: pointer;
  margin: 0 3px; transition: all 0.15s;
}
.act-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.act-edit:hover { border-color: #2563eb; color: #2563eb; }
.act-del:hover { border-color: #dc2626; color: #dc2626; background: #fef2f2; }

.empty { padding: 40px; text-align: center; color: #9ca3af; }

/* Pagination */
.pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 10px; padding: 12px 20px; border-top: 1px solid #e5e7eb;
}
.page-btn {
  padding: 4px 14px; border: 1px solid #d1d5db; border-radius: 5px;
  background: #fff; color: #374151; font-size: 1em; cursor: pointer;
}
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-btn:hover:not(:disabled) { border-color: #2563eb; color: #2563eb; }
.page-info { font-size: 0.85em; color: #6b7280; }

/* Sub-modal (form / confirm) */
.sub-modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 600;
}
.sub-modal {
  background: #fff; border-radius: 12px;
  width: 420px; max-width: 90vw;
  box-shadow: 0 8px 30px rgba(0,0,0,0.2);
}
.sub-modal-sm { width: 380px; }
.sub-modal-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #e5e7eb;
}
.sub-modal-hdr h3 { margin: 0; font-size: 1em; color: #1f2937; }
.sub-modal-body { padding: 20px; }
.sub-modal-ftr {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 20px; border-top: 1px solid #e5e7eb;
}
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 0.82em; font-weight: 600; color: #4b5563; margin-bottom: 4px; }
.field input, .field select {
  width: 100%; padding: 9px 11px; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 0.9em; color: #1f2937;
  background: #f9fafb; box-sizing: border-box; font-family: inherit;
}
.field input:focus, .field select:focus {
  outline: none; border-color: #2563eb; background: #fff;
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}
.form-error {
  margin-top: 10px; padding: 8px 12px; background: #fef2f2;
  border: 1px solid #fecaca; border-radius: 6px; color: #dc2626; font-size: 0.85em;
}
</style>
