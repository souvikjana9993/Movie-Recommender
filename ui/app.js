/* =============================================================================
   App Logic - Jellyseerr Style
   ============================================================================= */

const API_BASE = window.location.origin;

// State
let allRecommendations = [];
let genreMap = {};
let currentView = 'home';

// DOM Elements
const views = {
    home: document.getElementById('home-view'),
    discover: document.getElementById('discover-view'),
    settings: document.getElementById('settings-view')
};

const hero = {
    section: document.getElementById('hero-section'),
    backdrop: document.getElementById('hero-backdrop'),
    title: document.getElementById('hero-title'),
    overview: document.getElementById('hero-overview'),
    meta: document.getElementById('hero-meta'),
    type: document.getElementById('hero-type'),
    year: document.getElementById('hero-year'),
    genres: document.getElementById('hero-genres'),
    score: document.getElementById('hero-score')
};

// Intialize
document.addEventListener('DOMContentLoaded', async () => {
    initNavigation();
    initSliders();
    initSearch();
    await fetchGenres();
    await fetchRecommendations();
});

// ================== DATA FETCHING ==================

async function fetchGenres() {
    try {
        const res = await fetch(`${API_BASE}/genres`);
        const data = await res.json();
        data.genres.forEach(g => genreMap[g.id] = g.name);

        // Populate filter
        const filter = document.getElementById('genre-filter');
        data.genres.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = g.name;
            filter.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to fetch genres", e);
    }
}

async function fetchRecommendations() {
    // Get slider values
    const wContent = document.getElementById('weight-content').value;
    const wCollab = document.getElementById('weight-collab').value;
    const wConfidence = document.getElementById('weight-confidence').value;
    const wQuality = document.getElementById('weight-quality').value;

    const url = `${API_BASE}/recommendations/weighted?content_weight=${wContent}&collaborative_weight=${wCollab}&confidence_weight=${wConfidence}&quality_weight=${wQuality}&limit=50`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        allRecommendations = data.recommendations;

        renderHome(allRecommendations);
        renderGrid(allRecommendations); // Pre-render grid

    } catch (e) {
        console.error("Failed to fetch recommendations", e);
    }
}

// ================== RENDERING ==================

function renderHome(items) {
    if (!items || items.length === 0) return;

    // 1. Hero Section (Top Item)
    const topItem = items[0];
    updateHero(topItem);

    // 2. Top Picks Row (Next 10 items)
    const topPicks = items.slice(1, 15);
    renderRow('row-top-picks', topPicks);

    // 3. Discovery Row (Simulated "Because you watched" for demo)
    // In a real app, this would query specific history-based recs
    const discoveryItems = items.sort(() => 0.5 - Math.random()).slice(0, 15); // Shuffle
    renderRow('row-discovery', discoveryItems);

    // Update source text
    const sources = [...new Set(discoveryItems.map(i => i.source_item))].filter(Boolean);
    if (sources.length > 0) {
        document.getElementById('because-source').textContent = sources[0];
    }
}

function updateHero(item) {
    if (!item) return;

    // Image: Prefer backdrop, fall back to poster
    const imgUrl = item.backdrop_path
        ? `https://image.tmdb.org/t/p/original${item.backdrop_path}`
        : `https://image.tmdb.org/t/p/original${item.poster_path}`;

    hero.backdrop.style.backgroundImage = `url('${imgUrl}')`;
    hero.backdrop.style.opacity = '1'; // Fade in

    hero.title.textContent = item.title;
    hero.overview.textContent = item.overview;
    hero.type.textContent = item.type === 'movie' ? 'MOVIE' : 'TV SHOW';
    hero.year.textContent = item.release_date ? item.release_date.split('-')[0] : 'N/A';
    hero.score.textContent = (item.vote_average || 0).toFixed(1);

    // Map genre IDs to names
    let genres = '';
    if (item.genre_ids && Array.isArray(item.genre_ids)) {
        genres = item.genre_ids.map(id => genreMap[id]).filter(Boolean).slice(0, 3).join(', ');
    } else if (item.genres && Array.isArray(item.genres)) {
        genres = item.genres.slice(0, 3).join(', ');
    }
    hero.genres.textContent = genres;

    hero.section.classList.remove('hidden');

    // Store current hero item for "More Info" button
    hero.section.dataset.itemId = JSON.stringify(item);
}

