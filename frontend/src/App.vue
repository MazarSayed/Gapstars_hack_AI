<script setup>
import { ref, computed, onMounted, nextTick } from 'vue';
import { marked } from 'marked';

// ---------------------------------------------------------------------------
// App-level mode toggle: 'single' | 'project'
// ---------------------------------------------------------------------------
const appMode = ref('single');

// ---------------------------------------------------------------------------
// Project Chat State
// ---------------------------------------------------------------------------
const projects = ref([]); // [{ project_id, name, meeting_count }]
const activeProject = ref(null); // { project_id, name }
const newProjectName = ref('');
const isCreatingProject = ref(false);

const projectMeetingFile = ref(null);
const projectFileInputRef = ref(null);
const isAddingMeeting = ref(false);
const addMeetingStatus = ref('');

const projectChatMessages = ref([]); // [{ role: 'user'|'assistant', text, streaming? }]
const projectChatInput = ref('');
const isProjectChatStreaming = ref(false);
const chatScrollRef = ref(null);
let projectSocket = null;

const getBackendBase = () => {
  const host = window.location.host;
  if (host.includes('localhost') || host.includes('127.0.0.1')) {
    return 'http://localhost:8000';
  }
  return window.location.origin;
};

const getWsBase = () => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  if (host.includes('localhost') || host.includes('127.0.0.1')) {
    return `${proto}//localhost:8000`;
  }
  return `${proto}//${host}`;
};

const fetchProjects = async () => {
  try {
    const res = await fetch(`${getBackendBase()}/project`);
    if (res.ok) projects.value = await res.json();
  } catch (e) { /* backend not ready yet */ }
};

const createProject = async () => {
  const name = newProjectName.value.trim();
  if (!name) return;
  isCreatingProject.value = true;
  try {
    const res = await fetch(`${getBackendBase()}/project`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      const proj = await res.json();
      projects.value.push({ project_id: proj.project_id, name: proj.name, meeting_count: 0 });
      newProjectName.value = '';
      selectProject({ project_id: proj.project_id, name: proj.name });
    }
  } finally {
    isCreatingProject.value = false;
  }
};

const selectProject = (proj) => {
  activeProject.value = proj;
  projectChatMessages.value = [];
  addMeetingStatus.value = '';
  connectProjectChat(proj.project_id);
};

const connectProjectChat = (projectId) => {
  if (projectSocket) {
    projectSocket.close();
    projectSocket = null;
  }
  const ws = new WebSocket(`${getWsBase()}/ws/project/${projectId}/chat`);
  projectSocket = ws;

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'ready') return;
    if (data.type === 'chunk') {
      const last = projectChatMessages.value[projectChatMessages.value.length - 1];
      if (last && last.role === 'assistant' && last.streaming) {
        last.text += data.chunk;
        scrollChat();
      }
    }
    if (data.type === 'done') {
      const last = projectChatMessages.value[projectChatMessages.value.length - 1];
      if (last && last.streaming) last.streaming = false;
      isProjectChatStreaming.value = false;
    }
    if (data.type === 'error') {
      isProjectChatStreaming.value = false;
      projectChatMessages.value.push({ role: 'assistant', text: `Error: ${data.message}`, streaming: false });
    }
  };

  ws.onerror = () => {
    isProjectChatStreaming.value = false;
  };
};

const sendProjectChatMessage = () => {
  const q = projectChatInput.value.trim();
  if (!q || isProjectChatStreaming.value || !projectSocket || projectSocket.readyState !== WebSocket.OPEN) return;

  projectChatMessages.value.push({ role: 'user', text: q, streaming: false });
  projectChatMessages.value.push({ role: 'assistant', text: '', streaming: true });
  isProjectChatStreaming.value = true;
  projectChatInput.value = '';
  scrollChat();

  projectSocket.send(JSON.stringify({ question: q }));
};

const handleProjectChatKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendProjectChatMessage();
  }
};

const scrollChat = () => {
  nextTick(() => {
    if (chatScrollRef.value) {
      chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight;
    }
  });
};

const triggerProjectFileSelect = () => projectFileInputRef.value?.click();

const handleProjectFileSelect = (e) => {
  if (e.target.files.length > 0) projectMeetingFile.value = e.target.files[0];
};

const addMeetingToProject = async () => {
  if (!activeProject.value || !projectMeetingFile.value) return;
  isAddingMeeting.value = true;
  addMeetingStatus.value = 'Processing meeting transcript...';

  const formData = new FormData();
  formData.append('file', projectMeetingFile.value);

  try {
    const res = await fetch(`${getBackendBase()}/project/${activeProject.value.project_id}/meeting`, {
      method: 'POST',
      body: formData,
    });
    if (res.ok) {
      const result = await res.json();
      addMeetingStatus.value = `Added "${result.meeting_name}" — ${result.total_meetings} meeting(s) in project.`;
      // Update meeting count in list
      const proj = projects.value.find(p => p.project_id === activeProject.value.project_id);
      if (proj) proj.meeting_count = result.total_meetings;
      projectMeetingFile.value = null;
      if (projectFileInputRef.value) projectFileInputRef.value.value = '';
    } else {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      addMeetingStatus.value = `Error: ${err.detail}`;
    }
  } catch (e) {
    addMeetingStatus.value = `Error: ${e.message}`;
  } finally {
    isAddingMeeting.value = false;
  }
};

// --- State Variables ---
const theme = ref('dark');
const transcript = ref('');
const language = ref('English');
const isDragover = ref(false);
const selectedFile = ref(null);
const fileInputRef = ref(null);
const isUploading = ref(false);

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
const followupStream = ref('');
const statusMessage = ref('');
const summaryConsoleRef = ref(null);
const actionsConsoleRef = ref(null);

// Queues for character-by-character typewriter rendering
const isStreamingActive = ref(false);
let summaryQueue = [];
let actionsQueue = [];
let followupQueue = [];

