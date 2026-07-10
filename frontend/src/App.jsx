import React, { useState, useRef } from 'react';
import {
  Plus,
  Search,
  Grid,
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
  Notebook
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

  // Modal State
  const [showDocsModal, setShowDocsModal] = useState(false);

  // Uploading States
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");

  // File Input Ref
  const fileInputRef = useRef(null);

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

  // Handle Login Submission
  const handleLogin = (e) => {
    e.preventDefault();
    setAuthError('');

    if (!email || !password) {
      setAuthError('Email and Password are required.');
      return;
    }

    // Simulate login success
    const name = email.split('@')[0];
    setLoginUser({
      name: name.charAt(0).toUpperCase() + name.slice(1),
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

    // Simulate registration & login success
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

  // Create new conversation
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
    setSidebarExpanded(true); // Auto expand to show the list
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

  return (
    <>
      {/* Moving Pastel Background Blobs */}
      <div className="bg-blobs">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
        <div className="blob blob-3"></div>
      </div>

      {/* Conditional Render: Auth Screen vs. Main Workspace */}
      {!authToken ? (
        <div className="auth-wrapper">
          <div className="auth-card">
            <div className="auth-header">
              <div className="auth-logo">V</div>
              <h2 className="auth-title">Vectra AI</h2>
              <p className="auth-subtitle">Knowledge Graph Ingestion Workspace</p>
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
                      placeholder="John Doe" 
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
                    placeholder="name@example.com" 
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

              <button type="submit" className="auth-submit-btn">
                <span>{authScreen === 'login' ? 'Login to Vectra' : 'Register Account'}</span>
              </button>
            </form>

            <div className="auth-footer">
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
                  {/* New Chat Button */}
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

                  {/* Manage Documents Grid */}
                  <button 
                    className="nav-item" 
                    title="Uploaded Documents"
                    onClick={() => setShowDocsModal(true)}
                  >
                    <Grid size={20} />
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

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flexGrow: 1, maxHeight: 'calc(90vh - 180px)' }}>
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
                        >
                          <MessageSquare size={16} />
                          <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{conv.title}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Close Sidebar button (Always visible at the bottom of the sidebar) */}
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
            <div className="top-bar">
              <div className="dropdown-selector">
                <Sparkles size={16} className="text-accent" />
                <span>Vectra Assistant v1.0</span>
              </div>

              <div className="dashboard-title-center">
                Knowledge Graph Builder
              </div>

              <div className="profile-section">
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--black-magic-light)' }}>
                  {loginUser.name} ({loginUser.role})
                </span>
                <button 
                  className="dropdown-selector" 
                  style={{ border: 'none', background: 'rgba(0,0,0,0.05)', padding: '8px 12px' }}
                  onClick={handleLogout}
                  title="Logout"
                >
                  <LogOut size={14} />
                  <span>Logout</span>
                </button>
              </div>
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
              <div className="welcome-container">
                <h1 className="welcome-header">
                  Hi {loginUser.name}, Ready to Build Your Knowledge Base?
                  <span>Ingest documents, map relationships, and semantic search nodes.</span>
                </h1>

                {/* Grid of Interactive Actions */}
                <div className="card-grid">
                  
                  {/* Upload Card */}
                  <div className="glass-card" onClick={triggerFileUpload}>
                    <div>
                      <div className="card-icon">
                        <Upload size={24} />
                      </div>
                      <h3 className="card-title">Upload Documents</h3>
                      <p className="card-desc">
                        Ingest PDFs, TXT, CSV, or JSON specifications. Automatically chunk and extract vector embeddings.
                      </p>
                    </div>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600, alignSelf: 'flex-end', color: 'var(--accent-color)', marginTop: '12px' }}>
                      Click to browse files &rarr;
                    </span>
                  </div>

                  {/* Graph Card */}
                  <div className="glass-card" onClick={() => {
                    setInputVal("Generate a relational schema map from all active knowledge base documents.");
                  }}>
                    <div>
                      <div className="card-icon">
                        <BarChart3 size={24} />
                      </div>
                      <h3 className="card-title">Explore Knowledge Graph</h3>
                      <p className="card-desc">
                        Query the mapped entities, generate semantic relational reports, and browse entity structures.
                      </p>
                    </div>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600, alignSelf: 'flex-end', color: 'var(--accent-color)', marginTop: '12px' }}>
                      Explore graph relationships &rarr;
                    </span>
                  </div>

                </div>
              </div>
            ) : (
              /* Active Chat Window View */
              <div className="chat-window">
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
                  placeholder="Ask me anything about your uploaded documents or query the knowledge graph..." 
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