function renderRow(elementId, items) {
    const container = document.getElementById(elementId);
    container.innerHTML = ''; // Clear loading spinner

    items.forEach(item => {
        const card = createCard(item);
        container.appendChild(card);
    });
}

function renderGrid(items) {
    const container = document.getElementById('recommendations-grid');
    container.innerHTML = '';

    items.forEach(item => {
        const card = createCard(item);
        container.appendChild(card);
    });
}

function createCard(item) {
    const card = document.createElement('div');
    card.className = 'card';
    card.onclick = () => openModal(item);

    const posterUrl = item.poster_path
        ? `https://image.tmdb.org/t/p/w500${item.poster_path}`
        : 'https://via.placeholder.com/500x750?text=No+Poster';

    const scoreValue = item.final_score !== undefined ? item.final_score : (item.scores ? item.scores.hybrid : 0);
    const safeScore = isNaN(scoreValue) ? 0 : scoreValue;
    const score = Math.round(safeScore * 100);

    card.innerHTML = `
        <div class="card-poster">
            <img src="${posterUrl}" loading="lazy" alt="${item.title}">
            <div class="card-score">${score}%</div>
            <div class="card-overlay">
                <div class="card-title">${item.title}</div>
            </div>
        </div>
    `;
    return card;
}

// ================== INTERACTION ==================

function playHero() {
    alert("In a real app, this would play the video or open jellyfin!");
}

function openHeroDetails() {
    const itemData = hero.section.dataset.itemId;
    if (itemData) {
        openModal(JSON.parse(itemData));
    }
}

// Modal
function openModal(item) {
    const modal = document.getElementById('detail-modal');
    const content = document.getElementById('modal-content');

    const posterUrl = item.poster_path
        ? `https://image.tmdb.org/t/p/w500${item.poster_path}`
        : 'https://via.placeholder.com/500x750?text=No+Poster';

    const backdropUrl = item.backdrop_path
        ? `https://image.tmdb.org/t/p/original${item.backdrop_path}`
        : '';

    // Build Modal HTML
    const scores = item.scores || { hybrid: 0, content: 0, collaborative: 0, quality: item.vote_average / 10 || 0 };
    const finalScore = item.final_score !== undefined ? item.final_score : scores.hybrid;
    const serviceName = item.type === 'movie' ? 'Radarr' : 'Sonarr';

    content.innerHTML = `
        <img src="${posterUrl}" class="modal-poster-large" alt="${item.title}">
        <div class="modal-details">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                <h1 style="font-size: 2rem; margin: 0;">${item.title}</h1>
                <div id="modal-status-tags" style="display: flex; gap: 5px; margin-top: 8px;"></div>
            </div>
            
            <div style="display: flex; gap: 10px; color: var(--text-gray); margin-bottom: 1rem;">
                <span>${item.release_date ? item.release_date.split('-')[0] : (item.year || 'N/A')}</span>
                <span>•</span>
                <span>${(item.vote_average || 0).toFixed(1)}/10</span>
                <span>•</span>
                <span style="text-transform: uppercase; background: var(--primary); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px;">${item.type}</span>
            </div>
            
            <p style="line-height: 1.6; color: #ddd; margin-bottom: 2rem;">${item.overview}</p>
            
            <div style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 8px;">
                <h3 style="margin-bottom: 1rem; font-size: 14px; text-transform: uppercase; color: var(--text-gray); display: flex; align-items: center; gap: 8px;">
                    Match Score Breakdown 
                    <i class="fa-solid fa-circle-question" style="cursor: pointer; opacity: 0.7;" onclick="alert('Scores are calculated based on:\\n\\n1. Content: Similarity in genres, keywords, cast/crew.\\n2. Collaborative: Based on what similar users watched.\\n3. Quality: TMDB ratings and vote counts.\\n\\nTotal Match is a weighted average of these factors.')"></i>
                </h3>
                ${renderScoreBar('Total Match', finalScore, 'var(--primary)')}
                ${scores.content !== undefined ? renderScoreBar('Content Similarity', scores.content, '#3b82f6') : ''}
                ${scores.collaborative !== undefined ? renderScoreBar('Collab Filtering', scores.collaborative, '#10b981') : ''}
                ${item.scores ? '' : '<p style="font-size: 11px; color: var(--text-gray); margin-top: 4px;">Search result: Exact score breakdown not available.</p>'}
            </div>

            <div class="modal-actions" style="margin-top: 2rem; display: flex; gap: 1rem;">
                 <button id="btn-mark-watched" class="btn btn-primary" onclick="markWatched(${item.tmdb_id}, '${item.title.replace(/'/g, "\\\'")}', '${item.type}')">
                    <i class="fa-solid fa-check"></i> Mark Watched
                 </button>
                 <button id="btn-request" class="btn btn-glass" onclick="addToSonarr(${item.tmdb_id}, '${item.type}', '${item.title.replace(/'/g, "\\\'")}')">
                    <i class="fa-solid fa-download"></i> Request on ${serviceName}
                 </button>
            </div>
        </div>
    `;

    modal.classList.add('open');

    // Fetch and update status
    fetchItemStatus(item.tmdb_id, item.type);
}

