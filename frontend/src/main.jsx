import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthKitProvider } from '@workos-inc/authkit-react'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthKitProvider
      clientId={import.meta.env.VITE_WORKOS_CLIENT_ID}
      redirectUri={`${window.location.origin}/callback`}
    >
      <App />
    </AuthKitProvider>
  </StrictMode>,
)
