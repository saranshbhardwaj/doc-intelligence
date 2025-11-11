// src/App.jsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LandingPage from "./pages/LandingPage";
import UploadPage from "./pages/UploadPage";
import DashboardPage from "./pages/DashboardPage";
import SignInPage from "./pages/SignInPage";
import SignUpPage from "./pages/SignUpPage";
import CollectionsPage from "./pages/CollectionsPage";
import ChatPage from "./pages/ChatPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/app" element={<UploadPage />} />
          <Route path="/app/dashboard" element={<DashboardPage />} />
          <Route path="/app/chat" element={<CollectionsPage />} />
          <Route path="/app/chat/:collectionId" element={<ChatPage />} />
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
