// ============================================================
// SMS Web Viewer — API-driven Frontend
// ============================================================

const API_BASE = '/api';

// Fetch Interceptor for 401 Unauthorized
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await originalFetch(...args);
    if (response.status === 401) {
        // Show login modal if not already open
        const loginModalEl = document.getElementById('loginModal');
        if (loginModalEl && !loginModalEl.classList.contains('show')) {
            const modal = new bootstrap.Modal(loginModalEl);
            modal.show();
        }
    }
    return response;
};

// State
let currentContact = null;
let contactsData = [];
let conversationData = [];
let currentMessagesToRender = [];
let renderedCount = 0;
const CHUNK_SIZE = 50;

// DOM Elements
const contactList = document.getElementById('contact-list');
const chatWindow = document.getElementById('chat-window');
const callsWindow = document.getElementById('calls-window');
const contactSearch = document.getElementById('contact-search');
const contactFilter = document.getElementById('contact-filter');
const conversationSearch = document.getElementById('conversation-search');
const searchStartDate = document.getElementById('search-start-date');
const searchEndDate = document.getElementById('search-end-date');
const darkModeToggle = document.getElementById('dark-mode-toggle');
const syncDot = document.getElementById('sync-dot');
const syncText = document.getElementById('sync-text');
const manualUploadBtn = document.getElementById('manual-upload-btn');
const xmlUploadInput = document.getElementById('xml-upload-input');
const syncStats = document.getElementById('sync-stats');
const syncBtn = document.getElementById('sync-btn');
const exportBtnCSV = document.getElementById('export-csv');
const exportBtnPDF = document.getElementById('export-pdf');
const exportBtnJSON = document.getElementById('export-json');
const exportBtnMedia = document.getElementById('export-media');

// ---- API Functions ----
async function fetchContacts(search = '', filter = 'all') {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (filter && filter !== 'all') params.set('filter', filter);
    const url = `${API_BASE}/contacts?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch contacts: ${res.status}`);
    return res.json();
}

async function fetchConversation(normalizedAddress, search = '') {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    const url = `${API_BASE}/conversations/${encodeURIComponent(normalizedAddress)}?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch conversation: ${res.status}`);
    return res.json();
}

async function fetchCalls(normalizedAddress) {
    const url = `${API_BASE}/calls/${encodeURIComponent(normalizedAddress)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch calls: ${res.status}`);
    return res.json();
}

async function fetchSyncStatus() {
    const res = await fetch(`${API_BASE}/sync/status`);
    if (!res.ok) return null;
    return res.json();
}

