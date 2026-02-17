// --- Configuration ---
const API_BASE = window.location.origin;

let allRecommendations = [];
let tunerSettings = {
    content_weight: 0.40,
    collaborative_weight: 0.30,
    quality_weight: 0.20,
    confidence_weight: 0.10,
    genre: '',
    type: '',
    limit: 100
};
let pendingTunerSettings = { ...tunerSettings }; // Store pending changes
let hasPendingChanges = false;
let searchMode = localStorage.getItem('searchMode') || 'simple';
let syncPollInterval = null;

// --- Init ---
document.addEventListener('DOMContentLoaded', async () => {
    initTuner();
    initSearchMode();
    setupEventListeners();
    await populateGenres(); // Load genres before first recommendations fetch
    fetchRecommendations();

    // Check if a sync is already running
    try {
        const res = await fetch(`${API_BASE}/system/status`);
        const data = await res.json();
        if (data.status === 'running') {
            startSyncStatusPolling();
        }
    } catch (e) {
        console.error("Failed to check initial sync status:", e);
    }
});

async function initTuner() {
    try {
        // Load from localStorage first
        const localSettings = localStorage.getItem('tuner_settings');
        if (localSettings) {
            tunerSettings = { ...tunerSettings, ...JSON.parse(localSettings) };
        }

        // Then fetch from API, overriding local if available
        const res = await fetch(`${API_BASE}/settings/tuner`);
        if (res.ok) {
            const apiSettings = await res.json();
            tunerSettings = { ...tunerSettings, ...apiSettings };
        }
    } catch (e) {
        console.warn("Using default tuner settings or local settings:", e);
    } finally {
        // Ensure default limit is set if not present
        if (!tunerSettings.limit) tunerSettings.limit = 100;
        updateTunerUI();
    }
}

function initSearchMode() {
    const toggle = document.getElementById('search-mode-toggle');
    if (toggle) {
        // Set initial state based on saved preference
        toggle.checked = (searchMode === 'advanced');
        
        // Add event listener
        toggle.addEventListener('change', (e) => {
            searchMode = e.target.checked ? 'advanced' : 'simple';
            localStorage.setItem('searchMode', searchMode);
        });
    }
}

