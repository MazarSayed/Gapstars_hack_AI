<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { marked } from 'marked';

// ── Config ────────────────────────────────────────────────────────────────────
const getBase = () => {
  const h = window.location.host;
  return (h.includes('localhost') || h.includes('127.0.0.1'))
    ? 'http://localhost:8000' : window.location.origin;
};
const getWs = () => {
  const p = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const h = window.location.host;
  return (h.includes('localhost') || h.includes('127.0.0.1'))
    ? `${p}//localhost:8000` : `${p}//${h}`;
};

// ── Theme ─────────────────────────────────────────────────────────────────────
const theme = ref('dark');
const toggleTheme = () => {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  document.body.className = theme.value + '-theme';
  localStorage.setItem('theme', theme.value);
};

// ── Navigation ────────────────────────────────────────────────────────────────
const view = ref('overview'); // 'overview' | 'project' | 'meeting'
const activeProjectId = ref(null);
const activeMeetingId = ref(null);
const activeTab = ref('overview');
const meetingFilter = ref('all');

// ── Data ──────────────────────────────────────────────────────────────────────
const sidebarProjects = ref([]);
const projectCache = ref({});
const summaryCache = ref({});
const summaryLoading = ref({});

// ── Sidebar ───────────────────────────────────────────────────────────────────
const expandedIds = ref(new Set());
const showNewProjectForm = ref(false);
const newProjectName = ref('');
const isCreatingProject = ref(false);
const projectNameInputRef = ref(null);

// ── Upload modal ──────────────────────────────────────────────────────────────
const showUpload = ref(false);
const uploadFile = ref(null);
const uploadProjectId = ref('');
const uploadNewName = ref('');
const isDragover = ref(false);
const isUploading = ref(false);
const uploadStatus = ref('');
const uploadError = ref('');
const uploadFileRef = ref(null);


// ── Chat panel ────────────────────────────────────────────────────────────────
const isChatOpen = ref(false);
const chatMessages = ref([
  {
    role: 'model',
    content: "Hi! I'm your Meeting Assistant. You can ask me questions about this meeting's decisions, action items, or anything else in the transcript.",
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
]);
const chatInput = ref('');
const isChatConnecting = ref(false);
const isChatStreaming = ref(false);
const chatScrollRef = ref(null);
const chatTabScrollRef = ref(null);
let chatSocket = null;
let projectSocket = null;

// ── Toast ─────────────────────────────────────────────────────────────────────
const toastMsg = ref('');
const toastVisible = ref(false);
let toastTimer = null;
const showToast = (msg) => {
  toastMsg.value = msg;
  toastVisible.value = true;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastVisible.value = false; }, 2800);
};

// ── Computed ──────────────────────────────────────────────────────────────────
const activeProject = computed(() => projectCache.value[activeProjectId.value] || null);
const activeMeeting = computed(() => {
  if (!activeProject.value || activeMeetingId.value === null) return null;
  return activeProject.value.meetings?.find(m => m.id === activeMeetingId.value) || null;
});

// ── Followup & Jira ───────────────────────────────────────────────────────────
const isGeneratingFollowup = ref(false);

const groupedJiraTasks = computed(() => {
  const tasks = activeMeeting.value?.followup?.jira_tasks || [];
  const groups = {
    'Engineering': [],
    'Design': [],
    'Marketing': [],
    'Product': [],
    'General': []
  };
  tasks.forEach(t => {
    const comp = t.component || 'General';
    if (!groups[comp]) groups[comp] = [];
    groups[comp].push(t);
  });
  Object.keys(groups).forEach(k => {
    if (groups[k].length === 0 && k !== 'Engineering' && k !== 'Design' && k !== 'Product') {
      delete groups[k];
    }
  });
  return groups;
});

