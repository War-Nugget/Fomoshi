import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { Layout } from "./components/Layout";
import { Account } from "./pages/Account";
import { Event } from "./pages/Event";
import { Landing } from "./pages/Landing";
import { League } from "./pages/League";
import { Leaderboard } from "./pages/Leaderboard";
import { HowItWorks, NotFound, Privacy, Terms } from "./pages/Legal";
import { Login } from "./pages/Login";
import { Market } from "./pages/Market";
import { Markets } from "./pages/Markets";
import { ForgotPassword, ResetPassword } from "./pages/PasswordReset";
import { Portfolio } from "./pages/Portfolio";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/markets" element={<Markets />} />
            <Route path="/markets/:ticker" element={<Market />} />
            <Route path="/events/:eventTicker" element={<Event />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/leagues/:id" element={<League />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/account" element={<Account />} />
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