function setupEventListeners() {
    // Tuner Drawer Toggle
    const toggleBtn = document.getElementById('toggle-tuner');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const drawer = document.getElementById('tuner-drawer');
            drawer.classList.toggle('closed');
        });
    }

    // Sliders - Store changes in pending settings
    ['content', 'collab', 'quality', 'confidence'].forEach(key => {
        const slider = document.getElementById(`weight-${key}`);
        if (slider) {
            slider.addEventListener('input', (e) => {
                const val = parseFloat(e.target.value);
                document.getElementById(`val-${key}`).innerText = val.toFixed(2);

                // Map 'collab' to 'collaborative_weight' for backend compatibility
                const settingsKey = key === 'collab' ? 'collaborative_weight' : `${key}_weight`;
                pendingTunerSettings[settingsKey] = val;

                markTunerPending(true);
            });
        }
    });

    // Discovery Filters
    const genreFilter = document.getElementById('filter-genre');
    if (genreFilter) {
        genreFilter.onchange = (e) => {
            tunerSettings.genre = e.target.value;
            saveSettings();
            fetchRecommendations();
        };
    }

    const typeFilter = document.getElementById('filter-type');
    if (typeFilter) {
        typeFilter.onchange = (e) => {
            tunerSettings.type = e.target.value;
            saveSettings();
            fetchRecommendations();
        };
    }

    const limitFilter = document.getElementById('filter-limit');
    if (limitFilter) {
        limitFilter.onchange = (e) => {
            tunerSettings.limit = parseInt(e.target.value);
            saveSettings();
            fetchRecommendations();
        };
    }

    const resetBtn = document.getElementById('reset-tuner');
    if (resetBtn) {
        resetBtn.onclick = () => {
            tunerSettings = {
                content_weight: 0.40,
                collaborative_weight: 0.30,
                quality_weight: 0.20,
                confidence_weight: 0.10,
                genre: '',
                type: '',
                limit: 100
            };
            pendingTunerSettings = { ...tunerSettings };
            updateTunerUI();
            saveSettings();
            fetchRecommendations();
            markTunerPending(false);
        };
    }

    // Confirm button - Apply pending changes
    const confirmBtn = document.getElementById('confirm-tuner');
    if (confirmBtn) {
        confirmBtn.onclick = () => {
            if (!hasPendingChanges) return;
            
            // Apply pending changes
            tunerSettings = { ...tunerSettings, ...pendingTunerSettings };
            
            // Save and fetch
            saveSettings();
            fetchRecommendations();
            
            // Reset pending state
            markTunerPending(false);
        };
    }

    // App Logo Reset
    const logo = document.querySelector('.brand');
    if (logo) {
        logo.style.cursor = 'pointer';
        logo.onclick = () => {
            const searchInput = document.getElementById('global-search');
            if (searchInput) searchInput.value = '';

            // Re-use tuner reset logic
            tunerSettings = {
                content_weight: 0.40,
                collaborative_weight: 0.30,
                quality_weight: 0.20,
                confidence_weight: 0.10,
                genre: '',
                type: '',
                limit: 100
            };
            updateTunerUI();
            saveSettings();
            fetchRecommendations();

            // Close drawer if open
            const drawer = document.getElementById('tuner-drawer');
            if (drawer) drawer.classList.add('closed');
        };
    }

    // Search with Debounce
    const searchInput = document.getElementById('global-search');
    if (searchInput) {
        searchInput.addEventListener('input', debounce((e) => {
            const query = e.target.value;
            if (query.length > 2) {
                performGlobalSearch(query);
            } else if (query.length === 0) {
                fetchRecommendations(); // Restore original recs
            }
        }, 500));
    }
}

// --- Utilities ---
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function performGlobalSearch(query) {
    const grid = document.getElementById('main-grid');
    const modeText = searchMode === 'advanced' ? 'Advanced Search...' : 'Searching...';
    grid.innerHTML = `<div class="loading-full"><p>${modeText}</p></div>`;

    try {
        const res = await fetch(`${API_BASE}/search/tmdb?query=${encodeURIComponent(query)}&mode=${searchMode}`);
        const data = await res.json();
        const results = data.results || [];

        // Normalize results for the grid
        results.forEach(item => {
            item.match_score = null;
            item.recommended_because = data.method ? [`Found via ${data.method}`] : ["Found via search"];
        });

        renderGrid(results);
        const countEl = document.getElementById('recs-count');
        if (countEl) countEl.innerText = `${results.length} search results`;
    } catch (e) {
        console.error("Global search failed:", e);
        renderGrid(allRecommendations); // Fallback
    }
}

// --- Persistence ---
let saveTimeout;
function debounceSaveSettings() {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(saveSettings, 2000);
}

async function saveSettings() {
    localStorage.setItem('tuner_settings', JSON.stringify(tunerSettings));
    fetch(`${API_BASE}/settings/tuner`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(tunerSettings)
    }).catch(e => console.error("Persistence failed:", e));
}

// Mark tuner as having pending changes
function markTunerPending(pending) {
    hasPendingChanges = pending;
    const confirmBtn = document.getElementById('confirm-tuner');
    const statusText = document.getElementById('tuner-status');
    
    if (confirmBtn) {
        confirmBtn.disabled = !pending;
        if (pending) {
            confirmBtn.classList.add('btn-pending');
        } else {
            confirmBtn.classList.remove('btn-pending');
        }
    }
    
    if (statusText) {
        if (pending) {
            statusText.innerHTML = '<span style="color: var(--accent);">⚠️ Click Confirm to apply changes</span>';
        } else {
            statusText.innerText = 'Adjust sliders and click Confirm';
        }
    }
}