const generateFollowup = async () => {
  if (!activeProjectId.value || !activeMeetingId.value || isGeneratingFollowup.value) return;
  isGeneratingFollowup.value = true;
  try {
    const res = await fetch(`${getBase()}/project/${activeProjectId.value}/meeting/${activeMeetingId.value}/followup`, {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      if (activeMeeting.value) {
        activeMeeting.value.followup = data.followup;
      }
      showToast('Follow-up and Jira tasks generated successfully!');
    } else {
      const err = await res.json().catch(() => ({ detail: 'Failed to generate' }));
      showToast(`Error: ${err.detail}`);
    }
  } catch (e) {
    showToast(`Error: ${e.message}`);
  } finally {
    isGeneratingFollowup.value = false;
  }
};

const copyAllJira = () => {
  const tasks = activeMeeting.value?.followup?.jira_tasks || [];
  if (!tasks.length) return;
  const md = tasks.map(t => {
    return `### [JIRA] ${t.title}\n- **Component:** ${t.component}\n- **Assignee:** ${t.assignee}\n- **Priority:** ${t.priority}\n- **Due Date:** ${t.due_date}\n\n**Description:**\n${t.description}`;
  }).join('\n\n---\n\n');
  navigator.clipboard.writeText(md);
  showToast('Copied all Jira tasks to clipboard');
};

const copyJiraTask = (t) => {
  const md = `### [JIRA] ${t.title}\n- **Component:** ${t.component}\n- **Assignee:** ${t.assignee}\n- **Priority:** ${t.priority}\n- **Due Date:** ${t.due_date}\n\n**Description:**\n${t.description}`;
  navigator.clipboard.writeText(md);
  showToast(`Copied "${t.title}" to clipboard`);
};

const copyEmail = () => {
  const body = activeMeeting.value?.followup?.email_body || '';
  if (!body) return;
  navigator.clipboard.writeText(body);
  showToast('Copied email body to clipboard');
};
const totalMeetings = computed(() =>
  sidebarProjects.value.reduce((s, p) => s + p.meeting_count, 0)
);
const filteredActions = computed(() => {
  const items = activeMeeting.value?.actions?.action_items || [];
  if (meetingFilter.value === 'all') return items;
  if (meetingFilter.value === 'needs_clarification')
    return items.filter(i => i.status === 'Needs clarification');
  return items.filter(i => i.priority === meetingFilter.value);
});
const activeProjectInList = computed(() =>
  sidebarProjects.value.find(p => p.project_id === activeProjectId.value)
);
const maxMeetingCount = computed(() =>
  Math.max(...sidebarProjects.value.map(p => p.meeting_count), 1)
);

// ── Fetch helpers ─────────────────────────────────────────────────────────────
const fetchProjects = async () => {
  try {
    const res = await fetch(`${getBase()}/project`);
    if (res.ok) sidebarProjects.value = await res.json();
  } catch {}
};

const fetchProjectDetail = async (pid) => {
  try {
    const res = await fetch(`${getBase()}/project/${pid}`);
    if (res.ok) projectCache.value[pid] = await res.json();
  } catch {}
};

const fetchProjectSummary = async (pid) => {
  if (summaryLoading.value[pid]) return;
  summaryLoading.value[pid] = true;
  try {
    const res = await fetch(`${getBase()}/project/${pid}/summary`);
    if (res.ok) summaryCache.value[pid] = await res.json();
  } catch {} finally {
    summaryLoading.value[pid] = false;
  }
};

// ── Navigation ────────────────────────────────────────────────────────────────
const goOverview = () => {
  view.value = 'overview';
  activeProjectId.value = null;
  activeMeetingId.value = null;
  closeChat();
};

const selectProject = async (pid) => {
  activeProjectId.value = pid;
  activeMeetingId.value = null;
  view.value = 'project';
  expandedIds.value = new Set([...expandedIds.value, pid]);
  chatMessages.value = [];
  connectProjectChat(pid);
  if (!projectCache.value[pid]) await fetchProjectDetail(pid);
  if (!summaryCache.value[pid]) fetchProjectSummary(pid);
};

const selectMeeting = async (pid, mid) => {
  if (activeProjectId.value !== pid) {
    activeProjectId.value = pid;
    if (!projectCache.value[pid]) await fetchProjectDetail(pid);
  }
  activeMeetingId.value = mid;
  view.value = 'meeting';
  activeTab.value = 'overview';
  meetingFilter.value = 'all';
  closeChat();
};

const toggleExpand = async (pid) => {
  const next = new Set(expandedIds.value);
  if (next.has(pid)) { next.delete(pid); } else {
    next.add(pid);
    if (!projectCache.value[pid]) fetchProjectDetail(pid);
  }
  expandedIds.value = next;
};

// ── Create project ────────────────────────────────────────────────────────────
const createProject = async () => {
  const name = newProjectName.value.trim();
  if (!name) return;
  isCreatingProject.value = true;
  try {
    const res = await fetch(`${getBase()}/project`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      const p = await res.json();
      sidebarProjects.value.push({ project_id: p.project_id, name: p.name, meeting_count: 0 });
      newProjectName.value = '';
      showNewProjectForm.value = false;
      showToast(`Project "${p.name}" created`);
    }
  } finally { isCreatingProject.value = false; }
};

// ── Upload & Streaming State ──────────────────────────────────────────────────
const isStreaming = ref(false);
const currentStep = ref(1); // 1: Extracting transcript, 2: Streaming Summary/Actions, 3: Drafting Followup, 4: Saving, 5: Done
const streamLogs = ref([]);
const streamSummaryRaw = ref('');
const streamActionsRaw = ref('');
const streamFollowupRaw = ref('');

// Extracted variables via partial JSON parser
const liveConciseSummary = ref('');
const liveActionItems = ref([]);
const liveEmailBody = ref('');

const addStreamLog = (msg) => {
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  streamLogs.value.push({ time, message: msg });
  nextTick(() => {
    const el = document.getElementById('streaming-logs');
    if (el) el.scrollTop = el.scrollHeight;
  });
};

const updateLiveSummary = (accumulated) => {
  const match = accumulated.match(/"concise_summary"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (match) {
    try {
      liveConciseSummary.value = JSON.parse('"' + match[1].replace(/([^"\\])$/, '$1"') + '"');
    } catch {
      liveConciseSummary.value = match[1];
    }
  }
};

const updateLiveActions = (accumulated) => {
  const list = [];
  const match = accumulated.match(/"action_items"\s*:\s*\[([\s\S]*?)\]/);
  if (match) {
    try {
      const items = JSON.parse('[' + match[1] + ']');
      liveActionItems.value = items;
      return;
    } catch {
      const objRegex = /\{[^{}]*?\}/g;
      let m;
      while ((m = objRegex.exec(match[1])) !== null) {
        try {
          list.push(JSON.parse(m[0]));
        } catch {}
      }
    }
  } else {
    const arrayStart = accumulated.indexOf('"action_items"');
    if (arrayStart !== -1) {
      const partialArray = accumulated.substring(arrayStart);
      const objRegex = /\{[^{}]*?\}/g;
      let m;
      while ((m = objRegex.exec(partialArray)) !== null) {
        try {
          list.push(JSON.parse(m[0]));
        } catch {}
      }
    }
  }
  liveActionItems.value = list;
};

const updateLiveFollowup = (accumulated) => {
  const match = accumulated.match(/"email_body"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (match) {
    try {
      liveEmailBody.value = JSON.parse('"' + match[1].replace(/([^"\\])$/, '$1"') + '"');
    } catch {
      liveEmailBody.value = match[1];
    }
  }
};

// ── Upload ────────────────────────────────────────────────────────────────────
const openUpload = (pid = '') => {
  uploadFile.value = null;
  uploadProjectId.value = pid || sidebarProjects.value[0]?.project_id || '__new__';
  uploadNewName.value = '';
  uploadStatus.value = '';
  uploadError.value = '';
  isDragover.value = false;
  showUpload.value = true;
};

const closeUpload = () => { if (!isUploading.value) showUpload.value = false; };

const handleUploadDrop = (e) => {
  e.preventDefault();
  isDragover.value = false;
  const f = e.dataTransfer.files[0];
  if (f) uploadFile.value = f;
};

const ACCEPTED_EXTS = new Set(['txt','docx','pdf','mp3','wav','ogg','m4a','aac','mp4','mov','avi','webm']);

const doUpload = async () => {
  if (!uploadFile.value) return;
  let pid = uploadProjectId.value;

  if (pid === '__new__') {
    const name = uploadNewName.value.trim();
    if (!name) { uploadError.value = 'Enter a project name.'; return; }
    const r = await fetch(`${getBase()}/project`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) { uploadError.value = 'Failed to create project.'; return; }
    const p = await r.json();
    sidebarProjects.value.push({ project_id: p.project_id, name: p.name, meeting_count: 0 });
    pid = p.project_id;
  }

  if (!pid) { uploadError.value = 'Select or create a project first.'; return; }

  const ext = uploadFile.value.name.split('.').pop().toLowerCase();
  if (!ACCEPTED_EXTS.has(ext)) { uploadError.value = `Unsupported file type ".${ext}".`; return; }

  isUploading.value = true;
  isStreaming.value = true;
  currentStep.value = 1;
  streamLogs.value = [];
  streamSummaryRaw.value = '';
  streamActionsRaw.value = '';
  streamFollowupRaw.value = '';
  liveConciseSummary.value = '';
  liveActionItems.value = [];
  liveEmailBody.value = '';
  uploadError.value = '';

  addStreamLog(`Extracting transcript from ${uploadFile.value.name}...`);

  const form = new FormData();
  form.append('file', uploadFile.value);

  let transcript = '';
  let filename = uploadFile.value.name;

  try {
    const res = await fetch(`${getBase()}/upload/transcript`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to extract transcript' }));
      throw new Error(err.detail || 'Transcript extraction failed.');
    }
    const transcriptData = await res.json();
    transcript = transcriptData.transcript;
    filename = transcriptData.filename || filename;
  } catch (e) {
    uploadError.value = e.message;
    isUploading.value = false;
    isStreaming.value = false;
    return;
  }

  addStreamLog('Transcript extracted successfully.');
  currentStep.value = 2;
  addStreamLog('Connecting to AI analyzer stream...');

  let ws = null;
  try {
    const p = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = (host.includes('localhost') || host.includes('127.0.0.1'))
      ? `${p}//localhost:8000/ws/summarize`
      : `${p}//${host}/ws/summarize`;

    ws = new WebSocket(wsUrl);
  } catch (e) {
    uploadError.value = `WebSocket connection failed: ${e.message}`;
    isUploading.value = false;
    isStreaming.value = false;
    return;
  }

  ws.onopen = () => {
    addStreamLog('Connected to AI streaming service. Starting analysis...');
    ws.send(JSON.stringify({
      transcript,
      language: 'English',
      project_id: pid,
      filename
    }));
  };

  ws.onmessage = async (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'status') {
      addStreamLog(msg.message);
      if (msg.message.includes('Drafting')) {
        currentStep.value = 3;
      } else if (msg.message.includes('Saving')) {
        currentStep.value = 4;
      }
    } else if (msg.type === 'summary_chunk') {
      streamSummaryRaw.value += msg.chunk;
      updateLiveSummary(streamSummaryRaw.value);
      nextTick(() => {
        const el = document.getElementById('live-summary-body');
        if (el) el.scrollTop = el.scrollHeight;
      });
    } else if (msg.type === 'actions_chunk') {
      streamActionsRaw.value += msg.chunk;
      updateLiveActions(streamActionsRaw.value);
      nextTick(() => {
        const el = document.getElementById('live-actions-body');
        if (el) el.scrollTop = el.scrollHeight;
      });
    } else if (msg.type === 'followup_chunk') {
      streamFollowupRaw.value += msg.chunk;
      updateLiveFollowup(streamFollowupRaw.value);
      nextTick(() => {
        const el = document.getElementById('live-followup-body');
        if (el) el.scrollTop = el.scrollHeight;
      });
    } else if (msg.type === 'summary_done') {
      addStreamLog('Summary generated completely.');
    } else if (msg.type === 'actions_done') {
      addStreamLog('Action items extracted completely.');
    } else if (msg.type === 'followup_done') {
      addStreamLog('Follow-up drafts written completely.');
    } else if (msg.type === 'complete') {
      addStreamLog('Meeting analysis completed and saved successfully.');
      currentStep.value = 5;
      ws.close();

      setTimeout(async () => {
        await fetchProjects();
        delete projectCache.value[pid];
        delete summaryCache.value[pid];
        showUpload.value = false;
        isUploading.value = false;
        isStreaming.value = false;
        showToast(`"${filename}" added`);
        if (msg.meeting_id) {
          await selectMeeting(pid, msg.meeting_id);
        } else {
          await selectProject(pid);
        }
      }, 1000);
    } else if (msg.type === 'error') {
      uploadError.value = msg.message;
      addStreamLog(`Error: ${msg.message}`);
      isUploading.value = false;
      isStreaming.value = false;
      ws.close();
    }
  };

  ws.onerror = (err) => {
    uploadError.value = 'WebSocket connection error occurred.';
    addStreamLog('Error: WebSocket connection failed.');
    isUploading.value = false;
    isStreaming.value = false;
  };

  ws.onclose = () => {
    addStreamLog('Connection closed.');
  };
};

// ── Chat ──────────────────────────────────────────────────────────────────────
const openChat = () => {
  isChatOpen.value = true;
  if (!projectSocket || projectSocket.readyState !== WebSocket.OPEN) {
    connectProjectChat(activeProjectId.value);
  }
};

const closeChat = () => {
  isChatOpen.value = false;
  if (projectSocket) { projectSocket.close(); projectSocket = null; }
  chatMessages.value = [];
};

const connectProjectChat = (pid) => {
  if (projectSocket) { projectSocket.close(); projectSocket = null; }
  const ws = new WebSocket(`${getWs()}/ws/project/${pid}/chat`);
  projectSocket = ws;
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'chunk') {
      const last = chatMessages.value[chatMessages.value.length - 1];
      if (last && last.role === 'assistant' && last.streaming) {
        last.text += data.chunk;
        scrollChat();
      }
    }
    if (data.type === 'done') {
      const last = chatMessages.value[chatMessages.value.length - 1];
      if (last && last.streaming) last.streaming = false;
      isChatStreaming.value = false;
    }
    if (data.type === 'error') {
      isChatStreaming.value = false;
      chatMessages.value.push({ role: 'assistant', text: `Error: ${data.message}`, streaming: false });
    }
  };

  ws.onerror = () => {
    isChatStreaming.value = false;
  };
};

const sendChat = () => {
  const q = chatInput.value.trim();
  if (!q || isChatStreaming.value || !projectSocket || projectSocket.readyState !== WebSocket.OPEN) return;
  chatMessages.value.push({ role: 'user', text: q });
  chatMessages.value.push({ role: 'assistant', text: '', streaming: true });
  isChatStreaming.value = true;
  chatInput.value = '';
  scrollChat();
  projectSocket.send(JSON.stringify({ question: q }));
};

const handleChatKey = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
};

const scrollChat = () => {
  nextTick(() => {
    if (chatScrollRef.value) chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight;
    if (chatTabScrollRef.value) chatTabScrollRef.value.scrollTop = chatTabScrollRef.value.scrollHeight;
  });
};

const renderMarkdown = (text) => {
  if (!text) return '';
  return marked.parse(text, { breaks: true });
};

// ── Demo Visualizer State ──────────────────────────────────────────────────────
const demoSelectedNode = ref('input'); // 'input' | 'translator' | 'coordinator' | 'summarizer' | 'actions' | 'websocket' | 'frontend'
const demoSimulationActive = ref(false);
const demoSimulationStep = ref(0); // 0: idle, 1: input scanning, 2: translator check, 3: coordinator dispatch, 4: parallel execution, 5: ws streaming, 6: done
const demoLogs = ref([]);
const demoSummaryText = ref('');
const demoActionsList = ref([]);
const demoInspectorTab = ref('prompt_summarizer'); // 'prompt_summarizer' | 'prompt_action' | 'pydantic' | 'fastapi'
let demoInterval = null;

// Mock Data for streaming simulation
const mockTranscript = `Sarah: We need to finalize the landing page designs by Friday.
Dave: I can take care of the landing page mockups.
Sarah: Great, Dave. Also, we need to schedule user testing for next week. Let's aim for Tuesday, and make sure we have at least 5 participants.
John: I'll recruit the users and set up the testing schedule by Monday.`;

const mockSummaryChunks = [
  "The team ", "discussed ", "finalizing the landing ", "page designs by Friday ", "and scheduling user ", 
  "testing for next week. ", "Dave will own ", "the landing page designs, ", "and John will recruit ", 
  "5 participants for user ", "testing and schedule ", "the sessions by Monday."
];

const mockActions = [
  { action: "Finalize landing page mockups", owner: "Dave", due_date: "Friday", priority: "High", status: "Clear" },
  { action: "Recruit 5 user testing participants & schedule sessions", owner: "John", due_date: "Monday", priority: "High", status: "Clear" }
];

const goDemo = () => {
  view.value = 'demo';
  activeProjectId.value = null;
  activeMeetingId.value = null;
  closeChat();
  resetDemo();
};

const resetDemo = () => {
  if (demoInterval) {
    clearInterval(demoInterval);
    demoInterval = null;
  }
  demoSimulationActive.value = false;
  demoSimulationStep.value = 0;
  demoSelectedNode.value = 'input';
  demoLogs.value = [];
  demoSummaryText.value = '';
  demoActionsList.value = [];
  addDemoLog("System idle. Click 'Start Simulation' to begin.");
};

const addDemoLog = (msg) => {
  const time = new Date().toLocaleTimeString([], { hour12: false });
  demoLogs.value.push({ time, message: msg });
  // Scroll demo terminal to bottom
  nextTick(() => {
    const el = document.getElementById('demo-terminal-body');
    if (el) el.scrollTop = el.scrollHeight;
  });
};

const startDemoSimulation = () => {
  resetDemo();
  demoSimulationActive.value = true;
  runDemoStep();
};

const runDemoStep = () => {
  if (!demoSimulationActive.value) return;

  // Step 1: Input transcript uploaded
  demoSimulationStep.value = 1;
  demoSelectedNode.value = 'input';
  addDemoLog("INFO: Initializing analysis workflow...");
  addDemoLog("INFO: Reading input transcript (138 characters)");
  
  // Step 2: Language Check after 1.5s
  setTimeout(() => {
    if (!demoSimulationActive.value) return;
    demoSimulationStep.value = 2;
    demoSelectedNode.value = 'translator';
    addDemoLog("INFO: Language detector triggered");
    addDemoLog("INFO: Language detected: 'English'. Skipping translation agent.");
    
    // Step 3: Parallel Dispatcher after 1.5s
    setTimeout(() => {
      if (!demoSimulationActive.value) return;
      demoSimulationStep.value = 3;
      demoSelectedNode.value = 'coordinator';
      addDemoLog("WS CONNECTING: ws://localhost:8000/ws/summarize");
      addDemoLog("WS CONNECTED: Session 4f9e-a89c initialized");
      addDemoLog("INFO: Invoking parallel agents via asyncio.gather()");
      
      // Step 4: Parallel Agent Execution after 1.8s
      setTimeout(() => {
        if (!demoSimulationActive.value) return;
        demoSimulationStep.value = 4;
        demoSelectedNode.value = 'summarizer'; // Highlight summarizer
        demoInspectorTab.value = 'prompt_summarizer';
        addDemoLog("AGENT 1 (Summarizer): Prompting Gemini-1.5-Flash...");
        addDemoLog("AGENT 2 (Action Item): Prompting Gemini-1.5-Flash...");
        
        // Parallel prompt logging
        setTimeout(() => {
          if (!demoSimulationActive.value) return;
          demoSelectedNode.value = 'actions'; // Highlight action agent
          demoInspectorTab.value = 'prompt_action';
          addDemoLog("AGENT 1: Gemini response received. Parsing JSON.");
          addDemoLog("AGENT 2: Gemini response received. Parsing JSON.");
          
          // Step 5: WS Streaming after 1.5s
          setTimeout(() => {
            if (!demoSimulationActive.value) return;
            demoSimulationStep.value = 5;
            demoSelectedNode.value = 'websocket';
            addDemoLog("WS SEND: Starting JSON stream chunks serialization");
            
            let chunkIdx = 0;
            demoInterval = setInterval(() => {
              if (!demoSimulationActive.value) {
                clearInterval(demoInterval);
                return;
              }
              
              if (chunkIdx < mockSummaryChunks.length) {
                const chunk = mockSummaryChunks[chunkIdx];
                demoSummaryText.value += chunk;
                addDemoLog(`WS RECV (summary_chunk): "${chunk}"`);
                
                // Gradually feed action items
                if (chunkIdx === 4) {
                  demoActionsList.value.push(mockActions[0]);
                  addDemoLog(`WS RECV (actions_done): Added high priority action for ${mockActions[0].owner}`);
                }
                if (chunkIdx === 9) {
                  demoActionsList.value.push(mockActions[1]);
                  addDemoLog(`WS RECV (actions_done): Added action for ${mockActions[1].owner}`);
                }
                
                chunkIdx++;
              } else {
                clearInterval(demoInterval);
                demoInterval = null;
                
                // Step 6: Done
                demoSimulationStep.value = 6;
                demoSelectedNode.value = 'frontend';
                addDemoLog("WS RECV: { type: 'complete', status: 'saved', id: 'meeting_demo_99' }");
                addDemoLog("INFO: Pipeline execution completed successfully in 8.4s");
                demoSimulationActive.value = false;
              }
            }, 600); // stream a chunk every 600ms
            
          }, 1500);
        }, 1200);
      }, 1500);
    }, 1500);
  }, 1500);
};

// ── Watchers ──────────────────────────────────────────────────────────────────
watch(activeTab, (newTab) => {
  if (newTab === 'chat') {
    chatMessages.value = [];
    connectProjectChat(activeProjectId.value);
  } else {
    if (!isChatOpen.value && projectSocket) {
      projectSocket.close();
      projectSocket = null;
    }
  }
});

watch(showNewProjectForm, (isOpen) => {
  if (isOpen) {
    nextTick(() => {
      projectNameInputRef.value?.focus();
    });
  }
});

// ── Mount ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  const saved = localStorage.getItem('theme') || 'dark';
  theme.value = saved;
  document.body.className = saved + '-theme';
  fetchProjects();
});
</script>

<template>
  <div class="app-root" :class="theme === 'light' ? 'light-theme' : 'dark-theme'">
    <div class="glow-bg"></div>

    <!-- ══ Upload Modal ══ -->
    <Teleport to="body">
      <div v-if="showUpload" class="modal-backdrop" @click.self="closeUpload">
        <div :class="isStreaming ? 'streaming-modal-card' : 'modal-card'">
          <template v-if="!isStreaming">
            <div class="modal-header">
              <h3>Add Meeting</h3>
              <button class="modal-close-btn" @click="closeUpload" :disabled="isUploading">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>

            <div class="modal-dropzone"
              :class="{ dragover: isDragover, 'has-file': !!uploadFile }"
              @dragover.prevent="isDragover = true"
              @dragleave="isDragover = false"
              @drop="handleUploadDrop"
              @click="!uploadFile && uploadFileRef?.click()"
            >
              <input type="file" ref="uploadFileRef" class="hidden-input"
                accept=".txt,.docx,.pdf,.mp3,.wav,.ogg,.m4a,.aac,.mp4,.mov,.avi,.webm"
                @change="e => { if (e.target.files[0]) uploadFile = e.target.files[0]; }" />
              <div v-if="!uploadFile" class="dropzone-content">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                <p><strong>Drop file here</strong> or click to browse</p>
                <p class="file-hint">TXT · DOCX · PDF · MP3 · MP4 and more</p>
              </div>
              <div v-else class="file-selected-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                <span class="file-name">{{ uploadFile.name }}</span>
                <button class="remove-file-btn" @click.stop="uploadFile = null">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
              </div>
            </div>

            <div class="modal-field">
              <label>Assign to Project</label>
              <select v-model="uploadProjectId" :disabled="isUploading">
                <option v-for="p in sidebarProjects" :key="p.project_id" :value="p.project_id">
                  {{ p.name }} ({{ p.meeting_count }} meetings)
                </option>
                <option value="__new__">+ Create new project…</option>
              </select>
            </div>

            <div v-if="uploadProjectId === '__new__'" class="modal-field">
              <label>New Project Name</label>
              <input class="text-input-field" v-model="uploadNewName"
                placeholder="e.g. Q3 Product Planning" :disabled="isUploading" />
            </div>

            <p v-if="uploadStatus" class="upload-status-msg">{{ uploadStatus }}</p>
            <p v-if="uploadError" class="upload-error-msg">{{ uploadError }}</p>

            <div class="modal-actions">
              <button class="secondary-btn" @click="closeUpload" :disabled="isUploading">Cancel</button>
              <button class="primary-btn upload-btn-modal"
                :disabled="isUploading || !uploadFile" @click="doUpload">
                <span v-if="isUploading" class="spinner-tiny"></span>
                {{ isUploading ? 'Processing…' : 'Upload & Analyze' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="streaming-header">
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spinner-tiny" style="margin-right: 5px;"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg>
                Live AI Analysis
                <span class="streaming-header-badge">
                  Processing
                </span>
              </h3>
              <span class="file-name" style="font-size: 13.5px; opacity: 0.85;">{{ uploadFile?.name }}</span>
            </div>

            <div class="streaming-stepper">
              <div class="streaming-step" :class="{ active: currentStep === 1, completed: currentStep > 1 }">
                <span class="streaming-step-icon">1</span>
                <span>Extracting Transcript</span>
              </div>
              <div class="streaming-step" :class="{ active: currentStep === 2, completed: currentStep > 2 }">
                <span class="streaming-step-icon">2</span>
                <span>Streaming Analysis</span>
              </div>
              <div class="streaming-step" :class="{ active: currentStep === 3, completed: currentStep > 3 }">
                <span class="streaming-step-icon">3</span>
                <span>Drafting Follow-ups</span>
              </div>
              <div class="streaming-step" :class="{ active: currentStep === 4, completed: currentStep > 4 }">
                <span class="streaming-step-icon">4</span>
                <span>Saving Meeting</span>
              </div>
            </div>

            <div class="streaming-panels-grid">
              <!-- Panel 1: Live Summary -->
              <div class="streaming-panel-card" :class="{ active: currentStep === 2 }">
                <div class="streaming-panel-header">
                  <h4>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    Live Summary
                  </h4>
                  <span class="streaming-panel-status" :class="currentStep === 2 ? 'streaming' : (currentStep > 2 ? 'done' : 'waiting')">
                    {{ currentStep === 2 ? 'Streaming' : (currentStep > 2 ? 'Done' : 'Waiting') }}
                  </span>
                </div>
                <div class="streaming-panel-body" id="live-summary-body" :class="{ streaming: currentStep === 2 }">
                  <div v-if="!liveConciseSummary && currentStep <= 2" class="streaming-panel-card-empty">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                    <span>Awaiting agent response...</span>
                  </div>
                  <div v-else>
                    <p>{{ liveConciseSummary }}<span v-if="currentStep === 2" class="typing-cursor">▋</span></p>
                  </div>
                </div>
              </div>

              <!-- Panel 2: Live Action Items -->
              <div class="streaming-panel-card" :class="{ active: currentStep === 2 }">
                <div class="streaming-panel-header">
                  <h4>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"></path><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                    Live Action Items
                  </h4>
                  <span class="streaming-panel-status" :class="currentStep === 2 ? 'streaming' : (currentStep > 2 ? 'done' : 'waiting')">
                    {{ currentStep === 2 ? 'Streaming' : (currentStep > 2 ? 'Done' : 'Waiting') }}
                  </span>
                </div>
                <div class="streaming-panel-body" id="live-actions-body" :class="{ streaming: currentStep === 2 }">
                  <div v-if="!liveActionItems.length && currentStep <= 2" class="streaming-panel-card-empty">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                    <span>Awaiting agent response...</span>
                  </div>
                  <div v-else class="streaming-action-list">
                    <div v-for="(item, idx) in liveActionItems" :key="idx" class="streaming-action-list-item">
                      <div class="streaming-action-title">
                        {{ item.action }}
                        <span v-if="item.priority" class="streaming-action-badge" :class="'prio-' + item.priority.toLowerCase()">
                          {{ item.priority }}
                        </span>
                      </div>
                      <div class="streaming-action-meta">
                        <span v-if="item.owner">Owner: {{ item.owner }}</span>
                        <span v-if="item.due_date">Due: {{ item.due_date }}</span>
                      </div>
                    </div>
                    <span v-if="currentStep === 2" class="typing-cursor" style="margin-top: 10px;">▋</span>
                  </div>
                </div>
              </div>

              <!-- Panel 3: Live Follow-up Email -->
              <div class="streaming-panel-card" :class="{ active: currentStep === 3 }">
                <div class="streaming-panel-header">
                  <h4>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
                    Live Follow-up Email
                  </h4>
                  <span class="streaming-panel-status" :class="currentStep === 3 ? 'streaming' : (currentStep > 3 ? 'done' : 'waiting')">
                    {{ currentStep === 3 ? 'Streaming' : (currentStep > 3 ? 'Done' : 'Waiting') }}
                  </span>
                </div>
                <div class="streaming-panel-body" id="live-followup-body" :class="{ streaming: currentStep === 3 }" style="font-family: monospace; white-space: pre-wrap;">
                  <div v-if="!liveEmailBody && currentStep <= 3" class="streaming-panel-card-empty">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                    <span>Awaiting agent response...</span>
                  </div>
                  <div v-else>
                    {{ liveEmailBody }}<span v-if="currentStep === 3" class="typing-cursor">▋</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="streaming-terminal-output" id="streaming-logs">
              <div v-for="(log, idx) in streamLogs" :key="idx" class="terminal-line">
                <span class="terminal-timestamp">[{{ log.time }}]</span>
                <span class="terminal-text">{{ log.message }}</span>
              </div>
            </div>

            <p v-if="uploadError" class="upload-error-msg" style="margin-top: 10px; margin-bottom: 0;">{{ uploadError }}</p>

            <div v-if="uploadError" class="modal-actions" style="margin-top: 15px; padding-top: 0; border: none; justify-content: flex-end; gap: 10px;">
              <button class="secondary-btn" @click="isStreaming = false; isUploading = false; uploadError = '';">Back</button>
              <button class="primary-btn" @click="doUpload">Retry</button>
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- ══ Create Project Modal ══ -->
    <Teleport to="body">
      <div v-if="showNewProjectForm" class="modal-backdrop" @click.self="showNewProjectForm = false">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Create New Project</h3>
            <button class="modal-close-btn" @click="showNewProjectForm = false" :disabled="isCreatingProject">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
          
          <div class="modal-body-content">
            <p class="modal-desc">Enter a name for your new project to start organizing meetings, transcripts, and action items.</p>
            <div class="text-input-group">
              <label for="new-project-name-input">Project Name</label>
              <input 
                id="new-project-name-input"
                ref="projectNameInputRef"
                class="text-input-field" 
                v-model="newProjectName"
                placeholder="e.g., Q3 Cloud Migration"
                :disabled="isCreatingProject"
                @keydown.enter="createProject"
                @keydown.esc="showNewProjectForm = false"
              />
            </div>
          </div>

          <div class="modal-footer-actions">
            <button class="secondary-btn" @click="showNewProjectForm = false" :disabled="isCreatingProject">Cancel</button>
            <button class="primary-btn" 
              :disabled="isCreatingProject || !newProjectName.trim()"
              @click="createProject">
              <span v-if="isCreatingProject">Creating...</span>
              <span v-else>Create Project</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ App Shell ══ -->
    <div class="app-shell">

      <!-- Sidebar -->
      <aside class="sidebar">
        <div class="sidebar-logo">
          <div class="logo-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="url(#lg)"/>
              <defs><linearGradient id="lg" x1="2" y1="2" x2="22" y2="22"><stop stop-color="#818CF8"/><stop offset="1" stop-color="#C084FC"/></linearGradient></defs>
            </svg>
          </div>
          <span class="logo-text">Meeting<span class="logo-accent">AI</span></span>
        </div>

        <nav class="sidebar-nav">
          <button class="nav-item" :class="{ active: view === 'overview' }" @click="goOverview">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
            Overview
          </button>

          <div class="nav-section-label">Projects</div>

          <div v-if="!sidebarProjects.length" class="sidebar-no-projects">
            No projects yet
          </div>

          <div v-for="proj in sidebarProjects" :key="proj.project_id" class="project-tree-item">
            <div class="project-tree-row"
              :class="{ active: activeProjectId === proj.project_id && view !== 'overview' }"
              @click="selectProject(proj.project_id)"
            >
              <button class="expand-btn" @click.stop="toggleExpand(proj.project_id)" :title="expandedIds.has(proj.project_id) ? 'Collapse' : 'Expand'">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"
                  :style="{ transform: expandedIds.has(proj.project_id) ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.18s' }">
                  <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
              </button>
              <svg class="tree-folder-icon" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
              <span class="tree-project-name">{{ proj.name }}</span>
              <span class="tree-count-badge">{{ proj.meeting_count }}</span>
            </div>

            <div v-if="expandedIds.has(proj.project_id)" class="meeting-subtree">
              <div v-if="!projectCache[proj.project_id]" class="subtree-loading">
                <span class="spinner-tiny"></span>
              </div>
              <div v-else-if="!projectCache[proj.project_id].meetings?.length" class="subtree-empty">
                No meetings
              </div>
              <div v-else
                v-for="mtg in projectCache[proj.project_id].meetings" :key="mtg.id"
                class="meeting-subtree-row"
                :class="{ active: activeMeetingId === mtg.id }"
                @click="selectMeeting(proj.project_id, mtg.id)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                <span>{{ mtg.name || 'Untitled' }}</span>
              </div>
            </div>
          </div>
        </nav>

        <div class="sidebar-footer">
          <button class="new-project-btn" @click="showNewProjectForm = true">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            New Project
          </button>
        </div>
      </aside>

      <!-- Main wrapper -->
      <div class="main-wrapper">

        <!-- Top bar -->
        <header class="top-bar">
          <nav class="breadcrumb">
            <button class="bc-link" @click="goOverview">Home</button>
            <template v-if="view !== 'overview' && view !== 'demo'">
              <span class="bc-sep">/</span>
              <button class="bc-link" @click="selectProject(activeProjectId)">
                {{ activeProjectInList?.name || '…' }}
              </button>
            </template>
            <template v-if="view === 'meeting'">
              <span class="bc-sep">/</span>
              <span class="bc-current">{{ activeMeeting?.name || 'Meeting' }}</span>
            </template>
            <template v-if="view === 'demo'">
              <span class="bc-sep">/</span>
              <span class="bc-current">System Demo</span>
            </template>
          </nav>

          <div class="top-bar-actions">
            <button class="demo-btn" :class="{ active: view === 'demo' }" @click="goDemo">
              <span class="demo-pulse-dot"></span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 4px;"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
              <span>Inner Workings (Demo)</span>
            </button>
            <button class="add-meeting-btn" @click="openUpload(activeProjectId || '')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              Add Meeting
            </button>
            <button class="theme-toggle" @click="toggleTheme">
              <svg v-if="theme === 'light'" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
              <svg v-else width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
            </button>
          </div>
        </header>

        <!-- Content -->
        <main class="content-area">

          <!-- ── System Demo ── -->
          <div v-if="view === 'demo'" class="view-demo animate-fade-in">
            <div class="view-header project-view-header">
              <div>
                <h1>System Architecture & Flow Demo</h1>
                <p class="view-subtitle">Visualize how parallel agents process transcripts, stream JSON via FastAPI WebSockets, and update the UI in real-time.</p>
              </div>
              <div class="project-header-btns">
                <button class="primary-btn" @click="startDemoSimulation" :disabled="demoSimulationActive" style="width: auto;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                  {{ demoSimulationStep > 0 && !demoSimulationActive ? 'Re-run Demo' : 'Start Simulation' }}
                </button>
                <button class="secondary-btn" @click="resetDemo">
                  Reset
                </button>
              </div>
            </div>

            <!-- Pipeline Architecture Flow Diagram -->
            <div class="demo-card pipeline-card">
              <h3 class="panel-section-title">Interactive System Pipeline</h3>
              <p class="panel-section-desc">Click any node in the diagram to inspect its backend code, prompts, or data schemas in the inspector panel.</p>

              <div class="pipeline-flow-wrapper">
                <!-- Node 1: Input -->
                <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'input', current: demoSimulationStep === 1 }">
                  <div class="pipeline-node" @click="demoSelectedNode = 'input'">
                    <div class="node-icon-wrap">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    </div>
                    <span class="node-name">Raw Transcript</span>
                    <span class="node-sub">Meeting notes / file</span>
                  </div>
                </div>

                <div class="flow-arrow" :class="{ running: demoSimulationStep >= 1, completed: demoSimulationStep > 1 }">
                  <svg width="30" height="20" viewBox="0 0 30 20" fill="none"><path d="M0 10 H26 M20 4 L26 10 L20 16" stroke="currentColor" stroke-width="2"></path></svg>
                </div>

                <!-- Node 2: Translator Check -->
                <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'translator', current: demoSimulationStep === 2 }">
                  <div class="pipeline-node" @click="demoSelectedNode = 'translator'">
                    <div class="node-icon-wrap">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15h-4.6a2 2 0 0 1-1.85-1.28L12 7l-2.55 6.72A2 2 0 0 1 7.6 15H3"></path></svg>
                    </div>
                    <span class="node-name">Language Check</span>
                    <span class="node-sub">Translator Agent</span>
                  </div>
                </div>

                <div class="flow-arrow" :class="{ running: demoSimulationStep >= 2, completed: demoSimulationStep > 2 }">
                  <svg width="30" height="20" viewBox="0 0 30 20" fill="none"><path d="M0 10 H26 M20 4 L26 10 L20 16" stroke="currentColor" stroke-width="2"></path></svg>
                </div>

                <!-- Node 3: Coordinator / asyncio.gather -->
                <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'coordinator', current: demoSimulationStep === 3 }">
                  <div class="pipeline-node" @click="demoSelectedNode = 'coordinator'">
                    <div class="node-icon-wrap">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                    </div>
                    <span class="node-name">Parallel Coordinator</span>
                    <span class="node-sub">asyncio.gather()</span>
                  </div>
                </div>

                <!-- Parallel Path Split Arrows -->
                <div class="split-arrows">
                  <svg width="40" height="80" viewBox="0 0 40 80" fill="none" class="split-path-svg">
                    <path d="M0 40 H15 Q20 40 20 20 V15 Q20 10 30 10 H40" stroke="currentColor" stroke-width="2" class="path-upper" :class="{ running: demoSimulationStep >= 3, completed: demoSimulationStep > 3 }"></path>
                    <path d="M0 40 H15 Q20 40 20 60 V65 Q20 70 30 70 H40" stroke="currentColor" stroke-width="2" class="path-lower" :class="{ running: demoSimulationStep >= 3, completed: demoSimulationStep > 3 }"></path>
                  </svg>
                </div>

                <!-- Parallel Agent Sub-block -->
                <div class="parallel-agents-column">
                  <!-- Node 4: Summarizer Agent -->
                  <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'summarizer', current: demoSimulationStep === 4 && demoSelectedNode === 'summarizer' }">
                    <div class="pipeline-node agent-node" @click="demoSelectedNode = 'summarizer'; demoInspectorTab = 'prompt_summarizer'">
                      <div class="node-icon-wrap purple-glow">
                        <span class="agent-number-badge">A1</span>
                      </div>
                      <span class="node-name">Summarizer Agent</span>
                      <span class="node-sub">Prompt + Gemini</span>
                    </div>
                  </div>

                  <!-- Node 5: Action Item Agent -->
                  <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'actions', current: demoSimulationStep === 4 && demoSelectedNode === 'actions' }">
                    <div class="pipeline-node agent-node" @click="demoSelectedNode = 'actions'; demoInspectorTab = 'prompt_action'">
                      <div class="node-icon-wrap indigo-glow">
                        <span class="agent-number-badge">A2</span>
                      </div>
                      <span class="node-name">Action Item Agent</span>
                      <span class="node-sub">Prompt + Gemini</span>
                    </div>
                  </div>
                </div>

                <!-- Parallel Path Merge Arrows -->
                <div class="split-arrows merge-arrows">
                  <svg width="40" height="80" viewBox="0 0 40 80" fill="none" class="split-path-svg">
                    <path d="M0 10 H10 Q20 10 20 30 V35 Q20 40 25 40 H40" stroke="currentColor" stroke-width="2" class="path-upper" :class="{ running: demoSimulationStep >= 4, completed: demoSimulationStep > 4 }"></path>
                    <path d="M0 70 H10 Q20 70 20 50 V45 Q20 40 25 40 H40" stroke="currentColor" stroke-width="2" class="path-lower" :class="{ running: demoSimulationStep >= 4, completed: demoSimulationStep > 4 }"></path>
                  </svg>
                </div>

                <!-- Node 6: WebSocket Streaming -->
                <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'websocket', current: demoSimulationStep === 5 }">
                  <div class="pipeline-node" @click="demoSelectedNode = 'websocket'; demoInspectorTab = 'fastapi'">
                    <div class="node-icon-wrap">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
                    </div>
                    <span class="node-name">FastAPI WebSocket</span>
                    <span class="node-sub">asyncio.Lock Serialize</span>
                  </div>
                </div>

                <div class="flow-arrow" :class="{ running: demoSimulationStep >= 5, completed: demoSimulationStep > 5 }">
                  <svg width="30" height="20" viewBox="0 0 30 20" fill="none"><path d="M0 10 H26 M20 4 L26 10 L20 16" stroke="currentColor" stroke-width="2"></path></svg>
                </div>

                <!-- Node 7: Web Frontend -->
                <div class="pipeline-node-container" :class="{ active: demoSelectedNode === 'frontend', current: demoSimulationStep === 6 }">
                  <div class="pipeline-node" @click="demoSelectedNode = 'frontend'; demoInspectorTab = 'pydantic'">
                    <div class="node-icon-wrap">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                    </div>
                    <span class="node-name">Web Frontend</span>
                    <span class="node-sub">Vue incremental render</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Two Column Simulation Layout -->
            <div class="demo-split-grid">
              
              <!-- Left Column: Live Simulation -->
              <div class="demo-left-column">
                
                <!-- Mock WebSocket Message Terminal -->
                <div class="demo-card terminal-card">
                  <div class="terminal-card-header">
                    <div class="terminal-dots">
                      <span class="dot-red"></span>
                      <span class="dot-yellow"></span>
                      <span class="dot-green"></span>
                    </div>
                    <span class="terminal-title">WebSocket Messages Tunnel (/ws/summarize)</span>
                    <span class="terminal-status-badge" :class="{ active: demoSimulationActive }">
                      {{ demoSimulationActive ? 'Streaming' : 'Connected' }}
                    </span>
                  </div>
                  <div class="terminal-card-body" id="demo-terminal-body">
                    <div v-if="!demoLogs.length" class="terminal-empty-text">
                      No logs. Click 'Start Simulation' above to stream messages.
                    </div>
                    <div v-for="(log, idx) in demoLogs" :key="idx" class="terminal-log-line">
                      <span class="log-time">[{{ log.time }}]</span>
                      <span class="log-message" :class="{
                        'log-ws-recv': log.message.startsWith('WS RECV'),
                        'log-ws-send': log.message.startsWith('WS SEND'),
                        'log-ws-connect': log.message.startsWith('WS CONNECT')
                      }">{{ log.message }}</span>
                    </div>
                  </div>
                </div>

                <!-- Mock UI rendering card -->
                <div class="demo-card ui-preview-card">
                  <div class="ui-preview-header">
                    <span class="ui-preview-dot"></span>
                    <span>Live UI Rendering Panel</span>
                  </div>

                  <div class="ui-preview-body">
                    <!-- Meeting Title -->
                    <div class="preview-meeting-title">
                      <h3>Q3 Design Sync</h3>
                      <span class="preview-meeting-date">May 22, 2026</span>
                    </div>

                    <!-- Transcript sample -->
                    <div class="preview-transcript-container">
                      <div class="preview-transcript-label">SOURCE TRANSCRIPT INGESTION:</div>
                      <pre class="preview-transcript-text">{{ mockTranscript }}</pre>
                    </div>

                    <!-- Realtime Output fields -->
                    <div class="preview-live-fields">
                      <div class="preview-summary-box">
                        <div class="preview-field-header">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                          <span>Incremental Summary:</span>
                          <span v-if="demoSimulationStep === 5" class="preview-streaming-badge">Streaming</span>
                        </div>
                        <div class="preview-summary-text-box" :class="{ streaming: demoSimulationStep === 5 }">
                          <p v-if="!demoSummaryText" class="preview-empty-desc">Waiting for Summarizer Agent chunk packages...</p>
                          <p v-else>{{ demoSummaryText }}<span v-if="demoSimulationStep === 5" class="typing-cursor">▋</span></p>
                        </div>
                      </div>

                      <div class="preview-actions-box">
                        <div class="preview-field-header">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;"><path d="M9 11l3 3L22 4"></path><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2 2V5a2 2 0 0 1 2-2h11"></path></svg>
                          <span>Extracted Action Items:</span>
                        </div>
                        <div class="preview-actions-list">
                          <div v-if="!demoActionsList.length" class="preview-empty-desc">Waiting for Action Item Agent output...</div>
                          <div v-else v-for="(act, idx) in demoActionsList" :key="idx" class="preview-action-card">
                            <div class="preview-action-top">
                              <span class="act-name">{{ act.action }}</span>
                              <span class="act-prio" :class="act.priority.toLowerCase()">{{ act.priority }}</span>
                            </div>
                            <div class="preview-action-meta">
                              <span>Owner: <strong>{{ act.owner }}</strong></span>
                              <span>Due: <strong>{{ act.due_date }}</strong></span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Right Column: Code & Prompt Inspector -->
              <div class="demo-right-column">
                <div class="demo-card inspector-card">
                  <div class="inspector-header">
                    <nav class="inspector-tabs">
                      <button class="inspect-tab-btn" :class="{ active: demoInspectorTab === 'prompt_summarizer' }" @click="demoInspectorTab = 'prompt_summarizer'">
                        Summarizer Prompt
                      </button>
                      <button class="inspect-tab-btn" :class="{ active: demoInspectorTab === 'prompt_action' }" @click="demoInspectorTab = 'prompt_action'">
                        Action Item Prompt
                      </button>
                      <button class="inspect-tab-btn" :class="{ active: demoInspectorTab === 'pydantic' }" @click="demoInspectorTab = 'pydantic'">
                        Pydantic Schemas
                      </button>
                      <button class="inspect-tab-btn" :class="{ active: demoInspectorTab === 'fastapi' }" @click="demoInspectorTab = 'fastapi'">
                        FastAPI Websocket
                      </button>
                    </nav>
                  </div>
                  
                  <div class="inspector-body">
                    <!-- Summarizer Prompt -->
                    <div v-if="demoInspectorTab === 'prompt_summarizer'" class="inspector-pane active">
                      <div class="pane-file-info">
                        <span>prompts/summarizer_prompt.md</span>
                        <span class="badge-tag">AGENT 1 PROMPT</span>
                      </div>
                      <pre class="code-block-display"><code>You are a Meeting Summarizer Agent. Your job is to analyze meeting transcripts or notes and produce a structured summary.

You must extract:
1. Key discussion points (bullet list of main topics covered)
2. Decisions made during the meeting (anything that was agreed upon or concluded)
3. A concise summary (2-4 sentences capturing the essence of the meeting)
4. Open questions (unresolved topics that need follow-up)
5. Missing information (context that was referenced but not provided)

Rules:
- Be factual — only include what is explicitly stated in the transcript.
- Keep the concise summary short and business-focused.

Respond ONLY with valid JSON matching this schema:
{
  "key_discussion_points": ["..."],
  "decisions_made": ["..."],
  "concise_summary": "...",
  "open_questions": ["..."],
  "missing_information": ["..."]
}</code></pre>
                    </div>

                    <!-- Action Prompt -->
                    <div v-if="demoInspectorTab === 'prompt_action'" class="inspector-pane active">
                      <div class="pane-file-info">
                        <span>prompts/action_item_prompt.md</span>
                        <span class="badge-tag">AGENT 2 PROMPT</span>
                      </div>
                      <pre class="code-block-display"><code>You are an Action Item Agent. Your job is to extract all action items from meeting transcripts or notes and produce a structured report.

For each action item you must identify:
1. The specific action to be taken (clear, verb-led description)
2. The owner (person responsible) — use "Unassigned" if not mentioned
3. The due date — use "Needs date" if not mentioned
4. Status: "Clear" if the action is well-defined, "Needs clarification" if vague
5. Priority: "High" / "Medium" / "Low" based on urgency cues

Decision logic:
- If owner is missing → owner = "Unassigned", add to flagged_issues
- If deadline is missing → due_date = "Needs date", add to flagged_issues

Respond ONLY with valid JSON matching this schema:
{
  "action_items": [
    {
      "action": "...",
      "owner": "...",
      "due_date": "...",
      "status": "Clear | Needs clarification",
      "priority": "High | Medium | Low"
    }
  ],
  "flagged_issues": ["..."]
}</code></pre>
                    </div>

                    <!-- Pydantic Schemas -->
                    <div v-if="demoInspectorTab === 'pydantic'" class="inspector-pane active">
                      <div class="pane-file-info">
                        <span>schema/meeting_schema.py</span>
                        <span class="badge-tag">PYDANTIC VALIDATION MODELS</span>
                      </div>
                      <pre class="code-block-display"><code>from enum import Enum
from pydantic import BaseModel, Field

class ActionStatus(str, Enum):
    clear = "Clear"
    needs_clarification = "Needs clarification"

class ActionPriority(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"

class ActionItem(BaseModel):
    action: str = Field(..., description="Verb-led description")
    owner: str = Field(default="Unassigned")
    due_date: str = Field(default="Needs date")
    status: ActionStatus = Field(default=ActionStatus.clear)
    priority: ActionPriority = Field(default=ActionPriority.medium)

class ActionItemReport(BaseModel):
    action_items: list[ActionItem] = Field(default_factory=list)
    flagged_issues: list[str] = Field(default_factory=list)

class MeetingSummary(BaseModel):
    concise_summary: str = Field(..., description="2-4 sentence overview")
    key_discussion_points: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

class MeetingWorkflowResult(BaseModel):
    summary: MeetingSummary
    action_report: ActionItemReport</code></pre>
                    </div>

                    <!-- FastAPI WS Code -->
                    <div v-if="demoInspectorTab === 'fastapi'" class="inspector-pane active">
                      <div class="pane-file-info">
                        <span>backend/main.py</span>
                        <span class="badge-tag">FASTAPI WEBSOCKET ENDPOINT</span>
                      </div>
                      <pre class="code-block-display"><code>@app.websocket("/ws/summarize")
async def ws_summarize(websocket: WebSocket):
    await websocket.accept()
    try:
        # Lock prevents concurrent writes to WebSocket from parallel tasks
        send_lock = asyncio.Lock()

        async def send(payload: dict) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        async def run_and_stream(stream_fn, agent_type: str, transcript: str) -> dict:
            accumulated = ""
            async for chunk in stream_fn(client, transcript):
                accumulated += chunk
                await send({"type": f"{agent_type}_chunk", "chunk": chunk})
            result = parse_json(accumulated)
            await send({"type": f"{agent_type}_done", "data": result})
            return result

        # Run both agents concurrently
        summary_data, actions_data = await asyncio.gather(
            run_and_stream(stream_meeting_summarizer, "summary", transcript),
            run_and_stream(stream_action_item_agent, "actions", transcript),
        )

        await send({"type": "complete"})
    except WebSocketDisconnect:
        pass</code></pre>
                    </div>

                  </div>
                </div>
              </div>

            </div>
          </div>

          <!-- ── Overview ── -->
          <div v-else-if="view === 'overview'" class="view-overview">
            <div class="view-header">
              <h1>Overview</h1>
              <p class="view-subtitle">All your projects and meetings at a glance.</p>
            </div>

            <div class="stats-row">
              <div class="stat-card stat-projects">
                <div class="stat-icon-wrap">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                </div>
                <div>
                  <div class="stat-val">{{ sidebarProjects.length }}</div>
                  <div class="stat-lbl">Projects</div>
                </div>
              </div>
              <div class="stat-card stat-meetings">
                <div class="stat-icon-wrap">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                </div>
                <div>
                  <div class="stat-val">{{ totalMeetings }}</div>
                  <div class="stat-lbl">Total Meetings</div>
                </div>
              </div>
              <div v-if="sidebarProjects.length > 0" class="stat-card stat-avg">
                <div class="stat-icon-wrap">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                </div>
                <div>
                  <div class="stat-val">{{ (totalMeetings / sidebarProjects.length).toFixed(1) }}</div>
                  <div class="stat-lbl">Avg / Project</div>
                </div>
              </div>
            </div>

            <div v-if="!sidebarProjects.length" class="overview-empty">
              <div class="empty-illustration">
                <div class="empty-circle"></div>
                <svg class="empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
              </div>
              <h3>No projects yet</h3>
              <p>Create a project from the sidebar, then upload meeting files to start building intelligence.</p>
              <button class="primary-btn" style="margin-top:18px;width:auto;" @click="showNewProjectForm = true">
                Create First Project
              </button>
            </div>

            <template v-else>
              <h2 class="section-heading">All Projects</h2>
              <div class="projects-grid">
                <div v-for="proj in sidebarProjects" :key="proj.project_id"
                  class="project-card" @click="selectProject(proj.project_id)">
                  <div class="project-card-top">
                    <div class="project-card-folder">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                    </div>
                    <span class="project-card-name">{{ proj.name }}</span>
                  </div>
                  <div class="project-card-count">{{ proj.meeting_count }} meeting{{ proj.meeting_count !== 1 ? 's' : '' }}</div>
                  <div class="project-mini-bar">
                    <div class="project-mini-bar-fill"
                      :style="{ width: Math.round((proj.meeting_count / maxMeetingCount) * 100) + '%' }">
                    </div>
                  </div>
                  <div class="project-card-cta">View Project →</div>
                </div>

                <div class="project-card project-card-new" @click="showNewProjectForm = true">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                  <span>New Project</span>
                </div>
              </div>
            </template>
          </div>

          <!-- ── Project View ── -->
          <div v-else-if="view === 'project'" class="view-project">
            <div class="view-header project-view-header">
              <div>
                <h1>{{ activeProjectInList?.name }}</h1>
                <p class="view-subtitle">
                  <span class="badge-count">{{ activeProjectInList?.meeting_count || 0 }} meetings</span>
                </p>
              </div>
              <div class="project-header-btns">
                <button class="secondary-btn" @click="openUpload(activeProjectId)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                  Add Meeting
                </button>
                <button class="secondary-btn" :class="{ 'btn-active': isChatOpen }"
                  @click="isChatOpen ? closeChat() : openChat()">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                  {{ isChatOpen ? 'Close Chat' : 'Chat' }}
                </button>
              </div>
            </div>

            <div class="project-body" :class="{ 'with-chat': isChatOpen }">
              <div class="project-main-col">

                <!-- AI Summary card -->
                <div class="project-summary-card">
                  <div class="psc-header">
                    <h2>Strategic Summary</h2>
                    <button v-if="summaryCache[activeProjectId]" class="btn-ghost-sm"
                      @click="delete summaryCache[activeProjectId]; fetchProjectSummary(activeProjectId)">
                      ↺ Refresh
                    </button>
                  </div>

                  <div v-if="summaryLoading[activeProjectId]" class="psc-loading">
                    <span class="spinner-tiny"></span>
                    <span>Analyzing all meeting transcripts…</span>
                  </div>

                  <div v-else-if="!activeProjectInList?.meeting_count" class="psc-hint">
                    Add meetings to this project to generate a strategic summary.
                  </div>

                  <div v-else-if="!summaryCache[activeProjectId]" class="psc-hint">
                    <button class="primary-btn" style="width:auto;"
                      @click="fetchProjectSummary(activeProjectId)">
                      Generate Summary
                    </button>
                  </div>

                  <div v-else class="psc-body">
                    <div class="psc-overview">
                      <p>{{ summaryCache[activeProjectId].overview }}</p>
                    </div>

                    <div class="psc-grid">
                      <div class="psc-block" v-if="summaryCache[activeProjectId].strategic_goals?.length">
                        <h4>Strategic Goals</h4>
                        <ul class="styled-list bullet-list">
                          <li v-for="(g,i) in summaryCache[activeProjectId].strategic_goals" :key="i">{{ g }}</li>
                        </ul>
                      </div>

                      <div class="psc-block" v-if="summaryCache[activeProjectId].key_themes?.length">
                        <h4>Key Themes</h4>
                        <div class="theme-chips">
                          <span class="theme-chip" v-for="(t,i) in summaryCache[activeProjectId].key_themes" :key="i">{{ t }}</span>
                        </div>
                      </div>

                      <div class="psc-block" v-if="summaryCache[activeProjectId].major_decisions?.length">
                        <h4>Major Decisions</h4>
                        <ul class="styled-list check-list">
                          <li v-for="(d,i) in summaryCache[activeProjectId].major_decisions" :key="i">{{ d }}</li>
                        </ul>
                      </div>

                      <div class="psc-block" v-if="summaryCache[activeProjectId].risks_and_concerns?.length">
                        <h4>Risks & Concerns</h4>
                        <ul class="styled-list warning-list">
                          <li v-for="(r,i) in summaryCache[activeProjectId].risks_and_concerns" :key="i">{{ r }}</li>
                        </ul>
                      </div>
                    </div>

                    <div v-if="summaryCache[activeProjectId].current_direction" class="psc-direction">
                      <h4>Current Direction</h4>
                      <p>{{ summaryCache[activeProjectId].current_direction }}</p>
                    </div>

                    <div v-if="summaryCache[activeProjectId].open_questions?.length" class="psc-block psc-questions">
                      <h4>Open Questions</h4>
                      <ul class="styled-list question-list">
                        <li v-for="(q,i) in summaryCache[activeProjectId].open_questions" :key="i">{{ q }}</li>
                      </ul>
                    </div>

                    <div v-if="summaryCache[activeProjectId].progress_assessment" class="psc-progress">
                      <h4>Progress Assessment</h4>
                      <p>{{ summaryCache[activeProjectId].progress_assessment }}</p>
                    </div>

                    <p class="psc-meta">Based on {{ summaryCache[activeProjectId].meetings_analyzed }} meeting{{ summaryCache[activeProjectId].meetings_analyzed !== 1 ? 's' : '' }}</p>
                  </div>
                </div>

                <!-- Meetings list -->
                <div class="meetings-section">
                  <h2 class="section-heading">Meetings</h2>

                  <div v-if="!activeProject" class="meetings-loading">
                    <span class="spinner-tiny"></span> Loading…
                  </div>

                  <div v-else-if="!activeProject.meetings?.length" class="meetings-empty-state">
                    <p>No meetings yet.</p>
                    <button class="primary-btn" style="width:auto;margin-top:12px;"
                      @click="openUpload(activeProjectId)">Add First Meeting</button>
                  </div>

                  <div v-else class="meetings-list">
                    <div v-for="mtg in activeProject.meetings" :key="mtg.id"
                      class="meeting-card" @click="selectMeeting(activeProjectId, mtg.id)">
                      <div class="meeting-card-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                      </div>
                      <div class="meeting-card-body">
                        <h4>{{ mtg.name || 'Untitled Meeting' }}</h4>
                        <p class="meeting-card-summary">{{ mtg.summary?.concise_summary || 'No summary' }}</p>
                      </div>
                      <div class="meeting-card-meta">
                        <span class="meeting-action-count">{{ mtg.actions?.action_items?.length || 0 }} actions</span>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Chat slide-over -->
              <div v-if="isChatOpen" class="chat-panel">
                <div class="chat-panel-header">
                  <span>Project Chat</span>
                  <button class="btn-ghost-sm" @click="closeChat">✕</button>
                </div>

                <div v-if="!chatMessages.length" class="chat-panel-hints">
                  <p>Ask anything about this project's meetings.</p>
                  <div class="chat-hint-chips" style="margin-top:10px;">
                    <span class="hint-chip" @click="chatInput='What decisions have been made so far?'; sendChat()">What decisions were made?</span>
                    <span class="hint-chip" @click="chatInput='What are the open action items?'; sendChat()">Open action items?</span>
                    <span class="hint-chip" @click="chatInput='Catch me up on this project.'; sendChat()">Catch me up</span>
                  </div>
                </div>

                <div class="chat-messages" ref="chatScrollRef">
                  <div v-for="(msg, i) in chatMessages" :key="i"
                    class="chat-message" :class="msg.role">
                    <div class="message-bubble" :class="{ streaming: msg.streaming }">
                      <span class="msg-role-label" :class="{ 'agent-label': msg.role === 'assistant' }">
                        {{ msg.role === 'user' ? 'You' : 'Project Agent' }}
                      </span>
                      <div class="message-text" v-html="renderMarkdown(msg.text)"></div>
                      <span v-if="msg.streaming" class="typing-cursor">▋</span>
                    </div>
                  </div>
                </div>

                <div class="chat-input-row">
                  <textarea class="chat-textarea" v-model="chatInput" rows="2"
                    placeholder="Ask about this project…"
                    :disabled="isChatStreaming"
                    @keydown="handleChatKey"></textarea>
                  <button class="chat-send-btn"
                    :disabled="isChatStreaming || !chatInput.trim()"
                    @click="sendChat">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- ── Meeting View ── -->
          <div v-else-if="view === 'meeting' && activeMeeting" class="view-meeting">
            <div class="view-header">
              <h1>{{ activeMeeting.name || 'Untitled Meeting' }}</h1>
              <p class="view-subtitle">{{ activeProjectInList?.name }}</p>
            </div>

            <div class="results-dashboard">
              <nav class="dashboard-tabs">
                <button class="tab-btn" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">Overview</button>
                <button class="tab-btn" :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'">Summary</button>
                <button class="tab-btn" :class="{ active: activeTab === 'actions' }" @click="activeTab = 'actions'">Action Items</button>
                <button class="tab-btn" :class="{ active: activeTab === 'jira' }" @click="activeTab = 'jira'">Jira Tasks</button>
                <button class="tab-btn" :class="{ active: activeTab === 'email' }" @click="activeTab = 'email'">Follow-up Email</button>
                <button class="tab-btn" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">Chat</button>
              </nav>

              <div class="tab-contents">

                <!-- Overview tab -->
                <div v-if="activeTab === 'overview'" class="tab-pane active">
                  <div class="metrics-grid">
                    <div class="metric-card card-glow-primary">
                      <span class="metric-label">Total Actions</span>
                      <span class="metric-value">{{ activeMeeting.actions?.action_items?.length || 0 }}</span>
                    </div>
                    <div class="metric-card card-glow-high">
                      <span class="metric-label">High Priority</span>
                      <span class="metric-value">{{ activeMeeting.actions?.action_items?.filter(i => i.priority === 'High').length || 0 }}</span>
                    </div>
                    <div class="metric-card card-glow-warning">
                      <span class="metric-label">Flagged Issues</span>
                      <span class="metric-value">{{ activeMeeting.actions?.flagged_issues?.length || 0 }}</span>
                    </div>
                    <div class="metric-card card-glow-info">
                      <span class="metric-label">Open Questions</span>
                      <span class="metric-value">{{ activeMeeting.summary?.open_questions?.length || 0 }}</span>
                    </div>
                  </div>

                  <div class="quick-summary-box">
                    <h3>Concise Summary</h3>
                    <p class="concise-text">{{ activeMeeting.summary?.concise_summary }}</p>
                  </div>

                  <div class="overview-details-grid">
                    <div class="decisions-summary-card">
                      <h3>Key Decisions</h3>
                      <ul v-if="activeMeeting.summary?.decisions_made?.length" class="styled-list check-list">
                        <li v-for="(d,i) in activeMeeting.summary.decisions_made.slice(0,5)" :key="i">{{ d }}</li>
                      </ul>
                      <p v-else style="color:var(--text-muted);font-size:13.5px;">No decisions recorded.</p>
                    </div>
                    <div class="warnings-summary-card">
                      <h3>Flagged Issues</h3>
                      <ul v-if="activeMeeting.actions?.flagged_issues?.length" class="styled-list warning-list">
                        <li v-for="(f,i) in activeMeeting.actions.flagged_issues.slice(0,5)" :key="i">{{ f }}</li>
                      </ul>
                      <p v-else style="color:var(--success);font-size:13.5px;">✓ No issues flagged.</p>
                    </div>
                  </div>
                </div>

                <!-- Summary tab -->
                <div v-if="activeTab === 'summary'" class="tab-pane active">
                  <div class="section-block">
                    <h3 class="section-title">Concise Summary</h3>
                    <div class="summary-highlight-box"><p>{{ activeMeeting.summary?.concise_summary }}</p></div>
                  </div>
                  <div class="section-split">
                    <div class="section-block">
                      <h3 class="section-title">Key Discussion Points</h3>
                      <ul v-if="activeMeeting.summary?.key_discussion_points?.length" class="styled-list bullet-list">
                        <li v-for="(pt,i) in activeMeeting.summary.key_discussion_points" :key="i">{{ pt }}</li>
                      </ul>
                      <p v-else style="color:var(--text-muted);font-size:13.5px;">None found.</p>
                    </div>
                    <div class="section-block">
                      <h3 class="section-title">Decisions Made</h3>
                      <ul v-if="activeMeeting.summary?.decisions_made?.length" class="styled-list check-list">
                        <li v-for="(d,i) in activeMeeting.summary.decisions_made" :key="i">{{ d }}</li>
                      </ul>
                      <p v-else style="color:var(--text-muted);font-size:13.5px;">None recorded.</p>
                    </div>
                  </div>
                  <div class="section-split">
                    <div class="section-block">
                      <h3 class="section-title">Open Questions</h3>
                      <ul v-if="activeMeeting.summary?.open_questions?.length" class="styled-list question-list">
                        <li v-for="(q,i) in activeMeeting.summary.open_questions" :key="i">{{ q }}</li>
                      </ul>
                      <p v-else style="color:var(--text-muted);font-size:13.5px;">None.</p>
                    </div>
                    <div class="section-block">
                      <h3 class="section-title">Missing Information</h3>
                      <ul v-if="activeMeeting.summary?.missing_information?.length" class="styled-list warning-list">
                        <li v-for="(m,i) in activeMeeting.summary.missing_information" :key="i">{{ m }}</li>
                      </ul>
                      <p v-else style="color:var(--text-muted);font-size:13.5px;">None flagged.</p>
                    </div>
                  </div>
                </div>

                <!-- Actions tab -->
                <div v-if="activeTab === 'actions'" class="tab-pane active">
                  <div class="actions-header">
                    <div class="filter-bar">
                      <button class="filter-chip" :class="{ active: meetingFilter === 'all' }" @click="meetingFilter = 'all'">All</button>
                      <button class="filter-chip" :class="{ active: meetingFilter === 'High' }" @click="meetingFilter = 'High'">High</button>
                      <button class="filter-chip" :class="{ active: meetingFilter === 'Medium' }" @click="meetingFilter = 'Medium'">Medium</button>
                      <button class="filter-chip" :class="{ active: meetingFilter === 'Low' }" @click="meetingFilter = 'Low'">Low</button>
                      <button class="filter-chip" :class="{ active: meetingFilter === 'needs_clarification' }" @click="meetingFilter = 'needs_clarification'">Needs Clarification</button>
                    </div>
                  </div>

                  <div v-if="activeMeeting.actions?.flagged_issues?.length" class="actions-warning-banner">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    <div>
                      <h4>Attention Required</h4>
                      <p>{{ activeMeeting.actions.flagged_issues.length }} issue(s) flagged.</p>
                    </div>
                  </div>

                  <div class="action-items-list">
                    <div v-for="(task,i) in filteredActions" :key="i"
                      class="action-card"
                      :class="[`priority-${task.priority?.toLowerCase()}`, { 'status-clarify': task.status === 'Needs clarification' }]">
                      <div class="action-card-main">
                        <h4>{{ task.action }}</h4>
                        <div class="action-card-meta">
                          <div class="meta-item"><span class="label">Assignee:</span><span class="val">{{ task.owner }}</span></div>
                          <div class="meta-item"><span class="label">Due:</span><span class="val">{{ task.due_date }}</span></div>
                        </div>
                      </div>
                      <div class="action-card-badges">
                        <span class="badge" :class="`prio-${task.priority?.toLowerCase()}`">{{ task.priority }}</span>
                        <span class="badge" :class="task.status === 'Clear' ? 'status-clear' : 'status-needs-clarification'">{{ task.status }}</span>
                      </div>
                    </div>
                    <div v-if="!filteredActions.length" class="empty-filter-state">
                      No action items match this filter.
                    </div>
                  </div>
                </div>

                <!-- Jira Tasks tab -->
                <div v-if="activeTab === 'jira'" class="tab-pane active">
                  <div v-if="isGeneratingFollowup" class="followup-generating-state">
                    <span class="spinner-large"></span>
                    <h3>Generating Follow-up Details</h3>
                    <p>Creating Jira tasks and email drafts for this meeting...</p>
                  </div>
                  <div v-else-if="!activeMeeting.followup || !activeMeeting.followup.jira_tasks || !activeMeeting.followup.jira_tasks.length" class="followup-empty-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line><line x1="15" y1="3" x2="15" y2="21"></line><line x1="3" y1="9" x2="21" y2="9"></line><line x1="3" y1="15" x2="21" y2="15"></line></svg>
                    <h3>No Jira tasks generated</h3>
                    <p>Generate follow-up email drafts and Jira-ready tickets for this meeting.</p>
                    <button class="primary-btn" style="margin-top: 12px; width: auto;" @click="generateFollowup">
                      Generate Follow-up
                    </button>
                  </div>
                  <template v-else>
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
                                <span class="jira-prio-badge" :class="task.priority?.toLowerCase()">{{ task.priority }}</span>
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
                  </template>
                </div>

                <!-- Follow-up Email tab -->
                <div v-if="activeTab === 'email'" class="tab-pane active">
                  <div v-if="isGeneratingFollowup" class="followup-generating-state">
                    <span class="spinner-large"></span>
                    <h3>Generating Follow-up Details</h3>
                    <p>Creating Jira tasks and email drafts for this meeting...</p>
                  </div>
                  <div v-else-if="!activeMeeting.followup || !activeMeeting.followup.email_body" class="followup-empty-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
                    <h3>No follow-up email generated</h3>
                    <p>Generate a professional follow-up email draft and Jira-ready tickets for this meeting.</p>
                    <button class="primary-btn" style="margin-top: 12px; width: auto;" @click="generateFollowup">
                      Generate Follow-up
                    </button>
                  </div>
                  <template v-else>
                    <div class="email-editor-header">
                      <div class="subject-line">
                        <span class="prefix">Subject:</span>
                        <span id="email-subject-val">{{ activeMeeting.followup.email_subject }}</span>
                      </div>
                      <button class="secondary-btn" @click="copyEmail">
                        <span class="btn-text">Copy Email Body</span>
                      </button>
                    </div>
                    <div class="email-editor-container">
                      <textarea 
                        v-model="activeMeeting.followup.email_body" 
                        class="email-textarea" 
                        spellcheck="false"
                      ></textarea>
                    </div>
                  </template>
                </div>

                <!-- Chat tab -->
                <div v-if="activeTab === 'chat'" class="tab-pane active chat-tab-pane">
                  <div class="chat-tab-container">
                    <div class="chat-tab-header">
                      <div class="chat-tab-title">
                        <span class="active-dot"></span>
                        <h3>Project Meeting Assistant</h3>
                      </div>
                      <p class="chat-tab-subtitle">Ask questions about all meetings, decisions, and action items in this project.</p>
                    </div>

                    <!-- Suggested questions -->
                    <div v-if="!chatMessages.length" class="chat-tab-suggestions">
                      <p class="suggestions-label">Suggested Questions</p>
                      <div class="chat-suggestions-grid">
                        <button class="chat-suggestion-btn" @click="chatInput='What decisions have been made so far across all meetings?'; sendChat()">
                          <span class="btn-icon">💡</span>
                          <span class="btn-text">What decisions were made?</span>
                        </button>
                        <button class="chat-suggestion-btn" @click="chatInput='What are the open action items and their owners?'; sendChat()">
                          <span class="btn-icon">📋</span>
                          <span class="btn-text">Open action items?</span>
                        </button>
                        <button class="chat-suggestion-btn" @click="chatInput='Summarize the main themes of this project.'; sendChat()">
                          <span class="btn-icon">🎯</span>
                          <span class="btn-text">Summarize project themes</span>
                        </button>
                      </div>
                    </div>

                    <!-- Message history -->
                    <div class="chat-tab-messages" ref="chatTabScrollRef">
                      <div class="chat-bubble-wrap assistant" v-if="!chatMessages.length">
                        <div class="chat-bubble">
                          <span class="msg-role-label agent-label">Project Agent</span>
                          <div class="chat-bubble-content">
                            <p>Hi! I'm your project assistant. I have access to all the meetings and transcripts in this project. Ask me anything!</p>
                          </div>
                        </div>
                      </div>

                      <div v-for="(msg, i) in chatMessages" :key="i"
                        class="chat-bubble-wrap" :class="msg.role">
                        <div class="chat-bubble" :class="{ streaming: msg.streaming }">
                          <span class="msg-role-label" :class="{ 'agent-label': msg.role === 'assistant' }">
                            {{ msg.role === 'user' ? 'You' : 'Project Agent' }}
                          </span>
                          <div class="chat-bubble-content" v-html="renderMarkdown(msg.text)"></div>
                          <span v-if="msg.streaming" class="typing-cursor">▋</span>
                        </div>
                      </div>
                    </div>

                    <!-- Input row -->
                    <div class="chat-tab-input-form">
                      <textarea class="chat-tab-textarea" v-model="chatInput" rows="1"
                        placeholder="Ask a question about this project..."
                        :disabled="isChatStreaming"
                        @keydown="handleChatKey"></textarea>
                      <button class="chat-tab-send-btn"
                        :disabled="isChatStreaming || !chatInput.trim()"
                        @click="sendChat">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <line x1="22" y1="2" x2="11" y2="13"></line>
                          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </main>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toastVisible" class="toast-notification">{{ toastMsg }}</div>
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────────────────*/
.app-root {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  position: relative;
}

.glow-bg {
  position: fixed;
  width: 500px;
  height: 500px;
  top: -150px;
  right: -80px;
  background: radial-gradient(circle, rgba(129,140,248,0.12) 0%, transparent 70%);
  pointer-events: none;
  filter: blur(60px);
  z-index: 0;
}

.app-shell {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────────*/
.sidebar {
  width: 220px;
  min-width: 220px;
  background: rgba(10,14,29,0.85);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  backdrop-filter: blur(12px);
  z-index: 10;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.logo-icon {
  width: 30px;
  height: 30px;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--border-color);
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.3px;
}

.logo-accent {
  background: linear-gradient(135deg, hsl(244,96%,66%), hsl(290,96%,66%));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  border-radius: 7px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  text-align: left;
}

.nav-item:hover { background: rgba(255,255,255,0.05); color: var(--text-main); }
.nav-item.active { background: rgba(99,102,241,0.15); color: var(--primary); }

.nav-section-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-muted);
  padding: 10px 10px 4px;
  opacity: 0.6;
}

.sidebar-no-projects {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 10px;
  opacity: 0.6;
}

/* Project tree */
.project-tree-item { display: flex; flex-direction: column; }

.project-tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s;
  min-width: 0;
}