// Lenient partial JSON parser to allow progressive streaming render of dashboard
const parsePartialJSON = (jsonStr) => {
  if (!jsonStr) return null;
  let str = jsonStr.trim();
  
  // Clean markdown block code wrappers if the stream starts with them
  if (str.startsWith('```')) {
    str = str.replace(/^```json\s*/i, '').replace(/```$/, '').trim();
  }
  
  try {
    return JSON.parse(str);
  } catch (e) {
    // Continue with repair logic
  }

  let openBraces = 0;
  let openBrackets = 0;
  let inString = false;
  let escaped = false;
  
  for (let i = 0; i < str.length; i++) {
    const char = str[i];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === '\\') {
      escaped = true;
      continue;
    }
    if (char === '"') {
      inString = !inString;
      continue;
    }
    if (!inString) {
      if (char === '{') openBraces++;
      else if (char === '}') openBraces--;
      else if (char === '[') openBrackets++;
      else if (char === ']') openBrackets--;
    }
  }

  if (inString) {
    str += '"';
  }

  if (openBrackets > 0) {
    str += ']'.repeat(openBrackets);
  }
  if (openBraces > 0) {
    str += '}'.repeat(openBraces);
  }

  // Remove potential trailing commas from incomplete JSON properties
  let cleaned = str.replace(/,\s*\]/g, ']').replace(/,\s*\}/g, '}');
  
  try {
    return JSON.parse(cleaned);
  } catch (e2) {
    return null;
  }
};

const processSummaryQueue = () => {
  if (summaryQueue.length > 0) {
    const batchSize = Math.max(1, Math.floor(summaryQueue.length / 12));
    for (let i = 0; i < batchSize; i++) {
      if (summaryQueue.length > 0) {
        summaryStream.value += summaryQueue.shift();
      }
    }
    
    const parsed = parsePartialJSON(summaryStream.value);
    if (parsed) {
      summaryResult.value = parsed;
    }
    
    scrollConsole(summaryConsoleRef);
  }
};

const processActionsQueue = () => {
  if (actionsQueue.length > 0) {
    const batchSize = Math.max(1, Math.floor(actionsQueue.length / 12));
    for (let i = 0; i < batchSize; i++) {
      if (actionsQueue.length > 0) {
        actionsStream.value += actionsQueue.shift();
      }
    }
    
    const parsed = parsePartialJSON(actionsStream.value);
    if (parsed) {
      actionReportResult.value = parsed;
    }
    
    scrollConsole(actionsConsoleRef);
  }
};

const processFollowupQueue = () => {
  if (followupQueue.length > 0) {
    const batchSize = Math.max(1, Math.floor(followupQueue.length / 12));
    for (let i = 0; i < batchSize; i++) {
      if (followupQueue.length > 0) followupStream.value += followupQueue.shift();
    }
    const parsed = parsePartialJSON(followupStream.value);
    if (parsed) followupResult.value = parsed;
  }
};

const tickStreamQueues = () => {
  if (!isStreamingActive.value) return;
  processSummaryQueue();
  processActionsQueue();
  processFollowupQueue();
  requestAnimationFrame(tickStreamQueues);
};

// Toast alerts
const toastMessage = ref('');
const showToastActive = ref(false);

// Error State
const workflowError = ref(null);
const is503Error = computed(() => {
  if (!workflowError.value) return false;
  const msg = workflowError.value.toLowerCase();
  return msg.includes('503') || msg.includes('unavailable') || msg.includes('high demand') || msg.includes('overloaded');
});

const retryWorkflow = () => {
  workflowError.value = null;
  runWorkflow();
};

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
  fetchProjects();
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

const ACCEPTED_EXTS = new Set([
  'txt', 'docx', 'pdf',
  'mp3', 'wav', 'ogg', 'm4a', 'aac',
  'mp4', 'mov', 'avi', 'webm',
]);

const uploadTranscriptFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const host = window.location.host;
  const urls = (host.includes('localhost') || host.includes('127.0.0.1'))
    ? ['http://localhost:8000/upload/transcript', 'http://localhost:8001/upload/transcript']
    : [`${window.location.origin}/upload/transcript`];

  for (const url of urls) {
    try {
      const res = await fetch(url, { method: 'POST', body: formData });
      if (res.ok) {
        const json = await res.json();
        return json.transcript;
      }
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Upload failed');
    } catch (e) {
      if (e instanceof TypeError) continue;
      throw e;
    }
  }
  throw new Error('Could not connect to backend. Is the server running?');
};