// --- Data Fetching ---
function clearGrid() {
    const grid = document.getElementById('main-grid');
    if (grid) grid.innerHTML = '';
}

function showLoading() {
    const grid = document.getElementById('main-grid');
    if (grid) grid.innerHTML = '<div class="loading-full"><p>Loading recommendations...</p></div>';
}

async function fetchRecommendations() {
    clearGrid();
    showLoading();

    const { content_weight, collaborative_weight, quality_weight, confidence_weight, genre, type, limit } = tunerSettings;
    const url = `${API_BASE}/recommendations/weighted?` +
        `content_weight=${content_weight}&` +
        `collaborative_weight=${collaborative_weight}&` +
        `quality_weight=${quality_weight}&` +
        `confidence_weight=${confidence_weight}&` +
        `limit=${limit}` +
        (genre ? `&genre=${encodeURIComponent(genre)}` : '') +
        (type ? `&type_filter=${encodeURIComponent(type)}` : '');

    try {
        const res = await fetch(url);
        const data = await res.json();
        allRecommendations = data.recommendations || [];
        renderGrid(allRecommendations);

        const countEl = document.getElementById('recs-count');
        if (countEl) countEl.innerText = `${allRecommendations.length} results`;
    } catch (e) {
        console.error("Fetch recommendations failed:", e);
        renderGrid([]);
    }
}

