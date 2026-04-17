import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthKitProvider } from '@workos-inc/authkit-react'
import posthog from 'posthog-js'
import { PostHogProvider } from '@posthog/react'
import './index.css'
import App from './App.jsx'

posthog.init(import.meta.env.VITE_PUBLIC_POSTHOG_TOKEN, {
  api_host: import.meta.env.VITE_PUBLIC_POSTHOG_HOST,
  defaults: '2026-01-30',
  session_recording: {
    maskAllInputs: true,
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <PostHogProvider client={posthog}>
      <AuthKitProvider
        clientId={import.meta.env.VITE_WORKOS_CLIENT_ID}
        redirectUri={`${window.location.origin}/callback`}
        devMode={true}
      >
        <App />
      </AuthKitProvider>
    </PostHogProvider>
  </StrictMode>,
)