const processFile = async (file) => {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!ACCEPTED_EXTS.has(ext)) {
    alert(`Unsupported file type ".${ext}".\nAccepted: TXT, DOCX, PDF, MP3, WAV, OGG, M4A, AAC, MP4, MOV, AVI, WEBM`);
    return;
  }

  selectedFile.value = file;
  transcript.value = '';

  if (ext === 'txt') {
    const reader = new FileReader();
    reader.onload = (e) => { transcript.value = e.target.result; };
    reader.readAsText(file);
    return;
  }

  isUploading.value = true;
  try {
    transcript.value = await uploadTranscriptFile(file);
  } catch (e) {
    alert(`Upload failed: ${e.message}`);
    selectedFile.value = null;
  } finally {
    isUploading.value = false;
  }
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
  viewState.value = 'dashboard';
  isAnalyzing.value = true;
  loadingStep.value = 'translate';
  statusMessage.value = 'Connecting to workflow agents...';

  // Clear previous results completely
  workflowError.value = null;
  summaryResult.value = null;
  actionReportResult.value = null;
  followupResult.value = null;

  // Initialize and trigger live streaming queues
  isStreamingActive.value = true;
  summaryQueue = [];
  actionsQueue = [];
  followupQueue = [];
  summaryStream.value = '';
  actionsStream.value = '';
  followupStream.value = '';
  requestAnimationFrame(tickStreamQueues);
  
  agentSummarizerActive.value = false;
  agentActionActive.value = false;
  agentFollowupActive.value = false;

  // Determine WebSocket endpoint candidates
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  
  let wsUrls = [];
  if (host.includes('localhost') || host.includes('127.0.0.1')) {
    // Try standard port 8000, then fallback to 8001 (to bypass PHP conflict)
    wsUrls.push(`${wsProtocol}//localhost:8000/ws/summarize`);
    wsUrls.push(`${wsProtocol}//localhost:8001/ws/summarize`);
    wsUrls.push(`${wsProtocol}//127.0.0.1:8000/ws/summarize`);
    wsUrls.push(`${wsProtocol}//127.0.0.1:8001/ws/summarize`);
  } else {
    wsUrls.push(`${wsProtocol}//${host}/ws/summarize`);
  }

  const establishConnection = (urlIndex) => {
    if (urlIndex >= wsUrls.length) {
      workflowError.value = 'WebSocket connection failed.\n\nReason: A port conflict was detected on port 8000 (likely due to a local PHP built-in server or another service listening on localhost:8000).\n\nSolutions:\n1. Run the FastAPI server on port 8001 instead: uv run uvicorn main:app --port 8001\n2. Or, terminate the conflicting PHP process: kill -9 <PHP_PID>';
      isStreamingActive.value = false;
      viewState.value = 'dashboard';
      isAnalyzing.value = false;
      return;
    }

    const currentUrl = wsUrls[urlIndex];
    statusMessage.value = `Connecting to workflow agents (${urlIndex + 1}/${wsUrls.length})...`;
    console.log(`Connecting to WebSocket: ${currentUrl}`);

    let socket;
    try {
      socket = new WebSocket(currentUrl);
    } catch (err) {
      console.error(`Failed to construct WebSocket for ${currentUrl}:`, err);
      establishConnection(urlIndex + 1);
      return;
    }

    // Set a connection timeout to detect hanging ports (like PHP ignoring WS connections)
    const connectionTimeout = setTimeout(() => {
      if (socket.readyState !== WebSocket.OPEN) {
        console.warn(`Connection timeout for ${currentUrl}. Trying next...`);
        socket.close();
        establishConnection(urlIndex + 1);
      }
    }, 2000);

    socket.onopen = () => {
      clearTimeout(connectionTimeout);
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
          if (data.chunk) {
            summaryQueue.push(...data.chunk.split(''));
          }
          agentSummarizerActive.value = true;
        } 
        
        else if (data.type === 'actions_chunk') {
          if (data.chunk) {
            actionsQueue.push(...data.chunk.split(''));
          }
          agentActionActive.value = true;
        } 
        
        else if (data.type === 'summary_done') {
          if (summaryQueue.length > 0) {
            summaryStream.value += summaryQueue.join('');
            summaryQueue = [];
          }
          summaryResult.value = data.data;
        } 
        
        else if (data.type === 'actions_done') {
          if (actionsQueue.length > 0) {
            actionsStream.value += actionsQueue.join('');
            actionsQueue = [];
          }
          actionReportResult.value = data.data;
        }

        else if (data.type === 'followup_chunk') {
          if (data.chunk) followupQueue.push(...data.chunk.split(''));
          agentFollowupActive.value = true;
          loadingStep.value = 'followup';
        }

        else if (data.type === 'followup_done') {
          if (followupQueue.length > 0) {
            followupStream.value += followupQueue.join('');
            followupQueue = [];
          }
          followupResult.value = data.data;
        }

        else if (data.type === 'complete') {
          // Flush any remaining characters immediately
          isStreamingActive.value = false;
          if (summaryQueue.length > 0) { summaryStream.value += summaryQueue.join(''); summaryQueue = []; }
          if (actionsQueue.length > 0) { actionsStream.value += actionsQueue.join(''); actionsQueue = []; }
          if (followupQueue.length > 0) { followupStream.value += followupQueue.join(''); followupQueue = []; }

          loadingStep.value = 'done';
          viewState.value = 'dashboard';
          isAnalyzing.value = false;
          socket.close();
          triggerToast('Workflow analysis completed successfully!');
        } 
        
        else if (data.type === 'error') {
          workflowError.value = data.message;
          isStreamingActive.value = false;
          viewState.value = 'dashboard';
          isAnalyzing.value = false;
          socket.close();
        }
      } catch (err) {
        console.error('Failed to parse WebSocket event:', err);
      }
    };

    socket.onerror = (err) => {
      clearTimeout(connectionTimeout);
      console.warn(`WebSocket error on ${currentUrl}:`, err);
      if (socket.readyState !== WebSocket.OPEN) {
        socket.close();
        establishConnection(urlIndex + 1);
      } else {
        workflowError.value = 'Workflow connection was interrupted.';
        isStreamingActive.value = false;
        viewState.value = 'dashboard';
        isAnalyzing.value = false;
      }
    };

    socket.onclose = () => {
      console.log(`Workflow socket closed for ${currentUrl}.`);
    };
  };

  establishConnection(0);
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

// --- Chatbot Integration ---
const isChatOpen = ref(false);
const chatInput = ref('');
const isChatConnecting = ref(false);
const isChatStreaming = ref(false);
const chatMessagesRef = ref(null);

const chatMessages = ref([
  {
    role: 'model',
    content: "Hi! I'm your Meeting Assistant. You can ask me questions about this meeting's decisions, action items, or anything else in the transcript.",
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
]);

let chatSocket = null;

const suggestedQuestions = [
  "Summarize the key decisions",
  "What are the high priority actions?",
  "Who is responsible for what?",
  "Is there any missing info?"
];

const renderMarkdown = (text) => {
  if (!text) return '';
  return marked.parse(text, { breaks: true });
};

const scrollChatToEnd = () => {
  nextTick(() => {
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight;
    }
  });
};

const toggleChat = () => {
  isChatOpen.value = !isChatOpen.value;
  if (isChatOpen.value) {
    scrollChatToEnd();
  }
};

const transmitChatMessage = (text, botIndex) => {
  if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
    const botMsg = chatMessages.value[botIndex];
    if (botMsg) {
      botMsg.content = "Failed to send message. Connection closed.";
      botMsg.isStreaming = false;
    }
    isChatStreaming.value = false;
    return;
  }

  const payload = {
    message: text,
    transcript: transcript.value || '',
    analysis_results: {
      summary: summaryResult.value || null,
      action_items: actionReportResult.value || null,
      followup: followupResult.value || null
    }
  };

  chatSocket.send(JSON.stringify(payload));
};

