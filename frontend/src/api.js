// src/api.js
/**
 * Core API client configuration
 *
 * This file exports the base axios instance used by all API services.
 * Individual services (e.g., extractionService.js) import this for their requests.
 */
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  timeout: 500_000, // 5 minutes for long-running extractions
  headers: {
    "Content-Type": "application/json",
  },
});

export default api;
