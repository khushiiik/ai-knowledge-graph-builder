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
  Edit2
} from 'lucide-react';

export default function App() {
  // Authentication State
  const [authToken, setAuthToken] = useState(null);
  const [loginUser, setLoginUser] = useState(null);
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

  // Uploading States
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");

  // Refs
  const fileInputRef = useRef(null);
  const chatInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Mock Conversations (Knowledge Graph themed)
  const [conversations, setConversations] = useState([
    {
      id: "conv-1",
      title: "Project Architecture Extraction",
      messages: [
        { sender: "assistant", text: "Hello! I am Vectra AI, your Knowledge Graph Builder assistant. Ask me questions or upload files to ingest into the graph database." },
        { sender: "user", text: "What entities were extracted from the documentation?" },
        { sender: "assistant", text: "The following entities were extracted and successfully mapped in the Neo4j graph db:\n- `Vectra AI` (AI System)\n- `Vite` (Frontend Build Tool)\n- `Qdrant` (Vector Database)\n- `Neo4j` (Graph Database)\n- `PostgreSQL` (Relational Database)" }
      ]
    },
    {
      id: "conv-2",
      title: "Semantic Search Evaluation",
      messages: [
        { sender: "assistant", text: "Hello! I can help you search semantic nodes in your database." },
        { sender: "user", text: "How are files isolated in Qdrant?" },
        { sender: "assistant", text: "Each document chunk is tagged with your user's `tenant_id` at indexing time. Queries are executed with a payload filter matching your user ID to ensure complete multi-tenant security." }
      ]
    },
    {
      id: "conv-3",
      title: "Neo4j Relation Mapping",
      messages: [
        { sender: "assistant", text: "Hello! Ready to map node relationships?" }
      ]
    }
  ]);

  const [activeConversationId, setActiveConversationId] = useState("conv-1");
  const activeConversation = conversations.find(c => c.id === activeConversationId) || conversations[0];

  // Mock Ingested Documents
  const [documents, setDocuments] = useState([
    { id: "doc-1", name: "project_specification.pdf", size: "1.2 MB", type: "PDF" },
    { id: "doc-2", name: "neo4j_schema.json", size: "8 KB", type: "JSON" },
    { id: "doc-3", name: "ingested_nodes.txt", size: "4 KB", type: "TXT" }
  ]);

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
  const handleLogin = (e) => {
    e.preventDefault();
    setAuthError('');

    if (!email || !password) {
      setAuthError('Email and Password are required.');
      return;
    }

    // Set first name appropriately
    const rawName = email.split('@')[0];
    const formattedName = rawName.charAt(0).toUpperCase() + rawName.slice(1);

    setLoginUser({
      name: formattedName,
      email: email,
      role: "Developer"
    });
    setAuthToken('mock_token_key');
  };

  // Handle Register Submission
  const handleRegister = (e) => {
    e.preventDefault();
    setAuthError('');

    if (!email || !password || !fullName) {
      setAuthError('Full Name, Email and Password are required.');
      return;
    }

    setLoginUser({
      name: fullName,
      email: email,
      role: "Developer"
    });
    setAuthToken('mock_token_key');
  };

  // Handle Logout
  const handleLogout = () => {
    setAuthToken(null);
    setLoginUser(null);
    setEmail('');
    setPassword('');
    setFullName('');
  };

  // Create new conversation (creates conversation but does not expand the sidebar)
  const createNewConversation = () => {
    const newId = `conv-${Date.now()}`;
    const newConv = {
      id: newId,
      title: `New Semantic Session ${conversations.length + 1}`,
      messages: [
        { sender: "assistant", text: "Hello! Started a new session. Upload files or ask me anything." }
      ]
    };
    setConversations([newConv, ...conversations]);
    setActiveConversationId(newId);
  };

  // Start renaming a conversation
  const startRename = (convId, currentTitle) => {
    setEditingConvId(convId);
    setEditingTitle(currentTitle);
  };

  // Save renamed conversation
  const saveRename = (convId) => {
    if (editingTitle.trim()) {
      setConversations(prev => prev.map(c => {
        if (c.id === convId) {
          return { ...c, title: editingTitle.trim() };
        }
        return c;
      }));
    }
    setEditingConvId(null);
  };

  // Handle Send Message
  const handleSendMessage = (e) => {
    if (e) e.preventDefault();
    if (!inputVal.trim() || isLlmGenerating) return;

    const userMsg = { sender: "user", text: inputVal };
    
    // Add user message locally
    const updatedConversations = conversations.map(c => {
      if (c.id === activeConversationId) {
        return {
          ...c,
          messages: [...c.messages, userMsg]
        };
      }
      return c;
    });
    setConversations(updatedConversations);
    setInputVal("");
    setIsLlmGenerating(true);

    // Simulate LLM response after 1.2s
    setTimeout(() => {
      const responses = [
        "Based on the semantic search, the database matches these concepts: Neo4j links Vite frontend node to Qdrant vector index.",
        "Generating the knowledge graph relation list... Ingestion validation returns healthy graph indices.",
        "I've updated the semantic knowledge graph. Let me know if you would like me to compile these parameters into a structured report.",
        "I don't have information about that in the current uploaded document context. Please upload the relevant specification file."
      ];
      const randomResponse = responses[Math.floor(Math.random() * responses.length)];
      const assistantMsg = { sender: "assistant", text: randomResponse };

      setConversations(prev => prev.map(c => {
        if (c.id === activeConversationId) {
          return {
            ...c,
            messages: [...c.messages, assistantMsg]
          };
        }
        return c;
      }));
      setIsLlmGenerating(false);
    }, 1200);
  };

  // Trigger File Input Click
  const triggerFileUpload = () => {
    fileInputRef.current?.click();
  };

  // Handle File upload simulation
  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    setIsUploading(true);
    setUploadProgress(`Ingesting ${files.length} file(s)...`);

    // Simulate ingestion delay
    setTimeout(() => {
      const newDocs = files.map((file, idx) => ({
        id: `doc-${Date.now()}-${idx}`,
        name: file.name,
        size: `${(file.size / (1024 * 1024)).toFixed(2)} MB`,
        type: file.name.split('.').pop().toUpperCase()
      }));

      setDocuments(prev => [...newDocs, ...prev]);
      setIsUploading(false);
      setUploadProgress("");

      // Trigger standard confirmation banner
      const notification = document.getElementById('upload-notice');
      if (notification) {
        notification.style.display = 'flex';
        setTimeout(() => {
          notification.style.display = 'none';
        }, 3000);
      }
    }, 1500);
  };

  // Handle document deletion
  const handleDeleteDocument = (docId) => {
    setDocuments(prev => prev.filter(doc => doc.id !== docId));
  };

  // Filter conversations
  const filteredConversations = conversations.filter(c => 
    c.title.toLowerCase().includes(convSearchQuery.toLowerCase())
  );

  // Extract first name for dynamic Claude-like greeting
  const getFirstName = () => {
    if (!loginUser?.name) return 'Guest';
    // Take the first segment split by spaces
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
                <div className="chat-list-container" style={{ display: 'flex', width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem', letterSpacing: '0.5px', textTransform: 'uppercase', opacity: 0.8 }}>Chats</span>
                    <button 
                      onClick={() => setSearchOpen(!searchOpen)} 
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--black-magic)' }}
                      title="Filter chats"
                    >
                      <Search size={15} />
                    </button>
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

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flexGrow: 1, maxHeight: 'calc(100% - 140px)' }}>
                    {filteredConversations.length === 0 ? (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
                        No active sessions found
                      </div>
                    ) : (
                      filteredConversations.map(conv => (
                        <div 
                          key={conv.id} 
                          className={`chat-item ${conv.id === activeConversationId ? 'active' : ''}`}
                          onClick={() => {
                            if (editingConvId !== conv.id) {
                              setActiveConversationId(conv.id);
                            }
                          }}
                          style={{ display: 'flex', justifyContent: 'space-between', paddingRight: '12px' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1, overflow: 'hidden' }}>
                            <MessageSquare size={16} />
                            {editingConvId === conv.id ? (
                              <input 
                                type="text"
                                className="chat-input"
                                value={editingTitle}
                                onChange={(e) => setEditingTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    saveRename(conv.id);
                                  }
                                }}
                                onBlur={() => saveRename(conv.id)}
                                autoFocus
                                style={{ 
                                  background: 'rgba(255,255,255,0.8)', 
                                  border: '1px solid var(--black-magic)',
                                  borderRadius: '6px',
                                  padding: '2px 6px',
                                  fontSize: '0.85rem',
                                  width: '100%'
                                }}
                              />
                            ) : (
                              <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{conv.title}</span>
                            )}
                          </div>
                          
                          {editingConvId !== conv.id && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                startRename(conv.id, conv.title);
                              }}
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
                              title="Rename chat"
                            >
                              <Edit2 size={13} />
                            </button>
                          )}
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
                    <span className="profile-card-role">{loginUser?.role}</span>
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
              </div>
            ) : (
              /* Active Chat Window View */
              <div className="chat-window" style={{ paddingBottom: '20px' }}>
                {activeConversation.messages.map((msg, i) => (
                  <div 
                    key={i} 
                    className={`message-bubble ${msg.sender === 'user' ? 'user' : 'assistant'}`}
                    style={{ whiteSpace: 'pre-line' }}
                  >
                    {msg.text}
                  </div>
                ))}
                {isLlmGenerating && (
                  <div className="message-bubble assistant" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Querying Vectra AI knowledge indices in Qdrant...</span>
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

                {/* Send Airplane Button */}
                <button type="submit" className="input-send-btn" title="Send message">
                  <Send size={18} />
                </button>
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
                          <FileText size={20} style={{ color: 'var(--accent-color)' }} />
                          <div>
                            <div className="doc-name">{doc.name}</div>
                            <div className="doc-size">{doc.size} &bull; {doc.type}</div>
                          </div>
                        </div>
                        <button 
                          className="delete-doc-btn" 
                          title="Delete Document"
                          onClick={() => handleDeleteDocument(doc.id)}
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

        </div>
      )}
    </>
  );
}