const connectChatSocket = (onOpenCallback) => {
  isChatConnecting.value = true;
  
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  
  let chatUrls = [];
  if (host.includes('localhost') || host.includes('127.0.0.1')) {
    chatUrls.push(`${wsProtocol}//localhost:8000/ws/chat`);
    chatUrls.push(`${wsProtocol}//localhost:8001/ws/chat`);
    chatUrls.push(`${wsProtocol}//127.0.0.1:8000/ws/chat`);
    chatUrls.push(`${wsProtocol}//127.0.0.1:8001/ws/chat`);
  } else {
    chatUrls.push(`${wsProtocol}//${host}/ws/chat`);
  }

  const tryConnect = (urlIndex) => {
    if (urlIndex >= chatUrls.length) {
      isChatConnecting.value = false;
      isChatStreaming.value = false;
      const lastBotMsg = chatMessages.value[chatMessages.value.length - 1];
      if (lastBotMsg && lastBotMsg.isStreaming) {
        lastBotMsg.content = "Could not establish connection to the chat server.";
        lastBotMsg.isStreaming = false;
      }
      return;
    }

    const url = chatUrls[urlIndex];
    
    try {
      chatSocket = new WebSocket(url);
    } catch (e) {
      console.error(`Failed to create WebSocket for chat on ${url}`, e);
      tryConnect(urlIndex + 1);
      return;
    }

    chatSocket.onopen = () => {
      isChatConnecting.value = false;
      if (onOpenCallback) onOpenCallback();
    };

    chatSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const botMsg = chatMessages.value[chatMessages.value.length - 1];
        
        if (data.type === 'chunk') {
          if (botMsg && botMsg.isStreaming) {
            botMsg.content += data.chunk;
            scrollChatToEnd();
          }
        } else if (data.type === 'done') {
          if (botMsg && botMsg.isStreaming) {
            botMsg.content = data.response || botMsg.content;
            botMsg.isStreaming = false;
            scrollChatToEnd();
          }
          isChatStreaming.value = false;
        } else if (data.type === 'error') {
          if (botMsg && botMsg.isStreaming) {
            botMsg.content = `Error: ${data.message}`;
            botMsg.isStreaming = false;
          }
          isChatStreaming.value = false;
        }
      } catch (e) {
        console.error("Error parsing chat socket event:", e);
      }
    };

    chatSocket.onerror = (err) => {
      console.warn(`Chat socket error on ${url}:`, err);
      if (chatSocket.readyState !== WebSocket.OPEN) {
        chatSocket.close();
        tryConnect(urlIndex + 1);
      }
    };

    chatSocket.onclose = () => {
      chatSocket = null;
      isChatStreaming.value = false;
    };
  };

  tryConnect(0);
};

const sendChatMessage = (messageText) => {
  const textToSend = messageText || chatInput.value.trim();
  if (!textToSend) return;

  chatMessages.value.push({
    role: 'user',
    content: textToSend,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  });

  if (!messageText) {
    chatInput.value = '';
  }

  scrollChatToEnd();

  const botMessageIndex = chatMessages.value.length;
  chatMessages.value.push({
    role: 'model',
    content: '',
    isStreaming: true,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  });

  isChatStreaming.value = true;

  if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
    connectChatSocket(() => {
      transmitChatMessage(textToSend, botMessageIndex);
    });
  } else {
    transmitChatMessage(textToSend, botMessageIndex);
  }
};