// ---- Global Search ----
const globalSearchEl = document.getElementById('global-search');
globalSearchEl.addEventListener('keypress', async (e) => {
    if (e.key === 'Enter') {
        const query = globalSearchEl.value.trim();
        if (!query) return;
        
        document.getElementById('messages-tab').click();
        chatWindow.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary" role="status"></div></div>';
        
        try {
            const res = await fetch(`${API_BASE}/search/global?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            renderGlobalSearchResults(data, query);
        } catch (e) {
            console.error('Global search failed', e);
            chatWindow.innerHTML = '<div class="alert alert-danger m-3">Search failed</div>';
        }
    }
});

function renderGlobalSearchResults(messages, query) {
    if (!messages || messages.length === 0) {
        chatWindow.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-search d-block"></i>
                <p>No messages found matching "${escapeHtml(query)}"</p>
            </div>`;
        return;
    }
    
    // Clear active contact
    document.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
    currentContact = null;
    
    let html = `<h5 class="mb-3 border-bottom pb-2">Global Search Results: "${escapeHtml(query)}"</h5>`;
    
    messages.forEach(msg => {
        const d = new Date(msg.date_ms);
        const dateStr = msg.readable_date || d.toLocaleString();
        const contactName = msg.contact_name || msg.normalized_address || "Unknown";
        
        let bodyHtml = escapeHtml(msg.body || '');
        if (query) {
            // Safe highlight
            const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            bodyHtml = bodyHtml.replace(regex, '<mark>$1</mark>');
        }
        
        const isIncoming = msg.source === 'sms' ? msg.type === 1 : msg.type === 1;
        const icon = isIncoming ? '<i class="fas fa-arrow-down text-success"></i> Received' : '<i class="fas fa-arrow-up text-primary"></i> Sent';
        
        html += `
            <div class="card mb-2 border shadow-sm" style="cursor: pointer; transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'" onclick="loadGlobalResult('${msg.normalized_address}')">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between mb-1">
                        <strong><i class="fas fa-user-circle text-muted me-1"></i> ${escapeHtml(contactName)}</strong>
                        <small class="text-muted">${dateStr}</small>
                    </div>
                    <div class="small text-muted mb-2">${icon}</div>
                    <div class="message-bubble w-100 ${isIncoming ? 'incoming' : 'outgoing'}" style="max-width: 100%">
                        ${bodyHtml}
                    </div>
                </div>
            </div>
        `;
    });
    
    chatWindow.innerHTML = html;
}

window.loadGlobalResult = async function(normalized_address) {
    globalSearchEl.value = '';
    const item = document.querySelector(`[data-number="${normalized_address}"]`);
    if (item) {
        item.click();
    } else {
        currentContact = { normalized_address };
        await loadMessages(normalized_address);
        await loadCalls(normalized_address);
        if (window.innerWidth <= 768) {
            document.body.classList.add('mobile-chat-active');
        }
    }
};

// ---- Messages Tab Rendering ----
function renderContacts(contacts) {
    contactList.innerHTML = '';
    if (contacts.length === 0) {
        contactList.innerHTML = `
            <li class="empty-state">
                <i class="fas fa-address-book d-block"></i>
                <span>No contacts found</span>
            </li>`;
        return;
    }
    contacts.forEach(c => {
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        if (currentContact === c.normalized_address) li.classList.add('active');
        li.innerHTML = `
            <div>
                <div class="contact-name">${escapeHtml(c.display_name || 'Unknown')}</div>
                <div class="contact-number">${escapeHtml(c.normalized_address)}</div>
            </div>
            <span class="contact-count">${c.message_count}</span>`;
        li.addEventListener('click', () => selectContact(c.normalized_address));
        contactList.appendChild(li);
    });
}

function renderMessages(messages, append = false) {
    if (!append) {
        chatWindow.innerHTML = '';
        renderedCount = 0;
    }

    if (messages.length === 0) {
        chatWindow.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-comments d-block"></i>
                <p>No messages found</p>
            </div>`;
        return;
    }

    const endIdx = messages.length - renderedCount;
    if (endIdx <= 0) return; // All rendered
    
    const startIdx = Math.max(0, endIdx - CHUNK_SIZE);
    const chunk = messages.slice(startIdx, endIdx);
    
    const fragment = document.createDocumentFragment();
    let prevMsg = null;

    const oldScrollHeight = chatWindow.scrollHeight;

    chunk.forEach((msg, i) => {
        const msgDate = new Date(msg.date_ms);
        const dateStr = msgDate.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
        
        let showDate = false;
        if (prevMsg) {
            const prevDateStr = new Date(prevMsg.date_ms).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
            if (dateStr !== prevDateStr) showDate = true;
        } else if (startIdx === 0 && i === 0 || !append && i === 0) {
            showDate = true;
        }

        if (showDate) {
            const div = document.createElement('div');
            div.className = 'date-divider';
            div.innerHTML = `<span>${dateStr}</span>`;
            fragment.appendChild(div);
        }

        const isIncoming = msg.type === 1;
        const row = document.createElement('div');
        row.className = `message-row ${isIncoming ? 'incoming' : 'outgoing'}`;

        let clusterCls = '';
        const nextMsg = chunk[i+1];
        const isSamePrev = prevMsg && prevMsg.type === msg.type && (msg.date_ms - prevMsg.date_ms) < 120000;
        const isSameNext = nextMsg && nextMsg.type === msg.type && (nextMsg.date_ms - msg.date_ms) < 120000;
        
        if (isSamePrev && isSameNext) clusterCls = 'cluster-middle';
        else if (isSamePrev) clusterCls = 'cluster-bottom';
        else if (isSameNext) clusterCls = 'cluster-top';
        
        if (isSamePrev) row.classList.add('clustered');

        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${isIncoming ? 'incoming' : 'outgoing'} ${clusterCls}`;

        if (msg.body) {
            const bodyEl = document.createElement('div');
            let text = escapeHtml(msg.body);
            const searchVal = conversationSearch.value.trim();
            if (searchVal) {
                const regex = new RegExp(`(${escapeRegExp(searchVal)})`, 'gi');
                text = text.replace(regex, '<mark>$1</mark>');
            }
            bodyEl.innerHTML = text;
            bubble.appendChild(bodyEl);
        }

        if (msg.has_media && msg.source === 'mms' && msg.media_parts && msg.media_parts.length > 0) {
            const mediaContainer = document.createElement('div');
            mediaContainer.className = 'message-media-container mt-2';
            
            const btn = document.createElement('button');
            btn.className = 'btn btn-sm btn-outline-secondary';
            btn.innerHTML = `<i class="fas fa-paperclip"></i> Load ${msg.media_parts.length} Attachment(s)`;
            
            btn.addEventListener('click', () => {
                btn.style.display = 'none';
                msg.media_parts.forEach(part => {
                    const url = `${API_BASE}/mms/${msg.id}/media/${part.id}`;
                    let el;
                    if (part.content_type.startsWith('image/')) {
                        el = document.createElement('img');
                        el.src = url;
                        el.className = 'img-fluid rounded mt-1 mb-1 d-block';
                        el.addEventListener('click', () => openLightbox(url, 'image'));
                    } else if (part.content_type.startsWith('video/')) {
                        el = document.createElement('video');
                        el.src = url;
                        el.controls = true;
                        el.className = 'img-fluid rounded mt-1 mb-1 d-block';
                        el.style.maxWidth = '250px';
                    } else if (part.content_type.startsWith('audio/')) {
                        el = document.createElement('audio');
                        el.src = url;
                        el.controls = true;
                        el.className = 'mt-1 mb-1 d-block';
                    } else {
                        el = document.createElement('a');
                        el.href = url;
                        el.target = '_blank';
                        el.textContent = `Download attachment (${part.content_type})`;
                        el.className = 'd-block mt-1 mb-1';
                    }
                    mediaContainer.appendChild(el);
                });
            });
            mediaContainer.appendChild(btn);
            bubble.appendChild(mediaContainer);
        }

        const timeEl = document.createElement('div');
        timeEl.className = 'message-time';
        timeEl.textContent = new Date(msg.date_ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        bubble.appendChild(timeEl);

        row.appendChild(bubble);
        fragment.appendChild(row);
        prevMsg = msg;
    });

    if (append) {
        chatWindow.insertBefore(fragment, chatWindow.firstChild);
        chatWindow.scrollTop = chatWindow.scrollHeight - oldScrollHeight;
    } else {
        chatWindow.appendChild(fragment);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    
    renderedCount += chunk.length;
}

chatWindow.addEventListener('scroll', () => {
    if (chatWindow.scrollTop === 0 && renderedCount < currentMessagesToRender.length) {
        renderMessages(currentMessagesToRender, true);
    }
});

function openLightbox(url, type) {
    const lb = document.getElementById('lightbox');
    const container = document.getElementById('lightbox-container');
    container.innerHTML = '';
    if (type === 'image') {
        const img = document.createElement('img');
        img.src = url;
        img.id = 'lightbox-content';
        container.appendChild(img);
    }
    lb.classList.add('active');
}

document.getElementById('lightbox-close').addEventListener('click', () => {
    document.getElementById('lightbox').classList.remove('active');
});
document.getElementById('lightbox').addEventListener('click', (e) => {
    if (e.target.id === 'lightbox' || e.target.id === 'lightbox-container') {
        document.getElementById('lightbox').classList.remove('active');
    }
});

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function renderCalls(calls) {
    callsWindow.innerHTML = '';
    if (calls.length === 0) {
        callsWindow.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-phone d-block"></i>
                <p>No call history</p>
            </div>`;
        return;
    }
    calls.forEach(call => {
        const typeMap = {
            1: { label: 'Incoming', cls: 'incoming', icon: 'fa-phone-arrow-down' },
            2: { label: 'Outgoing', cls: 'outgoing', icon: 'fa-phone-arrow-up' },
            3: { label: 'Missed', cls: 'missed', icon: 'fa-phone-missed' }
        };
        const info = typeMap[call.type] || typeMap[1];
        const duration = call.duration > 0 ? formatDuration(call.duration) : 'No answer';

        const div = document.createElement('div');
        div.className = 'call-item';
        div.innerHTML = `
            <div class="call-icon ${info.cls}"><i class="fas ${info.icon}"></i></div>
            <div class="flex-grow-1">
                <div style="font-weight:500; font-size:0.85rem;">${info.label}</div>
                <div style="font-size:0.75rem; color:var(--text-secondary);">${call.readable_date || formatTimestamp(call.date_ms)}</div>
            </div>
            <div style="font-size:0.8rem; color:var(--text-secondary);">${duration}</div>`;
        callsWindow.appendChild(div);
    });
}

function updateSyncStatus(data) {
    if (!data) return;
    
    const progressContainer = document.getElementById('sync-progress-container');
    const progressBar = document.getElementById('sync-progress-bar');
    
    syncDot.className = 'sync-dot ' + (data.status || 'never');
    
    if (data.status === 'success') {
        syncText.textContent = `Last synced: ${new Date(data.timestamp).toLocaleString()}`;
        if (progressContainer && !progressContainer.classList.contains('d-none')) {
            progressBar.style.width = '100%';
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-success');
            syncText.textContent = 'Sync Complete!';
            setTimeout(() => {
                progressContainer.classList.add('d-none');
                syncText.textContent = `Last synced: ${new Date(data.timestamp).toLocaleString()}`;
            }, 3000);
        }
    } else if (data.status === 'running') {
        syncText.textContent = 'Syncing...';
        progressContainer.classList.remove('d-none');
        progressBar.classList.add('progress-bar-animated');
        progressBar.classList.remove('bg-success');
        
        let pct = 0;
        if (data.stats && data.stats.processing) {
            syncText.textContent = `Processing ${data.stats.processing}...`;
            pct = 100;
        } else if (data.stats && typeof data.stats.progress === 'number') {
            pct = data.stats.progress;
            const type = data.stats.progress_type || '';
            syncText.textContent = `Downloading ${type} (${pct}%)...`;
        }
        progressBar.style.width = `${pct}%`;
    } else if (data.status === 'error') {
        syncText.textContent = `Sync error: ${data.error || 'Unknown'}`;
        progressContainer.classList.add('d-none');
    } else {
        syncText.textContent = 'No sync performed yet';
        progressContainer.classList.add('d-none');
    }
    
    if (data.stats && Object.keys(data.stats).length > 0 && data.status !== 'running') {
        const parts = [];
        if (data.stats.sms !== undefined) parts.push(`${data.stats.sms} SMS`);
        if (data.stats.mms !== undefined) parts.push(`${data.stats.mms} MMS`);
        if (data.stats.calls !== undefined) parts.push(`${data.stats.calls} calls`);
        syncStats.textContent = parts.length > 0 ? `(${parts.join(', ')})` : '';
    } else if (data.status === 'running') {
        syncStats.textContent = '';
    }
}

// ---- Actions ----
async function selectContact(normalizedAddress) {
    currentContact = normalizedAddress;
    // Re-render contacts to update active state
    renderContacts(contactsData);
    // Mobile View specific
    document.getElementById('app-container').classList.add('mobile-chat-active');

    chatWindow.innerHTML = `
        <div class="d-flex justify-content-center align-items-center mt-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <span class="ms-3 text-muted">Loading messages...</span>
        </div>`;
        
    callsWindow.innerHTML = `
        <div class="d-flex justify-content-center align-items-center mt-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <span class="ms-3 text-muted">Loading calls...</span>
        </div>`;

    // Load conversation
    try {
        conversationData = await fetchConversation(normalizedAddress);
        currentMessagesToRender = conversationData;
        
        // Reset search bar when switching contacts
        conversationSearch.value = '';
        searchStartDate.value = '';
        searchEndDate.value = '';
        
        renderMessages(currentMessagesToRender);
    } catch (e) {
        console.error(e);
        chatWindow.innerHTML = '<div class="empty-state"><p>Failed to load messages</p></div>';
    }
    // Load calls
    try {
        const calls = await fetchCalls(normalizedAddress);
        renderCalls(calls);
    } catch (e) {
        console.error(e);
        callsWindow.innerHTML = '<div class="empty-state"><p>Failed to load calls</p></div>';
    }
}

// Manual Upload
manualUploadBtn.addEventListener('click', () => {
    xmlUploadInput.click();
});

xmlUploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Client-side size guard — mirrors the server-side 4 GB limit
    const MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024; // 4 GB
    if (file.size > MAX_UPLOAD_BYTES) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        alert(
            `❌ File too large\n\n` +
            `"${file.name}" is ${sizeMB} MB, which exceeds the maximum upload size of 4 GB.\n\n` +
            `Please split the backup into smaller files and try again.`
        );
        xmlUploadInput.value = '';
        return;
    }
    
    // Simple heuristic to determine if calls or sms
    let fileType = "sms";
    if (file.name.toLowerCase().includes("calls")) {
        fileType = "calls";
    }
    
    const formData = new FormData();
    formData.append("file", file);
    formData.append("file_type", fileType);
    
    manualUploadBtn.disabled = true;
    manualUploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
    
    try {
        const res = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (res.ok) {
            alert(`Upload complete! ${data.message}`);
            await loadContacts();
            if (currentContact) selectContact(currentContact);
        } else {
            alert(`Upload failed: ${data.detail || 'Unknown error'}`);
        }
    } catch (err) {
        alert("Upload failed: " + err.message);
    } finally {
        manualUploadBtn.disabled = false;
        manualUploadBtn.innerHTML = '<i class="fas fa-upload"></i> Upload XML';
        xmlUploadInput.value = ''; // Reset input
    }
});

async function triggerSync() {
    syncBtn.disabled = true;
    syncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
    try {
        await fetch(`${API_BASE}/sync`, { method: 'POST' });
        // Poll for completion
        const pollInterval = setInterval(async () => {
            const status = await fetchSyncStatus();
            updateSyncStatus(status);
            if (status && status.status !== 'running') {
                clearInterval(pollInterval);
                syncBtn.disabled = false;
                syncBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Now';
                
                if (status.status === 'success') {
                    // Soft refresh data
                    await loadContacts();
                    if (currentContact) {
                        selectContact(currentContact);
                    }
                } else if (status.status === 'error') {
                    alert('Sync failed: ' + status.error);
                }
            }
        }, 2000);
    } catch (e) {
        console.error(e);
        syncBtn.disabled = false;
        syncBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Now';
    }
}

async function loadContacts() {
    const search = contactSearch.value.trim();
    const filter = contactFilter.value;
    try {
        contactsData = await fetchContacts(search, filter);
        renderContacts(contactsData);
    } catch (e) {
        console.error('Failed to load contacts:', e);
    }
}

// ---- Event Listeners ----
let searchDebounce;
contactSearch.addEventListener('input', () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(loadContacts, 300);
});

contactFilter.addEventListener('change', loadContacts);

document.getElementById('toggle-search').addEventListener('click', () => {
    const container = document.getElementById('search-bar-container');
    container.classList.toggle('search-bar-collapsed');
    container.classList.toggle('search-bar-expanded');
});

document.getElementById('btn-mobile-back')?.addEventListener('click', () => {
    document.getElementById('app-container').classList.remove('mobile-chat-active');
});

function applyFilters() {
    const term = conversationSearch.value.toLowerCase();
    const startVal = searchStartDate.value;
    const endVal = searchEndDate.value;

    let startMs = null;
    let endMs = null;

    if (startVal) startMs = new Date(startVal + "T00:00:00").getTime();
    if (endVal) endMs = new Date(endVal + "T23:59:59").getTime();

    currentMessagesToRender = conversationData.filter(msg => {
        if (term && (!msg.body || !msg.body.toLowerCase().includes(term))) {
            return false;
        }
        if (startMs && msg.date_ms < startMs) return false;
        if (endMs && msg.date_ms > endMs) return false;
        return true;
    });

    renderMessages(currentMessagesToRender);
}

conversationSearch.addEventListener('input', applyFilters);
searchStartDate.addEventListener('change', applyFilters);
searchEndDate.addEventListener('change', applyFilters);

// Export Functions
exportBtnCSV.addEventListener('click', (e) => {
    e.preventDefault();
    if (!currentContact) { alert('Select a contact first.'); return; }
    window.location.href = `${API_BASE}/export/csv/${encodeURIComponent(currentContact)}`;
});

exportBtnJSON.addEventListener('click', (e) => {
    e.preventDefault();
    if (!currentContact) { alert('Select a contact first.'); return; }
    window.location.href = `${API_BASE}/export/json/${encodeURIComponent(currentContact)}`;
});

exportBtnMedia.addEventListener('click', (e) => {
    e.preventDefault();
    if (!currentContact) { alert('Select a contact first.'); return; }
    window.location.href = `${API_BASE}/export/media/${encodeURIComponent(currentContact)}`;
});

document.getElementById('export-pdf').addEventListener('click', async (e) => {
    e.preventDefault();
    if (!currentContact || !conversationData.length) {
        alert('Select a contact with messages first.');
        return;
    }
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    const name = conversationData[0]?.contact_name || 'Unknown';

    doc.setFontSize(18);
    doc.text('Message Conversation', 10, 10);
    doc.setFontSize(12);
    doc.text(`Contact: ${name}`, 10, 20);
    doc.text(`Number: ${currentContact}`, 10, 30);

    let y = 40;
    doc.setFontSize(10);

    conversationData.forEach((msg, i) => {
        const msgType = msg.type === 1 ? 'Received' : 'Sent';
        const header = `${i + 1}. ${msgType} (${msg.readable_date || ''})`;
        const body = msg.body || '';
        const lines = doc.splitTextToSize(body, 180);

        doc.setTextColor(100);
        doc.text(header, 10, y); y += 6;
        doc.setTextColor(50);
        lines.forEach(line => { doc.text(line, 10, y); y += 6; });
        y += 4;

        if (y > 270) { doc.addPage(); y = 10; }
    });

    doc.save(`Messages_${name !== 'Unknown' ? name : currentContact}.pdf`);
});

// Dark Mode
darkModeToggle.addEventListener('click', toggleDarkMode);

function toggleDarkMode() {
    const isDark = document.body.classList.toggle('dark-mode');
    if (isDark) {
        loadDarkModeCSS();
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light Mode';
    } else {
        unloadDarkModeCSS();
        darkModeToggle.innerHTML = '<i class="fas fa-moon"></i> Dark Mode';
    }
    localStorage.setItem('darkMode', isDark);
}

function loadDarkModeCSS() {
    let link = document.getElementById('dark-mode-styles');
    if (!link || link.getAttribute('href') === '#') {
        if (link) link.remove();
        link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'dark-mode.css';
        link.id = 'dark-mode-styles';
        document.head.appendChild(link);
    }
}

function unloadDarkModeCSS() {
    const link = document.getElementById('dark-mode-styles');
    if (link) link.remove();
}

// ---- Utility ----
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function formatTimestamp(ms) {
    if (!ms) return '';
    return new Date(ms).toLocaleString();
}

function formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ---- Auth / Settings Actions ----
const settingsModalEl = document.getElementById('settingsModal');
const gdriveStatusEl = document.getElementById('gdrive-status');
const gdriveConnectContainer = document.getElementById('gdrive-connect-container');
const gdriveSettingsContainer = document.getElementById('gdrive-settings-container');

settingsModalEl.addEventListener('show.bs.modal', async () => {
    try {
        const res = await fetch(`${API_BASE}/auth/status`);
        if (res.ok) {
            const data = await res.json();

            if (data.connected) {
                gdriveStatusEl.innerHTML = '<span class="badge bg-success">Connected</span>';
                gdriveConnectContainer.classList.add('d-none');
                gdriveSettingsContainer.classList.remove('d-none');
                await loadDriveFolders(data.folder_id);
                const schedSelect = document.getElementById('sync-schedule-select');
                if (schedSelect) schedSelect.value = data.sync_schedule || "manual";
                
                const notifUrls = document.getElementById('notification-urls');
                if (notifUrls) notifUrls.value = data.notification_urls || '';
                
                const notifSuccess = document.getElementById('notify-success');
                if (notifSuccess) notifSuccess.checked = data.notify_on_success || false;
                
                const notifFailure = document.getElementById('notify-failure');
                if (notifFailure) notifFailure.checked = data.notify_on_failure !== undefined ? data.notify_on_failure : true;
            } else {
                gdriveStatusEl.innerHTML = '<span class="badge bg-warning text-dark">Not Connected</span>';
                gdriveConnectContainer.classList.remove('d-none');
                gdriveSettingsContainer.classList.add('d-none');
            }
        }
    } catch (e) {
        console.error("Failed to check auth status", e);
        gdriveStatusEl.innerHTML = '<span class="badge bg-danger">Error</span>';
    }
    
    // Load Database Statistics
    const statsContainer = document.getElementById('db-stats-container');
    statsContainer.innerHTML = '<p class="text-muted">Loading stats...</p>';
    try {
        const res = await fetch(`${API_BASE}/stats`);
        if (res.ok) {
            const stats = await res.json();
            statsContainer.innerHTML = `
                <ul class="list-group">
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        Total Contacts
                        <span class="badge bg-primary rounded-pill">${stats.total_contacts.toLocaleString()}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        Total Messages (SMS + MMS)
                        <span class="badge bg-primary rounded-pill">${(stats.total_sms + stats.total_mms).toLocaleString()}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        Total Calls
                        <span class="badge bg-primary rounded-pill">${stats.total_calls.toLocaleString()}</span>
                    </li>
                </ul>
            `;
        } else {
            statsContainer.innerHTML = '<p class="text-danger">Failed to load statistics.</p>';
        }
    } catch (e) {
        console.error("Failed to load stats", e);
        statsContainer.innerHTML = '<p class="text-danger">Failed to load statistics.</p>';
    }
});

document.getElementById('btn-connect-gdrive')?.addEventListener('click', async () => {
    try {
        const res = await fetch(`${API_BASE}/auth/login`);
        const data = await res.json();
        if (data.url) window.location.href = data.url;
    } catch (e) {
        alert('Failed to initiate login: ' + e.message);
    }
});

async function loadDriveFolders(selectedId) {
    const select = document.getElementById('gdrive-folder-select');
    select.innerHTML = '<option value="">Loading...</option>';
    try {
        const res = await fetch(`${API_BASE}/gdrive/folders`);
        const folders = await res.json();
        select.innerHTML = '<option value="">-- Select Folder --</option>';
        folders.forEach(f => {
            const option = document.createElement('option');
            option.value = f.id;
            option.textContent = f.name;
            if (f.id === selectedId) option.selected = true;
            select.appendChild(option);
        });
    } catch (e) {
        select.innerHTML = '<option value="">Error loading folders</option>';
    }
}

document.getElementById('gdrive-folder-search')?.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const options = document.querySelectorAll('#gdrive-folder-select option');
    options.forEach(opt => {
        if (!opt.value) return; // Always keep the placeholder
        const text = opt.textContent.toLowerCase();
        opt.style.display = text.includes(term) ? '' : 'none';
    });
});

document.getElementById('btn-save-gdrive-settings')?.addEventListener('click', async () => {
    const select = document.getElementById('gdrive-folder-select');
    const folder_id = select.value;
    const scheduleSelect = document.getElementById('sync-schedule-select');
    const sync_schedule = scheduleSelect ? scheduleSelect.value : "manual";
    
    const notification_urls = document.getElementById('notification-urls')?.value || '';
    const notify_on_success = document.getElementById('notify-success')?.checked || false;
    const notify_on_failure = document.getElementById('notify-failure')?.checked || false;
    
    if (!folder_id) return alert('Please select a folder');
    
    try {
        const res = await fetch(`${API_BASE}/gdrive/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                folder_id, 
                sync_schedule,
                notification_urls,
                notify_on_success,
                notify_on_failure
            })
        });
        if (res.ok) {
            alert('Settings saved!');
            const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
            modal.hide();
        } else {
            const data = await res.json();
            alert('Error: ' + data.detail);
        }
    } catch (e) {
        alert('Failed to save settings: ' + e.message);
    }
});

