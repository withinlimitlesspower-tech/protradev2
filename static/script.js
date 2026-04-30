/**
 * AI Crypto Trading Dashboard - Frontend JavaScript
 * Handles chat interaction, voice recording, file upload, signal polling,
 * typing animation, and mobile menu toggle.
 * @module script
 */

// ============================================================================
// Configuration & State
// ============================================================================

/** Application configuration constants */
const CONFIG = {
    /** Polling interval for signal updates in milliseconds */
    SIGNAL_POLL_INTERVAL: 5000,
    /** Maximum file size allowed for uploads (10MB) */
    MAX_FILE_SIZE: 10 * 1024 * 1024,
    /** Allowed file types for upload */
    ALLOWED_FILE_TYPES: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 'text/plain'],
    /** API endpoints */
    API: {
        CHAT: '/api/chat',
        SIGNALS: '/api/signals',
        UPLOAD: '/api/upload',
        VOICE: '/api/voice'
    },
    /** CSS class names */
    CSS: {
        TYPING_INDICATOR: 'typing-indicator',
        MESSAGE_USER: 'message-user',
        MESSAGE_BOT: 'message-bot',
        ACTIVE: 'active',
        HIDDEN: 'hidden'
    }
};

/** Application state */
const state = {
    /** Whether a chat message is currently being sent */
    isSending: false,
    /** Whether voice recording is in progress */
    isRecording: false,
    /** MediaRecorder instance for voice recording */
    mediaRecorder: null,
    /** Array of audio chunks for recording */
    audioChunks: [],
    /** Last signal data received */
    lastSignals: null,
    /** Polling interval ID */
    pollInterval: null,
    /** WebSocket connection (if available) */
    websocket: null
};

// ============================================================================
// DOM Element References
// ============================================================================

/** Cache DOM elements for performance */
const elements = {
    chatContainer: document.getElementById('chat-container'),
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    sendButton: document.getElementById('send-button'),
    voiceButton: document.getElementById('voice-button'),
    fileInput: document.getElementById('file-input'),
    fileButton: document.getElementById('file-button'),
    uploadProgress: document.getElementById('upload-progress'),
    signalContainer: document.getElementById('signal-container'),
    signalList: document.getElementById('signal-list'),
    mobileMenuToggle: document.getElementById('mobile-menu-toggle'),
    mobileMenu: document.getElementById('mobile-menu'),
    typingIndicator: document.getElementById('typing-indicator'),
    errorToast: document.getElementById('error-toast')
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Sanitize user input to prevent XSS attacks
 * @param {string} input - Raw user input
 * @returns {string} Sanitized input
 */
function sanitizeInput(input) {
    if (typeof input !== 'string') return '';
    const div = document.createElement('div');
    div.textContent = input;
    return div.innerHTML;
}

/**
 * Validate file before upload
 * @param {File} file - File to validate
 * @returns {Object} Validation result { valid: boolean, error?: string }
 */
function validateFile(file) {
    if (!file) {
        return { valid: false, error: 'No file selected' };
    }
    
    if (file.size > CONFIG.MAX_FILE_SIZE) {
        return { valid: false, error: 'File size exceeds 10MB limit' };
    }
    
    if (!CONFIG.ALLOWED_FILE_TYPES.includes(file.type)) {
        return { valid: false, error: 'File type not supported' };
    }
    
    return { valid: true };
}

/**
 * Show error toast notification
 * @param {string} message - Error message to display
 */
function showError(message) {
    if (!elements.errorToast) return;
    
    const toast = elements.errorToast;
    toast.textContent = message;
    toast.classList.remove('hidden');
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.add('hidden');
        toast.classList.remove('show');
    }, 5000);
}

/**
 * Format timestamp for display
 * @param {string|Date} timestamp - Timestamp to format
 * @returns {string} Formatted time string
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ============================================================================
// Chat Functionality
// ============================================================================

/**
 * Add a message to the chat container
 * @param {string} content - Message content
 * @param {'user'|'bot'} type - Message type
 * @param {string} [timestamp] - Optional timestamp
 */
