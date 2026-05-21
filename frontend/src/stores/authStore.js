import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister } from '../api/index.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isAuthenticated = computed(() => !!token.value)

  const role = computed(() => {
    if (!token.value) return 'user'
    try {
      return JSON.parse(atob(token.value.split('.')[1])).role || 'user'
    } catch { return 'user' }
  })

  const isAdmin = computed(() => role.value === 'admin')

  function setAuth(newToken, newUsername) {
    token.value = newToken
    username.value = newUsername
    localStorage.setItem('token', newToken)
    localStorage.setItem('username', newUsername)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
  }

  async function login(loginUsername, password) {
    const res = await apiLogin(loginUsername, password)
    setAuth(res.data.access_token, res.data.username)
    return res.data
  }

  async function register(regUsername, password) {
    const res = await apiRegister(regUsername, password)
    setAuth(res.data.access_token, res.data.username)
    return res.data
  }

  return { token, username, isAuthenticated, role, isAdmin, login, register, logout, setAuth }
})