document.getElementById('btn-test-notification')?.addEventListener('click', async () => {
    const urls = document.getElementById('notification-urls')?.value;
    const resultDiv = document.getElementById('notification-test-result');
    if (!urls) {
        resultDiv.innerHTML = '<span class="text-danger">Please enter at least one URL first.</span>';
        return;
    }
    
    resultDiv.innerHTML = '<span class="text-muted">Sending test notification...</span>';
    try {
        const res = await fetch(`${API_BASE}/gdrive/test-notification`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls })
        });
        if (res.ok) {
            resultDiv.innerHTML = '<span class="text-success"><i class="fas fa-check"></i> Notification sent!</span>';
        } else {
            const data = await res.json();
            resultDiv.innerHTML = `<span class="text-danger"><i class="fas fa-times"></i> ${data.detail || 'Failed to send'}</span>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<span class="text-danger"><i class="fas fa-times"></i> ${e.message}</span>`;
    }
});

// ---- Auth & Tokens ----
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const errEl = document.getElementById('login-error');
    const u = document.getElementById('login-username').value;
    const p = document.getElementById('login-password').value;
    
    btn.disabled = true;
    errEl.classList.add('d-none');
    
    const formData = new FormData();
    formData.append('username', u);
    formData.append('password', p);
    
    try {
        const res = await originalFetch(`${API_BASE}/user/login`, {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            window.location.reload();
        } else {
            const data = await res.json();
            errEl.textContent = data.detail || 'Login failed';
            errEl.classList.remove('d-none');
        }
    } catch (err) {
        errEl.textContent = 'Connection error';
        errEl.classList.remove('d-none');
    } finally {
        btn.disabled = false;
    }
});