.project-tree-row:hover { background: rgba(255,255,255,0.05); }
.project-tree-row.active { background: rgba(99,102,241,0.15); }

.expand-btn {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-radius: 3px;
  transition: background 0.15s;
}
.expand-btn:hover { background: rgba(255,255,255,0.08); }

.tree-folder-icon { color: var(--primary); opacity: 0.75; flex-shrink: 0; }

.tree-project-name {
  flex: 1;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-count-badge {
  font-size: 10px;
  color: var(--text-muted);
  background: rgba(255,255,255,0.06);
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
}

.meeting-subtree {
  margin-left: 22px;
  border-left: 1px solid var(--border-color);
  padding-left: 6px;
  margin-bottom: 4px;
}

.subtree-loading, .subtree-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 8px;
  opacity: 0.6;
}

.meeting-subtree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 11.5px;
  color: var(--text-muted);
  transition: all 0.15s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meeting-subtree-row:hover { background: rgba(255,255,255,0.04); color: var(--text-main); }
.meeting-subtree-row.active { background: rgba(99,102,241,0.1); color: var(--primary); }
.meeting-subtree-row svg { flex-shrink: 0; opacity: 0.6; }

/* Sidebar footer */
.sidebar-footer {
  padding: 10px 8px 14px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.new-project-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: 1px dashed rgba(255,255,255,0.12);
  border-radius: 7px;
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.new-project-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: rgba(99,102,241,0.06);
}