const clearChat = () => {
  chatMessages.value = [
    {
      role: 'model',
      content: "Hi! I'm your Meeting Assistant. You can ask me questions about this meeting's decisions, action items, or anything else in the transcript.",
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ];
  if (chatSocket) {
    chatSocket.close();
  }
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

      <div class="mode-toggle-group">
        <button class="mode-toggle-btn" :class="{ active: appMode === 'single' }" @click="appMode = 'single'">Single Meeting</button>
        <button class="mode-toggle-btn" :class="{ active: appMode === 'project' }" @click="appMode = 'project'">Project Chat</button>
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

    <!-- Project Chat Mode -->
    <main v-if="appMode === 'project'" class="main-content">
      <!-- Left: Project Manager -->
      <section class="panel input-panel">
        <div class="panel-header">
          <h2>Project Chat</h2>
          <p class="subtitle">Group meetings into a project and ask questions across all of them.</p>
        </div>

        <div class="panel-body">
          <!-- Create Project -->
          <div class="input-field" style="margin-bottom: 12px;">
            <label>New Project Name</label>
            <input
              type="text"
              v-model="newProjectName"
              placeholder="e.g. Q2 Product Planning"
              class="text-input-field"
              @keydown.enter="createProject"
            />
          </div>
          <button class="primary-btn" :disabled="isCreatingProject || !newProjectName.trim()" @click="createProject" style="margin-bottom: 20px;">
            <span class="btn-text">{{ isCreatingProject ? 'Creating...' : 'Create Project' }}</span>
          </button>

          <!-- Project List -->
          <div v-if="projects.length" class="project-list">
            <h4 class="section-label">Your Projects</h4>
            <div
              v-for="proj in projects"
              :key="proj.project_id"
              class="project-item"
              :class="{ active: activeProject?.project_id === proj.project_id }"
              @click="selectProject(proj)"
            >
              <span class="project-name">{{ proj.name }}</span>
              <span class="project-meeting-count">{{ proj.meeting_count }} meeting{{ proj.meeting_count !== 1 ? 's' : '' }}</span>
            </div>
          </div>

          <!-- Add Meeting -->
          <div v-if="activeProject" class="add-meeting-section">
            <h4 class="section-label">Add Meeting to "{{ activeProject.name }}"</h4>
            <div class="file-dropzone" style="cursor: pointer;" @click="triggerProjectFileSelect">
              <input
                type="file"
                ref="projectFileInputRef"
                accept=".txt,.docx,.pdf,.mp3,.wav,.ogg,.m4a,.aac,.mp4,.mov,.avi,.webm"
                class="hidden-input"
                @change="handleProjectFileSelect"
              />
              <div class="dropzone-content">
                <svg class="upload-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                <p v-if="!projectMeetingFile"><strong>Click to upload</strong> a meeting file</p>
                <p v-else class="file-name">{{ projectMeetingFile.name }}</p>
              </div>
            </div>
            <button
              class="primary-btn"
              :disabled="isAddingMeeting || !projectMeetingFile"
              @click="addMeetingToProject"
              style="margin-top: 10px;"
            >
              <span class="btn-text">{{ isAddingMeeting ? 'Processing...' : 'Add to Project' }}</span>
            </button>
            <p v-if="addMeetingStatus" class="add-meeting-status" :class="{ error: addMeetingStatus.startsWith('Error') }">
              {{ addMeetingStatus }}
            </p>
          </div>
        </div>
      </section>

      <!-- Right: Chat Interface -->
      <section class="panel results-panel">
        <div v-if="!activeProject" class="empty-state">
          <div class="empty-illustration">
            <div class="empty-circle"></div>
            <svg class="empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
          </div>
          <h3>Select or Create a Project</h3>
          <p>Create a project on the left, add meeting recordings or transcripts, then ask questions that span all meetings.</p>
        </div>

        <div v-else class="project-chat-container">
          <div class="project-chat-header">
            <span class="project-chat-title">{{ activeProject.name }}</span>
            <span class="project-meeting-badge">
              {{ projects.find(p => p.project_id === activeProject.project_id)?.meeting_count || 0 }} meetings
            </span>
          </div>

          <div v-if="!projects.find(p => p.project_id === activeProject.project_id)?.meeting_count" class="chat-empty-hint">
            Add at least one meeting on the left to start chatting.
          </div>

          <!-- Message History -->
          <div class="chat-messages" ref="chatScrollRef">
            <div v-if="!projectChatMessages.length" class="chat-starter-hints">
              <p class="chat-hint-title">Try asking:</p>
              <div class="chat-hint-chips">
                <span class="hint-chip" @click="projectChatInput = 'What decisions have been made so far?'; sendProjectChatMessage()">What decisions have been made?</span>
                <span class="hint-chip" @click="projectChatInput = 'Which action items are still open?'; sendProjectChatMessage()">Which action items are open?</span>
                <span class="hint-chip" @click="projectChatInput = 'Catch me up on the project so far'; sendProjectChatMessage()">Catch me up on the project</span>
                <span class="hint-chip" @click="projectChatInput = 'What risks or blockers were mentioned?'; sendProjectChatMessage()">What risks were mentioned?</span>
              </div>
            </div>

            <div
              v-for="(msg, idx) in projectChatMessages"
              :key="idx"
              class="chat-message"
              :class="msg.role"
            >
              <div class="message-bubble" :class="{ streaming: msg.streaming }">
                <span v-if="msg.role === 'user'" class="msg-role-label">You</span>
                <span v-else class="msg-role-label agent-label">Project Agent</span>
                <div class="message-text" v-html="renderMarkdown(msg.text)"></div>
                <span v-if="msg.streaming" class="typing-cursor">▋</span>
              </div>
            </div>
          </div>

          <!-- Chat Input -->
          <div class="chat-input-row">
            <textarea
              v-model="projectChatInput"
              class="chat-textarea"
              placeholder="Ask anything about your project meetings..."
              rows="2"
              :disabled="isProjectChatStreaming"
              @keydown="handleProjectChatKeydown"
            ></textarea>
            <button class="chat-send-btn" :disabled="isProjectChatStreaming || !projectChatInput.trim()" @click="sendProjectChatMessage">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
      </section>
    </main>

    <!-- Single Meeting Mode -->
    <main v-else class="main-content">
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
            :class="{ dragover: isDragover, uploading: isUploading }"
            @click="!isUploading && triggerFileSelect()"
            @dragover="!isUploading && handleDragOver($event)"
            @dragleave="handleDragLeave"
            @drop="!isUploading && handleDrop($event)"
          >
            <input
              type="file"
              ref="fileInputRef"
              accept=".txt,.docx,.pdf,.mp3,.wav,.ogg,.m4a,.aac,.mp4,.mov,.avi,.webm"
              class="hidden-input"
              @change="handleFileSelect"
            >
            <div v-if="!selectedFile" class="dropzone-content">
              <svg class="upload-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              <p><strong>Drag & drop a file</strong> or <span class="highlight-link">browse</span></p>
              <p class="file-hint">TXT, DOCX, PDF, MP3, WAV, MP4 and more — up to 100MB</p>
            </div>

            <div v-else class="selected-file-info">
              <span v-if="isUploading" class="upload-spinner-inline"></span>
              <span class="file-name">{{ isUploading ? 'Extracting transcript...' : selectedFile.name }}</span>
              <button v-if="!isUploading" type="button" class="remove-file-btn" @click.stop="removeFile">
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
            <div class="stream-console" :class="{ active: agentSummarizerActive }">
              <div class="console-header">
                <h5>📝 Summarizer Agent Feed</h5>
                <span class="console-status" :class="{ streaming: isStreamingActive && summaryQueue.length > 0 }"></span>
              </div>
              <div class="console-content" ref="summaryConsoleRef">
                <span>{{ summaryStream }}</span><span class="typing-cursor" v-if="isStreamingActive && summaryStream">▋</span><span class="placeholder-text" v-if="!summaryStream">Awaiting stream...</span>
              </div>
            </div>
            <div class="stream-console" :class="{ active: agentActionActive }">
              <div class="console-header">
                <h5>⚡ Action Item Agent Feed</h5>
                <span class="console-status" :class="{ streaming: isStreamingActive && actionsQueue.length > 0 }"></span>
              </div>
              <div class="console-content" ref="actionsConsoleRef">
                <span>{{ actionsStream }}</span><span class="typing-cursor" v-if="isStreamingActive && actionsStream">▋</span><span class="placeholder-text" v-if="!actionsStream">Awaiting stream...</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Output Dashboard -->
        <div v-else-if="viewState === 'dashboard'" class="results-dashboard">
          <!-- Error Panel -->
          <div v-if="workflowError" class="workflow-error-panel animate-fade-in">
            <div class="error-panel-header">
              <div class="error-title-container">
                <svg class="error-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                  <line x1="12" y1="9" x2="12" y2="13"></line>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                <span>Workflow Execution Interrupted</span>
              </div>
              <button class="clear-error-btn" @click="workflowError = null" title="Dismiss error">&times;</button>
            </div>
            <p class="error-message">
              {{ is503Error ? 'Google Gemini is currently experiencing temporary high demand and rate limits. Please wait a few seconds and try again.' : workflowError }}
            </p>
            <div class="error-actions">
              <button class="retry-btn-accent" @click="retryWorkflow">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
                </svg>
                <span>Retry Workflow</span>
              </button>
            </div>
          </div>

          <!-- Live Agent Streams Status (Collapsible Panel during active analysis) -->
          <div v-if="isAnalyzing" class="live-progress-overlay">
            <div class="progress-banner-header">
              <div class="progress-status-container">
                <span class="spinner-tiny"></span>
                <span class="progress-title">Workflow Agents Executing...</span>
              </div>
              <span class="status-msg-badge">{{ statusMessage }}</span>
            </div>
            
            <div class="stream-consoles-container inline-consoles">
              <div class="stream-console" :class="{ active: agentSummarizerActive }">
                <div class="console-header">
                  <h5>📝 Summarizer Agent Feed</h5>
                  <span class="console-status" :class="{ streaming: isStreamingActive && summaryQueue.length > 0 }"></span>
                </div>
                <div class="console-content" ref="summaryConsoleRef">
                  <span>{{ summaryStream }}</span><span class="typing-cursor" v-if="isStreamingActive && summaryStream">▋</span><span class="placeholder-text" v-if="!summaryStream">Awaiting stream...</span>
                </div>
              </div>
              <div class="stream-console" :class="{ active: agentActionActive }">
                <div class="console-header">
                  <h5>⚡ Action Item Agent Feed</h5>
                  <span class="console-status" :class="{ streaming: isStreamingActive && actionsQueue.length > 0 }"></span>
                </div>
                <div class="console-content" ref="actionsConsoleRef">
                  <span>{{ actionsStream }}</span><span class="typing-cursor" v-if="isStreamingActive && actionsStream">▋</span><span class="placeholder-text" v-if="!actionsStream">Awaiting stream...</span>
                </div>
              </div>
            </div>
          </div>

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
              <div class="jira-header" v-if="followupResult?.jira_tasks?.length">
                <p class="description">Action items converted to Jira tasks and categorized by department component.</p>
                <button class="secondary-btn" @click="copyAllJira">
                  <span>Copy All tasks (MD)</span>
                </button>
              </div>

              <div v-if="followupResult?.jira_tasks?.length" class="jira-board">
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

              <div v-else-if="isAnalyzing" class="jira-board-skeleton">
                <div class="jira-column-skeleton" v-for="col in ['Engineering', 'Design', 'Marketing']" :key="col">
                  <div class="jira-col-header-skeleton">
                    <h4>{{ col }}</h4>
                    <span class="skeleton-badge">...</span>
                  </div>
                  <div class="jira-col-cards-skeleton">
                    <div class="jira-card-skeleton">
                      <div class="skeleton-line short"></div>
                      <div class="skeleton-line"></div>
                      <div class="skeleton-line medium"></div>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="jira-empty-state">
                <div class="empty-icon-wrap">
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="9" y1="3" x2="9" y2="21"></line>
                    <line x1="15" y1="3" x2="15" y2="21"></line>
                  </svg>
                </div>
                <h3>No Jira Tasks Generated</h3>
                <p>Tasks will map automatically once the action item agent resolves.</p>
              </div>
            </div>

            <!-- 5. FOLLOW-UP EMAIL TAB -->
            <div v-if="activeTab === 'email'" class="tab-pane active">
              <div class="email-editor-header">
                <div class="subject-line">
                  <span class="prefix">Subject:</span>
                  <span id="email-subject-val">{{ followupResult?.email_subject || (isAnalyzing ? 'Drafting subject line...' : 'No email subject generated') }}</span>
                </div>
                <button class="secondary-btn" :disabled="!followupResult" @click="copyEmail">
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
                <div v-else-if="isAnalyzing" class="email-skeleton-textarea">
                  <span class="skeleton-text">Drafting email content...</span>
                  <span class="typing-cursor">▋</span>
                </div>
                <div v-else class="email-empty-state">
                  <p>No email draft generated yet. Run the workflow to produce the follow-up draft.</p>
                </div>
              </div>
            </div>

          </div>
        </div>

      </section>
    </main>

    <!-- Chatbot Widget -->
    <div class="chatbot-widget" :class="{ open: isChatOpen }">
      <!-- Chat Toggle Button -->
      <button class="chat-toggle-btn" @click="toggleChat" aria-label="Toggle Chatbot">
        <svg v-if="!isChatOpen" class="chat-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
        <svg v-else class="close-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
        <span v-if="!isChatOpen" class="chat-badge-pulse"></span>
      </button>

      <!-- Chat Window Panel -->
      <div v-if="isChatOpen" class="chat-window-panel">
        <div class="chat-window-header">
          <div class="chat-window-title">
            <span class="active-dot"></span>
            <h4>Meeting AI Chatbot</h4>
          </div>
          <button class="chat-clear-btn" @click="clearChat" title="Clear Conversation">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          </button>
        </div>

        <!-- Chat Suggested Questions -->
        <div class="chat-suggestions" v-if="chatMessages.length <= 1">
          <span class="suggestions-label">Suggestions:</span>
          <div class="suggestions-list">
            <button 
              v-for="(q, idx) in suggestedQuestions" 
              :key="idx" 
              class="suggestion-chip"
              @click="sendChatMessage(q)"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <!-- Chat Messages Container -->
        <div class="chat-messages-container" ref="chatMessagesRef">
          <div 
            v-for="(msg, idx) in chatMessages" 
            :key="idx" 
            class="chat-bubble-wrap" 
            :class="msg.role"
          >
            <div class="chat-bubble">
              <div v-if="msg.role === 'model'" class="chat-bubble-content" v-html="renderMarkdown(msg.content)"></div>
              <div v-else class="chat-bubble-content">{{ msg.content }}</div>
              
              <span class="chat-timestamp">{{ msg.timestamp }}</span>
              <span v-if="msg.isStreaming && !msg.content" class="chat-loader-dots">
                <span></span><span></span><span></span>
              </span>
              <span class="typing-cursor" v-if="msg.isStreaming && msg.content">▋</span>
            </div>
          </div>
        </div>

        <!-- Chat Input Form -->
        <form class="chat-input-form" @submit.prevent="sendChatMessage(null)">
          <input 
            type="text" 
            v-model="chatInput" 
            placeholder="Ask about decisions, actions..." 
            :disabled="isChatStreaming"
            aria-label="Chat input"
          >
          <button type="submit" class="chat-send-btn" :disabled="!chatInput.trim() || isChatStreaming" aria-label="Send message">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </form>
      </div>
    </div>

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
  height: 180px;
  overflow: hidden;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.stream-console.active {
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.08);
}

.console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 6px;
  margin-bottom: 6px;
}