function addMessage(content, type, timestamp) {
    if (!elements.chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type === 'user' ? CONFIG.CSS.MESSAGE_USER : CONFIG.CSS.MESSAGE_BOT}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = sanitizeInput(content);
    
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = timestamp || formatTime(new Date());
    
    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timeDiv);
    elements.chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

/**
 * Show typing indicator in chat
 */
function showTypingIndicator() {
    if (!elements.typingIndicator) return;
    elements.typingIndicator.classList.remove(CONFIG.CSS.HIDDEN);
}

/**
 * Hide typing indicator
 */
function hideTypingIndicator() {
    if (!elements.typingIndicator) return;
    elements.typingIndicator.classList.add(CONFIG.CSS.HIDDEN);
}

/**
 * Send chat message to backend
 * @param {string} message - Message to send
 * @returns {Promise<void>}
 */
async function sendChatMessage(message) {
    if (state.isSending || !message.trim()) return;
    
    state.isSending = true;
    const sanitizedMessage = sanitizeInput(message.trim());
    
    // Add user message to chat
    addMessage(sanitizedMessage, 'user');
    
    // Clear input
    if (elements.chatInput) {
        elements.chatInput.value = '';
    }
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch(CONFIG.API.CHAT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ message: sanitizedMessage })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Hide typing indicator
        hideTypingIndicator();
        
        // Add bot response
        if (data.response) {
            addMessage(data.response, 'bot', data.timestamp);
        }
        
        // Update signal data if included
        if (data.signals) {
            updateSignals(data.signals);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        hideTypingIndicator();
        showError('Failed to send message. Please try again.');
        
        // Add error message to chat
        addMessage('Sorry, I encountered an error. Please try again.', 'bot');
        
    } finally {
        state.isSending = false;
    }
}

/**
 * Get CSRF token from meta tag
 * @returns {string} CSRF token
 */
function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// ============================================================================
// Voice Recording
// ============================================================================

/**
 * Initialize voice recording
 * @returns {Promise<void>}
 */
async function initializeVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.mediaRecorder = new MediaRecorder(stream);
        
        state.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                state.audioChunks.push(event.data);
            }
        };
        
        state.mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
            state.audioChunks = [];
            await sendVoiceRecording(audioBlob);
        };
        
    } catch (error) {
        console.error('Error initializing voice recording:', error);
        showError('Microphone access denied. Please enable microphone permissions.');
    }
}

/**
 * Toggle voice recording
 */
async function toggleVoiceRecording() {
    if (!state.mediaRecorder) {
        await initializeVoiceRecording();
    }
    
    if (state.isRecording) {
        // Stop recording
        state.mediaRecorder.stop();
        state.isRecording = false;
        if (elements.voiceButton) {
            elements.voiceButton.classList.remove('recording');
            elements.voiceButton.textContent = '🎤';
        }
    } else {
        // Start recording
        state.audioChunks = [];
        state.mediaRecorder.start();
        state.isRecording = true;
        if (elements.voiceButton) {
            elements.voiceButton.classList.add('recording');
            elements.voiceButton.textContent = '🔴';
        }
    }
}

/**
 * Send voice recording to backend
 * @param {Blob} audioBlob - Recorded audio blob
 * @returns {Promise<void>}
 */
async function sendVoiceRecording(audioBlob) {
    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        
        const response = await fetch(CONFIG.API.VOICE, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.transcript) {
            addMessage(data.transcript, 'user');
            if (data.response) {
                addMessage(data.response, 'bot', data.timestamp);
            }
        }
        
    } catch (error) {
        console.error('Error sending voice recording:', error);
        showError('Failed to process voice recording.');
    }
}

// ============================================================================
// File Upload
// ============================================================================

/**
 * Handle file upload
 * @param {File} file - File to upload
 * @returns {Promise<void>}
 */
