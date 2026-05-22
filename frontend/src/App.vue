<script setup>
import { ref, computed, onMounted, nextTick } from 'vue';

// --- State Variables ---
const theme = ref('dark');
const transcript = ref('');
const language = ref('English');
const isDragover = ref(false);
const selectedFile = ref(null);
const fileInputRef = ref(null);

const viewState = ref('empty'); // 'empty' | 'loading' | 'dashboard'
const loadingStep = ref('translate'); // 'translate' | 'agents' | 'followup'
const activeTab = ref('overview');
const selectedFilter = ref('all');
const isAnalyzing = ref(false);

const agentSummarizerActive = ref(false);
const agentActionActive = ref(false);
const agentFollowupActive = ref(false);

// Live Stream Feeds
const summaryStream = ref('');
const actionsStream = ref('');
const statusMessage = ref('');
const summaryConsoleRef = ref(null);
const actionsConsoleRef = ref(null);

// Toast alerts
const toastMessage = ref('');
const showToastActive = ref(false);

// API Response Store
const summaryResult = ref(null);
const actionReportResult = ref(null);
const followupResult = ref(null);

// --- Computed Properties ---
const charCount = computed(() => transcript.value.length);

const filteredActionItems = computed(() => {
  if (!actionReportResult.value) return [];
  const items = actionReportResult.value.action_items || [];
  if (selectedFilter.value === 'all') return items;
  if (selectedFilter.value === 'needs_clarification') {
    return items.filter(item => item.status === 'Needs clarification');
  }
  return items.filter(item => item.priority === selectedFilter.value);
});

const groupedJiraTasks = computed(() => {
  if (!followupResult.value || !followupResult.value.jira_tasks) return {};
  const tasks = followupResult.value.jira_tasks;
  const groups = {};
  tasks.forEach(task => {
    const comp = task.component || 'General';
    if (!groups[comp]) groups[comp] = [];
    groups[comp].push(task);
  });
  return groups;
});

// --- Theme Handling ---
const toggleTheme = () => {
  if (theme.value === 'dark') {
    theme.value = 'light';
    document.body.classList.remove('dark-theme');
    document.body.classList.add('light-theme');
    localStorage.setItem('theme', 'light');
  } else {
    theme.value = 'dark';
    document.body.classList.remove('light-theme');
    document.body.classList.add('dark-theme');
    localStorage.setItem('theme', 'dark');
  }
};

onMounted(() => {
  const savedTheme = localStorage.getItem('theme') || 'dark';
  theme.value = savedTheme;
  if (savedTheme === 'light') {
    document.body.classList.remove('dark-theme');
    document.body.classList.add('light-theme');
  } else {
    document.body.classList.remove('light-theme');
    document.body.classList.add('dark-theme');
  }
});

// --- File Handling & Drag/Drop ---
const triggerFileSelect = () => {
  fileInputRef.value.click();
};

const handleDragOver = (e) => {
  e.preventDefault();
  isDragover.value = true;
};

const handleDragLeave = () => {
  isDragover.value = false;
};

const handleDrop = (e) => {
  e.preventDefault();
  isDragover.value = false;
  if (e.dataTransfer.files.length > 0) {
    processFile(e.dataTransfer.files[0]);
  }
};

const handleFileSelect = (e) => {
  if (e.target.files.length > 0) {
    processFile(e.target.files[0]);
  }
};

const processFile = (file) => {
  if (file.type !== 'text/plain' && !file.name.endsWith('.txt')) {
    alert('Please upload a plain text file (.txt).');
    return;
  }
  selectedFile.value = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    transcript.value = e.target.result;
  };
  reader.readAsText(file);
};

const removeFile = () => {
  selectedFile.value = null;
  transcript.value = '';
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
};

// --- Toast Utility ---
const triggerToast = (msg) => {
  toastMessage.value = msg;
  showToastActive.value = true;
  setTimeout(() => {
    showToastActive.value = false;
  }, 2500);
};