.new-proj-form { display: flex; flex-direction: column; gap: 8px; }
.new-proj-actions { display: flex; gap: 6px; justify-content: flex-end; }

.btn-ghost-xs, .btn-primary-xs {
  font-size: 11.5px;
  padding: 4px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.15s;
}
.btn-ghost-xs {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-muted);
}
.btn-ghost-xs:hover { border-color: var(--border-color-hover); color: var(--text-main); }
.btn-primary-xs {
  background: var(--primary);
  border: none;
  color: white;
}
.btn-primary-xs:disabled { opacity: 0.5; cursor: default; }

/* ── Main wrapper ─────────────────────────────────────────────────────────────*/
.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* ── Top bar ─────────────────────────────────────────────────────────────────*/
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-color);
  background: rgba(10,14,29,0.5);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
  z-index: 5;
}

.breadcrumb { display: flex; align-items: center; gap: 6px; }

.bc-link {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.bc-link:hover { color: var(--text-main); }
.bc-sep { color: var(--text-muted); font-size: 13px; opacity: 0.5; }
.bc-current { font-size: 13px; color: var(--text-main); font-weight: 500; }

.top-bar-actions { display: flex; align-items: center; gap: 10px; }

.add-meeting-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 14px;
  background: var(--primary);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 10px rgba(99,102,241,0.3);
}
.add-meeting-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(99,102,241,0.4); }