async function populateGenres() {
    try {
        const res = await fetch(`${API_BASE}/genres`);
        const genres = await res.json();
        
        // Populate quick filter in top bar
        const quickSelect = document.getElementById('quick-genre-filter');
        if (quickSelect) {
            quickSelect.innerHTML = '<option value="">All Genres</option>';
            genres.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.innerText = g;
                quickSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Failed to populate genres:", e);
    }
}

function applyQuickFilter() {
    const genre = document.getElementById('quick-genre-filter')?.value || '';
    const type = document.getElementById('quick-type-filter')?.value || '';
    
    // Also update tuner settings
    tunerSettings.genre = genre;
    tunerSettings.type = type;
    saveSettings();
    
    fetchRecommendations();
}

// --- Rendering ---
function renderGrid(items) {
    const grid = document.getElementById('main-grid');
    if (!grid) return;

    if (items.length === 0) {
        grid.innerHTML = '<div class="loading-full"><p>No recommendations found matching your criteria.</p></div>';
        return;
    }

    grid.innerHTML = '';
    items.forEach(item => {
        const card = createCard(item);
        grid.appendChild(card);
    });

    updateBatchStatuses(items);
}

function createCard(item) {
    const el = document.createElement('div');
    el.className = 'movie-card-v2';

    const posterUrl = item.poster_path ? 'https://image.tmdb.org/t/p/w500' + item.poster_path : 'https://via.placeholder.com/500x750?text=No+Poster';
    const safeTitle = item.title.replace(/'/g, "\\'");

    el.innerHTML = `
        <img src="${posterUrl}" alt="${item.title}" loading="lazy">
        <div class="card-overlay-v2">
            <div class="card-title-v2">${item.title}</div>
            <div class="overlay-actions">
                <div class="overlay-left" onclick="dislikeItem(event, ${item.tmdb_id}, '${safeTitle}', '${item.type}')" title="Hide for 4 months">
                    <i class="fa-solid fa-xmark overlay-action"></i>
                    <span class="overlay-text">Hide 4mo</span>
                </div>
                <div class="view-details-hint" onclick="openDetailsModal('${item.tmdb_id}', '${item.type}')">
                    <i class="fa-solid fa-circle-info"></i> Details
                </div>
                <div class="overlay-right" onclick="markWatched(event, ${item.tmdb_id}, '${safeTitle}', '${item.type}')">
                    <i class="fa-solid fa-check overlay-action"></i>
                    <span class="overlay-text">Watched</span>
                </div>
            </div>
        </div>
        <div class="status-tags" id="status-tags-${item.tmdb_id}"></div>
    `;

    el.onclick = (e) => {
        if (!e.target.closest('.overlay-left') && !e.target.closest('.overlay-right')) {
            openModal(item);
        }
    };

    return el;
}

function openDetailsModal(tmdbId, type) {
    const item = allRecommendations.find(r => r.tmdb_id == tmdbId);
    if (item) openModal(item);
}

function updateTunerUI() {
    // Sync pending settings with current settings
    pendingTunerSettings = { ...tunerSettings };
    
    Object.entries(tunerSettings).forEach(([key, val]) => {
        const uiKey = key === 'collaborative_weight' ? 'collab' : key.split('_')[0];
        const slider = document.getElementById(`weight-${uiKey}`);
        const span = document.getElementById(`val-${uiKey}`);
        if (slider) slider.value = val;
        if (span) span.innerText = typeof val === 'number' ? val.toFixed(2) : val;
    });

    const limitFilter = document.getElementById('filter-limit');
    if (limitFilter) limitFilter.value = tunerSettings.limit || 100;

    // Update quick filters in top bar
    const quickGenreFilter = document.getElementById('quick-genre-filter');
    if (quickGenreFilter) quickGenreFilter.value = tunerSettings.genre || '';

    const quickTypeFilter = document.getElementById('quick-type-filter');
    if (quickTypeFilter) quickTypeFilter.value = tunerSettings.type || '';
}

// --- Actions ---
async function markWatched(event, tmdbId, title, type) {
    if (event) event.stopPropagation();
    
    // Optimistic update - remove from UI immediately
    const card = document.querySelector(`.movie-card-v2`);
    if (card) {
        const allCards = document.querySelectorAll('.movie-card-v2');
        allCards.forEach(c => {
            const tags = c.querySelector(`#status-tags-${tmdbId}`);
            if (tags) {
                c.style.opacity = '0';
                setTimeout(() => c.remove(), 300);
            }
        });
    }
    
    try {
        const res = await fetch(`${API_BASE}/history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmdb_id: tmdbId, title, type })
        });
        if (res.ok) {
            // Item already removed from UI above - skip slow refetch
            allRecommendations = allRecommendations.filter(r => r.tmdb_id !== tmdbId);
            
            const countEl = document.getElementById('recs-count');
            if (countEl) countEl.innerText = `${allRecommendations.length} results`;
        }
    } catch (e) {
        console.error("Mark watched error:", e);
    }
}

async function dislikeItem(event, tmdbId, title, type) {
    if (event) event.stopPropagation();
    if (!confirm(`Hide "${title}" for 4 months?\n\nThis will:\n• Remove it from recommendations\n• Penalize similar movies\n• Automatically reappear after 4 months`)) return;

    // Optimistic update - remove from UI immediately
    const allCards = document.querySelectorAll('.movie-card-v2');
    allCards.forEach(c => {
        const tags = c.querySelector(`#status-tags-${tmdbId}`);
        if (tags) {
            c.style.opacity = '0';
            setTimeout(() => c.remove(), 300);
        }
    });

    try {
        const res = await fetch(`${API_BASE}/dislike`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmdb_id: tmdbId, title, type })
        });
        if (res.ok) {
            // Already removed from UI above
            allRecommendations = allRecommendations.filter(r => r.tmdb_id !== tmdbId);
            
            const countEl = document.getElementById('recs-count');
            if (countEl) countEl.innerText = `${allRecommendations.length} results`;
        }
    } catch (e) {
        console.error("Dislike error:", e);
    }
}

