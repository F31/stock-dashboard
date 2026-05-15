<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-hdr">
        <h3>📋 操作日志</h3>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <!-- Filters -->
      <div class="filters">
        <select v-model="filterAction" class="filter-sel" @change="search">
          <option value="">全部操作</option>
          <option value="login">登录</option>
          <option value="register">注册</option>
          <option value="add_stock">添加自选股</option>
          <option value="remove_stock">删除自选股</option>
          <option value="create_user">创建用户</option>
          <option value="update_user">修改用户</option>
          <option value="delete_user">删除用户</option>
        </select>
        <input v-model="filterUsername" class="filter-input" placeholder="按用户名搜索" @keydown.enter="search" />
        <button class="btn btn-sm btn-primary" @click="search">搜索</button>
        <button class="btn btn-sm btn-cancel" @click="resetFilters">重置</button>
        <span class="filter-total" v-if="total > 0">共 {{ total }} 条</span>
      </div>

      <div class="modal-body">
        <table class="log-table" v-if="logs.length">
          <thead>
            <tr>
              <th class="col-id">#</th>
              <th class="col-user">用户名</th>
              <th class="col-action">操作</th>
              <th class="col-target">目标</th>
              <th class="col-detail">详情</th>
              <th class="col-ip">IP</th>
              <th class="col-time">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td class="col-id">{{ log.id }}</td>
              <td class="col-user">{{ log.username }}</td>
              <td class="col-action">
                <span :class="['action-badge', actionClass(log.action)]">{{ actionLabel(log.action) }}</span>
              </td>
              <td class="col-target">{{ log.target }}</td>
              <td class="col-detail">{{ log.detail }}</td>
              <td class="col-ip">{{ log.ip_address }}</td>
              <td class="col-time">{{ log.created_at }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无日志数据</div>
      </div>

      <!-- Pagination -->
      <div class="pagination" v-if="totalPages > 1">
        <button :disabled="page <= 1" @click="goPage(page - 1)" class="page-btn">‹</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="goPage(page + 1)" class="page-btn">›</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listLogs } from '../api'

const emit = defineEmits(['close'])

const logs = ref([])
const page = ref(1)
const total = ref(0)
const pageSize = 20

const filterAction = ref('')
const filterUsername = ref('')

const totalPages = computed(() => Math.ceil(total.value / pageSize) || 1)

async function fetchData() {
  try {
    const filters = {}
    if (filterAction.value) filters.action = filterAction.value
    if (filterUsername.value.trim()) filters.username = filterUsername.value.trim()
    const res = await listLogs(page.value, pageSize, filters)
    logs.value = res.data.items || []
    total.value = res.data.total || 0
  } catch {
    logs.value = []
  }
}

function search() {
  page.value = 1
  fetchData()
}

function resetFilters() {
  filterAction.value = ''
  filterUsername.value = ''
  page.value = 1
  fetchData()
}

function goPage(p) {
  page.value = p
  fetchData()
}

const actionLabels = {
  login: '登录', register: '注册',
  add_stock: '添加自选股', remove_stock: '删除自选股',
  create_user: '创建用户', update_user: '修改用户', delete_user: '删除用户',
  api_call: 'API调用', api_query: '查询', api_delete: '删除', api_update: '更新', api_patch: '修改',
}

function actionLabel(a) {
  return actionLabels[a] || a
}

function actionClass(a) {
  if (['login', 'register'].includes(a)) return 'act-auth'
  if (a.includes('delete') || a.includes('remove')) return 'act-danger'
  if (a.includes('create') || a.includes('add')) return 'act-create'
  return 'act-info'
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
  width: 92vw;
  max-width: 1100px;
  max-height: 90vh;
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
.close-btn {
  background: none; border: none;
  font-size: 22px; color: #9ca3af; cursor: pointer;
  width: 30px; height: 30px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
.close-btn:hover { background: #f3f4f6; color: #374151; }

/* Filters */
.filters {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 20px; border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.filter-sel {
  padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 5px;
  font-size: 0.82em; color: #374151; background: #f9fafb;
}
.filter-input {
  padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 5px;
  font-size: 0.82em; color: #374151; width: 150px;
}
.filter-input:focus, .filter-sel:focus {
  outline: none; border-color: #2563eb;
}
.filter-total {
  margin-left: auto; font-size: 0.82em; color: #9ca3af;
}

.btn {
  padding: 5px 14px; border-radius: 5px; font-size: 0.82em; cursor: pointer;
  font-weight: 500; border: none; transition: all 0.15s;
}
.btn-sm { padding: 5px 12px; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover { background: #1d4ed8; }
.btn-cancel { background: #fff; color: #6b7280; border: 1px solid #d1d5db; }
.btn-cancel:hover { background: #f3f4f6; }

.modal-body { flex: 1; overflow-y: auto; padding: 0; }

/* Log table */
.log-table { width: 100%; border-collapse: collapse; font-size: 0.83em; }
.log-table th {
  position: sticky; top: 0; background: #f9fafb;
  padding: 9px 10px; text-align: left; font-weight: 600;
  color: #6b7280; border-bottom: 1px solid #e5e7eb; white-space: nowrap;
}
.log-table td { padding: 8px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
.log-table tbody tr:hover { background: #f9fafb; }
.col-id { width: 50px; color: #9ca3af; font-family: monospace; }
.col-user { width: 90px; font-weight: 500; color: #1f2937; }
.col-action { width: 110px; }
.col-target { width: 140px; color: #374151; }
.col-detail { color: #6b7280; min-width: 100px; }
.col-ip { width: 120px; color: #9ca3af; font-family: monospace; font-size: 0.9em; }
.col-time { width: 140px; color: #6b7280; white-space: nowrap; }

.action-badge { font-size: 0.8em; padding: 2px 8px; border-radius: 4px; font-weight: 600; white-space: nowrap; }
.act-auth { background: #dbeafe; color: #1e40af; }
.act-danger { background: #fee2e2; color: #b91c1c; }
.act-create { background: #dcfce7; color: #15803d; }
.act-info { background: #f3f4f6; color: #6b7280; }

.empty { padding: 40px; text-align: center; color: #9ca3af; }

/* Pagination */
.pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 10px; padding: 12px 20px; border-top: 1px solid #e5e7eb;
  flex-shrink: 0;
}
.page-btn {
  padding: 4px 14px; border: 1px solid #d1d5db; border-radius: 5px;
  background: #fff; color: #374151; font-size: 1em; cursor: pointer;
}
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-btn:hover:not(:disabled) { border-color: #2563eb; color: #2563eb; }
.page-info { font-size: 0.85em; color: #6b7280; }
</style>
