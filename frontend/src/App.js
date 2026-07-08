import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import Landing from "@/pages/Landing";
import Subscribe from "@/pages/Subscribe";
import Login from "@/pages/Login";
import Overview from "@/pages/Overview";
import Subscribers from "@/pages/Subscribers";
import Payments from "@/pages/Payments";
import Reports from "@/pages/Reports";
import Webhooks from "@/pages/Webhooks";
import Notifications from "@/pages/Notifications";
import ProtectedRoute from "@/components/ProtectedRoute";

export default function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Toaster theme="dark" position="top-right" toastOptions={{ style: { background: "#13161A", border: "1px solid #27272A", color: "#F3F4F6", borderRadius: "2px", fontFamily: "IBM Plex Sans, sans-serif" } }} />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/subscribe" element={<Subscribe />} />
          <Route path="/admin/login" element={<Login />} />
          <Route path="/admin" element={<ProtectedRoute><Overview /></ProtectedRoute>} />
          <Route path="/admin/subscribers" element={<ProtectedRoute><Subscribers /></ProtectedRoute>} />
          <Route path="/admin/payments" element={<ProtectedRoute><Payments /></ProtectedRoute>} />
          <Route path="/admin/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
          <Route path="/admin/webhooks" element={<ProtectedRoute><Webhooks /></ProtectedRoute>} />
          <Route path="/admin/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}
