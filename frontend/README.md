# 🎨 Meeting AI — Vue 3 & Vite Assistant Frontend

This directory contains the user interface for the **Multi-Agent Meeting Assistant** (Epic 8). It has been converted to a modern **Vue 3 single-page application** powered by **Vite**, offering robust reactivity, client-side caching, and structured styling.

---

## ⚡ Tech Stack & Features

*   **Framework**: Vue 3 (Composition API utilizing `<script setup>` syntax)
*   **Build Tool**: Vite (blazing fast cold starts and optimized production builds)
*   **Styling**: Vanilla HSL CSS variables, custom dark/light theme systems, and responsive layout structures
*   **Pulsing Agent Status**: Visual tracking of active agent workloads (Summarizer, Action Item, and Follow-up Agents)
*   **Statistical Dashboards**: Instantly updates metrics (Total tasks, High priority, Flags, Questions)
*   **Adaptive Fallback Engine**: If the backend only returns the basic summary and action report, the Vue frontend automatically synthesizes and structures the follow-up email and splits Jira tickets into categorized Kanban boards.

---

## 📂 Project Structure

```text
frontend/
├── package.json        # NPM dependencies and scripts (Vite, Vue 3, @vitejs/plugin-vue)
├── vite.config.js      # Vite compilation configurations
├── index.html          # HTML entry point (loads Google Fonts & mounts #app)
├── public/             # Static public assets
└── src/
    ├── main.js         # Instantiates the Vue app and registers base stylesheets
    ├── App.vue         # Core Single File Component (SFC) housing all template, script, and style bindings
    └── style.css       # Layout grid, typography rules, glassmorphism templates, and theme settings
```

---

## 🚀 Execution & Build Instructions

### 1. Installation
Install project dependencies first:
```bash
npm install
```

### 2. Run Locally in Development Mode
To launch the Vite development server with Hot Module Replacement (HMR):
```bash
npm run dev
```
Open **`http://localhost:5173/`** in your browser. 

*Note: The frontend will send API requests to `http://localhost:8000/api/analyze` (or resolve to the relative path `/api/analyze` if served on the same port).*

### 3. Build for Production
To bundle and optimize the application for production:
```bash
npm run build
```
This compiles assets to the `/dist` directory. The output includes:
*   Minified HTML
*   Bundled CSS
*   Optimized JS chunking (using Rolldown/Vite compilation)

---

## 🛡️ Integrated API Configuration

In `src/App.vue`, the `runWorkflow` action determines the host URL dynamically:
```javascript
const host = window.location.origin;
const apiEndpoint = host.includes('localhost') || host.includes('127.0.0.1')
  ? '/api/analyze'
  : 'http://localhost:8000/api/analyze';
```
This allows the app to function properly whether it is running standalone on Vite's dev server (`port 5173`) or served directly by the FastAPI backend (`port 8000`).
