<template>
  <div class="login-page">
    <div class="login-card">

      <!-- Brand -->
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M4 22 L10 14 L16 18 L22 8 L28 14" stroke="#2563eb" stroke-width="2.2"
              stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="28" cy="14" r="2" fill="#22c55e"/>
          </svg>
        </div>
        <h1>股票投资仪表盘</h1>
      </div>

      <!-- Mode toggle -->
      <div class="mode-bar">
        <button :class="['mode-btn', { active: isLogin }]" @click="isLogin = true; errorMsg = ''">登录</button>
        <button :class="['mode-btn', { active: !isLogin }]" @click="isLogin = false; errorMsg = ''">注册</button>
      </div>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="form">
        <div class="field">
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="用户名"
            autocomplete="username"
            :disabled="submitting"
          />
        </div>
        <div class="field">
          <input
            id="password"
            v-model="form.password"
            type="password"
            placeholder="密码"
            autocomplete="current-password"
            :disabled="submitting"
          />
        </div>

        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>

        <button type="submit" class="submit-btn" :disabled="submitting">
          <span v-if="submitting" class="spinner"></span>
          {{ submitting ? '处理中…' : isLogin ? '登录' : '注册' }}
        </button>
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

const form = reactive({ username: '', password: '' })

function resolveError(e, isLoginMode) {
  if (!e.response) return '网络连接失败，请检查网络后重试'
  const status = e.response.status
  const detail = e.response?.data?.detail || ''
  if (isLoginMode) {
    if (status === 401) return '用户名或密码不正确'
    if (status === 403) return '账号已被禁用，请联系管理员'
    if (status >= 500) return '服务器繁忙，请稍后重试'
    return detail || '登录失败，请重试'
  } else {
    if (status === 403) return detail || '注册功能已关闭，请联系管理员'
    if (status === 400 && detail.includes('已存在')) return '用户名已存在，请直接登录'
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
/* ── Page ── */
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}

/* ── Card ── */
.login-card {
  width: 360px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 12px;
  padding: 40px 36px 36px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.07);
}

/* ── Brand ── */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
}

.brand-icon {
  width: 36px;
  height: 36px;
  background: #eff6ff;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-icon svg {
  width: 22px;
  height: 22px;
}

.brand h1 {
  font-size: 17px;
  font-weight: 700;
  color: #111827;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

/* ── Mode toggle ── */
.mode-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 24px;
}

.mode-btn {
  flex: 1;
  padding: 8px 0;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-size: 14px;
  font-weight: 500;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.mode-btn.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
}

.mode-btn:not(.active):hover {
  color: #6b7280;
}

/* ── Form ── */
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  font-size: 14px;
  color: #111827;
  background: #fafafa;
  outline: none;
  transition: border-color 0.15s, background 0.15s;
  box-sizing: border-box;
  font-family: inherit;
}

.field input::placeholder {
  color: #c4c9d4;
}

.field input:focus {
  border-color: #2563eb;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(37,99,235,0.08);
}

.field input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Error ── */
.error {
  font-size: 13px;
  color: #ef4444;
  margin: 0;
  padding: 2px 0;
}

/* ── Submit ── */
.submit-btn {
  width: 100%;
  padding: 11px;
  margin-top: 4px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 7px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-family: inherit;
}

.submit-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── Spinner ── */
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
