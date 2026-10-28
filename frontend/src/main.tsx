import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Market } from "./pages/Market";
import { Markets } from "./pages/Markets";
import { Portfolio } from "./pages/Portfolio";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Markets />} />
            <Route path="/markets/:ticker" element={<Market />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/login" element={<Login />} />
            <Route path="*" element={<p className="notice">That page doesn’t exist.</p>} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