async function fetchItemStatus(tmdbId, type) {
    const statusTags = document.getElementById('modal-status-tags');
    const watchBtn = document.getElementById('btn-mark-watched');
    const requestBtn = document.getElementById('btn-request');

    try {
        const res = await fetch(`${API_BASE}/check/status?tmdb_id=${tmdbId}&type=${type}`);
        const status = await res.json();

        if (status.is_watched) {
            statusTags.innerHTML += '<span class="status-tag tag-watched">Watched</span>';
            if (watchBtn) watchBtn.disabled = true;
        }

        if (status.in_library) {
            statusTags.innerHTML += '<span class="status-tag tag-in-library">In Library</span>';
            if (requestBtn) {
                requestBtn.disabled = true;
                requestBtn.innerHTML = '<i class="fa-solid fa-check"></i> In Library';
            }
        } else if (status.is_requested) {
            statusTags.innerHTML += '<span class="status-tag tag-requested">Requested</span>';
            if (requestBtn) {
                requestBtn.disabled = true;
                requestBtn.innerHTML = '<i class="fa-solid fa-clock"></i> Requested';
            }
        }
    } catch (e) {
        console.warn("Status check failed", e);
    }
}

function renderScoreBar(label, value, color) {
    const safeValue = isNaN(value) ? 0 : value;
    const percentage = Math.round(safeValue * 100);
    return `
        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 8px;">
            <span style="width: 120px; font-size: 12px;">${label}</span>
            <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px;">
                <div style="width: ${percentage}%; background: ${color}; height: 100%; border-radius: 3px;" title="${label}: ${percentage}%"></div>
            </div>
            <span style="width: 30px; text-align: right; font-size: 12px; font-weight: bold;">${isNaN(percentage) ? 'N/A' : percentage + '%'}</span>
        </div>
    `;
}

function closeModal() {
    document.getElementById('detail-modal').classList.remove('open');
}


// Search
function initSearch() {
    const searchInput = document.getElementById('global-search');
    if (!searchInput) return;

    let timeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            const query = e.target.value.trim();
            if (query.length > 0) {
                // Switch to discover view and show results
                const discoverLink = document.querySelector('.nav-links li[data-view="discover"]');
                if (discoverLink) discoverLink.click();
                searchMovies(query);
            } else {
                // Clear search title if query is empty
                const title = document.querySelector('#discover-view .section-header h2');
                if (title) title.textContent = "Discover";
                fetchRecommendations(); // Reset
            }
        }, 500);
    });
}

async function searchMovies(query) {
    const container = document.getElementById('recommendations-grid');
    container.innerHTML = '<div class="loading-spinner"></div>';

    // Update title
    const title = document.querySelector('#discover-view .section-header h2');
    if (title) title.textContent = `Search: "${query}"`;

    try {
        // 1. Search Local Candidates
        const res = await fetch(`${API_BASE}/search?query=${encodeURIComponent(query)}`);
        const data = await res.json();

        let results = data.results || [];

        // 2. If few results, Search TMDB
        if (results.length < 5) {
            try {
                const tmdbRes = await fetch(`${API_BASE}/search/tmdb?query=${encodeURIComponent(query)}`);
                const tmdbData = await tmdbRes.json();

                // Merge/Append TMDB results (removing duplicates by ID)
                const existingIds = new Set(results.map(r => r.tmdb_id));
                const newItems = tmdbData.results.filter(r => !existingIds.has(r.tmdb_id));

                // Add a visual separator or just append? Appending is cleaner.
                // Mark them as "TMDB" source if needed, or just let them be naturally displayed.
                results = [...results, ...newItems];

            } catch (tmdbErr) {
                console.warn("TMDB Search failed", tmdbErr);
            }
        }

        if (results.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding: 2rem; color: var(--text-gray);">No results found.</div>';
            return;
        }

        renderGrid(results);

    } catch (e) {
        console.error("Search failed", e);
        container.innerHTML = '<p>Search failed.</p>';
    }
}

