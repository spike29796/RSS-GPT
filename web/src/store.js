// Shared UI state: day/night theme and title-language toggle, both persisted.
import { reactive } from 'vue'

export const ui = reactive({
  theme: document.documentElement.dataset.theme || 'dark',
  showZh: localStorage.getItem('showZh') === '1',
})

export function toggleTheme() {
  ui.theme = ui.theme === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = ui.theme
  localStorage.setItem('theme', ui.theme)
}

export function toggleZh() {
  ui.showZh = !ui.showZh
  localStorage.setItem('showZh', ui.showZh ? '1' : '0')
}