.stream-console h5 {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0;
}

.console-status {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  transition: background-color 0.3s, box-shadow 0.3s;
}

.console-status.streaming {
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: pulse-green 1.5s infinite;
}

@keyframes pulse-green {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.placeholder-text {
  color: var(--text-muted);
  font-style: italic;
}

.typing-cursor {
  display: inline-block;
  color: var(--primary);
  font-weight: bold;
  animation: blink-cursor 0.8s infinite steps(2, start);
  margin-left: 2px;
}

@keyframes blink-cursor {
  to { visibility: hidden; }
}

.console-content {
  font-family: 'Courier New', Courier, monospace;
  font-size: 11px;
  color: var(--text-main);
  line-height: 1.45;
  overflow-y: auto;
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
  text-align: left;
}

.live-progress-overlay {
  background: rgba(15, 23, 42, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--border-radius-md);
  padding: 16px;
  margin-bottom: 24px;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.05);
}

.progress-banner-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
}

.progress-status-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-title {
  font-weight: 600;
  color: var(--text-main);
}

.status-msg-badge {
  background: rgba(99, 102, 241, 0.12);
  color: #a5b4fc;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.spinner-tiny {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(99, 102, 241, 0.15);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin-tiny 1s linear infinite;
}

@keyframes spin-tiny {
  to { transform: rotate(360deg); }
}