// --- Workflow Execution (WebSockets) ---
const runWorkflow = async () => {
  const text = transcript.value.trim();
  if (!text) {
    alert('Please paste a transcript or upload a file first.');
    return;
  }

  // Set loading states
  viewState.value = 'loading';
  isAnalyzing.value = true;
  loadingStep.value = 'translate';
  statusMessage.value = 'Connecting to workflow agents...';

  // Clear live stream buffers
  summaryStream.value = '';
  actionsStream.value = '';
  
  agentSummarizerActive.value = false;
  agentActionActive.value = false;
  agentFollowupActive.value = false;

  // Determine WebSocket endpoint
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const wsHost = host.includes('localhost:5173') || host.includes('127.0.0.1:5173')
    ? 'localhost:8000'
    : host;
  const wsUrl = `${wsProtocol}//${wsHost}/ws/summarize`;

  let socket;
  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    console.error(err);
    alert('Failed to establish WebSocket connection.');
    viewState.value = 'empty';
    isAnalyzing.value = false;
    return;
  }

  socket.onopen = () => {
    statusMessage.value = 'Connected. Triggering agents...';
    const payload = {
      transcript: text,
      language: language.value
    };
    socket.send(JSON.stringify(payload));
  };

  socket.onmessage = (eventMsg) => {
    try {
      const data = JSON.parse(eventMsg.data);

      if (data.type === 'status') {
        statusMessage.value = data.message;
        if (data.message.toLowerCase().includes('started')) {
          loadingStep.value = 'agents';
          agentSummarizerActive.value = true;
          agentActionActive.value = true;
        } else if (data.message.toLowerCase().includes('translating')) {
          loadingStep.value = 'translate';
        }
      } 
      
      else if (data.type === 'summary_chunk') {
        summaryStream.value += data.chunk;
        agentSummarizerActive.value = true;
        scrollConsole(summaryConsoleRef);
      } 
      
      else if (data.type === 'actions_chunk') {
        actionsStream.value += data.chunk;
        agentActionActive.value = true;
        scrollConsole(actionsConsoleRef);
      } 
      
      else if (data.type === 'summary_done') {
        summaryResult.value = data.data;
      } 
      
      else if (data.type === 'actions_done') {
        actionReportResult.value = data.data;
      } 
      
      else if (data.type === 'complete') {
        statusMessage.value = 'Analysis complete. Drafting reports...';
        loadingStep.value = 'followup';
        agentFollowupActive.value = true;

        if (summaryResult.value && actionReportResult.value) {
          followupResult.value = generateClientSideFollowup(summaryResult.value, actionReportResult.value);
        }

        setTimeout(() => {
          loadingStep.value = 'done';
          viewState.value = 'dashboard';
          isAnalyzing.value = false;
          socket.close();
        }, 800);
      } 
      
      else if (data.type === 'error') {
        alert(`Agent Error: ${data.message}`);
        viewState.value = 'empty';
        isAnalyzing.value = false;
        socket.close();
      }
    } catch (err) {
      console.error('Failed to parse WebSocket event:', err);
    }
  };

  socket.onerror = (err) => {
    console.error('WebSocket error event:', err);
    alert('Workflow connection was interrupted.');
    viewState.value = 'empty';
    isAnalyzing.value = false;
  };

  socket.onclose = () => {
    console.log('Workflow socket closed.');
  };
};

const scrollConsole = (refVar) => {
  nextTick(() => {
    if (refVar.value) {
      refVar.value.scrollTop = refVar.value.scrollHeight;
    }
  });
};

// --- Copy Utilities ---
const copyEmail = () => {
  if (!followupResult.value) return;
  navigator.clipboard.writeText(followupResult.value.email_body);
  triggerToast('Email body copied to clipboard!');
};

const copyJiraTask = (task) => {
  const md = `h3. ${task.title}\n*Assignee*: ${task.assignee}\n*Priority*: ${task.priority}\n*Due Date*: ${task.due_date}\n\n*Description*\n${task.description}`;
  navigator.clipboard.writeText(md);
  triggerToast('Jira ticket Markdown copied!');
};

const copyAllJira = () => {
  if (!followupResult.value || !followupResult.value.jira_tasks) return;
  let md = '# Jira Import Task List\n\n';
  followupResult.value.jira_tasks.forEach(task => {
    md += `## ${task.title}\n`;
    md += `- **Component**: ${task.component}\n`;
    md += `- **Assignee**: ${task.assignee}\n`;
    md += `- **Priority**: ${task.priority}\n`;
    md += `- **Due Date**: ${task.due_date}\n\n`;
    md += `### Description\n${task.description}\n\n---\n\n`;
  });
  navigator.clipboard.writeText(md);
  triggerToast('All Jira tasks copied as Markdown!');
};

