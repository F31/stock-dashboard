import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authAPI } from '../api/index.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isAuthenticated = computed(() => !!token.value)

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
    const res = await authAPI.login(loginUsername, password)
    setAuth(res.data.access_token, res.data.username)
    return res.data
  }

  async function register(regUsername, password) {
    const res = await authAPI.register(regUsername, password)
    setAuth(res.data.access_token, res.data.username)
    return res.data
  }

  return { token, username, isAuthenticated, login, register, logout, setAuth }
})