async function triggerRegeneration() {
    if (!confirm("Start full system sync? This will refresh watch history and TMDB candidates.\n\nThis runs in the background and may take several minutes.")) return;

    // Show immediate feedback
    const syncBtn = document.querySelector('button[onclick="triggerRegeneration()"]');
    const syncIcon = document.getElementById('sync-icon');
    if (syncBtn) syncBtn.disabled = true;
    if (syncIcon) {
        syncIcon.classList.add('fa-spin');
        syncIcon.style.color = 'var(--accent-primary)';
    }

    try {
        const res = await fetch(`${API_BASE}/system/regenerate`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            console.log("Sync started:", data.message);
            startSyncStatusPolling();
        } else {
            alert("Failed to start sync. Check server logs.");
            if (syncBtn) syncBtn.disabled = false;
            if (syncIcon) syncIcon.classList.remove('fa-spin');
        }
    } catch (e) {
        console.error("Sync failed:", e);
        alert("Failed to start sync.");
        if (syncBtn) syncBtn.disabled = false;
        if (syncIcon) syncIcon.classList.remove('fa-spin');
    }
}

function startSyncStatusPolling() {
    const statusContainer = document.getElementById('sync-status');
    const syncIcon = document.getElementById('sync-icon');
    const syncBtn = document.querySelector('button[onclick="triggerRegeneration()"]');

    if (statusContainer) statusContainer.classList.remove('hidden');
    if (syncIcon) syncIcon.classList.add('fa-spin');

    if (syncPollInterval) clearInterval(syncPollInterval);

    syncPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/system/status`);
            const data = await res.json();

            const fill = document.getElementById('sync-progress-fill');
            const msg = document.getElementById('sync-status-msg');

            if (fill) fill.style.width = `${data.progress}%`;
            if (msg) msg.innerText = data.message || `Step: ${data.step}`;

            if (data.status === 'success' || data.status === 'failed' || data.status === 'idle') {
                clearInterval(syncPollInterval);
                
                // Re-enable button and reset icon
                if (syncBtn) syncBtn.disabled = false;
                if (syncIcon) {
                    syncIcon.classList.remove('fa-spin');
                    syncIcon.style.color = '';
                }

                // Hide after delay and refresh
                setTimeout(() => {
                    if (statusContainer) statusContainer.classList.add('hidden');
                    if (data.status === 'success') {
                        fetchRecommendations();
                        // Show success toast
                        showToast('Sync complete! Recommendations updated.');
                    } else if (data.status === 'failed') {
                        showToast('Sync failed. Check server logs.', 'error');
                    }
                }, 3000);
            }
        } catch (e) {
            console.error("Status poll error:", e);
        }
    }, 2000);
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fa-solid fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i> ${message}`;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'success' ? '#00b894' : '#d63031'};
        color: white;
        border-radius: 8px;
        font-weight: 500;
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// --- Details Modal ---
function openModal(item) {
    const modal = document.getElementById('movie-modal');
    const content = document.getElementById('modal-content');
    if (!modal || !content) return;

    modal.classList.add('active');

    const posterUrl = item.poster_path ? 'https://image.tmdb.org/t/p/w500' + item.poster_path : 'https://via.placeholder.com/500x750?text=No+Poster';
    const score = item.scores ? (item.scores.hybrid * 100).toFixed(0) : '0';

    content.innerHTML = `
        <div style="display: flex; gap: 30px; padding: 40px; color: white;">
            <img src="${posterUrl}" style="width: 300px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
            <div style="flex: 1;">
                <h1 style="font-family: 'Outfit', sans-serif; font-size: 2.5rem; margin-bottom: 10px;">${item.title}</h1>
                <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <span class="badge" style="background: var(--accent);">${item.type.toUpperCase()}</span>
                    <span class="badge" style="background: #333;">${item.year || 'N/A'}</span>
                    <span class="badge" style="background:#f1c40f; color: black;"><i class="fa-solid fa-star"></i> ${item.vote_average || '0.0'}</span>
                </div>
                <p style="color: #ccc; line-height: 1.6; font-size: 1.1rem; margin-bottom: 30px;">${item.overview || 'No overview available.'}</p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 40px;">
                    <div>
                        <h3 style="margin-bottom: 5px; color: var(--accent);">Genres</h3>
                        <p>${item.genres ? item.genres.join(', ') : 'N/A'}</p>
                    </div>
                    <div>
                        <h3 style="margin-bottom: 5px; color: var(--accent);">Match Score</h3>
                        <p style="font-size: 1.5rem; font-weight: 700;">${score}% Match</p>
                    </div>
                </div>
                <div style="margin-top: 40px; display: flex; gap: 15px;">
                    <button id="modal-req-btn" class="btn btn-primary" onclick="requestItem(${item.tmdb_id}, '${item.type}')">
                        <i class="fa-solid fa-cloud-arrow-down"></i> Add to Library
                    </button>
                    <button class="btn btn-glass" onclick="closeModal()">Close</button>
                </div>
            </div>
        </div>
    `;
    fetchItemStatus(item.tmdb_id, item.type);
}