document.getElementById('btn-logout')?.addEventListener('click', async (e) => {
    e.preventDefault();
    await originalFetch(`${API_BASE}/user/logout`, { method: 'POST' });
    window.location.reload();
});

const tokensModalEl = document.getElementById('tokensModal');
if (tokensModalEl) {
    tokensModalEl.addEventListener('show.bs.modal', loadTokens);
}

async function loadTokens() {
    const list = document.getElementById('tokens-list');
    list.innerHTML = '<li class="list-group-item text-center text-muted small py-3">Loading tokens...</li>';
    try {
        const res = await fetch(`${API_BASE}/user/tokens`);
        if (res.ok) {
            const tokens = await res.json();
            if (tokens.length === 0) {
                list.innerHTML = '<li class="list-group-item text-center text-muted small py-3">No API tokens generated yet.</li>';
                return;
            }
            list.innerHTML = '';
            tokens.forEach(t => {
                const li = document.createElement('li');
                li.className = 'list-group-item d-flex justify-content-between align-items-center';
                const date = new Date(t.created_at).toLocaleString();
                const badge = t.is_global ? '<span class="badge bg-danger ms-2">Global</span>' : '';
                const desc = t.description ? `<div class="small text-muted mb-1">${t.description}</div>` : '';
                li.innerHTML = `
                    <div>
                        <strong>Token ID: ${t.id}</strong> ${badge}
                        ${desc}
                        <div class="small text-muted">Created: ${date}</div>
                    </div>
                    <button class="btn btn-sm btn-outline-danger" onclick="revokeToken('${t.id}')">Revoke</button>
                `;
                list.appendChild(li);
            });
        }
    } catch (e) {
        list.innerHTML = '<li class="list-group-item text-danger small">Failed to load tokens</li>';
    }
}

