import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  Search,
  Database,
  Send,
  Trash2,
  X,
  FileText,
  Upload,
  Download,
  BarChart3,
  ChevronLeft,
  MessageSquare,
  Sparkles,
  Loader2,
  FileCheck,
  LogOut,
  User,
  Lock,
  Mail,
  Edit2,
  BookOpen,
  Layers,
  Copy,
  Check
} from 'lucide-react';

const resolveDocumentName = (rawSource, docs = []) => {
  if (!rawSource) return 'Knowledge Base';

  // Try exact match with stored_filename, id, or name
  const match = docs.find(d => 
    d.stored_filename === rawSource || 
    d.id === rawSource || 
    d.name === rawSource ||
    (d.stored_filename && rawSource.includes(d.stored_filename)) ||
    (d.id && rawSource.includes(d.id))
  );
  if (match) return match.name;

  // Try UUID match
  const uuidMatch = rawSource.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
  if (uuidMatch) {
    const uuidStr = uuidMatch[1];
    const docByUuid = docs.find(d => d.id === uuidStr || (d.stored_filename && d.stored_filename.includes(uuidStr)));
    if (docByUuid) return docByUuid.name;
    
    // If user has uploaded 1 document, default to it
    if (docs.length === 1 && docs[0].name) {
      return docs[0].name;
    }

    const ext = rawSource.includes('.') ? '.' + rawSource.split('.').pop() : '';
    return `Doc-${uuidStr.slice(0, 8)}${ext}`;
  }

  return rawSource;
};