.inline-consoles {
  margin-top: 0 !important;
  max-width: 100% !important;
}

.file-dropzone.uploading {
  cursor: default;
  opacity: 0.75;
  pointer-events: none;
}

.upload-spinner-inline {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(99, 102, 241, 0.2);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin-tiny 0.8s linear infinite;
  flex-shrink: 0;
}

/* ---- Mode Toggle ---- */
.mode-toggle-group {
  display: flex;
  gap: 4px;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 3px;
}

.mode-toggle-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-toggle-btn.active {
  background: var(--primary);
  color: white;
}

/* ---- Project List ---- */
.project-list {
  margin-bottom: 20px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.project-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-radius: var(--border-radius-sm);
  border: 1px solid var(--border-color);
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba(255,255,255,0.02);
}

.project-item:hover {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.06);
}

.project-item.active {
  border-color: var(--primary);
  background: rgba(99, 102, 241, 0.1);
}

.project-name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-main);
}

.project-meeting-count {
  font-size: 11.5px;
  color: var(--text-muted);
  background: rgba(255,255,255,0.07);
  padding: 2px 8px;
  border-radius: 10px;
}

/* ---- Add Meeting Section ---- */
.add-meeting-section {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
  margin-top: 4px;
}

.add-meeting-status {
  font-size: 12.5px;
  color: var(--success, #10b981);
  margin-top: 8px;
}

.add-meeting-status.error {
  color: #f87171;
}

/* ---- Text input field ---- */
.text-input-field {
  width: 100%;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 9px 12px;
  font-size: 13.5px;
  color: var(--text-main);
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.text-input-field:focus {
  border-color: rgba(99, 102, 241, 0.5);
}

/* ---- Project Chat Container ---- */
.project-chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.project-chat-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0 14px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 12px;
  flex-shrink: 0;
}

.project-chat-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-main);
}

.project-meeting-badge {
  font-size: 11px;
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.chat-empty-hint {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-md);
  margin-bottom: 16px;
}

/* ---- Messages ---- */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-right: 4px;
  min-height: 0;
}

.chat-starter-hints {
  padding: 20px 0;
  text-align: center;
}

.chat-hint-title {
  font-size: 12.5px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.chat-hint-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.hint-chip {
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.2s;
}

.hint-chip:hover {
  background: rgba(99, 102, 241, 0.2);
}

.chat-message {
  display: flex;
}

.chat-message.user {
  justify-content: flex-end;
}

.chat-message.assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13.5px;
  line-height: 1.6;
  position: relative;
}

.chat-message.user .message-bubble {
  background: var(--primary);
  color: white;
  border-bottom-right-radius: 4px;
}

.chat-message.assistant .message-bubble {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-color);
  color: var(--text-main);
  border-bottom-left-radius: 4px;
}

.message-bubble.streaming {
  border-color: rgba(99, 102, 241, 0.3);
}

.msg-role-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
  opacity: 0.65;
}

.agent-label {
  color: #a5b4fc;
  opacity: 1;
}

.message-text {
  word-break: break-word;
}

/* ---- Chat Input ---- */
.chat-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-top: 12px;
  flex-shrink: 0;
}

.chat-textarea {
  flex: 1;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 10px 14px;
  font-size: 13.5px;
  color: var(--text-main);
  outline: none;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  transition: border-color 0.2s;
}

.chat-textarea:focus {
  border-color: rgba(99, 102, 241, 0.5);
}

.chat-send-btn {
  background: var(--primary);
  border: none;
  color: white;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity 0.2s;
}

.chat-send-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

/* ===========================================================================
   Chatbot Widget & Meeting Assistant Styles
   =========================================================================== */