async function revokeToken(id) {
    if (!confirm('Are you sure you want to revoke this token?')) return;
    try {
        const res = await fetch(`${API_BASE}/user/tokens/${id}`, { method: 'DELETE' });
        if (res.ok) {
            loadTokens();
        } else {
            alert('Failed to revoke token');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

document.getElementById('btn-generate-token')?.addEventListener('click', async () => {
    const isGlobal = document.getElementById('global-token-check')?.checked || false;
    const desc = document.getElementById('token-description-input')?.value.trim() || 'Generated API Token';
    try {
        const res = await fetch(`${API_BASE}/user/tokens?is_global=${isGlobal}&description=${encodeURIComponent(desc)}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('new-token-value').textContent = data.token;
            document.getElementById('new-token-alert').classList.remove('d-none');
            const descInput = document.getElementById('token-description-input');
            if (descInput) descInput.value = '';
            loadTokens();
        } else {
            const data = await res.json();
            alert('Error: ' + data.detail);
        }
    } catch (e) {
        alert('Failed to generate token');
    }
});

document.getElementById('btn-copy-token')?.addEventListener('click', async () => {
    const tokenVal = document.getElementById('new-token-value').textContent;
    try {
        await navigator.clipboard.writeText(tokenVal);
        const icon = document.querySelector('#btn-copy-token i');
        if (icon) {
            icon.className = 'fas fa-check text-success';
            setTimeout(() => {
                icon.className = 'fas fa-copy';
            }, 2000);
        }
    } catch (err) {
        console.error('Failed to copy', err);
    }
});

// ---- Init ----
(async function init() {
    // Restore dark mode
    if (localStorage.getItem('darkMode') === 'true') {
        document.body.classList.add('dark-mode');
        loadDarkModeCSS();
        darkModeToggle.innerHTML = '<i class="fas fa-sun"></i> Light Mode';
    }
    // Check for auth callback
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('auth') === 'success') {
        window.history.replaceState({}, document.title, window.location.pathname);
        setTimeout(() => {
            const modal = new bootstrap.Modal(document.getElementById('settingsModal'));
            modal.show();
        }, 500);
    }

    // Check user auth state
    try {
        const meRes = await originalFetch(`${API_BASE}/user/me`);
        if (meRes.ok) {
            const me = await meRes.json();
            document.getElementById('user-menu').style.display = 'block';
            document.getElementById('btn-show-login').style.display = 'none';
            document.getElementById('user-name-display').textContent = me.username;
            
            if (me.role === 'admin') {
                document.getElementById('global-token-container').classList.remove('d-none');
                document.getElementById('menu-user-management').classList.remove('d-none');
            }
            if (me.auth_mode === 'OIDC') {
                document.getElementById('oidc-login-section').classList.remove('d-none');
                document.getElementById('login-form').classList.add('d-none');
            }
            if (me.auth_mode === 'NONE') {
                document.getElementById('btn-logout').style.display = 'none';
            }
        } else {
            document.getElementById('user-menu').style.display = 'none';
            document.getElementById('btn-show-login').style.display = 'block';
        }
    } catch (e) {
        console.error('Failed to check auth state', e);
    }

    // Load sync status
    const status = await fetchSyncStatus();
    updateSyncStatus(status);
    // Load contacts
    await loadContacts();
})();

// ---- User Management & Password Change ----
document.getElementById('password-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const currentPass = document.getElementById('current-password').value;
    const newPass = document.getElementById('new-password').value;
    const errEl = document.getElementById('password-error');
    const succEl = document.getElementById('password-success');
    errEl.classList.add('d-none');
    succEl.classList.add('d-none');
    
    try {
        const res = await fetch(`${API_BASE}/user/password`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                current_password: currentPass,
                new_password: newPass
            })
        });
        const data = await res.json();
        if (res.ok) {
            succEl.textContent = 'Password updated successfully!';
            succEl.classList.remove('d-none');
            e.target.reset();
        } else {
            errEl.textContent = data.detail || 'Failed to update password';
            errEl.classList.remove('d-none');
        }
    } catch (err) {
        errEl.textContent = 'An error occurred';
        errEl.classList.remove('d-none');
    }
});

const userManagementModalEl = document.getElementById('userManagementModal');
if (userManagementModalEl) {
    userManagementModalEl.addEventListener('show.bs.modal', loadUsers);
}

async function loadUsers() {
    const tbody = document.getElementById('users-table-body');
    const errEl = document.getElementById('um-error');
    errEl.classList.add('d-none');
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Loading...</td></tr>';
    
    try {
        const res = await fetch(`${API_BASE}/user/all`);
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Failed to load users');
        }
        const users = await res.json();
        
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No users found</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        for (const u of users) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${u.username}</td>
                <td><span class="badge ${u.role === 'admin' ? 'bg-danger' : 'bg-primary'}">${u.role}</span></td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-danger btn-delete-user" data-id="${u.id}"><i class="fas fa-trash"></i></button>
                </td>
            `;
            tbody.appendChild(tr);
        }
        
        document.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id = e.currentTarget.getAttribute('data-id');
                if (!confirm('Are you sure you want to delete this user?')) return;
                
                try {
                    const dRes = await fetch(`${API_BASE}/user/${id}`, { method: 'DELETE' });
                    if (dRes.ok) {
                        loadUsers();
                    } else {
                        const dData = await dRes.json();
                        errEl.textContent = dData.detail || 'Failed to delete user';
                        errEl.classList.remove('d-none');
                    }
                } catch(err) {
                    errEl.textContent = 'Failed to delete user';
                    errEl.classList.remove('d-none');
                }
            });
        });
        
    } catch (err) {
        errEl.textContent = err.message;
        errEl.classList.remove('d-none');
        tbody.innerHTML = '';
    }
}

document.getElementById('create-user-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('cu-username').value;
    const password = document.getElementById('cu-password').value;
    const role = document.getElementById('cu-role').value;
    const errEl = document.getElementById('um-error');
    const succEl = document.getElementById('um-success');
    errEl.classList.add('d-none');
    succEl.classList.add('d-none');
    
    try {
        const res = await fetch(`${API_BASE}/user/create`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username, password, role })
        });
        
        if (res.ok) {
            succEl.textContent = 'User created successfully!';
            succEl.classList.remove('d-none');
            e.target.reset();
            loadUsers();
        } else {
            const data = await res.json();
            errEl.textContent = data.detail || 'Failed to create user';
            errEl.classList.remove('d-none');
        }
    } catch (err) {
        errEl.textContent = 'An error occurred';
        errEl.classList.remove('d-none');
    }
});
