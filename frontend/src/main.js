import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/dark-mode.css'
import { applyTheme } from './utils/theme'

// Apply theme (auto by time / light / dark) before first render to avoid flash
applyTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