.theme-toggle {
  width: 34px;
  height: 34px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-main);
  transition: all 0.2s;
}
.theme-toggle:hover { border-color: var(--border-color-hover); transform: scale(1.05); }

/* ── Content area ────────────────────────────────────────────────────────────*/
.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
}

.view-header { margin-bottom: 24px; }
.view-header h1 {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.view-subtitle { font-size: 13.5px; color: var(--text-muted); }

/* ── Overview ────────────────────────────────────────────────────────────────*/
.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 16px 20px;
  min-width: 150px;
  transition: all 0.2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-projects .stat-icon-wrap { background: rgba(99,102,241,0.15); color: var(--primary); }
.stat-meetings .stat-icon-wrap { background: rgba(16,185,129,0.15); color: var(--success); }
.stat-avg .stat-icon-wrap { background: rgba(245,158,11,0.15); color: var(--warning); }

.stat-val {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  display: block;
}
.stat-lbl {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  display: block;
  margin-top: 3px;
}

.overview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
  text-align: center;
  color: var(--text-muted);
}
.overview-empty h3 { font-family: var(--font-display); font-size: 20px; color: var(--text-main); margin-bottom: 8px; }
.overview-empty p { font-size: 14px; max-width: 320px; line-height: 1.5; }

.section-heading {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 16px;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.project-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 18px 20px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.project-card:hover {
  border-color: rgba(99,102,241,0.4);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.2);
}