.chatbot-widget {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.chat-toggle-btn {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary, #6366f1) 0%, #a855f7 100%);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  outline: none;
}

.chat-toggle-btn:hover {
  transform: scale(1.06) translateY(-2px);
  box-shadow: 0 12px 28px rgba(99, 102, 241, 0.45);
}

.chat-toggle-btn:active {
  transform: scale(0.95) translateY(0);
}

.chat-badge-pulse {
  position: absolute;
  top: 1px;
  right: 1px;
  width: 10px;
  height: 10px;
  background-color: #ef4444;
  border-radius: 50%;
  border: 2px solid #0f172a;
  animation: badge-pulse 2s infinite;
}

@keyframes badge-pulse {
  0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
  70% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
  100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}

.chat-window-panel {
  position: absolute;
  bottom: 64px;
  right: 0;
  width: 360px;
  height: 480px;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: chat-slide-in 0.25s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes chat-slide-in {
  from {
    opacity: 0;
    transform: translateY(20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.chat-window-header {
  padding: 12px 16px;
  background: rgba(30, 41, 59, 0.6);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-window-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.active-dot {
  width: 7px;
  height: 7px;
  background-color: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 6px #10b981;
}

.chat-window-title h4 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: #f3f4f6;
  letter-spacing: 0.2px;
}

.chat-clear-btn {
  background: transparent;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  padding: 5px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.chat-clear-btn:hover {
  color: #f3f4f6;
  background-color: rgba(255, 255, 255, 0.06);
}

.chat-suggestions {
  padding: 10px 14px;
  background: rgba(30, 41, 59, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.suggestions-label {
  display: block;
  font-size: 10.5px;
  color: #9ca3af;
  font-weight: 500;
  margin-bottom: 6px;
}

.suggestions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.suggestion-chip {
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #c7d2fe;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.suggestion-chip:hover {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.35);
  transform: translateY(-1px);
}

.chat-messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-bubble-wrap {
  display: flex;
  width: 100%;
}

.chat-bubble-wrap.user {
  justify-content: flex-end;
}

.chat-bubble-wrap.model {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 85%;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 12.5px;
  line-height: 1.55;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-bubble-wrap.user .chat-bubble {
  background: linear-gradient(135deg, var(--primary, #6366f1) 0%, #4f46e5 100%);
  color: white;
  border-bottom-right-radius: 2px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}

.chat-bubble-wrap.model .chat-bubble {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: #e5e7eb;
  border-bottom-left-radius: 2px;
}

.chat-timestamp {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.4);
  align-self: flex-end;
  margin-top: 4px;
}

.chat-bubble-wrap.model .chat-timestamp {
  color: #9ca3af;
}

.chat-bubble-content {
  word-break: break-word;
}

.chat-bubble-content p {
  margin: 0 0 6px 0;
}

.chat-bubble-content p:last-child {
  margin-bottom: 0;
}

.chat-bubble-content strong {
  color: #fff;
  font-weight: 600;
}

.chat-bubble-content code {
  font-family: Menlo, Monaco, Consolas, monospace;
  background: rgba(0, 0, 0, 0.25);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 85%;
  color: #f472b6;
}

.chat-bubble-content pre.code-block {
  margin: 8px 0;
  background: #0f172a;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.chat-bubble-content pre .code-header {
  background: rgba(255, 255, 255, 0.04);
  padding: 3px 8px;
  font-size: 9.5px;
  color: #a5b4fc;
  text-transform: uppercase;
  font-weight: bold;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.chat-bubble-content pre code {
  display: block;
  padding: 8px;
  overflow-x: auto;
  background: transparent;
  color: #e2e8f0;
  font-size: 11px;
}

.chat-bubble-content ul.chat-list, 
.chat-bubble-content ol.chat-list {
  margin: 6px 0;
  padding-left: 18px;
}

.chat-bubble-content li {
  margin-bottom: 3px;
}

.chat-input-form {
  padding: 10px 12px;
  background: rgba(30, 41, 59, 0.5);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  gap: 8px;
  align-items: center;
}

.chat-input-form input {
  flex: 1;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12.5px;
  color: #f3f4f6;
  outline: none;
  transition: all 0.2s;
}

.chat-input-form input:focus {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(255, 255, 255, 0.06);
}

.chat-input-form .chat-send-btn {
  background: var(--primary, #6366f1);
  border: none;
  color: white;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.chat-input-form .chat-send-btn:disabled {
  opacity: 0.5;
  cursor: default;
  background: rgba(255, 255, 255, 0.05);
  color: #6b7280;
}

.chat-loader-dots {
  display: inline-flex;
  gap: 3px;
  padding: 4px 0;
  align-items: center;
}

.chat-loader-dots span {
  width: 5px;
  height: 5px;
  background-color: #9ca3af;
  border-radius: 50%;
  animation: chat-loader-bounce 1.4s infinite ease-in-out both;
}

.chat-loader-dots span:nth-child(1) { animation-delay: -0.32s; }
.chat-loader-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes chat-loader-bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1.0); }
}

/* ---- Light Theme Tweaks ---- */
body.light-theme .chat-window-panel {
  background: rgba(255, 255, 255, 0.85);
  border-color: rgba(0, 0, 0, 0.08);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.1);
}

body.light-theme .chat-window-header {
  background: rgba(241, 245, 249, 0.7);
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

body.light-theme .chat-window-title h4 {
  color: #1e293b;
}

body.light-theme .chat-clear-btn {
  color: #64748b;
}

body.light-theme .chat-clear-btn:hover {
  color: #1e293b;
  background-color: rgba(0, 0, 0, 0.04);
}

body.light-theme .chat-suggestions {
  background: rgba(241, 245, 249, 0.4);
  border-bottom-color: rgba(0, 0, 0, 0.04);
}

body.light-theme .suggestions-label {
  color: #64748b;
}

body.light-theme .suggestion-chip {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.15);
  color: #4f46e5;
}

body.light-theme .suggestion-chip:hover {
  background: rgba(99, 102, 241, 0.14);
  border-color: rgba(99, 102, 241, 0.3);
}

body.light-theme .chat-bubble-wrap.model .chat-bubble {
  background: rgba(0, 0, 0, 0.035);
  border-color: rgba(0, 0, 0, 0.05);
  color: #334155;
}

body.light-theme .chat-bubble-wrap.model .chat-timestamp {
  color: #64748b;
}

body.light-theme .chat-bubble-content strong {
  color: #0f172a;
}

body.light-theme .chat-bubble-content code {
  background: rgba(0, 0, 0, 0.06);
  color: #db2777;
}

body.light-theme .chat-bubble-content pre.code-block {
  background: #f8fafc;
  border-color: rgba(0, 0, 0, 0.05);
}

body.light-theme .chat-bubble-content pre .code-header {
  background: rgba(0, 0, 0, 0.02);
  color: #4f46e5;
  border-bottom-color: rgba(0, 0, 0, 0.04);
}

body.light-theme .chat-bubble-content pre code {
  color: #334155;
}

body.light-theme .chat-input-form {
  background: rgba(241, 245, 249, 0.7);
  border-top-color: rgba(0, 0, 0, 0.06);
}

body.light-theme .chat-input-form input {
  background: rgba(255, 255, 255, 0.85);
  border-color: rgba(0, 0, 0, 0.1);
  color: #1e293b;
}

body.light-theme .chat-input-form input:focus {
  border-color: rgba(99, 102, 241, 0.4);
  background: #ffffff;
}

@media (max-width: 480px) {
  .chat-window-panel {
    width: calc(100vw - 32px);
    height: calc(100vh - 100px);
    right: 0;
  }
}

/* Table styles inside chat bubbles */
.chat-bubble-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 8px;
  overflow: hidden;
}

.chat-bubble-content th, 
.chat-bubble-content td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.chat-bubble-content th {
  background-color: rgba(255, 255, 255, 0.05);
  font-weight: 600;
  color: #a5b4fc;
}

.chat-bubble-content tr:last-child td {
  border-bottom: none;
}

body.light-theme .chat-bubble-content table {
  background: rgba(0, 0, 0, 0.02);
}

body.light-theme .chat-bubble-content th {
  background-color: rgba(0, 0, 0, 0.03);
  color: #4f46e5;
  border-bottom-color: rgba(0, 0, 0, 0.06);
}

body.light-theme .chat-bubble-content td {
  border-bottom-color: rgba(0, 0, 0, 0.04);
}
</style>
