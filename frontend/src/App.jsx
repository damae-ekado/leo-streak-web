import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar       from './components/Navbar'
import UploadPage   from './pages/UploadPage'
import DashboardPage from './pages/DashboardPage'
import { healthCheck } from './api/client'

function App() {
  // 서버 상태 표시 (Navbar 우측 점)
  useEffect(() => {
    const dot = document.getElementById('api-status')
    if (!dot) return
    healthCheck()
      .then(() => dot.classList.add('ok'))
      .catch(() => dot.classList.add('err'))
  }, [])

  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/"          element={<UploadPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App