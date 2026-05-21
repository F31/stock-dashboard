<template>
  <div class="login-page">
    <div class="login-card">
      <h2>Stock Dashboard</h2>

      <div class="tab-bar">
        <button :class="['tab', { active: tab === 'login' }]" @click="tab = 'login'">Login</button>
        <button :class="['tab', { active: tab === 'register' }]" @click="tab = 'register'">Register</button>
      </div>

      <div class="form">
        <input v-model="username" placeholder="Username" @keydown.enter="submit" />
        <input v-model="password" type="password" placeholder="Password" @keydown.enter="submit" />
        <button class="btn-submit" @click="submit" :disabled="busy">
          {{ busy ? 'Processing...' : tab === 'login' ? 'Login' : 'Register' }}
        </button>
      </div>

      <div v-if="error" class="error-msg">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login, register } from '../api'

const router = useRouter()
const tab = ref('login')
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  busy.value = true
  error.value = ''

  try {
    const fn = tab.value === 'login' ? login : register
    const res = await fn(username.value, password.value)
    localStorage.setItem('token', res.data.access_token)
    localStorage.setItem('username', username.value)
    router.push('/')
  } catch (e) {
    if (!e.response) {
      error.value = '网络连接失败，请检查网络后重试'
    } else if (e.response.status === 401) {
      error.value = '用户名或密码不正确，请重新输入'
    } else if (e.response.status === 400) {
      const d = e.response?.data?.detail || ''
      error.value = d.toLowerCase().includes('exists') ? '用户名已存在，请换一个或直接登录' : (d || '请求错误')
    } else if (e.response.status >= 500) {
      error.value = '服务器繁忙，请稍后重试'
    } else {
      error.value = e.response?.data?.detail || (tab.value === 'login' ? '登录失败，请重试' : '注册失败，请重试')
    }
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a;
}

.login-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 32px;
  width: 380px;
  max-width: 90vw;
}

h2 {
  text-align: center;
  margin: 0 0 20px;
  font-size: 1.3em;
}

.tab-bar {
  display: flex;
  margin-bottom: 20px;
  border-bottom: 1px solid #334155;
}

.tab {
  flex: 1;
  padding: 8px;
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  font-size: 0.95em;
  border-bottom: 2px solid transparent;
}

.tab.active {
  color: #60a5fa;
  border-bottom-color: #60a5fa;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form input {
  padding: 10px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 0.95em;
}

.form input:focus {
  outline: none;
  border-color: #2563eb;
}

.btn-submit {
  padding: 10px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.95em;
  cursor: pointer;
}

.btn-submit:disabled { opacity: 0.6; }

.error-msg {
  margin-top: 12px;
  padding: 8px;
  background: #7f1d1d;
  border-radius: 6px;
  color: #fca5a5;
  font-size: 0.85em;
  text-align: center;
}
</style>