function closeModal() {
    const modal = document.getElementById('movie-modal');
    if (modal) modal.classList.remove('active');
}

async function requestItem(tmdbId, type) {
    const btn = document.getElementById('modal-req-btn');
    const endpoint = type === 'movie' ? '/add/radarr' : '/add/sonarr';
    
    // Find the item title from recommendations
    const item = allRecommendations.find(r => r.tmdb_id == tmdbId);
    const title = item ? item.title : 'Unknown';

    if (btn) {
        btn.disabled = true;
        btn.innerText = "Processing...";
    }

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmdb_id: tmdbId, title: title })
        });
        const data = await res.json();
        
        if (btn) {
            if (res.ok && (data.status === 'success' || data.status === 'exists')) {
                btn.innerText = data.status === 'exists' ? "Already in Library" : "Added!";
                btn.style.background = data.status === 'exists' ? "#636e72" : "#55efc4";
            } else if (data.detail) {
                btn.innerText = "Error";
                btn.disabled = false;
                showToast(data.detail, 'error');
            } else {
                btn.innerText = "Failed";
                btn.disabled = false;
            }
        }
    } catch (e) {
        console.error("Request failed:", e);
        if (btn) {
            btn.innerText = "Failed";
            btn.disabled = false;
        }
    }
}

async function fetchItemStatus(tmdbId, type) {
    try {
        const res = await fetch(`${API_BASE}/check/status?tmdb_id=${tmdbId}&type=${type}`);
        const status = await res.json();
        updateTagsInUI(tmdbId, status);
    } catch (e) { }
}

async function updateBatchStatuses(items) {
    if (items.length === 0) return;
    const batchData = items.map(item => ({ tmdb_id: item.tmdb_id, type: item.type }));
    try {
        const res = await fetch(`${API_BASE}/check/status/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: batchData })
        });
        const batchResults = await res.json();
        for (const [tmdbId, status] of Object.entries(batchResults)) {
            updateTagsInUI(tmdbId, status);
        }
    } catch (e) {
        console.error("Batch status check failed:", e);
    }
}

function updateTagsInUI(tmdbId, status) {
    const tags = document.getElementById(`status-tags-${tmdbId}`);
    if (!tags) return;
    tags.innerHTML = '';
    if (status.is_watched) tags.innerHTML += '<span class="status-tag tag-watched" style="background:#55efc4; color:#000; padding:2px 8px; border-radius:4px; font-size:10px; margin-right:5px;">Watched</span>';
    if (status.in_library) tags.innerHTML += '<span class="status-tag tag-in-library" style="background:#6c5ce7; color:#fff; padding:2px 8px; border-radius:4px; font-size:10px; margin-right:5px;">In Library</span>';
    else if (status.is_requested) tags.innerHTML += '<span class="status-tag tag-requested" style="background:#ff7675; color:#fff; padding:2px 8px; border-radius:4px; font-size:10px;">Requested</span>';
}
