<template>
  <div class="login-page">
    <div class="login-card">
      <div class="logo">
        <svg viewBox="0 0 64 64" fill="none" class="logo-icon">
          <rect width="64" height="64" rx="12" fill="#3b82f6"/>
          <path d="M16 44 L24 32 L32 38 L42 22 L50 30" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <circle cx="50" cy="30" r="3" fill="#4ade80"/>
        </svg>
        <h1>股票投资仪表盘</h1>
        <p class="subtitle">Stock Investment Dashboard</p>
      </div>

      <form @submit.prevent="handleSubmit" class="login-form">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            required
            :disabled="submitting"
          />
        </div>
        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            required
            :disabled="submitting"
          />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <div class="btn-group">
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ submitting ? '处理中...' : isLogin ? '登录' : '注册' }}
          </button>
          <button type="button" class="btn btn-secondary" @click="isLogin = !isLogin">
            {{ isLogin ? '没有账号？去注册' : '已有账号？去登录' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore.js'

const router = useRouter()
const authStore = useAuthStore()

const isLogin = ref(true)
const submitting = ref(false)
const errorMsg = ref('')

const form = reactive({
  username: '',
  password: '',
})

function resolveError(e, isLoginMode) {
  if (!e.response) {
    return '网络连接失败，请检查网络后重试'
  }
  const status = e.response.status
  const detail = e.response?.data?.detail || ''
  if (isLoginMode) {
    if (status === 401) return '用户名或密码不正确，请重新输入'
    if (status === 403) return '账号已被禁用，请联系管理员'
    if (status >= 500) return '服务器繁忙，请稍后重试'
    return detail || '登录失败，请重试'
  } else {
    if (status === 400 && detail.toLowerCase().includes('exists')) return '用户名已存在，请换一个或直接登录'
    if (status === 422) return '用户名或密码格式不正确'
    if (status >= 500) return '服务器繁忙，请稍后重试'
    return detail || '注册失败，请重试'
  }
}

async function handleSubmit() {
  if (!form.username || !form.password) return
  submitting.value = true
  errorMsg.value = ''

  try {
    if (isLogin.value) {
      await authStore.login(form.username, form.password)
    } else {
      await authStore.register(form.username, form.password)
    }
    router.replace({ name: 'Dashboard' })
  } catch (e) {
    errorMsg.value = resolveError(e, isLogin.value)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  padding: 20px;
}

.login-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.logo {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  width: 56px;
  height: 56px;
  margin-bottom: 12px;
}

.logo h1 {
  font-size: 22px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.subtitle {
  font-size: 13px;
  color: var(--text-muted);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.form-group input {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.form-group input:focus {
  border-color: var(--accent);
}

.error-msg {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--down);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  text-align: center;
}

.btn-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}
</style>