async function handleFileUpload(file) {
    const validation = validateFile(file);
    if (!validation.valid) {
        showError(validation.error);
        return;
    }
    
    // Show upload progress
    if (elements.uploadProgress) {
        elements.uploadProgress.classList.remove(CONFIG.CSS.HIDDEN);
        elements.uploadProgress.value = 0;
    }
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const xhr = new XMLHttpRequest();
        
        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable && elements.uploadProgress) {
                const percentComplete = (event.loaded / event.total) * 100;
                elements.uploadProgress.value = percentComplete;
            }
        };
        
        const response = await new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    reject(new Error(`Upload failed with status ${xhr.status}`));
                }
            };
            xhr.onerror = () => reject(new Error('Upload failed'));
            xhr.open('POST', CONFIG.API.UPLOAD);
            xhr.setRequestHeader('X-CSRFToken', getCSRFToken());
            xhr.send(formData);
        });
        
        // Hide upload progress
        if (elements.uploadProgress) {
            elements.uploadProgress.classList.add(CONFIG.CSS.HIDDEN);
        }
        
        if (response.message) {
            addMessage(`📎 Uploaded: ${file.name}`, 'user');
            if (response.response) {
                addMessage(response.response, 'bot', response.timestamp);
            }
        }
        
    } catch (error) {
        console.error('Error uploading file:', error);
        showError('Failed to upload file. Please try again.');
        
        if (elements.uploadProgress) {
            elements.uploadProgress.classList.add(CONFIG.CSS.HIDDEN);
        }
    }
}

// ============================================================================
// Signal Polling
// ============================================================================

/**
 * Fetch latest signals from backend
 * @returns {Promise<void>}
 */
async function fetchSignals() {
    try {
        const response = await fetch(CONFIG.API.SIGNALS, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.signals) {
            updateSignals(data.signals);
        }
        
    } catch (error) {
        console.error('Error fetching signals:', error);
        // Don't show error for polling failures to avoid spam
    }
}

/**
 * Update signal display with new data
 * @param {Array} signals - Array of signal objects
 */
function updateSignals(signals) {
    if (!elements.signalList || !signals) return;
    
    state.lastSignals = signals;
    
    // Clear existing signals
    elements.signalList.innerHTML = '';
    
    // Add new signals
    signals.forEach(signal => {
        const signalCard = createSignalCard(signal);
        elements.signalList.appendChild(signalCard);
    });
}

/**
 * Create a signal card element
 * @param {Object} signal - Signal data
 * @returns {HTMLElement} Signal card element
 */
function createSignalCard(signal) {
    const card = document.createElement('div');
    card.className = 'signal-card';
    
    const typeClass = signal.type === 'buy' ? 'signal-buy' : 'signal-sell';
    card.classList.add(typeClass);
    
    card.innerHTML = `
        <div class="signal-header">
            <span class="signal-pair">${sanitizeInput(signal.pair || 'Unknown')}</span>
            <span class="signal-type ${typeClass}">${sanitizeInput(signal.type || 'N/A')}</span>
        </div>
        <div class="signal-details">
            <div class="signal-price">
                <span class="label">Price:</span>
                <span class="value">${sanitizeInput(signal.price || 'N/A')}</span>
            </div>
            <div class="signal-confidence">
                <span class="label">Confidence:</span>
                <span class="value">${sanitizeInput(signal.confidence || 'N/A')}%</span>
            </div>
            <div class="signal-time">
                <span class="label">Time:</span>
                <span class="value">${formatTime(signal.timestamp || new Date())}</span>
            </div>
        </div>
        ${signal.reason ? `<div class="signal-reason">${sanitizeInput(signal.reason)}</div>` : ''}
    `;
    
    return card;
}

/**
 * Start signal polling
 */
function startSignalPolling() {
    // Initial fetch
    fetchSignals();
    
    // Start interval
    state.pollInterval = setInterval(fetchSignals, CONFIG.SIGNAL_POLL_INTERVAL);
}

/**
 * Stop signal polling
 */
function stopSignalPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

// ============================================================================
// Mobile Menu
// ============================================================================

/**
 * Toggle mobile menu visibility
 */