export default function App() {
  const vectraModel = "Vectra Mini";

  // Authentication State
  const [authToken, setAuthToken] = useState(() => {
    return localStorage.getItem('vectra_auth_token');
  });
  const [loginUser, setLoginUser] = useState(() => {
    const saved = localStorage.getItem('vectra_login_user');
    if (saved) {
      try { return JSON.parse(saved); } catch (e) { }
    }
    return null;
  });
  const [authScreen, setAuthScreen] = useState('login'); // 'login' | 'register'

  // Auth Form Fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [authError, setAuthError] = useState('');

  // Sidebar UI states
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [convSearchQuery, setConvSearchQuery] = useState("");
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  // Rename Conversation States
  const [editingConvId, setEditingConvId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Modal State
  const [showDocsModal, setShowDocsModal] = useState(false);
  const [sourcesModalData, setSourcesModalData] = useState(null); // { sources: [...] }
  const [sourcesFilterTab, setSourcesFilterTab] = useState('all'); // 'all' | 'vector' | 'graph'
  const [copiedIdx, setCopiedIdx] = useState(null);

  // Uploading States
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");

  // Refs
  const fileInputRef = useRef(null);
  const chatInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const activeReaderRef = useRef(null);
  const prevDocsRef = useRef([]);

  // Load initial conversations from LocalStorage or default
  const [conversations, setConversations] = useState(() => {
    const saved = localStorage.getItem('vectra_conversations');
    if (saved) {
      try { return JSON.parse(saved); } catch (e) { }
    }
    return [
      {
        id: "conv-1",
        title: "New chat",
      }
    ];
  });

  const [activeConversationId, setActiveConversationId] = useState(() => {
    const saved = localStorage.getItem('vectra_conversations');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.length > 0) return parsed[0].id;
      } catch (e) { }
    }
    return "conv-1";
  });

  const activeConversationRaw = conversations.find(c => c.id === activeConversationId) || conversations[0] || { id: "conv-1", messages: [] };
  const activeConversation = {
    ...activeConversationRaw,
    messages: activeConversationRaw.messages || []
  };

  // Documents list fetched dynamically from backend
  const [documents, setDocuments] = useState([]);

  // Input Box States
  const [inputVal, setInputVal] = useState("");
  const [isLlmGenerating, setIsLlmGenerating] = useState(false);

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeConversation?.messages, isLlmGenerating]);

  // Persist auth tokens
  useEffect(() => {
    if (authToken) {
      localStorage.setItem('vectra_auth_token', authToken);
    } else {
      localStorage.removeItem('vectra_auth_token');
    }
  }, [authToken]);

  // Persist user profiles
  useEffect(() => {
    if (loginUser) {
      localStorage.setItem('vectra_login_user', JSON.stringify(loginUser));
    } else {
      localStorage.removeItem('vectra_login_user');
    }
  }, [loginUser]);

  // Persist conversations
  useEffect(() => {
    localStorage.setItem('vectra_conversations', JSON.stringify(conversations));
  }, [conversations]);

  // Fetch conversations list from database
  const fetchConversations = async () => {
    if (!authToken) return;
    try {
      const res = await fetch('/chat/conversations', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const mapped = data.map(c => ({
          id: c.id,
          title: c.title || "Untitled Conversation",
          messages: [] // Lazily loaded when selected
        }));

        setConversations(prev => {
          // Keep unsaved conversations (starting with conv-)
          const unsaved = prev.filter(c => c.id.startsWith("conv-"));
          const combined = [...unsaved];

          // Add database conversations, avoiding duplicates
          mapped.forEach(mc => {
            if (!combined.some(c => c.id === mc.id)) {
              combined.push(mc);
            }
          });

          // Restore active conversation ID
          const savedActiveId = localStorage.getItem('vectra_active_conversation_id');
          if (savedActiveId && combined.some(c => c.id === savedActiveId)) {
            setActiveConversationId(savedActiveId);
          } else if (combined.length > 0) {
            setActiveConversationId(combined[0].id);
          }

          return combined;
        });
      }
    } catch (err) {
      console.error('Failed to fetch conversations:', err);
    }
  };

  // Fetch messages for a specific conversation
  const fetchConversationMessages = async (convId) => {
    if (!authToken || !convId || convId.startsWith("conv-")) return;
    try {
      const res = await fetch(`/chat/conversations/${convId}/messages`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const mappedMsgs = data.map(m => {
          const chartSource = m.sources ? m.sources.find(s => s.type === 'chart') : null;
          const downloadSource = m.sources ? m.sources.find(s => s.type === 'download') : null;
          const citations = m.sources ? m.sources.filter(s => s.type !== 'chart' && s.type !== 'download') : null;
          return {
            sender: m.role,
            text: m.content,
            sources: citations && citations.length > 0 ? citations : null,
            chartFigure: chartSource ? chartSource.figure : null,
            downloadUrl: downloadSource ? downloadSource.downloadUrl : null,
            downloadFilename: downloadSource ? downloadSource.downloadFilename : null
          };
        });

        if (mappedMsgs.length === 0) {
          mappedMsgs.push({
            sender: "assistant",
            text: "Hello! Started a new session. Upload files or ask me anything."
          });
        }

        setConversations(prev => prev.map(c => {
          if (c.id === convId) {
            return { ...c, messages: mappedMsgs };
          }
          return c;
        }));
      }
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  };

  // Fetch documents from backend dynamically
  const fetchDocuments = async () => {
    if (!authToken) return;
    try {
      const res = await fetch('/documents', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const mapped = data.map(doc => ({
          id: doc.id,
          name: doc.original_filename,
          stored_filename: doc.stored_filename,
          size: `${(doc.file_size / (1024 * 1024)).toFixed(2)} MB`,
          type: doc.file_type.toUpperCase(),
          status: doc.status,
          progress: doc.progress || 0,
          currentStep: doc.current_step || '',
          errorMessage: doc.error_message || ''
        }));
        setDocuments(mapped);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
  };

  useEffect(() => {
    if (authToken) {
      fetchDocuments();
      fetchConversations();
    }
  }, [authToken]);

  useEffect(() => {
    if (activeConversationId) {
      localStorage.setItem('vectra_active_conversation_id', activeConversationId);
      if (!activeConversationId.startsWith("conv-")) {
        const active = conversations.find(c => c.id === activeConversationId);
        if (active && (!active.messages || active.messages.length === 0)) {
          fetchConversationMessages(activeConversationId);
        }
      }
    }
  }, [activeConversationId, authToken]);

  // Handle visual banners when background tasks transition to READY or FAILED
  useEffect(() => {
    const prevDocs = prevDocsRef.current;
    if (prevDocs && prevDocs.length > 0 && documents.length > 0) {
      documents.forEach(doc => {
        const prev = prevDocs.find(p => p.id === doc.id);
        if (prev) {
          if (prev.status !== 'READY' && doc.status === 'READY') {
            const notice = document.getElementById('upload-notice');
            if (notice) {
              notice.querySelector('span').innerText = `"${doc.name}" successfully processed & indexed in databases!`;
              notice.style.background = '';
              notice.style.borderColor = '';
              notice.style.color = '';
              notice.style.display = 'flex';
              setTimeout(() => {
                notice.style.display = 'none';
              }, 4000);
            }
          }
          if (prev.status !== 'FAILED' && doc.status === 'FAILED') {
            const notice = document.getElementById('upload-notice');
            if (notice) {
              notice.querySelector('span').innerText = `"${doc.name}" ingestion failed: ${doc.errorMessage || 'Unknown error'}`;
              notice.style.background = 'rgba(239, 68, 68, 0.15)';
              notice.style.borderColor = '#ef4444';
              notice.style.color = '#b91c1c';
              notice.style.display = 'flex';
              setTimeout(() => {
                notice.style.display = 'none';
                notice.style.background = '';
                notice.style.borderColor = '';
                notice.style.color = '';
              }, 6000);
            }
          }
        }
      });
    }
    prevDocsRef.current = documents;
  }, [documents]);

  // Poll for processing documents every 3 seconds
  useEffect(() => {
    if (!authToken) return;

    const hasProcessing = documents.some(doc =>
      doc.status === 'QUEUED' || doc.status === 'PROCESSING' || doc.status === 'UPLOADING'
    );

    if (!hasProcessing) return;

    const interval = setInterval(() => {
      fetchDocuments();
    }, 3000);

    return () => clearInterval(interval);
  }, [documents, authToken]);

  // ChatGPT-style focus on keydown when not in inputs
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') {
        return;
      }
      // Focus on printable key press
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && authToken) {
        chatInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [authToken]);

  // Handle Login Submission
  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');

    if (!email || !password) {
      setAuthError('Email and Password are required.');
      return;
    }

    try {
      const res = await fetch('/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Incorrect credentials.');
      }
      const data = await res.json();

      // Retrieve full name from registration profiles cache
      const cachedProfiles = JSON.parse(localStorage.getItem('vectra_user_profiles') || '{}');
      let name = cachedProfiles[email] || '';
      if (!name) {
        // Fallback: Parse dynamically from email prefix
        const rawName = email.split('@')[0];
        const firstSegment = rawName.split(/[\._-]/)[0];
        name = firstSegment.charAt(0).toUpperCase() + firstSegment.slice(1);
      }

      setLoginUser({
        name: name,
        email: email
      });
      setAuthToken(data.access_token);
    } catch (err) {
      setAuthError(err.message);
    }
  };

  // Handle Register Submission
  const handleRegister = async (e) => {
    e.preventDefault();
    setAuthError('');

    if (!email || !password || !fullName) {
      setAuthError('Full Name, Email and Password are required.');
      return;
    }

    try {
      const registerRes = await fetch('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, full_name: fullName, password })
      });
      if (!registerRes.ok) {
        const errData = await registerRes.json();
        throw new Error(errData.detail || 'Email already registered.');
      }

      // Automatically log in after registration
      const tokenRes = await fetch('/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!tokenRes.ok) {
        throw new Error('Registration succeeded, but login failed.');
      }
      const data = await tokenRes.json();

      // Save full name in profile cache
      const cachedProfiles = JSON.parse(localStorage.getItem('vectra_user_profiles') || '{}');
      cachedProfiles[email] = fullName;
      localStorage.setItem('vectra_user_profiles', JSON.stringify(cachedProfiles));

      setLoginUser({
        name: fullName,
        email: email
      });
      setAuthToken(data.access_token);
    } catch (err) {
      setAuthError(err.message);
    }
  };

  // Handle Logout
  const handleLogout = () => {
    setAuthToken(null);
    setLoginUser(null);
    setEmail('');
    setPassword('');
    setFullName('');
    setConversations([
      {
        id: "conv-1",
        title: "New chat",
        messages: [
          { sender: "assistant", text: "Hello! I am Vectra AI, your Knowledge Graph Builder assistant. Ask me questions or upload files to ingest into the graph database." }
        ]
      }
    ]);
    setActiveConversationId("conv-1");
    localStorage.removeItem('vectra_auth_token');
    localStorage.removeItem('vectra_login_user');
    localStorage.removeItem('vectra_conversations');
    localStorage.removeItem('vectra_active_conversation_id');
  };

  // Create new conversation
  const createNewConversation = () => {
    // Check if the current conversation is empty
    const activeConv = conversations.find(c => c.id === activeConversationId);
    if (activeConv && activeConv.messages.length <= 1) {
      return;
    }

    // Check if there is any other empty conversation to redirect to
    const emptyConv = conversations.find(c => c.messages.length <= 1);
    if (emptyConv) {
      setActiveConversationId(emptyConv.id);
      return;
    }

    const newId = `conv-${Date.now()}`;
    const newConv = {
      id: newId,
      title: "New chat",
      messages: [
        { sender: "assistant", text: "Hello! Started a new session. Upload files or ask me anything." }
      ]
    };
    setConversations([newConv, ...conversations]);
    setActiveConversationId(newId);
  };

  // Delete a conversation from db and local state
  const deleteConversation = async (e, convId) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this conversation?")) {
      if (!convId.startsWith("conv-") && authToken) {
        try {
          const res = await fetch(`/chat/conversations/${convId}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${authToken}`
            }
          });
          if (res.status === 401) {
            handleLogout();
            return;
          }
          if (!res.ok) {
            throw new Error('Failed to delete conversation.');
          }
        } catch (err) {
          alert(err.message);
          return;
        }
      }

      const updated = conversations.filter(c => c.id !== convId);
      setConversations(updated);

      if (activeConversationId === convId) {
        if (updated.length > 0) {
          setActiveConversationId(updated[0].id);
        } else {
          createNewConversation();
        }
      }
    }
  };

  // Handle downloading exported spreadsheet files securely
  const handleDownloadFile = async (downloadUrl, filename) => {
    try {
      const targetUrl = downloadUrl.startsWith('http') ? downloadUrl : downloadUrl;
      const res = await fetch(targetUrl, {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (!res.ok) {
        window.open(`${targetUrl}?token=${encodeURIComponent(authToken)}`, '_blank');
        return;
      }
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename || 'download.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      window.open(`${downloadUrl}?token=${encodeURIComponent(authToken)}`, '_blank');
    }
  };

  // Stop LLM streaming generation

  const stopGenerating = () => {
    if (activeReaderRef.current) {
      activeReaderRef.current.cancel();
      activeReaderRef.current = null;
    }
    setIsLlmGenerating(false);
  };

  // Handle Send Message (Actual SSE Streaming)
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!inputVal.trim() || isLlmGenerating || !authToken) return;

    const userMsg = { sender: "user", text: inputVal };
    const currentMessages = [...activeConversation.messages, userMsg];

    // Add user message locally
    setConversations(prev => prev.map(c => {
      if (c.id === activeConversationId) {
        return {
          ...c,
          messages: currentMessages
        };
      }
      return c;
    }));

    const question = inputVal;
    setInputVal("");
    setIsLlmGenerating(true);

    // Add a placeholder assistant message for incoming stream
    const updatedMessages = [...currentMessages, { sender: "assistant", text: "" }];
    setConversations(prev => prev.map(c => {
      if (c.id === activeConversationId) {
        return {
          ...c,
          messages: updatedMessages
        };
      }
      return c;
    }));

    try {
      const res = await fetch('/chat/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          question,
          conversation_id: (activeConversationId && activeConversationId.startsWith("conv-"))
            ? null
            : activeConversationId
        })
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (!res.ok) {
        throw new Error('Query error. Is Ollama or the backend offline?');
      }

      const reader = res.body.getReader();
      activeReaderRef.current = reader;
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let fullAnswer = "";

      let currentConvId = activeConversationId;
      let currentEvent = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last incomplete line in buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("event: ")) {
            currentEvent = trimmed.slice(7);
          } else if (trimmed.startsWith("data: ")) {
            try {
              const payload = JSON.parse(trimmed.slice(6));

              if (payload.conversation_id !== undefined) {
                const dbId = payload.conversation_id;
                const oldId = currentConvId;
                currentConvId = dbId;
                setConversations(prev => prev.map(c => {
                  if (c.id === oldId) {
                    return { ...c, id: dbId };
                  }
                  return c;
                }));
                setActiveConversationId(dbId);
              }

              if (payload.sources !== undefined) {
                setConversations(prev => prev.map(c => {
                  if (c.id === currentConvId) {
                    const msgs = [...c.messages];
                    if (msgs.length > 0) {
                      msgs[msgs.length - 1] = {
                        ...msgs[msgs.length - 1],
                        sources: payload.sources
                      };
                    }
                    return { ...c, messages: msgs };
                  }
                  return c;
                }));
              }

              if (payload.figure !== undefined) {
                setConversations(prev => prev.map(c => {
                  if (c.id === currentConvId) {
                    const msgs = [...c.messages];
                    if (msgs.length > 0) {
                      msgs[msgs.length - 1] = {
                        ...msgs[msgs.length - 1],
                        chartFigure: payload.figure
                      };
                    }
                    return { ...c, messages: msgs };
                  }
                  return c;
                }));
              }

              if (payload.downloadUrl !== undefined || currentEvent === 'download') {
                const dUrl = payload.downloadUrl || payload.download_url;
                const dFilename = payload.downloadFilename || payload.download_filename || payload.filename;
                if (dUrl) {
                  setConversations(prev => prev.map(c => {
                    if (c.id === currentConvId) {
                      const msgs = [...c.messages];
                      if (msgs.length > 0) {
                        msgs[msgs.length - 1] = {
                          ...msgs[msgs.length - 1],
                          downloadUrl: dUrl,
                          downloadFilename: dFilename
                        };
                      }
                      return { ...c, messages: msgs };
                    }
                    return c;
                  }));
                }
              }

              if (payload.token) {
                fullAnswer += payload.token;

                // Update assistant message with accumulated tokens
                setConversations(prev => prev.map(c => {
                  if (c.id === currentConvId) {
                    const msgs = [...c.messages];
                    if (msgs.length > 0) {
                      msgs[msgs.length - 1] = {
                        ...msgs[msgs.length - 1],
                        sender: "assistant",
                        text: fullAnswer
                      };
                    }
                    return { ...c, messages: msgs };
                  }
                  return c;
                }));
              }
            } catch (err) {
              // Ignore partial JSON parsing errors
            }
          }
        }
      }
    } catch (err) {
      const errorMsg = { sender: "assistant", text: `Error: ${err.message}` };
      setConversations(prev => prev.map(c => {
        if (c.id === activeConversationId) {
          return {
            ...c,
            messages: [...currentMessages, errorMsg]
          };
        }
        return c;
      }));
    } finally {
      activeReaderRef.current = null;
      setIsLlmGenerating(false);
    }
  };

  // Trigger File Input Click
  const triggerFileUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0 || !authToken) return;

    setIsUploading(true);
    setUploadProgress(`Ingesting ${files.length} file(s)...`);

    try {
      // Perform concurrent background uploads
      const uploadPromises = files.map(async (file) => {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/documents/upload', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${authToken}` },
          body: formData
        });
        if (res.status === 401) {
          handleLogout();
          throw new Error("Unauthorized");
        }
        if (!res.ok) {
          throw new Error(`Failed to upload ${file.name}`);
        }
        return res.json();
      });

      await Promise.all(uploadPromises);
      await fetchDocuments();
    } catch (err) {
      alert(err.message);
    } finally {
      setIsUploading(false);
      setUploadProgress("");
    }
  };

  const handleDeleteDocument = async (docId) => {
    if (!authToken) return;
    try {
      const res = await fetch(`/documents/${docId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        setDocuments(prev => prev.filter(doc => doc.id !== docId));
      } else {
        throw new Error('Failed to delete document.');
      }
    } catch (err) {
      alert(err.message);
    }
  };

  // Filter conversations
  const filteredConversations = conversations.filter(c =>
    c.title.toLowerCase().includes(convSearchQuery.toLowerCase())
  );

  // Extract first name for dynamic Claude-like greeting
  const getFirstName = () => {
    if (!loginUser?.name) return 'Guest';
    return loginUser.name.split(' ')[0];
  };

  return (
    <>
      {/* Dynamic Background Blobs */}
      <div className="bg-blobs">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
        <div className="blob blob-3"></div>
      </div>

      {/* Conditional Render: Auth Screen vs. Main Workspace */}
      {!authToken ? (
        <div className="auth-wrapper">
          <div className="auth-card">
            {/* Split layout: Left Branding panel for desktop */}
            <div className="auth-left">
              <h2 style={{ fontSize: '2rem', fontWeight: 800 }}>Vectra AI</h2>
              <p style={{ opacity: 0.8, fontSize: '0.95rem', lineHeight: '1.6' }}>
                Build modern semantic databases instantly. Ingest PDFs, text sheets, and JSON schemas to auto-extract entities, match vectors, and map relationships in your graph database.
              </p>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '24px' }}>
                <span style={{ fontSize: '0.75rem', background: 'rgba(255,255,255,0.15)', padding: '6px 12px', borderRadius: '20px' }}>Neo4j Graph Mapping</span>
                <span style={{ fontSize: '0.75rem', background: 'rgba(255,255,255,0.15)', padding: '6px 12px', borderRadius: '20px' }}>Qdrant Multi-Tenancy</span>
              </div>
            </div>

            {/* Split layout: Right Form fields panel */}
            <div className="auth-right">
              <div style={{ textAlign: 'center' }}>
                <h3 className="auth-title" style={{ fontSize: '1.5rem' }}>
                  {authScreen === 'login' ? 'Welcome back' : 'Create account'}
                </h3>
                <p className="auth-subtitle">
                  {authScreen === 'login' ? 'Sign in to access your knowledge graph' : 'Set up your profile'}
                </p>
              </div>

              {authError && <div className="auth-error">{authError}</div>}

              <form onSubmit={authScreen === 'login' ? handleLogin : handleRegister} className="auth-form">
                {authScreen === 'register' && (
                  <div className="auth-group">
                    <label className="auth-label">Full Name</label>
                    <div style={{ position: 'relative' }}>
                      <User size={16} style={{ position: 'absolute', left: '12px', top: '15px', color: 'var(--text-muted)' }} />
                      <input
                        type="text"
                        placeholder="Max Butler"
                        className="auth-input"
                        style={{ paddingLeft: '38px', width: '100%' }}
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                <div className="auth-group">
                  <label className="auth-label">Email Address</label>
                  <div style={{ position: 'relative' }}>
                    <Mail size={16} style={{ position: 'absolute', left: '12px', top: '15px', color: 'var(--text-muted)' }} />
                    <input
                      type="email"
                      placeholder="max@example.com"
                      className="auth-input"
                      style={{ paddingLeft: '38px', width: '100%' }}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="auth-group">
                  <label className="auth-label">Password</label>
                  <div style={{ position: 'relative' }}>
                    <Lock size={16} style={{ position: 'absolute', left: '12px', top: '15px', color: 'var(--text-muted)' }} />
                    <input
                      type="password"
                      placeholder="••••••••"
                      className="auth-input"
                      style={{ paddingLeft: '38px', width: '100%' }}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </div>
                </div>

                <button type="submit" className="auth-submit-btn" style={{ marginTop: '8px' }}>
                  <span>{authScreen === 'login' ? 'Login to Vectra' : 'Register Account'}</span>
                </button>
              </form>

              <div className="auth-footer" style={{ marginTop: '8px' }}>
                {authScreen === 'login' ? (
                  <>
                    Don't have an account?
                    <button onClick={() => setAuthScreen('register')} className="auth-toggle-link">
                      Register
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?
                    <button onClick={() => setAuthScreen('login')} className="auth-toggle-link">
                      Login
                    </button>
                  </>
                )}
              </div>
            </div>

          </div>
        </div>
      ) : (
        <div className="app-container">

          {/* SIDEBAR */}
          <aside className={`sidebar ${sidebarExpanded ? 'expanded' : ''}`}>
            <div className="sidebar-top">

              {/* Logo */}
              <div className="sidebar-logo-container">
                <div className="sidebar-logo">V</div>
                {sidebarExpanded && <span className="sidebar-title">Vectra AI</span>}
              </div>

              {/* Conditionally Render: Icons (if collapsed) vs. Chats List (if expanded) */}
              {!sidebarExpanded ? (
                <div className="sidebar-nav">
                  {/* New Chat Button (Creates a new session but does NOT expand the sidebar) */}
                  <button
                    className="nav-item"
                    title="New Session"
                    onClick={createNewConversation}
                  >
                    <Plus size={20} />
                  </button>

                  {/* Toggle Conversation List (Extra Button to Expand) */}
                  <button
                    className="nav-item"
                    title="Conversation List"
                    onClick={() => {
                      setSearchOpen(false);
                      setSidebarExpanded(true);
                    }}
                  >
                    <MessageSquare size={20} />
                  </button>

                  {/* Search Toggle */}
                  <button
                    className="nav-item"
                    title="Search Sessions"
                    onClick={() => {
                      setSearchOpen(true);
                      setSidebarExpanded(true);
                    }}
                  >
                    <Search size={20} />
                  </button>

                  {/* Manage Documents Database Icon */}
                  <button
                    className="nav-item"
                    title="Uploaded Documents"
                    onClick={() => setShowDocsModal(true)}
                  >
                    <Database size={20} />
                  </button>
                </div>
              ) : (
                /* Expanded Sidebar Mode: Hide original buttons and show chat listing (Gemini style) */
                <div className="chat-list-container" style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem', letterSpacing: '0.5px', textTransform: 'uppercase', opacity: 0.8 }}>Chats</span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={createNewConversation}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--black-magic)' }}
                        title="New Chat"
                      >
                        <Plus size={15} />
                      </button>
                      <button
                        onClick={() => setSearchOpen(!searchOpen)}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--black-magic)' }}
                        title="Filter chats"
                      >
                        <Search size={15} />
                      </button>
                    </div>
                  </div>

                  {searchOpen && (
                    <div style={{ marginBottom: '16px' }}>
                      <input
                        type="text"
                        placeholder="Search chats..."
                        className="chat-input"
                        style={{
                          background: 'rgba(255,255,255,0.4)',
                          padding: '8px 12px',
                          borderRadius: '8px',
                          border: '1px solid var(--glass-border)',
                          width: '100%',
                          fontSize: '0.85rem'
                        }}
                        value={convSearchQuery}
                        onChange={(e) => setConvSearchQuery(e.target.value)}
                      />
                    </div>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flexGrow: 1 }}>
                    {filteredConversations.length === 0 ? (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
                        No active sessions found
                      </div>
                    ) : (
                      filteredConversations.map(conv => (
                        <div
                          key={conv.id}
                          className={`chat-item ${conv.id === activeConversationId ? 'active' : ''}`}
                          onClick={() => setActiveConversationId(conv.id)}
                          style={{ display: 'flex', justifyContent: 'space-between', paddingRight: '12px' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1, overflow: 'hidden' }}>
                            <MessageSquare size={16} style={{ flexShrink: 0 }} />
                            <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{conv.title}</span>
                          </div>

                          <button
                            onClick={(e) => deleteConversation(e, conv.id)}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              cursor: 'pointer',
                              color: 'var(--text-muted)',
                              padding: '2px',
                              display: 'flex',
                              alignItems: 'center',
                              opacity: 0.6
                            }}
                            className="chat-delete-btn"
                            title="Delete chat"
                          >
                            <Trash2 size={13} style={{ flexShrink: 0 }} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Sidebar bottom Profile panel */}
            <div className="sidebar-profile">
              {/* Profile Popover Menu (renders above card when toggled) */}
              {showProfileMenu && (
                <>
                  <div className="popover-backdrop" onClick={() => setShowProfileMenu(false)} />
                  <div className="profile-popover">
                    <div className="popover-header">
                      <div className="profile-avatar-circle">
                        {loginUser?.name ? loginUser.name.charAt(0).toUpperCase() : 'U'}
                      </div>
                      <div className="popover-header-details">
                        <span className="popover-header-name">{loginUser?.name}</span>
                        <span className="popover-header-email">{loginUser?.email}</span>
                      </div>
                    </div>

                    <div className="popover-item" onClick={() => { alert('Upgrade plan window coming soon!'); setShowProfileMenu(false); }}>
                      <Sparkles size={14} />
                      <span>Upgrade plan</span>
                    </div>
                    <div className="popover-item" onClick={() => { alert('Personalization options coming soon!'); setShowProfileMenu(false); }}>
                      <Sparkles size={14} style={{ opacity: 0 }} />
                      <span>Personalization</span>
                    </div>
                    <div className="popover-item" onClick={() => { alert('Profile editor coming soon!'); setShowProfileMenu(false); }}>
                      <User size={14} />
                      <span>Profile</span>
                    </div>
                    <div className="popover-item" onClick={() => { alert('Settings window coming soon!'); setShowProfileMenu(false); }}>
                      <Sparkles size={14} style={{ opacity: 0 }} />
                      <span>Settings</span>
                    </div>
                    <div className="popover-item" onClick={() => { alert('Help desk coming soon!'); setShowProfileMenu(false); }}>
                      <Sparkles size={14} style={{ opacity: 0 }} />
                      <span>Help</span>
                    </div>

                    <div className="popover-divider" />

                    <button className="popover-item popover-item-logout" onClick={() => { handleLogout(); setShowProfileMenu(false); }}>
                      <LogOut size={14} />
                      <span>Log out</span>
                    </button>
                  </div>
                </>
              )}

              {/* Avatar trigger card (different based on collapsed/expanded sidebar) */}
              {!sidebarExpanded ? (
                <div
                  className="profile-avatar-circle"
                  style={{ cursor: 'pointer', margin: '0 auto' }}
                  onClick={() => setShowProfileMenu(!showProfileMenu)}
                  title={loginUser?.name || "Profile Menu"}
                >
                  {loginUser?.name ? loginUser.name.charAt(0).toUpperCase() : 'U'}
                </div>
              ) : (
                <div className="sidebar-profile-card" onClick={() => setShowProfileMenu(!showProfileMenu)}>
                  <div className="profile-avatar-circle">
                    {loginUser?.name ? loginUser.name.charAt(0).toUpperCase() : 'U'}
                  </div>
                  <div className="profile-card-details">
                    <span className="profile-card-name">{loginUser?.name}</span>
                    <span className="profile-card-model">{vectraModel}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Close Sidebar button */}
            <button
              className="collapse-btn"
              onClick={() => setSidebarExpanded(false)}
            >
              <ChevronLeft size={16} />
              <span>Collapse</span>
            </button>
          </aside>

          {/* MAIN DASHBOARD AREA */}
          <main className="main-dashboard">

            {/* Top Bar */}
            <div className="top-bar" style={{ marginBottom: '24px' }}>
              <div className="dropdown-selector">
                <Sparkles size={16} className="text-accent" />
                <span>Vectra Assistant v1.0</span>
              </div>

              {/* Removed center title & right logout panel for space */}
              <div></div>
            </div>

            {/* Notification notice for upload success */}
            <div
              id="upload-notice"
              className="upload-status"
              style={{ display: 'none', position: 'absolute', top: '90px', right: '32px', width: 'auto', zIndex: 90 }}
            >
              <FileCheck size={18} />
              <span>Documents successfully uploaded & indexed in Qdrant!</span>
            </div>

            {/* Active Document Ingestion Progress Logs */}
            {documents.filter(doc => doc.status !== 'READY').length > 0 && (
              <div className="active-ingestion-jobs" style={{
                margin: '0 auto 24px auto',
                maxWidth: '720px',
                width: '100%',
                background: 'rgba(255, 255, 255, 0.45)',
                borderRadius: '16px',
                border: '1px solid var(--glass-border)',
                padding: '12px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                boxShadow: '0 4px 30px rgba(0, 0, 0, 0.05)',
                backdropFilter: 'blur(10px)'
              }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--black-magic)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Loader2 size={14} className="animate-spin text-accent" />
                  <span>Ingestion Progress & System Logs</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {documents.filter(doc => doc.status !== 'READY').map(job => (
                    <div key={job.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.8rem', background: 'rgba(255,255,255,0.4)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(0,0,0,0.03)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                        <FileText size={14} style={{ color: job.status === 'FAILED' ? 'red' : 'var(--accent-color)', flexShrink: 0 }} />
                        <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.name}</span>
                        {job.status === 'FAILED' ? (
                          <span style={{ color: 'red', fontSize: '0.75rem', marginLeft: '6px' }}>(Failed: {job.errorMessage || 'Ingestion failed'})</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginLeft: '6px' }}>({job.currentStep || 'Processing...'})</span>
                        )}
                      </div>

                      {job.status !== 'FAILED' && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div style={{ width: '80px', height: '6px', background: 'rgba(0,0,0,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div style={{ width: `${job.progress}%`, height: '100%', background: 'var(--accent-color)', transition: 'width 0.3s ease' }}></div>
                          </div>
                          <span style={{ fontWeight: 700, minWidth: '35px', textAlign: 'right' }}>{job.progress}%</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Core Content Area */}
            {activeConversation.messages.length <= 1 ? (
              /* Welcome / Initial Dashboard View */
              <div className="welcome-container" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                <h1 className="welcome-header" style={{ fontSize: '2.5rem', display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center', marginBottom: '40px' }}>
                  <span>Hello {getFirstName()}.</span>
                  <span style={{ color: '#6b7a99', fontSize: '1.2rem', fontWeight: 400, letterSpacing: '0.3px', marginTop: '6px' }}>
                    Ready to build your knowledge base? Grab a coffee and let's map out some data.
                  </span>
                </h1>

                {/* Grid of Interactive Actions */}
                <div className="card-grid" style={{ maxWidth: '720px', margin: '0 auto', width: '100%' }}>

                  {/* Upload Card */}
                  <div className="glass-card" onClick={triggerFileUpload} style={{ minHeight: '180px' }}>
                    <div>
                      <div className="card-icon">
                        <Upload size={22} />
                      </div>
                      <h3 className="card-title" style={{ fontSize: '1.15rem' }}>Upload Documents</h3>
                      <p className="card-desc" style={{ fontSize: '0.85rem' }}>
                        Ingest PDFs, TXT, CSV, or JSON specifications. Automatically chunk and extract vector embeddings.
                      </p>
                    </div>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, alignSelf: 'flex-end', color: 'var(--accent-color)', marginTop: '8px' }}>
                      Click to browse files &rarr;
                    </span>
                  </div>

                  {/* Graph Card */}
                  <div className="glass-card" onClick={() => {
                    setInputVal("Generate a relational schema map from all active knowledge base documents.");
                  }} style={{ minHeight: '180px' }}>
                    <div>
                      <div className="card-icon">
                        <BarChart3 size={22} />
                      </div>
                      <h3 className="card-title" style={{ fontSize: '1.15rem' }}>Explore Knowledge Graph</h3>
                      <p className="card-desc" style={{ fontSize: '0.85rem' }}>
                        Query the mapped entities, generate semantic relational reports, and browse entity structures.
                      </p>
                    </div>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, alignSelf: 'flex-end', color: 'var(--accent-color)', marginTop: '8px' }}>
                      Explore graph relationships &rarr;
                    </span>
                  </div>

                </div>

                {isUploading && (
                  <div className="upload-status" style={{ maxWidth: '400px', margin: '24px auto 0 auto' }}>
                    <Loader2 size={16} className="animate-spin" />
                    <span>{uploadProgress}</span>
                  </div>
                )}
              </div>
            ) : (
              /* Active Chat Window View */
              <div className="chat-window" style={{ paddingBottom: '20px' }}>
                {activeConversation.messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`message-bubble ${msg.sender === 'user' ? 'user' : 'assistant'} ${msg.chartFigure ? 'has-chart' : ''}`}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      width: msg.chartFigure ? '100%' : undefined,
                      maxWidth: msg.chartFigure ? '100%' : undefined
                    }}
                  >
                    <div>{renderMessageText(cleanMessageText(msg.text))}</div>
                    {(() => {
                      let downloadUrl = msg.downloadUrl;
                      let downloadFilename = msg.downloadFilename;
                      if (!downloadUrl && msg.text) {
                        const downloadMatch = msg.text.match(/\/documents\/download\/([^\s\)]+)/);
                        if (downloadMatch) {
                          downloadUrl = downloadMatch[0];
                          downloadFilename = downloadMatch[1];
                        }
                      }
                      if (msg.sender === 'assistant' && downloadUrl) {
                        return (
                          <div style={{
                            marginTop: '8px',
                            background: 'rgba(255, 255, 255, 0.85)',
                            borderRadius: '12px',
                            border: '1px solid var(--glass-border)',
                            padding: '12px 16px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '12px',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.04)',
                            width: '100%',
                            maxWidth: '440px',
                            backdropFilter: 'blur(10px)'
                          }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', overflow: 'hidden' }}>
                              <div style={{
                                width: '36px',
                                height: '36px',
                                borderRadius: '8px',
                                background: 'rgba(79, 70, 229, 0.12)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0
                              }}>
                                <Download size={18} style={{ color: 'var(--accent-color)' }} />
                              </div>
                              <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                                <span style={{
                                  fontSize: '0.85rem',
                                  fontWeight: 600,
                                  color: 'var(--black-magic)',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap'
                                }}>
                                  {downloadFilename || 'exported_data.csv'}
                                </span>
                                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                  Extracted CSV Spreadsheet &bull; Ready to Download
                                </span>
                              </div>
                            </div>
                            <button
                              onClick={() => handleDownloadFile(downloadUrl, downloadFilename)}
                              style={{
                                background: 'var(--accent-color, #4f46e5)',
                                color: '#ffffff',
                                border: 'none',
                                padding: '6px 14px',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 6px rgba(79, 70, 229, 0.2)',
                                flexShrink: 0,
                                transition: 'opacity 0.2s'
                              }}
                              onMouseOver={(e) => e.currentTarget.style.opacity = 0.9}
                              onMouseOut={(e) => e.currentTarget.style.opacity = 1}
                            >
                              <span>Download CSV</span>
                            </button>
                          </div>
                        );
                      }
                      return null;
                    })()}
                    {msg.chartFigure && (
                      <div className="chart-container" style={{ marginTop: '12px', width: '100%' }}>
                        <PlotlyChart figure={msg.chartFigure} />
                      </div>
                    )}
                    {msg.sender === 'assistant' && msg.sources && msg.sources.filter(s => s.type !== 'chart' && s.type !== 'download' && (s.source || s.text)).length > 0 && (
                      <div className="message-sources-footer">
                        <button
                          type="button"
                          className="sources-trigger-btn"
                          onClick={() => {
                            setSourcesFilterTab('all');
                            setSourcesModalData({
                              sources: msg.sources.filter(s => s.type !== 'chart' && s.type !== 'download' && (s.source || s.text))
                            });
                          }}
                        >
                          <BookOpen size={14} className="sources-btn-icon" />
                          <span>Sources</span>
                          <span className="sources-count-badge">
                            {msg.sources.filter(s => s.type !== 'chart' && s.type !== 'download' && (s.source || s.text)).length}
                          </span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {isUploading && (
                  <div className="message-bubble assistant" style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(79, 70, 229, 0.1)', borderColor: 'var(--accent-color)' }}>
                    <Loader2 size={16} className="animate-spin text-accent" />
                    <span style={{ fontWeight: 500 }}>{uploadProgress}</span>
                  </div>
                )}
                {isLlmGenerating && (
                  <div className="message-bubble assistant" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Loader2 size={16} className="animate-spin text-accent" />
                    <span style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>Vectra AI is thinking...</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}

            {/* INPUT AREA */}
            <div className="bottom-input-container">
              {isUploading && (
                <div className="upload-status" style={{ marginBottom: '12px' }}>
                  <Loader2 size={16} className="animate-spin" />
                  <span>{uploadProgress}</span>
                </div>
              )}
              <form onSubmit={handleSendMessage} className="glass-input-bar">
                {/* Plus upload button */}
                <button
                  type="button"
                  className="input-plus-btn"
                  onClick={triggerFileUpload}
                  title="Upload multiple documents"
                >
                  <Plus size={20} />
                </button>

                {/* Hidden file input */}
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  multiple
                  onChange={handleFileChange}
                  accept=".pdf,.docx,.txt,.csv,.xlsx,.json,.md"
                />

                {/* Chat Text Input */}
                <input
                  type="text"
                  ref={chatInputRef}
                  placeholder="Ask Vectra..."
                  className="chat-input"
                  value={inputVal}
                  onChange={(e) => setInputVal(e.target.value)}
                />

                {/* Send/Stop Pulse Button */}
                {isLlmGenerating ? (
                  <button
                    type="button"
                    className="input-send-btn pulse"
                    onClick={stopGenerating}
                    title="Stop generating"
                    style={{ background: 'var(--accent-color)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <span className="stop-icon" style={{ display: 'block', width: '10px', height: '10px', background: 'white', borderRadius: '2px' }}></span>
                  </button>
                ) : (
                  <button type="submit" className="input-send-btn" title="Send message" disabled={!inputVal.trim()}>
                    <Send size={18} />
                  </button>
                )}
              </form>
            </div>

          </main>

          {/* DOCUMENTS LIST MODAL */}
          {showDocsModal && (
            <>
              <div className="modal-backdrop" onClick={() => setShowDocsModal(false)} />
              <div className="docs-panel">
                <div className="docs-header">
                  <h3 className="docs-title">My Uploaded Documents</h3>
                  <button className="close-modal-btn" onClick={() => setShowDocsModal(false)}>
                    <X size={24} />
                  </button>
                </div>

                <div className="docs-list">
                  {documents.length === 0 ? (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                      No documents ingested yet. Click the + button to add files.
                    </div>
                  ) : (
                    documents.map(doc => (
                      <div key={doc.id} className="doc-item-row">
                        <div className="doc-item-info">
                          {doc.status === 'READY' ? (
                            <FileText size={20} style={{ color: 'var(--accent-color)' }} />
                          ) : doc.status === 'FAILED' ? (
                            <FileText size={20} style={{ color: 'red' }} />
                          ) : (
                            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent-color)' }} />
                          )}
                          <div>
                            <div className="doc-name">{doc.name}</div>
                            <div className="doc-size">
                              {doc.size} &bull; {doc.type}
                              {(doc.status === 'QUEUED' || doc.status === 'PROCESSING' || doc.status === 'UPLOADING') && (
                                <span style={{ marginLeft: '8px', color: 'var(--accent-color)', fontWeight: 600 }}>
                                  ({doc.progress}% {doc.currentStep ? `- ${doc.currentStep}` : ''})
                                </span>
                              )}
                              {doc.status === 'FAILED' && (
                                <span style={{ marginLeft: '8px', color: 'red', fontWeight: 600 }}>
                                  (Failed)
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <button
                          className="delete-doc-btn"
                          title="Delete Document"
                          onClick={() => handleDeleteDocument(doc.id)}
                          disabled={doc.status !== 'READY' && doc.status !== 'FAILED'}
                          style={{ opacity: (doc.status !== 'READY' && doc.status !== 'FAILED') ? 0.4 : 1 }}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}

          {/* SOURCES MODAL POPUP */}
          {sourcesModalData && (
            <div className="sources-modal-backdrop" onClick={() => setSourcesModalData(null)}>
              <div className="sources-modal-window" onClick={(e) => e.stopPropagation()}>
                {/* Modal Header */}
                <div className="sources-modal-header">
                  <div className="sources-modal-header-left">
                    <div className="sources-modal-header-icon">
                      <BookOpen size={20} />
                    </div>
                    <div>
                      <h3 className="sources-modal-title">Sources & References</h3>
                      <div className="sources-modal-subtitle">
                        {sourcesModalData.sources.length} retrieved passage{sourcesModalData.sources.length === 1 ? '' : 's'} used for this response
                      </div>
                    </div>
                  </div>
                  <button
                    className="sources-modal-close-btn"
                    onClick={() => setSourcesModalData(null)}
                    title="Close sources"
                  >
                    <X size={18} />
                  </button>
                </div>

                {/* Filter Tabs */}
                {(() => {
                  const vectorCount = sourcesModalData.sources.filter(s => s.type !== 'graph').length;
                  const graphCount = sourcesModalData.sources.filter(s => s.type === 'graph').length;
                  if (vectorCount > 0 && graphCount > 0) {
                    return (
                      <div className="sources-modal-tabs">
                        <button
                          className={`sources-tab-btn ${sourcesFilterTab === 'all' ? 'active' : ''}`}
                          onClick={() => setSourcesFilterTab('all')}
                        >
                          All Sources ({sourcesModalData.sources.length})
                        </button>
                        <button
                          className={`sources-tab-btn ${sourcesFilterTab === 'vector' ? 'active' : ''}`}
                          onClick={() => setSourcesFilterTab('vector')}
                        >
                          <Database size={13} /> Vector DB ({vectorCount})
                        </button>
                        <button
                          className={`sources-tab-btn ${sourcesFilterTab === 'graph' ? 'active' : ''}`}
                          onClick={() => setSourcesFilterTab('graph')}
                        >
                          <Layers size={13} /> Knowledge Graph ({graphCount})
                        </button>
                      </div>
                    );
                  }
                  return null;
                })()}

                {/* Modal Body List */}
                <div className="sources-modal-body">
                  {sourcesModalData.sources
                    .filter(s => {
                      if (sourcesFilterTab === 'vector') return s.type !== 'graph';
                      if (sourcesFilterTab === 'graph') return s.type === 'graph';
                      return true;
                    })
                    .map((src, idx) => {
                      const isGraph = src.type === 'graph';
                      const docName = resolveDocumentName(src.source, documents);
                      const pageNum = src.page !== null && src.page !== undefined ? src.page + 1 : null;
                      const isCopied = copiedIdx === idx;

                      return (
                        <div key={idx} className="source-card">
                          {/* Source Header */}
                          <div className="source-card-header">
                            <div className="source-card-doc-info">
                              <div className={`source-card-doc-icon ${isGraph ? 'graph' : 'vector'}`}>
                                {isGraph ? <Layers size={15} /> : <FileText size={15} />}
                              </div>
                              <span className="source-card-doc-name" title={src.source || 'Knowledge Base'}>
                                {docName}
                              </span>
                            </div>

                            <div className="source-card-badges">
                              {pageNum !== null && (
                                <span className="source-badge page-badge">
                                  Page {pageNum}
                                </span>
                              )}
                              {isGraph ? (
                                <span className="source-badge graph-badge">
                                  <Layers size={11} /> Graph Fact
                                </span>
                              ) : (
                                <span className="source-badge vector-badge">
                                  <Database size={11} /> Vector Search
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Source Passage Content */}
                          {src.text && (
                            <div className="source-card-text">
                              {src.text}
                            </div>
                          )}

                          {/* Source Card Footer */}
                          <div className="source-card-footer">
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                              Passage #{idx + 1}
                            </span>
                            {src.text && (
                              <button
                                className="source-card-copy-btn"
                                onClick={() => {
                                  if (navigator.clipboard) {
                                    navigator.clipboard.writeText(src.text);
                                  }
                                  setCopiedIdx(idx);
                                  setTimeout(() => setCopiedIdx(null), 2000);
                                }}
                              >
                                {isCopied ? <Check size={13} style={{ color: '#10b981' }} /> : <Copy size={13} />}
                                <span>{isCopied ? 'Copied' : 'Copy passage'}</span>
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            </div>
          )}

        </div>
      )}
    </>
  );
}

function renderMessageText(text) {
  if (!text) return "";

  const lines = text.split("\n");
  const blocks = [];
  let currentTable = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    // Detect Markdown Table row (e.g. | col1 | col2 |)
    if (line.startsWith("|") && line.endsWith("|")) {
      if (!currentTable) {
        currentTable = [];
      }
      // Ignore delimiter lines (like |---|---| or | --- | --- |)
      if (!/^\|[\s\-:\t|]+\|$/.test(line)) {
        const cells = line.split("|").slice(1, -1).map(c => c.trim());
        currentTable.push(cells);
      }
      continue;
    }

    // End of table block if non-table line is encountered
    if (currentTable) {
      blocks.push({ type: "table", rows: currentTable });
      currentTable = null;
    }

    if (!line) {
      blocks.push({ type: "spacer" });
      continue;
    }

    // Heading blocks (# Heading)
    if (line.startsWith("### ")) {
      blocks.push({ type: "h3", content: line.slice(4) });
    } else if (line.startsWith("## ")) {
      blocks.push({ type: "h2", content: line.slice(3) });
    } else if (line.startsWith("# ")) {
      blocks.push({ type: "h1", content: line.slice(2) });
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      blocks.push({ type: "bullet", content: line.slice(2) });
    } else {
      blocks.push({ type: "paragraph", content: line });
    }
  }

  if (currentTable) {
    blocks.push({ type: "table", rows: currentTable });
  }

  return (
    <div className="rendered-markdown" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
      {blocks.map((block, idx) => {
        if (block.type === "spacer") {
          return <div key={idx} style={{ height: '4px' }} />;
        }

        if (block.type === "table") {
          const [header, ...bodyRows] = block.rows;
          return (
            <div key={idx} style={{ overflowX: 'auto', margin: '8px 0', borderRadius: '10px', border: '1px solid rgba(0,0,0,0.08)', boxShadow: '0 2px 8px rgba(0,0,0,0.03)' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '0.85rem', background: '#ffffff' }}>
                {header && (
                  <thead style={{ background: 'rgba(79, 70, 229, 0.08)', borderBottom: '2px solid rgba(79, 70, 229, 0.2)' }}>
                    <tr>
                      {header.map((cell, cIdx) => (
                        <th key={cIdx} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, color: 'var(--black-magic)' }}>
                          {formatInlineMarkdown(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {bodyRows.map((row, rIdx) => (
                    <tr key={rIdx} style={{ borderBottom: '1px solid rgba(0,0,0,0.04)', background: rIdx % 2 === 0 ? '#ffffff' : 'rgba(0,0,0,0.02)' }}>
                      {row.map((cell, cIdx) => (
                        <td key={cIdx} style={{ padding: '8px 12px', color: '#2d3748' }}>
                          {formatInlineMarkdown(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (block.type === "h1" || block.type === "h2" || block.type === "h3") {
          const fontSize = block.type === "h1" ? "1.2rem" : block.type === "h2" ? "1.05rem" : "0.95rem";
          return (
            <div key={idx} style={{ fontWeight: 700, fontSize, marginTop: '8px', color: 'var(--black-magic)' }}>
              {formatInlineMarkdown(block.content)}
            </div>
          );
        }

        if (block.type === "bullet") {
          return (
            <div key={idx} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', paddingLeft: '4px' }}>
              <span style={{ color: 'var(--accent-color, #4f46e5)', fontWeight: 'bold', fontSize: '0.9rem' }}>•</span>
              <div>{formatInlineMarkdown(block.content)}</div>
            </div>
          );
        }

        return (
          <div key={idx}>
            {formatInlineMarkdown(block.content)}
          </div>
        );
      })}
    </div>
  );
}

function formatInlineMarkdown(text) {
  if (!text) return "";

  const regex = /(\*\*.*?\*\*|\[.*?\]\(.*?\))/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong key={match.index} style={{ fontWeight: 700, color: 'var(--black-magic)' }}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("[")) {
      const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        parts.push(
          <a
            key={match.index}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: 'var(--accent-color, #4f46e5)',
              textDecoration: 'underline',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            {linkMatch[1]}
          </a>
        );
      } else {
        parts.push(token);
      }
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

function cleanMessageText(text) {
  if (!text) return "";
  let clean = text;
  // Clean tool call JSON payloads completely
  clean = clean.replace(/^\s*\{[\s\S]*?"type"\s*:\s*"tool"[\s\S]*?\}/g, '').trim();
  if (clean.startsWith('{') && clean.includes('"tool"')) {
    const lastIndex = clean.lastIndexOf('}');
    if (lastIndex !== -1) {
      clean = clean.slice(lastIndex + 1).trim();
    }
  }
  // Strip any leftover stray JSON braces
  clean = clean.replace(/^\s*\}\s*/, '').trim();
  clean = clean.replace(/\s*\}\s*$/, '').trim();

  // Strip duplicate raw markdown download links so the rich card UI displays cleanly below
  clean = clean.replace(/\[Download [^\]]+\]\(\/documents\/download\/[^\)]+\)/gi, '');
  clean = clean.replace(/You can download the file here:\s*/gi, '');
  return clean.trim();
}

function PlotlyChart({ figure }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (containerRef.current && window.Plotly && figure) {
      try {
        const parsedFigure = typeof figure === 'string' ? JSON.parse(figure) : figure;
        const cleanLayout = { ...(parsedFigure.layout || {}) };
        delete cleanLayout.width;

        const layout = {
          ...cleanLayout,
          autosize: true,
          margin: { l: 45, r: 25, t: 40, b: 45 },
          paper_bgcolor: '#ffffff',
          plot_bgcolor: '#ffffff',
          font: { family: 'Outfit, sans-serif', size: 12 }
        };
        
        window.Plotly.newPlot(
          containerRef.current,
          parsedFigure.data,
          layout,
          { responsive: true, displayModeBar: true, displaylogo: false }
        ).then(() => {
          if (window.Plotly && containerRef.current) {
            window.Plotly.Plots.resize(containerRef.current);
          }
        });

        const handleResize = () => {
          if (window.Plotly && containerRef.current) {
            window.Plotly.Plots.resize(containerRef.current);
          }
        };

        window.addEventListener('resize', handleResize);
        const t1 = setTimeout(handleResize, 50);
        const t2 = setTimeout(handleResize, 200);

        return () => {
          window.removeEventListener('resize', handleResize);
          clearTimeout(t1);
          clearTimeout(t2);
        };
      } catch (err) {
        console.error("Error rendering Plotly chart:", err);
      }
    }
  }, [figure]);

  return (
    <div style={{ position: 'relative', width: '100%', background: '#ffffff', borderRadius: '12px', border: '1px solid rgba(0,0,0,0.1)', padding: '16px', boxShadow: '0 4px 12px rgba(0,0,0,0.04)' }}>
      <div ref={containerRef} style={{ width: '100%', height: '420px' }} />
      <button
        onClick={() => {
          if (window.Plotly && containerRef.current) {
            window.Plotly.downloadImage(containerRef.current, {
              format: 'png',
              filename: 'plotly_chart',
              height: 600,
              width: 800
            });
          }
        }}
        style={{
          position: 'absolute',
          bottom: '12px',
          right: '12px',
          zIndex: 10,
          background: 'var(--accent-color, #4f46e5)',
          color: '#ffffff',
          border: 'none',
          padding: '6px 12px',
          borderRadius: '6px',
          cursor: 'pointer',
          fontSize: '0.72rem',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          boxShadow: '0 2px 6px rgba(79, 70, 229, 0.2)'
        }}
      >
        <span>📷 Download PNG</span>
      </button>
    </div>
  );
}