// Navigation
function initNavigation() {
    const links = document.querySelectorAll('.nav-links li');
    links.forEach(link => {
        link.addEventListener('click', () => {
            const target = link.dataset.view;
            if (!target) return;

            // Active state
            links.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            // View switching
            Object.values(views).forEach(v => v.classList.add('hidden'));
            views[target].classList.remove('hidden');

            // Special case for Hero
            if (target === 'home') {
                hero.section.classList.remove('hidden');
            } else {
                hero.section.classList.add('hidden');
            }
        });
    });
}

function showSettings() {
    const settingsLink = document.querySelector('.nav-links li[data-view="settings"]');
    if (settingsLink) settingsLink.click();
}

// Sliders (Debounced update)
function initSliders() {
    const inputs = document.querySelectorAll('.slider');
    inputs.forEach(input => {
        input.addEventListener('input', (e) => {
            // Update value label
            const label = document.getElementById(`val-${e.target.id.split('-')[1]}`);
            if (label) label.textContent = e.target.value;

            // Debounce fetch
            clearTimeout(window.sliderTimeout);
            window.sliderTimeout = setTimeout(fetchRecommendations, 500);
        });
    });
}

// Button Helpers
function setLoading(btn, isLoading, originalContent) {
    if (!btn) return;
    if (isLoading) {
        btn.dataset.original = btn.innerHTML;
        btn.classList.add('btn-loading');
        btn.disabled = true;
    } else {
        btn.innerHTML = btn.dataset.original || originalContent;
        btn.classList.remove('btn-loading');
        btn.disabled = false;
    }
}

// API Actions
async function markWatched(tmdbId, title, type) {
    if (!confirm(`Mark '${title}' as watched?`)) return;

    const btn = document.getElementById('btn-mark-watched');
    setLoading(btn, true);

    try {
        const res = await fetch(`${API_BASE}/history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmdb_id: tmdbId, title: title, type: type })
        });

        if (res.ok) {
            alert("Marked as watched!");
            allRecommendations = allRecommendations.filter(r => r.tmdb_id !== tmdbId);
            renderHome(allRecommendations);
            renderGrid(allRecommendations);
            closeModal();
        } else {
            const data = await res.json();
            alert(`Error: ${data.detail || 'Failed to update history'}`);
            setLoading(btn, false);
        }
    } catch (e) {
        alert("Error marking as watched.");
        setLoading(btn, false);
    }
}

async function addToSonarr(tmdbId, type, title) {
    const endpoint = type === 'movie' ? '/add/radarr' : '/add/sonarr';
    const service = type === 'movie' ? 'Radarr' : 'Sonarr';

    if (!confirm(`Request '${title}' on ${service}?`)) return;

    const btn = document.getElementById('btn-request');
    setLoading(btn, true);

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmdb_id: tmdbId, title: title })
        });

        const data = await res.json();

        if (res.ok) {
            alert(`Success: ${data.message}`);
            closeModal();
        } else {
            if (data.status === 'exists') {
                alert(`Info: ${data.message}`);
                closeModal();
            } else {
                alert(`Error: ${data.detail || 'Request failed'}`);
                setLoading(btn, false);
            }
        }
    } catch (e) {
        alert(`Failed to connect to API.`);
        setLoading(btn, false);
    }
}

async function triggerRegeneration() {
    if (!confirm("Start full recommendation update?\n\nThis will fetch new data from Jellyfin/TMDB and recalculate all scores. It runs in the background and takes 5-10 minutes.")) return;

    const btn = document.querySelector('.admin-card .btn-primary');
    setLoading(btn, true);

    try {
        const res = await fetch(`${API_BASE}/system/regenerate`, { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            alert("Update Started! You can continue using the app. Recommendations will refresh automatically when done.");
        } else {
            alert(`Error: ${data.detail}`);
            setLoading(btn, false);
        }
    } catch (e) {
        alert("Failed to trigger update.");
        setLoading(btn, false);
    }
}