function toggleMobileMenu() {
    if (!elements.mobileMenu) return;
    
    const isHidden = elements.mobileMenu.classList.contains(CONFIG.CSS.HIDDEN);
    
    if (isHidden) {
        elements.mobileMenu.classList.remove(CONFIG.CSS.HIDDEN);
        elements.mobileMenu.classList.add('show');
        if (elements.mobileMenuToggle) {
            elements.mobileMenuToggle.setAttribute('aria-expanded', 'true');
        }
    } else {
        elements.mobileMenu.classList.add(CONFIG.CSS.HIDDEN);
        elements.mobileMenu.classList.remove('show');
        if (elements.mobileMenuToggle) {
            elements.mobileMenuToggle.setAttribute('aria-expanded', 'false');
        }
    }
}

/**
 * Close mobile menu
 */
function closeMobileMenu() {
    if (elements.mobileMenu) {
        elements.mobileMenu.classList.add(CONFIG.CSS.HIDDEN);
        elements.mobileMenu.classList.remove('show');
    }
    if (elements.mobileMenuToggle) {
        elements.mobileMenuToggle.setAttribute('aria-expanded', 'false');
    }
}

// ============================================================================
// Event Listeners
// ============================================================================

/**
 * Initialize all event listeners
 */
function initializeEventListeners() {
    // Chat send button
    if (elements.sendButton && elements.chatInput) {
        elements.sendButton.addEventListener('click', () => {
            sendChatMessage(elements.chatInput.value);
        });
        
        elements.chatInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendChatMessage(elements.chatInput.value);
            }
        });
    }
    
    // Voice recording button
    if (elements.voiceButton) {
        elements.voiceButton.addEventListener('click', toggleVoiceRecording);
    }
    
    // File upload button
    if (elements.fileButton && elements.fileInput) {
        elements.fileButton.addEventListener('click', () => {
            elements.fileInput.click();
        });
        
        elements.fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                handleFileUpload(file);
            }
            // Reset input
            event.target.value = '';
        });
    }
    
    // Mobile menu toggle
    if (elements.mobileMenuToggle) {
        elements.mobileMenuToggle.addEventListener('click', toggleMobileMenu);
        
        // Close menu on outside click
        document.addEventListener('click', (event) => {
            if (elements.mobileMenu && 
                !elements.mobileMenu.contains(event.target) && 
                !elements.mobileMenuToggle.contains(event.target)) {
                closeMobileMenu();
            }
        });
        
        // Close menu on escape key
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeMobileMenu();
            }
        });
    }
    
    // Window resize handler
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (window.innerWidth > 768) {
                closeMobileMenu();
            }
        }, 250);
    });
}

// ============================================================================
// WebSocket Connection (Optional Enhancement)
// ============================================================================

/**
 * Initialize WebSocket connection for real-time updates
 */
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    try {
        state.websocket = new WebSocket(wsUrl);
        
        state.websocket.onopen = () => {
            console.log('WebSocket connection established');
        };
        
        state.websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'signal') {
                    updateSignals([data.signal]);
                } else if (data.type === 'chat') {
                    addMessage(data.content, 'bot', data.timestamp);
                    hideTypingIndicator();
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };
        
        state.websocket.onclose = () => {
            console.log('WebSocket connection closed');
            // Reconnect after delay
            setTimeout(initializeWebSocket, 5000);
        };
        
        state.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
    } catch (error) {
        console.error('Error initializing WebSocket:', error);
    }
}

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize the application
 */
function initializeApp() {
    console.log('AI Crypto Trading Dashboard initialized');
    
    // Initialize event listeners
    initializeEventListeners();
    
    // Start signal polling
    startSignalPolling();
    
    // Initialize WebSocket (optional)
    // initializeWebSocket();
    
    // Add initial welcome message
    addMessage('Welcome to AI Crypto Trading Dashboard! How can I assist you today?', 'bot');
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}

// ============================================================================
// Export for testing (if using modules)
// ============================================================================

// Uncomment for module-based testing
// export {
//     sendChatMessage,
//     toggleVoiceRecording,
//     handleFileUpload,
//     fetchSignals,
//     toggleMobileMenu,
//     sanitizeInput,
//     validateFile,
//     addMessage,
//     updateSignals
// };