// --- Fallback Follow-up Generator ---
const generateClientSideFollowup = (summary, report) => {
  const dateString = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const emailSubject = `Follow-up: Meeting Alignment & Action Items (${dateString})`;

  let emailBody = `Dear Team,\n\nHere is a summary of the decisions made and the outstanding tasks from our recent check-in. Please review the items below and align on your respective deliverables.\n\n`;
  emailBody += `### Summary\n${summary.concise_summary}\n\n`;

  if (summary.decisions_made && summary.decisions_made.length > 0) {
    emailBody += `### Key Decisions\n`;
    summary.decisions_made.forEach(dec => {
      emailBody += `- ✓ ${dec}\n`;
    });
    emailBody += `\n`;
  }

  if (report.action_items && report.action_items.length > 0) {
    emailBody += `### Action Items\n`;
    emailBody += `| Action | Owner | Due Date |\n`;
    emailBody += `| :--- | :--- | :--- |\n`;
    report.action_items.forEach(item => {
      emailBody += `| ${item.action} | **${item.owner}** | ${item.due_date} |\n`;
    });
    emailBody += `\n`;
  }

  if (summary.open_questions && summary.open_questions.length > 0) {
    emailBody += `### Open Questions / Gaps\n`;
    summary.open_questions.forEach(q => {
      emailBody += `- ? ${q}\n`;
    });
    emailBody += `\n`;
  }

  emailBody += `Please reach out if you have questions or require further clarification.\n\nBest regards,\n[Your Name]`;

  const jiraTasks = (report.action_items || []).map(item => {
    let comp = 'General';
    const ownerLower = item.owner.toLowerCase();
    const actionLower = item.action.toLowerCase();

    if (ownerLower.includes('james') || ownerLower.includes('mike') || actionLower.includes('auth') || actionLower.includes('api') || actionLower.includes('code') || actionLower.includes('refactor') || actionLower.includes('server') || actionLower.includes('it')) {
      comp = 'Engineering';
    } else if (ownerLower.includes('priya') || actionLower.includes('design') || actionLower.includes('screen') || actionLower.includes('ui') || actionLower.includes('ux')) {
      comp = 'Design';
    } else if (ownerLower.includes('tom') || actionLower.includes('marketing') || actionLower.includes('landing') || actionLower.includes('brand')) {
      comp = 'Marketing';
    } else if (ownerLower.includes('sarah') || actionLower.includes('roadmap') || actionLower.includes('plan') || actionLower.includes('product')) {
      comp = 'Product';
    } else if (ownerLower.includes('paula') || ownerLower.includes('hr') || actionLower.includes('floor') || actionLower.includes('hiring') || actionLower.includes('onboarding')) {
      comp = 'HR';
    } else if (ownerLower.includes('legal') || ownerLower.includes('irene') || actionLower.includes('contract') || actionLower.includes('clause') || actionLower.includes('terms')) {
      comp = 'Legal';
    } else if (ownerLower.includes('finance') || ownerLower.includes('fatima') || actionLower.includes('budget') || actionLower.includes('expense')) {
      comp = 'Finance';
    } else if (ownerLower.includes('marcus') || ownerLower.includes('david') || actionLower.includes('routing') || actionLower.includes('provision')) {
      comp = 'Operations';
    }

    let jiraPrio = 'Medium';
    if (item.priority === 'High') jiraPrio = 'High';
    if (item.priority === 'Low') jiraPrio = 'Low';

    const desc = `As discussed in the meeting, this task is assigned to ${item.owner}. Please coordinate and complete before the deadline: ${item.due_date}.`;

    return {
      title: item.action,
      description: desc,
      priority: jiraPrio,
      assignee: item.owner,
      due_date: item.due_date,
      component: comp
    };
  });

  return {
    email_subject: emailSubject,
    email_body: emailBody,
    jira_tasks: jiraTasks
  };
};
</script>