.project-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.project-card-folder { color: var(--primary); opacity: 0.8; flex-shrink: 0; }
.project-card-name { font-size: 14px; font-weight: 600; color: var(--text-main); }
.project-card-count { font-size: 12px; color: var(--text-muted); }

.project-mini-bar {
  height: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  overflow: hidden;
}
.project-mini-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), hsl(290,90%,65%));
  border-radius: 2px;
  transition: width 0.4s ease;
}

.project-card-cta { font-size: 12px; color: var(--primary); font-weight: 500; }

.project-card-new {
  border-style: dashed;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted);
  min-height: 120px;
}
.project-card-new:hover { color: var(--primary); border-color: var(--primary); }
.project-card-new span { font-size: 13px; font-weight: 500; }

/* ── Project view ────────────────────────────────────────────────────────────*/
.project-view-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.badge-count {
  display: inline-block;
  background: rgba(99,102,241,0.15);
  color: #a5b4fc;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid rgba(99,102,241,0.2);
}
.project-header-btns { display: flex; gap: 8px; align-items: center; }

.btn-active {
  border-color: var(--primary) !important;
  color: var(--primary) !important;
  background: rgba(99,102,241,0.1) !important;
}

.btn-ghost-sm {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 5px;
  transition: all 0.15s;
}
.btn-ghost-sm:hover { color: var(--text-main); background: rgba(255,255,255,0.05); }

