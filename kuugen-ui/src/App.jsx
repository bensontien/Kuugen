import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm'; // Import GFM plugin to support tables and advanced syntax
import { useTranslation } from './hooks/useTranslation';
import './App.css';

function App() {
  const { currentLang, setLanguage, languages, t, translateStepTitle, translateStatus } = useTranslation();

  const [sessions, setSessions] = useState(() => [
    { id: 'session-' + Date.now().toString(), title: t('common.defaultSessionTitle'), messages: [] }
  ]);
  
  const [activeSessionId, setActiveSessionId] = useState(sessions[0].id);
  
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('kuugen-theme') || 'dark';
  });
  
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const activeMessages = sessions.find(s => s.id === activeSessionId)?.messages || [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeMessages]); 

  useEffect(() => {
    document.body.className = theme;
    localStorage.setItem('kuugen-theme', theme);
  }, [theme]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080/ws/chat');
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('🔌 WebSocket Connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const targetSessionId = data.session_id;

      if (!targetSessionId) return;

      setSessions((prevSessions) => prevSessions.map(session => {
        if (session.id !== targetSessionId) return session;

        const prevMessages = session.messages;

        if (data.type === 'status') {
          const lastMsg = prevMessages[prevMessages.length - 1];
          const newStatusMsg = {
            role: 'system',
            type: 'status',
            content: data.content,
            stage: data.stage,
            stage_params: data.stage_params,
            steps: data.steps || (lastMsg?.type === 'status' ? lastMsg.steps : [])
          };
          if (lastMsg && lastMsg.type === 'status') {
             return { ...session, messages: [...prevMessages.slice(0, -1), newStatusMsg] };
          }
          return { ...session, messages: [...prevMessages, newStatusMsg] };
        } 
        else if (data.type === 'result') {
          const filteredMessages = prevMessages.filter(msg => msg.type !== 'status');
          return { ...session, messages: [...filteredMessages, { role: 'assistant', type: 'result', data: data }] };
        } 
        else if (data.type === 'error') {
          const filteredMessages = prevMessages.filter(msg => msg.type !== 'status');
          return { ...session, messages: [...filteredMessages, { role: 'system', type: 'error', content: `❌ Error: ${data.content}` }] };
        }
        return session;
      }));
    };

    ws.onclose = () => {
      console.log('🔌 WebSocket Disconnected');
      setIsConnected(false);
    };

    return () => ws.close();
  }, []);

  const handleSendMessage = () => {
    if (!inputValue.trim() || !isConnected) return;
    
    const userText = inputValue.trim();
    
    setSessions(prev => prev.map(s => {
      if (s.id === activeSessionId) {
        const newTitle = s.messages.length === 0 ? userText.substring(0, 12) + "..." : s.title;
        return { ...s, title: newTitle, messages: [...s.messages, { role: 'user', content: userText }] };
      }
      return s;
    }));
    
    wsRef.current.send(JSON.stringify({ 
      message: userText,
      session_id: activeSessionId 
    }));
    
    setInputValue('');
    
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewChat = () => {
    const newSessionId = 'session-' + Date.now().toString();
    setSessions(prev => [{ id: newSessionId, title: t('common.defaultSessionTitle'), messages: [] }, ...prev]);
    setActiveSessionId(newSessionId); 
  };

  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'light' ? 'dark' : 'light'));
  };

  return (
    <div className="chat-container">
      <aside className={`sidebar ${isSidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-top">
          <div className="app-brand">
            <span className="app-logo">🤖</span>
            <h1>Kuugen</h1>
          </div>
          <button className="new-chat-btn" onClick={handleNewChat}>{t('common.newChat')}</button>
        </div>

        <div className="sidebar-history">
          {sessions.map(session => (
            <div 
              key={session.id} 
              className={`history-item ${session.id === activeSessionId ? 'active' : ''}`}
              onClick={() => setActiveSessionId(session.id)}
            >
              <span className="history-icon">💬</span>
              <span className="history-title">{session.title}</span>
            </div>
          ))}
        </div>
        
        <div className="sidebar-bottom">
          <div className="language-selector">
            <span className="lang-icon">🌐</span>
            <select 
              value={currentLang} 
              onChange={(e) => setLanguage(e.target.value)}
              className="lang-select"
              aria-label="Select Language"
            >
              {languages.map(lang => (
                <option key={lang.code} value={lang.code}>
                  {lang.icon} {lang.label}
                </option>
              ))}
            </select>
          </div>
          <button onClick={toggleTheme} className="theme-toggle-btn">
            {theme === 'light' ? t('common.toggleThemeDark') : t('common.toggleThemeLight')}
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="chat-header">
          <div className="header-left">
            <button 
              className="toggle-sidebar-btn" 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            </button>
            <h2>Kuugen</h2>
            <span 
              className={isConnected ? "status-dot connected" : "status-dot disconnected"}
              title={isConnected ? t('common.connected') : t('common.disconnected')}
            ></span>
          </div>
        </header>

        <div className="chat-window">
          {activeMessages.length === 0 ? (
            <div className="empty-state">
              <h3>{t('common.greeting')}</h3>
              <p>{t('common.greetingSub')}</p>
            </div>
          ) : (
            activeMessages.map((msg, index) => (
              <div key={index} className={`message-wrapper ${msg.role}`}>
                <div className="message-bubble">

                  {msg.role === 'user' && <p>{msg.content}</p>}

                  {msg.role === 'system' && (
                    <div className="system-status-box">
                      <div className="system-status-header">
                        <span className="spinner"></span> 
                        <p className="system-text">{translateStatus(msg)}</p>
                      </div>
                      {msg.steps && msg.steps.length > 0 && (
                        <div className="system-steps-list">
                          {msg.steps.map((step, sIdx) => (
                            <div key={step.id || sIdx} className={`system-step-item ${step.status}`}>
                              <span className="step-icon">
                                {step.status === 'completed' ? '✓' : step.status === 'running' ? '●' : step.status === 'failed' ? '✕' : '○'}
                              </span>
                              <span className="step-title">{translateStepTitle(step.id, step.title)}</span>
                              {step.node && <span className="step-node-tag">{step.node}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {msg.role === 'assistant' && msg.type === 'result' && (
                    <div className="result-content">
                      {msg.data.execution_steps && msg.data.execution_steps.length > 0 && (
                        <details className="execution-steps-details">
                          <summary className="details-summary-btn">
                            <span className="details-icon">⚡</span>
                            <span>
                              {t('step.executionStages')} ({t('step.stepsCompleted', {
                                completed: msg.data.execution_steps.filter(s => s.status === 'completed').length,
                                total: msg.data.execution_steps.length
                              })})
                            </span>
                          </summary>
                          <div className="system-steps-list">
                            {msg.data.execution_steps.map((step, sIdx) => (
                              <div key={step.id || sIdx} className={`system-step-item ${step.status}`}>
                                <span className="step-icon">
                                  {step.status === 'completed' ? '✓' : step.status === 'failed' ? '✕' : '○'}
                                </span>
                                <span className="step-title">{translateStepTitle(step.id, step.title)}</span>
                                {step.node && <span className="step-node-tag">{step.node}</span>}
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                      
                      {msg.data.reply && (
                        <div className="text-reply markdown-content">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({node: _node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" />
                            }}
                          >
                            {msg.data.reply}
                          </ReactMarkdown>
                        </div>
                      )}

                      <div className="cards-wrapper">
                        {msg.data.news_report && (
                          <div className="card news-card">
                            <h3>{t('cards.newsReport')}</h3>
                            <div className="markdown-content">
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                  a: ({node: _node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" />
                                }}
                              >
                                {msg.data.news_report}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}
                        {msg.data.search_report_file && (
                          <div className="card file-card">
                            <h3>{t('cards.paperSummary')}</h3>
                            <button className="file-path-btn">{t('cards.summaryLocation')} <code>{msg.data.search_report_file}</code></button>
                            {msg.data.search_report_content && (
                              <div className="markdown-content" style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  components={{
                                    a: ({node: _node, ...props}) => <a {...props} target="_blank" rel="noopener noreferrer" />
                                  }}
                                >
                                  {msg.data.search_report_content}
                                </ReactMarkdown>
                              </div>
                            )}
                          </div>
                        )}
                        {msg.data.translated_file && (
                          <div className="card file-card success">
                            <h3>{t('cards.translationComplete')}</h3>
                            <button className="file-path-btn success">{t('cards.openTranslation')} <code>{msg.data.translated_file}</code></button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        <footer className="chat-input-area">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                e.target.style.height = 'auto'; 
                e.target.style.height = `${e.target.scrollHeight}px`; 
              }}
              onKeyDown={handleKeyPress}
              placeholder={t('common.placeholder')}
              rows={1}
            />
            <button onClick={handleSendMessage} disabled={!isConnected || !inputValue.trim()} className="send-btn">
              {t('common.send')}
            </button>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;