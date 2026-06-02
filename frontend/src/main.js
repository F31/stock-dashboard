import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/dark-mode.css'

// Apply dark mode before first render to avoid flash
if (localStorage.getItem('darkMode') === '1') {
  document.documentElement.classList.add('dark')
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