.project-body {
  display: flex;
  gap: 24px;
  min-height: 0;
}
.project-main-col { flex: 1; display: flex; flex-direction: column; gap: 24px; min-width: 0; }
.project-body.with-chat .project-main-col { flex: 1; }

/* Project summary card */
.project-summary-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 22px 24px;
  backdrop-filter: blur(8px);
}

.psc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.psc-header h2 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
}

.psc-loading, .psc-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  color: var(--text-muted);
  padding: 8px 0;
}

.psc-body { display: flex; flex-direction: column; gap: 18px; }

.psc-overview {
  background: rgba(99,102,241,0.06);
  border-left: 3px solid var(--primary);
  border-radius: 0 8px 8px 0;
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-main);
}

.psc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.psc-block {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 14px 16px;
}
.psc-block h4, .psc-direction h4, .psc-progress h4 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 10px;
}
.psc-questions { grid-column: 1 / -1; }

.theme-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.theme-chip {
  background: rgba(99,102,241,0.1);
  border: 1px solid rgba(99,102,241,0.2);
  color: #a5b4fc;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
}

.psc-direction, .psc-progress {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 14px 16px;
  font-size: 13.5px;
  line-height: 1.6;
}

.psc-meta {
  font-size: 11.5px;
  color: var(--text-muted);
  opacity: 0.6;
}

/* Meetings list */
.meetings-section h2 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 14px;
}

.meetings-loading, .meetings-empty-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: var(--text-muted);
  padding: 20px;
}

.meetings-list { display: flex; flex-direction: column; gap: 10px; }

.meeting-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 14px 18px;
  cursor: pointer;
  transition: all 0.2s;
}
.meeting-card:hover {
  border-color: rgba(99,102,241,0.4);
  transform: translateX(3px);
}

.meeting-card-icon {
  width: 34px;
  height: 34px;
  background: rgba(99,102,241,0.1);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  flex-shrink: 0;
}

.meeting-card-body { flex: 1; min-width: 0; }
.meeting-card-body h4 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.meeting-card-summary {
  font-size: 12.5px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meeting-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.meeting-action-count {
  font-size: 11.5px;
  background: rgba(255,255,255,0.06);
  padding: 2px 8px;
  border-radius: 8px;
  color: var(--text-muted);
}

/* ── Chat panel ──────────────────────────────────────────────────────────────*/
.chat-panel {
  width: 340px;
  min-width: 340px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
  overflow: hidden;
  height: fit-content;
  max-height: calc(100vh - 200px);
}

.chat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.chat-panel-hints { padding: 16px; font-size: 13px; color: var(--text-muted); flex-shrink: 0; }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 200px;
  max-height: 380px;
}

.chat-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

/* ── Meeting view ────────────────────────────────────────────────────────────*/
.view-meeting .results-dashboard { display: flex; flex-direction: column; }

.empty-filter-state {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-md);
}

/* ── Upload modal ────────────────────────────────────────────────────────────*/
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  padding: 28px;
  width: 480px;
  max-width: 95vw;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  backdrop-filter: blur(16px);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modal-header h3 { font-family: var(--font-display); font-size: 18px; font-weight: 700; }

.modal-close-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  width: 30px;
  height: 30px;
  border-radius: 7px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.modal-close-btn:hover { color: var(--text-main); border-color: var(--border-color-hover); }

.modal-dropzone {
  border: 2px dashed var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba(255,255,255,0.01);
}
.modal-dropzone:hover, .modal-dropzone.dragover {
  border-color: var(--primary);
  background: var(--primary-glow);
}
.modal-dropzone.has-file { cursor: default; }

.file-selected-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 6px;
}

.modal-field { display: flex; flex-direction: column; gap: 7px; }
.modal-field label { font-size: 12.5px; font-weight: 600; color: var(--text-muted); }

.upload-status-msg { font-size: 12.5px; color: var(--primary); }
.upload-error-msg { font-size: 12.5px; color: var(--danger); }

.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

.modal-body-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-desc {
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--text-muted);
}

.modal-footer-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 10px;
}

