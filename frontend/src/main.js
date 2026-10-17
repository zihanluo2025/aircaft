import { createApp } from 'vue'
import { Locale } from 'vant'
import enUS from 'vant/es/locale/lang/en-US'
import App from './App.vue'
import 'vant/lib/index.css'
import './styles.css'

// Vant defaults to Chinese button/placeholder text (Cancel/Confirm etc.); the rest of this app's
// UI text is English, so switch Vant's locale to match instead of fixing each component one by one.
Locale.use('en-US', enUS)

createApp(App).mount('#app')