<template>
  <div class="glow-bg"></div>

  <div class="app-container">
    <!-- Header -->
    <header class="app-header">
      <div class="logo-area">
        <div class="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.477 2 2 6.477 2 12C2 17.523 6.477 22 12 22C17.523 22 22 17.523 22 12C22 6.477 17.523 2 12 2ZM13 17H11V15H13V17ZM13 13H11V7H13V13Z" fill="url(#logo-grad)"/>
            <defs>
              <linearGradient id="logo-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                <stop stop-color="#818CF8"/>
                <stop offset="1" stop-color="#C084FC"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1>Meeting<span>AI</span></h1>
      </div>

      <div class="agent-status-bar">
        <div class="agent-chip" :class="{ active: agentSummarizerActive }">
          <span class="pulse-dot"></span>
          <span>Summarizer Agent</span>
        </div>
        <div class="agent-chip" :class="{ active: agentActionActive }">
          <span class="pulse-dot"></span>
          <span>Action Item Agent</span>
        </div>
        <div class="agent-chip" :class="{ active: agentFollowupActive }">
          <span class="pulse-dot"></span>
          <span>Follow-up & Jira Agent</span>
        </div>
      </div>

      <button class="theme-toggle" @click="toggleTheme" aria-label="Toggle Theme">
        <svg v-if="theme === 'light'" class="sun-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.22" x2="5.64" y2="17.84"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
        <svg v-else class="moon-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </button>
    </header>

    <!-- Main Content Area -->
    <main class="main-content">
      <!-- Left Side: Input Panel -->
      <section class="panel input-panel">
        <div class="panel-header">
          <h2>Analyze Meeting</h2>
          <p class="subtitle">Submit a transcript or notes to trigger the multi-agent workflow.</p>
        </div>

        <div class="panel-body">
          <!-- Drop Zone -->
          <div 
            class="file-dropzone" 
            :class="{ dragover: isDragover }"
            @click="triggerFileSelect"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
          >
            <input 
              type="file" 
              ref="fileInputRef" 
              accept=".txt" 
              class="hidden-input" 
              @change="handleFileSelect"
            >
            <div v-if="!selectedFile" class="dropzone-content">
              <svg class="upload-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              <p><strong>Drag & drop transcript file</strong> or <span class="highlight-link">browse</span></p>
              <p class="file-hint">Plain text (.txt) up to 10MB</p>
            </div>
            
            <div v-else class="selected-file-info">
              <span class="file-name">{{ selectedFile.name }}</span>
              <button type="button" class="remove-file-btn" @click.stop="removeFile">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
          </div>

          <!-- Text Area Input -->
          <div class="text-input-group">
            <label for="transcript-input">Or paste transcript/meeting notes here</label>
            <div class="textarea-wrapper">
              <textarea 
                id="transcript-input" 
                v-model="transcript"
                placeholder="Sarah: Let's discuss the Q2 roadmap...&#10;James: The auth refactor is high priority..."
              ></textarea>
              <span class="char-counter">{{ charCount.toLocaleString() }} characters</span>
            </div>
          </div>

          <!-- Options Group -->
          <div class="options-grid">
            <div class="input-field">
              <label for="language-select">Target Language</label>
              <select id="language-select" v-model="language">
                <option value="English">English (No Translation)</option>
                <option value="Spanish">Spanish (Español)</option>
                <option value="French">French (Français)</option>
                <option value="German">German (Deutsch)</option>
                <option value="Japanese">Japanese (日本語)</option>
                <option value="Portuguese">Portuguese (Português)</option>
                <option value="Chinese">Chinese (中文)</option>
              </select>
            </div>
          </div>

          <!-- Action Button -->
          <button class="primary-btn" :disabled="isAnalyzing" @click="runWorkflow">
            <span class="btn-text">Run Workflow</span>
            <svg class="btn-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </button>
        </div>
      </section>

      <!-- Right Side: Results Panel -->
      <section class="panel results-panel" :class="{ 'empty-state-active': viewState === 'empty' }">
        
        <!-- Empty State -->
        <div v-if="viewState === 'empty'" class="empty-state">
          <div class="empty-illustration">
            <div class="empty-circle"></div>
            <svg class="empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
              <line x1="12" y1="22.08" x2="12" y2="12"></line>
            </svg>
          </div>
          <h3>Waiting for Transcript</h3>
          <p>Enter a meeting transcript on the left and run the workflow to view insights, action items, and generated follow-up drafts.</p>
        </div>

        <!-- Loading State -->
        <div v-else-if="viewState === 'loading'" class="loading-state">
          <div class="spinner-container">
            <div class="spinner-ring"></div>
            <div class="spinner-ring-inner"></div>
            <svg class="spinner-logo" width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C6.477 2 2 6.477 2 12C2 17.523 6.477 22 12 22C17.523 22 22 17.523 22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3>Analyzing Meeting Content</h3>
          <div class="loading-steps">
            <div class="loading-step" :class="{ 
              active: loadingStep === 'translate', 
              done: loadingStep === 'agents' || loadingStep === 'followup' || loadingStep === 'done' 
            }">
              Pre-processing transcript...
            </div>
            <div class="loading-step" :class="{ 
              active: loadingStep === 'agents', 
              done: loadingStep === 'followup' || loadingStep === 'done' 
            }">
              Running Agent 1 & Agent 2 in parallel...
            </div>
            <div class="loading-step" :class="{ 
              active: loadingStep === 'followup', 
              done: loadingStep === 'done' 
            }">
              Generating email draft & Jira tasks...
            </div>
          </div>

          <div class="loading-status-message" v-if="statusMessage">
            {{ statusMessage }}
          </div>

          <div class="stream-consoles-container">
            <div class="stream-console">
              <h5>📝 Summarizer Agent Feed</h5>
              <div class="console-content" ref="summaryConsoleRef">
                {{ summaryStream || 'Awaiting stream...' }}
              </div>
            </div>
            <div class="stream-console">
              <h5>⚡ Action Item Agent Feed</h5>
              <div class="console-content" ref="actionsConsoleRef">
                {{ actionsStream || 'Awaiting stream...' }}
              </div>
            </div>
          </div>
        </div>

        <!-- Output Dashboard -->
        <div v-else-if="viewState === 'dashboard'" class="results-dashboard">
          <!-- Nav Tabs -->
          <nav class="dashboard-tabs">
            <button class="tab-btn" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">
              <span>Overview</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'">
              <span>Summary</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'actions' }" @click="activeTab = 'actions'">
              <span>Action Items</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'jira' }" @click="activeTab = 'jira'">
              <span>Jira Tasks</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'email' }" @click="activeTab = 'email'">
              <span>Follow-up Email</span>
            </button>
          </nav>

          <!-- Tab Contents -->
          <div class="tab-contents">
            
            <!-- 1. OVERVIEW TAB -->
            <div v-if="activeTab === 'overview'" class="tab-pane active">
              <div class="metrics-grid">
                <div class="metric-card card-glow-primary">
                  <span class="metric-label">Total Actions</span>
                  <span class="metric-value">{{ actionReportResult?.action_items?.length || 0 }}</span>
                </div>
                <div class="metric-card card-glow-high">
                  <span class="metric-label">High Priority</span>
                  <span class="metric-value">
                    {{ actionReportResult?.action_items?.filter(i => i.priority === 'High').length || 0 }}
                  </span>
                </div>
                <div class="metric-card card-glow-warning">
                  <span class="metric-label">Needs Details</span>
                  <span class="metric-value">{{ actionReportResult?.flagged_issues?.length || 0 }}</span>
                </div>
                <div class="metric-card card-glow-info">
                  <span class="metric-label">Open Questions</span>
                  <span class="metric-value">{{ summaryResult?.open_questions?.length || 0 }}</span>
                </div>
              </div>

              <div class="quick-summary-box">
                <h3>Concise Meeting Summary</h3>
                <p class="concise-text">{{ summaryResult?.concise_summary }}</p>
              </div>

              <div class="overview-details-grid">
                <div class="decisions-summary-card">
                  <h3>Key Decisions</h3>
                  <ul v-if="summaryResult?.decisions_made?.length" class="styled-list check-list">
                    <li v-for="(dec, idx) in summaryResult.decisions_made.slice(0, 5)" :key="idx">{{ dec }}</li>
                  </ul>
                  <p v-else style="color: var(--text-muted); font-size: 13.5px;">No decisions recorded.</p>
                </div>
                <div class="warnings-summary-card">
                  <h3>Flagged Workflow Issues</h3>
                  <ul v-if="actionReportResult?.flagged_issues?.length" class="styled-list warning-list">
                    <li v-for="(issue, idx) in actionReportResult.flagged_issues.slice(0, 5)" :key="idx">{{ issue }}</li>
                  </ul>
                  <p v-else style="color: var(--success); font-size: 13.5px;">✓ No workflow issues flagged. All tasks clear!</p>
                </div>
              </div>
            </div>

            <!-- 2. SUMMARY TAB -->
            <div v-if="activeTab === 'summary'" class="tab-pane active">
              <div class="section-block">
                <h3 class="section-title">Concise Summary</h3>
                <div class="summary-highlight-box">
                  <p>{{ summaryResult?.concise_summary }}</p>
                </div>
              </div>

              <div class="section-split">
                <div class="section-block">
                  <h3 class="section-title">Key Discussion Points</h3>
                  <ul v-if="summaryResult?.key_discussion_points?.length" class="styled-list bullet-list">
                    <li v-for="(pt, idx) in summaryResult.key_discussion_points" :key="idx">{{ pt }}</li>
                  </ul>
                  <p v-else style="color: var(--text-muted); font-size: 13.5px;">No discussion points found.</p>
                </div>
                <div class="section-block">
                  <h3 class="section-title">Decisions Made</h3>
                  <ul v-if="summaryResult?.decisions_made?.length" class="styled-list check-list">
                    <li v-for="(dec, idx) in summaryResult.decisions_made" :key="idx">{{ dec }}</li>
                  </ul>
                  <p v-else style="color: var(--text-muted); font-size: 13.5px;">No decisions recorded.</p>
                </div>
              </div>

              <div class="section-split">
                <div class="section-block">
                  <h3 class="section-title">Open Questions</h3>
                  <ul v-if="summaryResult?.open_questions?.length" class="styled-list question-list">
                    <li v-for="(q, idx) in summaryResult.open_questions" :key="idx">{{ q }}</li>
                  </ul>
                  <p v-else style="color: var(--text-muted); font-size: 13.5px;">No unresolved questions.</p>
                </div>
                <div class="section-block">
                  <h3 class="section-title">Missing Information</h3>
                  <ul v-if="summaryResult?.missing_information?.length" class="styled-list warning-list">
                    <li v-for="(info, idx) in summaryResult.missing_information" :key="idx">{{ info }}</li>
                  </ul>
                  <p v-else style="color: var(--text-muted); font-size: 13.5px;">No missing information flagged.</p>
                </div>
              </div>
            </div>

            <!-- 3. ACTION ITEMS TAB -->
            <div v-if="activeTab === 'actions'" class="tab-pane active">
              <div class="actions-header">
                <div class="filter-bar">
                  <button 
                    class="filter-chip" 
                    :class="{ active: selectedFilter === 'all' }" 
                    @click="selectedFilter = 'all'"
                  >All</button>
                  <button 
                    class="filter-chip" 
                    :class="{ active: selectedFilter === 'High' }" 
                    @click="selectedFilter = 'High'"
                  >High Priority</button>
                  <button 
                    class="filter-chip" 
                    :class="{ active: selectedFilter === 'Medium' }" 
                    @click="selectedFilter = 'Medium'"
                  >Medium</button>
                  <button 
                    class="filter-chip" 
                    :class="{ active: selectedFilter === 'Low' }" 
                    @click="selectedFilter = 'Low'"
                  >Low</button>
                  <button 
                    class="filter-chip" 
                    :class="{ active: selectedFilter === 'needs_clarification' }" 
                    @click="selectedFilter = 'needs_clarification'"
                  >Needs Clarification</button>
                </div>
              </div>

              <div v-if="actionReportResult?.flagged_issues?.length" class="actions-warning-banner">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                  <line x1="12" y1="9" x2="12" y2="13"></line>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                <div>
                  <h4>Attention Required</h4>
                  <p>{{ actionReportResult.flagged_issues.length }} issue(s) flagged: missing owners, missing deadlines, or needing clarification.</p>
                </div>
              </div>

              <div class="action-items-list">
                <div 
                  v-for="(task, idx) in filteredActionItems" 
                  :key="idx" 
                  class="action-card"
                  :class="[
                    `priority-${task.priority.toLowerCase()}`, 
                    { 'status-clarify': task.status === 'Needs clarification' }
                  ]"
                >
                  <div class="action-card-main">
                    <h4>{{ task.action }}</h4>
                    <div class="action-card-meta">
                      <div class="meta-item">
                        <span class="label">Assignee:</span>
                        <span class="val">{{ task.owner }}</span>
                      </div>
                      <div class="meta-item">
                        <span class="label">Due:</span>
                        <span class="val">{{ task.due_date }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="action-card-badges">
                    <span class="badge" :class="`prio-${task.priority.toLowerCase()}`">{{ task.priority }}</span>
                    <span class="badge" :class="task.status === 'Clear' ? 'status-clear' : 'status-needs-clarification'">
                      {{ task.status }}
                    </span>
                  </div>
                </div>

                <div 
                  v-if="filteredActionItems.length === 0" 
                  style="text-align: center; padding: 40px; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--border-radius-md);"
                >
                  No action items match the selected filter.
                </div>
              </div>
            </div>

            <!-- 4. JIRA TASKS TAB -->
            <div v-if="activeTab === 'jira'" class="tab-pane active">
              <div class="jira-header">
                <p class="description">Action items converted to Jira tasks and categorized by department component.</p>
                <button class="secondary-btn" @click="copyAllJira">
                  <span>Copy All tasks (MD)</span>
                </button>
              </div>

              <div class="jira-board">
                <div v-for="(tasks, comp) in groupedJiraTasks" :key="comp" class="jira-column">
                  <div class="jira-col-header">
                    <h4>{{ comp }}</h4>
                    <span class="jira-task-count">{{ tasks.length }}</span>
                  </div>
                  <div class="jira-col-cards">
                    <div v-for="(task, idx) in tasks" :key="idx" class="jira-card">
                      <div class="jira-card-title">{{ task.title }}</div>
                      <div class="jira-card-desc">{{ task.description }}</div>
                      <div class="jira-card-footer">
                        <span class="jira-card-assignee">👤 {{ task.assignee }}</span>
                        <div class="jira-card-meta">
                          <span class="jira-prio-badge" :class="task.priority.toLowerCase()">{{ task.priority }}</span>
                          <button class="copy-card-btn" @click="copyJiraTask(task)" title="Copy Jira Ticket Markdown">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 5. FOLLOW-UP EMAIL TAB -->
            <div v-if="activeTab === 'email'" class="tab-pane active">
              <div class="email-editor-header">
                <div class="subject-line">
                  <span class="prefix">Subject:</span>
                  <span id="email-subject-val">{{ followupResult?.email_subject }}</span>
                </div>
                <button class="secondary-btn" @click="copyEmail">
                  <span class="btn-text">Copy Email Body</span>
                </button>
              </div>
              <div class="email-editor-container">
                <textarea 
                  v-if="followupResult" 
                  v-model="followupResult.email_body" 
                  class="email-textarea" 
                  spellcheck="false"
                ></textarea>
              </div>
            </div>

          </div>
        </div>

      </section>
    </main>

    <!-- Toast Notification Banner -->
    <div 
      v-if="showToastActive" 
      style="position: fixed; bottom: 20px; right: 20px; background: hsl(244, 90%, 65%); color: white; padding: 12px 24px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 1000; font-size: 13px; font-weight: 600;"
    >
      {{ toastMessage }}
    </div>

  </div>
</template>

<style scoped>
.loading-status-message {
  margin-top: 15px;
  font-size: 13.5px;
  color: var(--primary);
  font-weight: 500;
  text-align: center;
}

.stream-consoles-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  width: 100%;
  max-width: 650px;
  margin-top: 25px;
}

@media (max-width: 600px) {
  .stream-consoles-container {
    grid-template-columns: 1fr;
  }
}

.stream-console {
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 180px;
  overflow: hidden;
}

.stream-console h5 {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.console-content {
  font-family: 'Courier New', Courier, monospace;
  font-size: 11px;
  color: var(--text-main);
  line-height: 1.4;
  overflow-y: auto;
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
  text-align: left;
}
</style>