.upload-btn-modal {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 14px;
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

.chat-bubble-wrap.model,
.chat-bubble-wrap.assistant {
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

.chat-bubble-wrap.model .chat-bubble,
.chat-bubble-wrap.assistant .chat-bubble {
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

.chat-bubble-wrap.model .chat-timestamp,
.chat-bubble-wrap.assistant .chat-timestamp {
  text-align: left;
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

body.light-theme .chat-bubble-wrap.model .chat-bubble,
body.light-theme .chat-bubble-wrap.assistant .chat-bubble {
  background: rgba(0, 0, 0, 0.035);
  border-color: rgba(0, 0, 0, 0.05);
  color: #334155;
}

body.light-theme .chat-bubble-wrap.model .chat-timestamp,
body.light-theme .chat-bubble-wrap.assistant .chat-timestamp {
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
/* ── Toast ───────────────────────────────────────────────────────────────────*/
.toast-notification {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: linear-gradient(135deg, hsl(244,90%,60%), hsl(270,90%,60%));
  color: white;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  z-index: 999;
  box-shadow: 0 4px 16px rgba(99,102,241,0.4);
  animation: slideInToast 0.25s ease;
}

@keyframes slideInToast {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* ── Shared utilities (used from global style.css) ───────────────────────────*/
.spinner-tiny {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid rgba(99,102,241,0.15);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spinT 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spinT { to { transform: rotate(360deg); } }

.hidden-input { display: none; }

.animate-fade-in { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; } }

/* Follow-up & Jira specific styling */
.followup-generating-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  background: rgba(255, 255, 255, 0.02);
  border: 1px dashed rgba(255, 255, 255, 0.08);
  border-radius: var(--border-radius-lg);
  margin: 20px 0;
}

.followup-generating-state h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  margin: 16px 0 8px 0;
}

.followup-generating-state p {
  font-size: 14px;
  color: var(--text-muted);
  max-width: 400px;
}

.followup-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  background: rgba(255, 255, 255, 0.02);
  border: 1px dashed rgba(255, 255, 255, 0.08);
  border-radius: var(--border-radius-lg);
  margin: 20px 0;
}

.followup-empty-state svg {
  color: var(--primary);
  opacity: 0.8;
  margin-bottom: 16px;
}

.followup-empty-state h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
}

.followup-empty-state p {
  font-size: 14px;
  color: var(--text-muted);
  max-width: 400px;
  margin-bottom: 16px;
}

.spinner-large {
  display: inline-block;
  width: 40px;
  height: 40px;
  border: 3px solid rgba(99, 102, 241, 0.15);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spinLarge 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spinLarge {
  to { transform: rotate(360deg); }
}

/* ── Chat Tab Styles ── */
.chat-tab-pane {
  gap: 0 !important;
}

.chat-tab-container {
  display: flex;
  flex-direction: column;
  height: 580px;
  background: var(--bg-panel, rgba(30, 41, 59, 0.4));
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  overflow: hidden;
  backdrop-filter: blur(16px);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.35);
}

.chat-tab-header {
  padding: 16px 20px;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.chat-tab-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.chat-tab-title h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
}

.chat-tab-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

.chat-tab-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(0, 0, 0, 0.05);
}

.chat-tab-suggestions {
  padding: 16px 20px;
  background: rgba(0, 0, 0, 0.1);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.chat-tab-suggestions .suggestions-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.chat-suggestions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.chat-suggestion-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  color: var(--text-main);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  transition: var(--transition-smooth);
}

.chat-suggestion-btn:hover {
  background: rgba(99, 102, 241, 0.08);
  border-color: var(--primary);
  transform: translateY(-1px);
}

.chat-suggestion-btn .btn-icon {
  font-size: 16px;
}

.chat-suggestion-btn .btn-text {
  font-weight: 500;
}

.chat-tab-input-form {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 20px;
  background: rgba(0, 0, 0, 0.2);
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.chat-tab-textarea {
  flex: 1;
  background: var(--bg-input, rgba(0, 0, 0, 0.2));
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  color: var(--text-main);
  padding: 12px 16px;
  font-size: 13.5px;
  resize: none;
  line-height: 1.4;
  outline: none;
  transition: var(--transition-smooth);
}

.chat-tab-textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 8px var(--primary-glow);
}

.chat-tab-send-btn {
  width: 44px;
  height: 44px;
  border-radius: var(--border-radius-md);
  background: var(--primary);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--transition-smooth);
  flex-shrink: 0;
}

.chat-tab-send-btn:hover {
  background: hsl(244, 90%, 65%);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--primary-glow);
}

.chat-tab-send-btn:disabled {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

/* ── System Demo Styles ── */
.view-demo {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
}

.demo-card {
  background: var(--bg-panel);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-main);
  padding: 24px;
  transition: var(--transition-smooth);
}

.pipeline-card {
  overflow: hidden;
}

.panel-section-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 4px;
}

.panel-section-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 24px;
}

/* Interactive Pipeline Graph */
.pipeline-flow-wrapper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  overflow-x: auto;
  padding: 20px 10px;
  gap: 8px;
  width: 100%;
}

.pipeline-node-container {
  position: relative;
  border-radius: var(--border-radius-md);
  padding: 3px;
  transition: var(--transition-smooth);
  border: 2px solid transparent;
}

.pipeline-node-container.active {
  border-color: var(--primary);
  box-shadow: 0 0 14px var(--primary-glow);
}

.pipeline-node-container.current {
  animation: nodePulse 1.5s infinite;
}

@keyframes nodePulse {
  0% { transform: scale(1); box-shadow: 0 0 0 0 hsla(var(--primary-hue), 90%, 65%, 0.4); }
  70% { transform: scale(1.03); box-shadow: 0 0 0 8px hsla(var(--primary-hue), 90%, 65%, 0); }
  100% { transform: scale(1); box-shadow: 0 0 0 0 hsla(var(--primary-hue), 90%, 65%, 0); }
}

.pipeline-node {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 14px 18px;
  min-width: 145px;
  text-align: center;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  transition: var(--transition-smooth);
}

.pipeline-node:hover {
  background: rgba(255, 255, 255, 0.03);
  transform: translateY(-2px);
  border-color: var(--primary);
}

.node-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: var(--border-radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  position: relative;
}

.purple-glow {
  color: #c084fc;
  box-shadow: 0 0 10px rgba(192, 132, 252, 0.15);
}

.indigo-glow {
  color: #818cf8;
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.15);
}

.agent-number-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-main);
}

.node-name {
  font-family: var(--font-display);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-main);
}

.node-sub {
  font-size: 11px;
  color: var(--text-muted);
}

.flow-arrow {
  color: var(--border-color);
  transition: var(--transition-smooth);
  flex-shrink: 0;
}

.flow-arrow.running {
  color: var(--primary);
  animation: arrowGlow 1.2s infinite;
}

.flow-arrow.completed {
  color: var(--success);
}

@keyframes arrowGlow {
  0% { opacity: 0.4; transform: translateX(0); }
  50% { opacity: 1; transform: translateX(4px); }
  100% { opacity: 0.4; transform: translateX(0); }
}

.split-arrows {
  width: 40px;
  height: 80px;
  flex-shrink: 0;
  color: var(--border-color);
  display: flex;
  align-items: center;
}

.split-path-svg {
  width: 100%;
  height: 100%;
}

.split-path-svg path {
  stroke: var(--border-color);
  fill: none;
  transition: var(--transition-smooth);
}

.split-path-svg path.running {
  stroke: var(--primary);
  stroke-dasharray: 6 3;
  animation: pathFlow 1.2s linear infinite;
}

.split-path-svg path.completed {
  stroke: var(--success);
}

@keyframes pathFlow {
  from { stroke-dashoffset: 20; }
  to { stroke-dashoffset: 0; }
}

.parallel-agents-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-node {
  min-width: 155px;
}

/* Header Button Demo */
.demo-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-main);
  font-weight: 600;
  border-radius: var(--border-radius-sm);
  padding: 8px 14px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: var(--transition-smooth);
}

.demo-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--primary);
}

.demo-btn.active {
  background: var(--primary-glow-strong);
  border-color: var(--primary);
}

.demo-pulse-dot {
  width: 8px;
  height: 8px;
  background-color: var(--success);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--success);
  animation: pulse 1.8s infinite;
}

/* Two Column Demo Grid */
.demo-split-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 24px;
  align-items: stretch;
}

@media (max-width: 1024px) {
  .demo-split-grid {
    grid-template-columns: 1fr;
  }
}

.demo-left-column {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Terminal Card */
.terminal-card {
  background: #0f172a;
  border-color: rgba(255, 255, 255, 0.06);
  padding: 0;
  overflow: hidden;
  height: 250px;
  display: flex;
  flex-direction: column;
}

.terminal-card-header {
  background: #1e293b;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.terminal-dots {
  display: flex;
  gap: 6px;
  margin-right: 16px;
}

.terminal-dots span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.dot-red { background: #ef4444; }
.dot-yellow { background: #eab308; }
.dot-green { background: #22c55e; }

.terminal-title {
  font-family: monospace;
  font-size: 11.5px;
  color: #94a3b8;
  flex: 1;
}

.terminal-status-badge {
  font-family: monospace;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.05);
  color: #94a3b8;
}

.terminal-status-badge.active {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}

.terminal-card-body {
  padding: 16px;
  overflow-y: auto;
  font-family: 'Fira Code', 'Courier New', monospace;
  font-size: 12px;
  color: #cbd5e1;
  flex: 1;
  line-height: 1.5;
}

.terminal-empty-text {
  color: #64748b;
  text-align: center;
  padding-top: 40px;
  font-style: italic;
}

.terminal-log-line {
  margin-bottom: 6px;
  white-space: pre-wrap;
}

.log-time {
  color: #64748b;
  margin-right: 8px;
}

.log-message.log-ws-connect { color: #38bdf8; font-weight: 600; }
.log-message.log-ws-send { color: #f472b6; }
.log-message.log-ws-recv { color: #4ade80; }

/* UI Preview Card */
.ui-preview-card {
  padding: 20px;
}

.ui-preview-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}

.ui-preview-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--primary);
}

.preview-meeting-title h3 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
}

.preview-meeting-date {
  font-size: 11px;
  color: var(--text-muted);
}

.preview-transcript-container {
  margin-top: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 12px;
}

.preview-transcript-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 6px;
  letter-spacing: 0.5px;
}

.preview-transcript-text {
  font-family: monospace;
  font-size: 11.5px;
  color: var(--text-main);
  white-space: pre-wrap;
  opacity: 0.85;
}

.preview-live-fields {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  margin-top: 18px;
}

.preview-summary-box, .preview-actions-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-field-header {
  display: flex;
  align-items: center;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-muted);
}

.preview-streaming-badge {
  font-size: 9px;
  background: var(--primary-glow-strong);
  color: var(--primary);
  padding: 1px 6px;
  border-radius: 10px;
  margin-left: 8px;
  font-weight: 700;
  animation: pulse 1.5s infinite;
}

.preview-summary-text-box {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 14px;
  font-size: 13.5px;
  line-height: 1.55;
  min-height: 80px;
  color: var(--text-main);
  transition: var(--transition-smooth);
}

.preview-summary-text-box.streaming {
  border-color: var(--primary);
  box-shadow: 0 0 10px var(--primary-glow);
}

.preview-empty-desc {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.preview-actions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-action-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  padding: 12px 14px;
}

.preview-action-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.act-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-main);
}

.act-prio {
  font-size: 9.5px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.act-prio.high { background: var(--danger-glow); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.2); }
.act-prio.medium { background: var(--warning-glow); color: var(--warning); border: 1px solid rgba(234, 179, 8, 0.2); }
.act-prio.low { background: var(--info-glow); color: var(--info); border: 1px solid rgba(56, 189, 248, 0.2); }

.preview-action-meta {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 8px;
}

/* Inspector Card */
.inspector-card {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
}

.inspector-header {
  background: rgba(0, 0, 0, 0.15);
  border-bottom: 1px solid var(--border-color);
  overflow-x: auto;
}

.inspector-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 12px 0 12px;
}

.inspect-tab-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  white-space: nowrap;
  transition: var(--transition-smooth);
}

.inspect-tab-btn:hover {
  color: var(--text-main);
}

.inspect-tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.inspector-body {
  padding: 18px;
  flex: 1;
  overflow-y: auto;
}

.inspector-pane {
  display: none;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}

.inspector-pane.active {
  display: flex;
  animation: fadeIn 0.3s ease-out;
}

.pane-file-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pane-file-info span {
  font-family: monospace;
  font-size: 12.5px;
  color: var(--text-main);
  font-weight: 600;
}

.badge-tag {
  font-size: 9px;
  font-weight: 700;
  background: var(--primary-glow);
  color: var(--primary);
  border: 1px solid var(--border-color);
  padding: 2px 8px;
  border-radius: 4px;
}

.code-block-display {
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  padding: 16px;
  overflow-x: auto;
  font-family: 'Fira Code', 'Courier New', monospace;
  font-size: 12.5px;
  line-height: 1.55;
  color: #e2e8f0;
  max-height: 520px;
  overflow-y: auto;
}

.light-theme .code-block-display {
  background: rgba(0, 0, 0, 0.03);
  color: #1e293b;
}

.light-theme .terminal-card {
  border-color: rgba(0, 0, 0, 0.08);
}
</style>

