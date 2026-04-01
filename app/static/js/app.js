const API = '';

// State
let files = [];
let selectedIds = new Set();
let currentFileId = null;
let currentBrowseTarget = null;
let currentDirPath = '';
let selectedDirPath = '';
let currentPlayingId = null;
let currentPlayingLabel = '';
let currentPlayingCoverUrl = '';
let playbackRequestId = 0;
const audioPlayer = new Audio();
audioPlayer.preload = 'none';

// DOM refs
const fileTbody = document.getElementById('file-tbody');
const selectAll = document.getElementById('select-all');
const statusFilter = document.getElementById('status-filter');
const btnScan = document.getElementById('btn-scan');
const btnMove = document.getElementById('btn-move');
const moveMode = document.getElementById('move-mode');
const tagForm = document.getElementById('tag-form');
const batchNotice = document.getElementById('batch-notice');
const batchCount = document.getElementById('batch-count');
const btnBatchSave = document.getElementById('btn-batch-save');
const statsEl = document.getElementById('stats');
const dirModal = document.getElementById('dir-modal');
const dirPathInput = document.getElementById('dir-path-input');
const dirList = document.getElementById('dir-list');
const btnSelectDir = dirModal.querySelector('.btn-select-dir');

// Filter refs
const filterSearch = document.getElementById('filter-search');
const filterArtist = document.getElementById('filter-artist');
const filterAlbum = document.getElementById('filter-album');
const filterYear = document.getElementById('filter-year');
const btnClearFilters = document.getElementById('btn-clear-filters');
const btnClearTags = document.getElementById('btn-clear-tags');
const taskList = document.getElementById('task-list');
const btnCancelStuckTasks = document.getElementById('btn-cancel-stuck-tasks');
const fileDetailModal = document.getElementById('file-detail-modal');
const fileDetailContent = document.getElementById('file-detail-content');
const logDetailModal = document.getElementById('log-detail-modal');
const logDetailContent = document.getElementById('log-detail-content');
const processedActionModal = document.getElementById('processed-action-modal');
const btnProcessedAction = document.getElementById('btn-processed-action');
const btnAutoFill = document.getElementById('btn-auto-fill');
const btnBatchAcoustid = document.getElementById('btn-batch-acoustid');
const btnBatchOllama = document.getElementById('btn-batch-ollama');
const btnBatchDelete = document.getElementById('btn-batch-delete');
const ollamaIndicatorToggle = document.getElementById('ollama-indicator-toggle');
const ollamaStateLabel = document.getElementById('ollama-state-label');
const ollamaStateDetails = document.getElementById('ollama-state-details');
const ollamaIndicatorDetails = document.getElementById('ollama-indicator-details');
const ollamaEmoji = document.getElementById('ollama-emoji');
const btnCheckServices = document.getElementById('btn-check-services');
const ollamaServicesState = document.getElementById('ollama-services-state');
const nowPlayingCoverWrap = document.getElementById('now-playing-cover-wrap');
const nowPlayingCover = document.getElementById('now-playing-cover');
const nowPlayingCoverNext = document.getElementById('now-playing-cover-next');
const nowPlayingWaveform = document.getElementById('now-playing-waveform');
const nowPlayingControlsWrap = document.getElementById('now-playing-controls-wrap');
const nowPlayingPrevBtn = document.getElementById('now-playing-prev-btn');
const nowPlayingPlayPauseBtn = document.getElementById('now-playing-play-pause-btn');
const nowPlayingStopBtn = document.getElementById('now-playing-stop-btn');
const nowPlayingNextBtn = document.getElementById('now-playing-next-btn');
const nowPlayingPlayPauseIcon = nowPlayingPlayPauseBtn ? nowPlayingPlayPauseBtn.querySelector('.now-playing-ctrl-icon') : null;
const nowPlayingProgressWrap = document.getElementById('now-playing-progress-wrap');
const nowPlayingProgress = document.getElementById('now-playing-progress');
const nowPlayingCurrentTime = document.getElementById('now-playing-current-time');
const nowPlayingTotalTime = document.getElementById('now-playing-total-time');
const settingsSubtabs = document.querySelectorAll('.settings-subtab');
const settingsPanes = document.querySelectorAll('.settings-pane');
const fileListContainer = document.getElementById('file-list');
const cfgMobilePlayerOnly = document.getElementById('cfg-mobile-player-only');
const mobilePlayerToggleUiBtn = document.getElementById('mobile-player-toggle-ui');
const mobilePlayerCollapseBtn = document.getElementById('mobile-player-collapse-btn');
const mobileTrackListWrap = document.getElementById('mobile-track-list-wrap');
const mobileTrackList = document.getElementById('mobile-track-list');
const mobileTrackSearch = document.getElementById('mobile-track-search');
let mobilePlayerOverrideFullUi = false;
let mobilePlayerCollapsed = false;
let mobileTrackFiltered = [];
let mobileTrackHasQuery = false;
let mobileTrackRenderedCount = 0;
const MOBILE_TRACK_PAGE_SIZE = 50;
const MOBILE_TRACK_PAGE_STEP = 30;
const PLAYER_ICON_PATHS = {
    play: '/static/icons/player/play.svg',
    pause: '/static/icons/player/pause.svg',
};

// Task polling interval
let taskPollInterval = null;
let processedFilesCache = [];
let ollamaPollInterval = null;
let ollamaIndicatorExpanded = false;
let ollamaActivityInterval = null;
let ollamaActivityTick = 0;
let ollamaCurrentView = { state: 'idle', details: 'No activity yet' };
let ollamaBusyHintCount = 0;
let ollamaBusyHintText = '';
let isSeekingPlayback = false;
let nowPlayingCoverSwapTimer = null;
let nowPlayingWaveformRaf = null;
let nowPlayingAudioCtx = null;
let nowPlayingAnalyser = null;
let nowPlayingDataArray = null;
let nowPlayingSourceNode = null;
const WAVEFORM_STYLE_COUNT = 5;
const WAVEFORM_STYLE_STORAGE_KEY = 'mobile_waveform_style';
let nowPlayingWaveformStyle = 0;
let renderedFilesCount = 0;
const FILES_PAGE_SIZE = 120;
const FILES_PAGE_STEP = 80;

// Toast
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast ' + type;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 3000);
}

// Tab navigation
document.querySelectorAll('#sidebar li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelectorAll('#sidebar li').forEach(l => l.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        li.classList.add('active');
        document.getElementById('tab-' + li.dataset.tab).classList.add('active');
        if (li.dataset.tab === 'logs') loadLogs();
        if (li.dataset.tab === 'settings') loadSettings();
    });
});

// API helpers
async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(API + path, opts);
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
}

// Load stats
async function loadStats() {
    const s = await api('GET', '/api/stats');
    statsEl.textContent = `Total: ${s.total} | New: ${s.new} | Processed: ${s.processed} | Moved: ${s.moved} | Errors: ${s.errors}`;
}

// Load files
async function loadFiles() {
    const status = statusFilter.value;
    const search = filterSearch.value.trim();
    const artist = filterArtist.value;
    const album = filterAlbum.value;
    const year = filterYear.value;
    
    const params = new URLSearchParams({ status });
    if (search) params.append('search', search);
    if (artist) params.append('artist', artist);
    if (album) params.append('album', album);
    if (year) params.append('year', year);
    
    files = await api('GET', `/api/files?${params.toString()}`);
    selectedIds.clear();
    renderedFilesCount = 0;
    if (fileListContainer) fileListContainer.scrollTop = 0;
    renderFiles(true);
    applyMobileTrackFilter(true);
    updateMoveBtn();
    loadStats();
    
    // Update processed cache
    if (status === 'processed') {
        processedFilesCache = [...files];
    }
}

function maybeRenderMoreFiles() {
    if (!fileListContainer) return;
    const threshold = 180;
    const nearBottom = fileListContainer.scrollTop + fileListContainer.clientHeight >= fileListContainer.scrollHeight - threshold;
    if (nearBottom) {
        renderFiles(false);
    }
}

// Load filter options
async function loadFilterOptions() {
    try {
        const filters = await api('GET', `/api/files/filters?status=${statusFilter.value}`);
        
        // Populate artists
        const currentArtist = filterArtist.value;
        filterArtist.innerHTML = '<option value="">All Artists</option>';
        filters.artists.forEach(a => {
            filterArtist.innerHTML += `<option value="${escAttr(a)}">${esc(a)}</option>`;
        });
        if (currentArtist && filters.artists.includes(currentArtist)) {
            filterArtist.value = currentArtist;
        }
        
        // Populate albums
        const currentAlbum = filterAlbum.value;
        filterAlbum.innerHTML = '<option value="">All Albums</option>';
        filters.albums.forEach(a => {
            filterAlbum.innerHTML += `<option value="${escAttr(a)}">${esc(a)}</option>`;
        });
        if (currentAlbum && filters.albums.includes(currentAlbum)) {
            filterAlbum.value = currentAlbum;
        }
        
        // Populate years
        const currentYear = filterYear.value;
        filterYear.innerHTML = '<option value="">All Years</option>';
        filters.years.forEach(y => {
            filterYear.innerHTML += `<option value="${escAttr(y)}">${esc(y)}</option>`;
        });
        if (currentYear && filters.years.includes(currentYear)) {
            filterYear.value = currentYear;
        }
        
        // Initialize Select2 if not already done
        if (!filterArtist._select2Initialized) {
            $(filterArtist).select2({
                placeholder: $(filterArtist).attr('data-placeholder') || 'Select',
                allowClear: true,
                width: '200px'
            });
            filterArtist._select2Initialized = true;
        }
        if (!filterAlbum._select2Initialized) {
            $(filterAlbum).select2({
                placeholder: $(filterAlbum).attr('data-placeholder') || 'Select',
                allowClear: true,
                width: '200px'
            });
            filterAlbum._select2Initialized = true;
        }
        if (!filterYear._select2Initialized) {
            $(filterYear).select2({
                placeholder: $(filterYear).attr('data-placeholder') || 'Select',
                allowClear: true,
                width: '150px'
            });
            filterYear._select2Initialized = true;
        }
    } catch (e) {
        console.error('Failed to load filter options:', e);
    }
}

function escAttr(s) {
    return String(s).replace(/"/g, '&quot;');
}

function renderFiles(reset = false) {
    if (reset) {
        fileTbody.innerHTML = '';
        renderedFilesCount = 0;
    }
    const end = Math.min(files.length, renderedFilesCount === 0 ? FILES_PAGE_SIZE : renderedFilesCount + FILES_PAGE_STEP);
    const chunk = files.slice(renderedFilesCount, end);
    if (chunk.length === 0) return;

    chunk.forEach(f => {
        const isPlaying = currentPlayingId === f.id;
        const tr = document.createElement('tr');
        tr.dataset.id = f.id;
        if (selectedIds.has(f.id)) tr.classList.add('selected');
        if (isPlaying) tr.classList.add('playing');
        tr.innerHTML = `
            <td><input type="checkbox" class="row-cb" data-id="${f.id}" ${selectedIds.has(f.id) ? 'checked' : ''}></td>
            <td>
                <button class="btn btn-play" onclick="event.stopPropagation(); toggleTrackPlayback(${f.id})" title="${isPlaying ? 'Stop' : 'Play'}">${isPlaying ? '⏹' : '▶'}</button>
                <button class="btn btn-info" onclick="event.stopPropagation(); showFileDetail(${f.id})" title="View details">ℹ️</button>
            </td>
            <td>${renderFileStateBadges(f)}</td>
            <td>${esc(f.artist)}</td>
            <td>${esc(f.album)}</td>
            <td>${f.track_number || ''}</td>
            <td>${esc(f.title)}</td>
            <td>${esc(f.year)}</td>
        `;
        tr.addEventListener('click', (e) => {
            if (e.target.type === 'checkbox' || e.target.classList.contains('btn-info') || e.target.classList.contains('btn-play')) return;
            selectFile(f.id);
        });
        fileTbody.appendChild(tr);
        const cb = tr.querySelector('.row-cb');
        cb?.addEventListener('change', (e) => {
            const id = parseInt(e.target.dataset.id, 10);
            if (e.target.checked) selectedIds.add(id);
            else selectedIds.delete(id);
            e.target.closest('tr').classList.toggle('selected', e.target.checked);
            updateMoveBtn();
            updateBatchNotice();
        });
    });
    renderedFilesCount = end;
}

function renderFileStateBadges(file) {
    const badges = ['<span class="file-state-badge db">DB</span>'];
    if (file.is_newly_added) badges.push('<span class="file-state-badge fresh">NEW</span>');
    if (file.status === 'new') badges.push('<span class="file-state-badge pending">STATUS:new</span>');
    if (file.exists_on_disk === false) badges.push('<span class="file-state-badge missing">MISSING</span>');
    if (file.in_source_dir === false && file.in_output_dir === false) badges.push('<span class="file-state-badge orphan">OUTSIDE</span>');
    if (file.in_source_dir) badges.push('<span class="file-state-badge source">SRC</span>');
    if (file.in_output_dir) badges.push('<span class="file-state-badge output">OUT</span>');
    return badges.join('');
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

function getNextPlayableFileId(currentId) {
    const currentIndex = files.findIndex((f) => f.id === currentId);
    if (currentIndex === -1) return null;
    const nextFile = files[currentIndex + 1];
    return nextFile ? nextFile.id : null;
}

function getPrevPlayableFileId(currentId) {
    const currentIndex = files.findIndex((f) => f.id === currentId);
    if (currentIndex <= 0) return null;
    const prevFile = files[currentIndex - 1];
    return prevFile ? prevFile.id : null;
}

function updateNowPlayingControls() {
    if (!nowPlayingControlsWrap || !nowPlayingPrevBtn || !nowPlayingPlayPauseBtn || !nowPlayingStopBtn || !nowPlayingNextBtn) return;
    const hasTrack = currentPlayingId !== null;
    if (!hasTrack) {
        nowPlayingControlsWrap.style.display = 'none';
        nowPlayingPrevBtn.disabled = true;
        nowPlayingPlayPauseBtn.disabled = true;
        nowPlayingStopBtn.disabled = true;
        nowPlayingNextBtn.disabled = true;
        if (nowPlayingPlayPauseIcon) nowPlayingPlayPauseIcon.src = PLAYER_ICON_PATHS.play;
        return;
    }

    nowPlayingControlsWrap.style.display = '';
    nowPlayingPrevBtn.disabled = getPrevPlayableFileId(currentPlayingId) === null;
    nowPlayingNextBtn.disabled = getNextPlayableFileId(currentPlayingId) === null;
    nowPlayingStopBtn.disabled = false;
    nowPlayingPlayPauseBtn.disabled = false;
    if (nowPlayingPlayPauseIcon) {
        nowPlayingPlayPauseIcon.src = audioPlayer.paused ? PLAYER_ICON_PATHS.play : PLAYER_ICON_PATHS.pause;
    }
}

function formatPlaybackTime(secondsValue) {
    const seconds = Number(secondsValue);
    if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
    const rounded = Math.floor(seconds);
    const mins = Math.floor(rounded / 60);
    const secs = rounded % 60;
    return `${mins}:${String(secs).padStart(2, '0')}`;
}

function updateNowPlayingProgress() {
    if (!nowPlayingProgress || !nowPlayingProgressWrap || !nowPlayingCurrentTime || !nowPlayingTotalTime) return;
    const hasTrack = currentPlayingId !== null;
    if (!hasTrack) {
        nowPlayingProgressWrap.style.display = 'none';
        nowPlayingProgress.disabled = true;
        nowPlayingProgress.value = '0';
        nowPlayingCurrentTime.textContent = '0:00';
        nowPlayingTotalTime.textContent = '0:00';
        return;
    }

    nowPlayingProgressWrap.style.display = '';
    const duration = Number.isFinite(audioPlayer.duration) && audioPlayer.duration > 0 ? audioPlayer.duration : 0;
    const currentTime = Number.isFinite(audioPlayer.currentTime) ? audioPlayer.currentTime : 0;
    nowPlayingProgress.disabled = duration <= 0;

    if (!isSeekingPlayback) {
        nowPlayingProgress.value = duration > 0
            ? String(Math.min(100, Math.max(0, (currentTime / duration) * 100)))
            : '0';
    }

    nowPlayingCurrentTime.textContent = formatPlaybackTime(currentTime);
    nowPlayingTotalTime.textContent = formatPlaybackTime(duration);
}

audioPlayer.onended = () => {
    const finishedTrackId = currentPlayingId;
    const nextTrackId = getNextPlayableFileId(finishedTrackId);
    currentPlayingId = null;
    currentPlayingLabel = '';
    currentPlayingCoverUrl = '';
    renderFiles();
    updateMobileTrackPlayingState();
    animateOllamaStateView();
    updateNowPlayingControls();
    updateNowPlayingProgress();
    if (nextTrackId !== null) {
        window.toggleTrackPlayback(nextTrackId);
    }
};

audioPlayer.onerror = () => {
    currentPlayingId = null;
    currentPlayingLabel = '';
    currentPlayingCoverUrl = '';
    renderFiles();
    updateMobileTrackPlayingState();
    animateOllamaStateView();
    updateNowPlayingControls();
    updateNowPlayingProgress();
    toast('Cannot play this file', 'error');
};

function stopCurrentPlayback() {
    playbackRequestId += 1;
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
    if (currentPlayingId !== null) {
        currentPlayingId = null;
        currentPlayingLabel = '';
        currentPlayingCoverUrl = '';
        renderFiles();
        updateMobileTrackPlayingState();
        animateOllamaStateView();
        updateNowPlayingControls();
        updateNowPlayingProgress();
    }
}

function isExpectedPlaybackInterruption(err) {
    const name = String(err?.name || '');
    const msg = String(err?.message || '').toLowerCase();
    if (name === 'AbortError') return true;
    return msg.includes('play() request was interrupted')
        || msg.includes('media was removed from the document')
        || msg.includes('interrupted by a call to pause');
}

window.toggleTrackPlayback = async function(fileId) {
    if (currentPlayingId === fileId) {
        stopCurrentPlayback();
        return;
    }

    if (currentPlayingId !== null) {
        stopCurrentPlayback();
    }

    playbackRequestId += 1;
    const requestId = playbackRequestId;
    const audioUrl = `${API}/api/files/${fileId}/audio`;
    const file = files.find((f) => f.id === fileId) || {};
    const artist = String(file.artist || '').trim();
    const title = String(file.title || '').trim();
    const filename = String(file.filename || '').trim();
    currentPlayingLabel = (artist || title)
        ? `${artist || 'Unknown artist'} - ${title || 'Unknown title'}`
        : (filename || 'Now playing');
    currentPlayingCoverUrl = String(file.cover_url || '').trim();
    audioPlayer.src = audioUrl;
    currentPlayingId = fileId;
    renderFiles();
    updateMobileTrackPlayingState();
    animateOllamaStateView();
    updateNowPlayingControls();
    updateNowPlayingProgress();

    try {
        await audioPlayer.play();
        if (requestId !== playbackRequestId) {
            audioPlayer.pause();
        }
    } catch (e) {
        if (requestId !== playbackRequestId) return;
        if (isExpectedPlaybackInterruption(e)) {
            currentPlayingId = null;
            currentPlayingLabel = '';
            currentPlayingCoverUrl = '';
            renderFiles();
            updateMobileTrackPlayingState();
            animateOllamaStateView();
            updateNowPlayingControls();
            updateNowPlayingProgress();
            return;
        }
        currentPlayingId = null;
        currentPlayingLabel = '';
        currentPlayingCoverUrl = '';
        renderFiles();
        updateMobileTrackPlayingState();
        animateOllamaStateView();
        updateNowPlayingControls();
        updateNowPlayingProgress();
        toast('Playback failed: ' + (e?.message || 'unknown error'), 'error');
    }
};

audioPlayer.addEventListener('loadedmetadata', updateNowPlayingProgress);
audioPlayer.addEventListener('durationchange', updateNowPlayingProgress);
audioPlayer.addEventListener('timeupdate', updateNowPlayingProgress);
audioPlayer.addEventListener('pause', () => {
    updateNowPlayingProgress();
    updateNowPlayingControls();
});
audioPlayer.addEventListener('play', () => {
    updateNowPlayingProgress();
    updateNowPlayingControls();
});

if (nowPlayingProgress) {
    nowPlayingProgress.addEventListener('input', () => {
        if (currentPlayingId === null) return;
        isSeekingPlayback = true;
        const duration = Number.isFinite(audioPlayer.duration) ? audioPlayer.duration : 0;
        const percent = Number(nowPlayingProgress.value);
        const previewTime = duration > 0 ? (percent / 100) * duration : 0;
        nowPlayingCurrentTime.textContent = formatPlaybackTime(previewTime);
    });
    nowPlayingProgress.addEventListener('change', () => {
        if (currentPlayingId === null) return;
        const duration = Number.isFinite(audioPlayer.duration) ? audioPlayer.duration : 0;
        if (duration > 0) {
            const percent = Number(nowPlayingProgress.value);
            audioPlayer.currentTime = (percent / 100) * duration;
        }
        isSeekingPlayback = false;
        updateNowPlayingProgress();
    });
    nowPlayingProgress.addEventListener('pointerup', () => {
        isSeekingPlayback = false;
    });
}

if (nowPlayingPrevBtn) {
    nowPlayingPrevBtn.addEventListener('click', () => {
        if (currentPlayingId === null) return;
        const prevTrackId = getPrevPlayableFileId(currentPlayingId);
        if (prevTrackId !== null) {
            window.toggleTrackPlayback(prevTrackId);
        }
    });
}

if (nowPlayingNextBtn) {
    nowPlayingNextBtn.addEventListener('click', () => {
        if (currentPlayingId === null) return;
        const nextTrackId = getNextPlayableFileId(currentPlayingId);
        if (nextTrackId !== null) {
            window.toggleTrackPlayback(nextTrackId);
        }
    });
}

if (nowPlayingStopBtn) {
    nowPlayingStopBtn.addEventListener('click', () => {
        stopCurrentPlayback();
    });
}

if (nowPlayingPlayPauseBtn) {
    nowPlayingPlayPauseBtn.addEventListener('click', async () => {
        if (currentPlayingId === null) return;
        if (audioPlayer.paused) {
            try {
                await audioPlayer.play();
            } catch (e) {
                toast('Playback failed: ' + (e?.message || 'unknown error'), 'error');
            }
        } else {
            audioPlayer.pause();
        }
        updateNowPlayingControls();
    });
}

// Select all
selectAll.addEventListener('change', (e) => {
    document.querySelectorAll('.row-cb').forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        if (e.target.checked) selectedIds.add(id);
        else selectedIds.delete(id);
        cb.closest('tr').classList.toggle('selected', e.target.checked);
    });
    updateMoveBtn();
    updateBatchNotice();
});

// Status filter
statusFilter.addEventListener('change', () => {
    // Clear processed cache when changing status
    processedFilesCache = [];
    loadFiles();
    loadFilterOptions();
});

// Filter inputs
filterSearch.addEventListener('input', debounce(loadFiles, 300));
filterArtist.addEventListener('change', loadFiles);
filterAlbum.addEventListener('change', loadFiles);
filterYear.addEventListener('change', loadFiles);

// Clear filters
btnClearFilters.addEventListener('click', () => {
    filterSearch.value = '';
    filterArtist.value = '';
    filterAlbum.value = '';
    filterYear.value = '';
    loadFiles();
});

// Clear tag editor fields
btnClearTags.addEventListener('click', () => {
    document.getElementById('tag-artist').value = '';
    document.getElementById('tag-album').value = '';
    document.getElementById('tag-title').value = '';
    document.getElementById('tag-track').value = '0';
    document.getElementById('tag-year').value = '';
    document.getElementById('tag-format').value = '';
    document.getElementById('tag-medium').value = '1';
});

function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function detectClientOs() {
    const platform = String(navigator.platform || '').toLowerCase();
    const ua = String(navigator.userAgent || '').toLowerCase();
    if (platform.includes('win')) return 'windows';
    if (platform.includes('mac') || ua.includes('mac os')) return 'macos';
    if (platform.includes('linux') || ua.includes('linux')) return 'linux';
    return 'unknown';
}

function configureMoveModesByOs() {
    if (!moveMode) return;
    const os = detectClientOs();
    moveMode.value = 'move';
    const hardLinkOpt = moveMode.querySelector('option[value="hardlink"]');
    const symlinkOpt = moveMode.querySelector('option[value="symlink"]');

    if (os === 'windows') {
        if (hardLinkOpt) hardLinkOpt.textContent = 'Hard Link (same disk)';
        if (symlinkOpt) symlinkOpt.textContent = 'Symbolic Link (admin/dev mode)';
    } else if (os === 'macos') {
        if (hardLinkOpt) hardLinkOpt.textContent = 'Hard Link (same volume)';
        if (symlinkOpt) symlinkOpt.textContent = 'Symbolic Link (recommended for links)';
    } else if (os === 'linux') {
        if (hardLinkOpt) hardLinkOpt.textContent = 'Hard Link (same filesystem)';
        if (symlinkOpt) symlinkOpt.textContent = 'Symbolic Link';
    }
}

function isMobileViewport() {
    return window.matchMedia('(max-width: 900px)').matches;
}

function loadWaveformStylePreference() {
    try {
        const raw = window.localStorage.getItem(WAVEFORM_STYLE_STORAGE_KEY);
        const value = Number.parseInt(String(raw || ''), 10);
        if (Number.isFinite(value) && value >= 0 && value < WAVEFORM_STYLE_COUNT) {
            nowPlayingWaveformStyle = value;
        }
    } catch (e) {
        nowPlayingWaveformStyle = 0;
    }
    if (nowPlayingWaveform) {
        nowPlayingWaveform.dataset.style = String(nowPlayingWaveformStyle);
        nowPlayingWaveform.title = `Waveform style ${nowPlayingWaveformStyle + 1}/${WAVEFORM_STYLE_COUNT}. Tap to switch`;
    }
}

function saveWaveformStylePreference() {
    try {
        window.localStorage.setItem(WAVEFORM_STYLE_STORAGE_KEY, String(nowPlayingWaveformStyle));
    } catch (e) {
        // Ignore persistence errors.
    }
}

function cycleWaveformStyle() {
    nowPlayingWaveformStyle = (nowPlayingWaveformStyle + 1) % WAVEFORM_STYLE_COUNT;
    if (nowPlayingWaveform) {
        nowPlayingWaveform.dataset.style = String(nowPlayingWaveformStyle);
        nowPlayingWaveform.title = `Waveform style ${nowPlayingWaveformStyle + 1}/${WAVEFORM_STYLE_COUNT}. Tap to switch`;
    }
    saveWaveformStylePreference();
    toast(`Waveform style: ${nowPlayingWaveformStyle + 1}/${WAVEFORM_STYLE_COUNT}`, 'success');
}

function applyMobilePlayerOnlyMode() {
    const enabledInSettings = Boolean(cfgMobilePlayerOnly?.checked);
    const active = enabledInSettings && isMobileViewport() && !mobilePlayerOverrideFullUi;
    document.body.classList.toggle('mobile-player-only', active);
    const canCollapse = isMobileViewport() && !active;
    if (!canCollapse) {
        mobilePlayerCollapsed = false;
    }
    document.body.classList.toggle('mobile-player-collapsed', canCollapse && mobilePlayerCollapsed);
    if (mobilePlayerToggleUiBtn) {
        mobilePlayerToggleUiBtn.style.display = (enabledInSettings && isMobileViewport()) ? '' : 'none';
        mobilePlayerToggleUiBtn.textContent = active ? 'Show full interface' : 'Back to player-only';
    }
    if (mobilePlayerCollapseBtn) {
        mobilePlayerCollapseBtn.style.display = canCollapse ? '' : 'none';
        mobilePlayerCollapseBtn.textContent = mobilePlayerCollapsed ? '▸ Player' : '▾ Player';
        mobilePlayerCollapseBtn.title = mobilePlayerCollapsed ? 'Expand player' : 'Collapse player';
    }
    if (mobileTrackListWrap) {
        mobileTrackListWrap.style.display = active ? '' : 'none';
    }
    if (active && mobileTrackList) {
        mobileTrackList.scrollTop = 0;
    }
}

async function initMobilePlayerOnlyMode() {
    try {
        const cfg = await api('GET', '/api/config');
        if (cfgMobilePlayerOnly) {
            cfgMobilePlayerOnly.checked = Boolean(cfg.mobile_player_only);
        }
    } catch (e) {
        // Keep default unchecked state when config is temporarily unavailable.
    } finally {
        mobilePlayerOverrideFullUi = false;
        applyMobilePlayerOnlyMode();
    }
}

function getMobileTrackLabel(file) {
    const artist = String(file?.artist || '').trim();
    const title = String(file?.title || '').trim();
    const fallback = String(file?.filename || '').trim();
    if (artist || title) return `${artist || 'Unknown artist'} - ${title || 'Unknown title'}`;
    return fallback || 'Unknown track';
}

function isFilePlayable(file) {
    // Mobile player should only list files that physically exist.
    return Boolean(file) && file.exists_on_disk !== false;
}

function applyMobileTrackFilter(reset = true) {
    const playableFiles = files.filter(isFilePlayable);
    const query = String(mobileTrackSearch?.value || '').trim().toLowerCase();
    mobileTrackHasQuery = Boolean(query);
    if (!query) {
        mobileTrackFiltered = [...playableFiles];
    } else {
        mobileTrackFiltered = playableFiles.filter((f) => {
            return getMobileTrackLabel(f).toLowerCase().includes(query)
                || String(f?.album || '').toLowerCase().includes(query);
        });
    }
    renderMobileTrackList(reset);
}

function renderMobileTrackList(reset = false) {
    if (!mobileTrackList) return;
    if (reset) {
        mobileTrackList.innerHTML = '';
        mobileTrackRenderedCount = 0;
    }
    const src = mobileTrackHasQuery ? mobileTrackFiltered : files.filter(isFilePlayable);
    const end = Math.min(src.length, mobileTrackRenderedCount === 0 ? MOBILE_TRACK_PAGE_SIZE : mobileTrackRenderedCount + MOBILE_TRACK_PAGE_STEP);
    const chunk = src.slice(mobileTrackRenderedCount, end);
    if (chunk.length === 0 && mobileTrackRenderedCount === 0) {
        mobileTrackList.innerHTML = '<div class="mobile-track-item-title" style="padding: 0.65rem; color: var(--text-dim);">No tracks</div>';
        return;
    }

    chunk.forEach((f, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'mobile-track-item';
        btn.dataset.id = String(f.id);
        if (currentPlayingId === f.id) btn.classList.add('is-playing');
        const rowIndex = mobileTrackRenderedCount + idx + 1;
        btn.innerHTML = `
            <span class="mobile-track-item-index">${rowIndex}</span>
            <span class="mobile-track-item-title">${esc(getMobileTrackLabel(f))}</span>
        `;
        btn.addEventListener('click', () => window.toggleTrackPlayback(f.id));
        mobileTrackList.appendChild(btn);
    });
    mobileTrackRenderedCount = end;

    const oldMoreBtn = mobileTrackList.querySelector('.mobile-track-item-more');
    if (oldMoreBtn) oldMoreBtn.remove();
    if (mobileTrackRenderedCount < src.length) {
        const moreBtn = document.createElement('button');
        moreBtn.type = 'button';
        moreBtn.className = 'mobile-track-item-more';
        moreBtn.textContent = `Load more (${src.length - mobileTrackRenderedCount} left)`;
        moreBtn.addEventListener('click', () => renderMobileTrackList(false));
        mobileTrackList.appendChild(moreBtn);
    }
}

function maybeRenderMoreMobileTracks() {
    if (!mobileTrackList) return;
    const threshold = 140;
    const nearBottom = mobileTrackList.scrollTop + mobileTrackList.clientHeight >= mobileTrackList.scrollHeight - threshold;
    if (nearBottom) renderMobileTrackList(false);
}

function updateMobileTrackPlayingState() {
    if (!mobileTrackList) return;
    mobileTrackList.querySelectorAll('.mobile-track-item').forEach((el) => {
        const id = Number(el.dataset.id || 0);
        el.classList.toggle('is-playing', currentPlayingId === id);
    });
}

function scrollMobileTrackListToPlaying() {
    if (!isMobileViewport() || !mobileTrackList) return;
    if (currentPlayingId === null) return;
    const listSource = mobileTrackHasQuery ? mobileTrackFiltered : files.filter(isFilePlayable);
    const playingIndex = listSource.findIndex((f) => f.id === currentPlayingId);
    if (playingIndex === -1) return;

    // Lazy rendering can hide the active row. Render until it appears.
    while (mobileTrackRenderedCount <= playingIndex) {
        const prevCount = mobileTrackRenderedCount;
        renderMobileTrackList(false);
        if (mobileTrackRenderedCount === prevCount) break;
    }

    const playingEl = mobileTrackList.querySelector(`.mobile-track-item[data-id="${currentPlayingId}"]`);
    if (!playingEl) return;
    playingEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// Update move button
function updateMoveBtn() {
    btnMove.disabled = selectedIds.size === 0;
    btnAutoFill.disabled = selectedIds.size === 0;
    btnBatchAcoustid.disabled = selectedIds.size === 0;
    btnBatchOllama.disabled = selectedIds.size === 0;
    btnBatchDelete.disabled = selectedIds.size === 0;
    
    // Update processed action button
    const currentStatus = statusFilter.value;
    if (currentStatus === 'processed') {
        btnProcessedAction.disabled = files.length === 0;
        processedFilesCache = [...files];
        btnProcessedAction.textContent = `Action for ${files.length} Processed`;
    } else {
        btnProcessedAction.disabled = true;
        btnProcessedAction.textContent = 'Action for Processed';
        btnAutoFill.disabled = selectedIds.size === 0;
    }
}

// Update batch notice
function updateBatchNotice() {
    const count = selectedIds.size;
    if (count > 1) {
        batchNotice.style.display = 'block';
        batchCount.textContent = count;
        btnBatchSave.style.display = 'inline-block';
    } else {
        batchNotice.style.display = 'none';
        btnBatchSave.style.display = 'none';
    }
}

// Select single file -> load tags into editor
async function selectFile(id) {
    currentFileId = id;
    try {
        const tags = await api('GET', `/api/files/${id}/tags`);
        document.getElementById('tag-artist').value = tags.artist || '';
        document.getElementById('tag-album').value = tags.album || '';
        document.getElementById('tag-title').value = tags.title || '';
        document.getElementById('tag-track').value = tags.track_number || 0;
        document.getElementById('tag-year').value = tags.year || '';
        document.getElementById('tag-format').value = tags.medium_format || '';
        document.getElementById('tag-medium').value = tags.medium_number || 1;
    } catch (e) {
        toast('Failed to load tags: ' + e.message, 'error');
    }
}

// Save single file tags
tagForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentFileId) { toast('No file selected', 'error'); return; }
    const tags = {
        artist: document.getElementById('tag-artist').value,
        album: document.getElementById('tag-album').value,
        title: document.getElementById('tag-title').value,
        track_number: parseInt(document.getElementById('tag-track').value) || 0,
        year: document.getElementById('tag-year').value,
        medium_format: document.getElementById('tag-format').value,
        medium_number: parseInt(document.getElementById('tag-medium').value) || 1,
    };
    try {
        await api('PUT', `/api/files/${currentFileId}/tags`, tags);
        toast('Tags saved', 'success');
        loadFiles();
    } catch (e) {
        toast('Save failed: ' + e.message, 'error');
    }
});

// Batch save tags
btnBatchSave.addEventListener('click', async () => {
    if (selectedIds.size < 2) return;
    const tags = {};
    const artist = document.getElementById('tag-artist').value;
    const album = document.getElementById('tag-album').value;
    const title = document.getElementById('tag-title').value;
    const track = document.getElementById('tag-track').value;
    const year = document.getElementById('tag-year').value;
    const format = document.getElementById('tag-format').value;
    const medium = document.getElementById('tag-medium').value;

    if (artist) tags.artist = artist;
    if (album) tags.album = album;
    if (title) tags.title = title;
    if (track) tags.track_number = parseInt(track) || 0;
    if (year) tags.year = year;
    if (format) tags.medium_format = format;
    if (medium) tags.medium_number = parseInt(medium) || 1;

    if (Object.keys(tags).length === 0) { toast('Fill at least one field for batch edit', 'error'); return; }

    try {
        const res = await api('PUT', '/api/files/batch/tags', { ids: [...selectedIds], tags });
        const ok = res.results.filter(r => r.status === 'ok').length;
        toast(`Batch saved: ${ok}/${res.results.length}`, 'success');
        loadFiles();
    } catch (e) {
        toast('Batch save failed: ' + e.message, 'error');
    }
});

// Scan
btnScan.addEventListener('click', async () => {
    btnScan.disabled = true;
    btnScan.textContent = 'Scanning...';
    try {
        const res = await api('POST', '/api/scan');
        toast(`Scanned: ${res.scanned} new files`, 'success');
        loadFiles();
    } catch (e) {
        toast('Scan failed: ' + e.message, 'error');
    }
    btnScan.disabled = false;
    btnScan.textContent = 'Scan';
});

// Move
btnMove.addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    const mode = moveMode?.value || 'move';
    if (!confirm(`${mode.toUpperCase()}: process ${selectedIds.size} file(s)?`)) return;
    btnMove.disabled = true;
    try {
        const res = await api('POST', '/api/files/move', { ids: [...selectedIds], mode });
        // New API returns task info instead of results
        if (res.task_id) {
            toast(`${mode}: task queued (${selectedIds.size} files)`, 'success');
        } else {
            const moved = res.results ? res.results.filter(r => r.status === 'moved').length : 0;
            toast(`${mode}: ${moved}/${res.results ? res.results.length : 0}`, 'success');
        }
        loadFiles();
    } catch (e) {
        toast(`${mode} failed: ` + e.message, 'error');
    }
    btnMove.disabled = false;
});

// Batch mark as Delete status
btnBatchDelete.addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Mark ${selectedIds.size} file(s) with status Delete?`)) return;

    btnBatchDelete.disabled = true;
    try {
        const res = await api('PUT', '/api/files/status/batch', { ids: [...selectedIds], status: 'Delete' });
        toast(`Status Delete set: ${res.updated} file(s)`, 'success');
        loadFiles();
    } catch (e) {
        toast('Failed to set Delete status: ' + e.message, 'error');
    }
    btnBatchDelete.disabled = false;
});

// Logs
async function loadLogs() {
    try {
        const logs = await api('GET', '/api/logs?limit=100');
        const tbody = document.getElementById('logs-tbody');
        tbody.innerHTML = '';
        logs.forEach(l => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${new Date(l.timestamp).toLocaleString()}</td>
                <td>${esc(l.action)}</td>
                <td>${esc(l.details)}</td>
                <td><button class="btn btn-info" onclick="showLogDetail(${l.id})" title="View details">ℹ️</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        toast('Failed to load logs: ' + e.message, 'error');
    }
}
document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);

// Log Detail Modal
window.showLogDetail = async function(logId) {
    try {
        const detail = await api('GET', `/api/logs/${logId}`);
        renderLogDetail(detail);
        logDetailModal.style.display = 'flex';
    } catch (e) {
        toast('Failed to load log details: ' + e.message, 'error');
    }
};

function renderLogDetail(detail) {
    const meta = detail.metadata || {};
    
    logDetailContent.innerHTML = `
        <div class="detail-section">
            <h4>📋 Log Information</h4>
            <div class="detail-row">
                <span class="detail-label">ID</span>
                <span class="detail-value">${detail.id}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Action</span>
                <span class="detail-value">${esc(meta.action || detail.action)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Timestamp</span>
                <span class="detail-value">${new Date(detail.timestamp).toLocaleString()}</span>
            </div>
        </div>
        
        ${meta.action === 'move' ? `
        <div class="detail-section">
            <h4>📍 File Move Details</h4>
            <div class="detail-row" style="display: block;">
                <span class="detail-label">From:</span>
                <div class="detail-value" title="${esc(meta.from_path || 'N/A')}" style="text-align: left; margin-top: 0.3rem; color: var(--warning);">📂 ${esc(meta.from_path || 'N/A')}</div>
            </div>
            <div style="text-align: center; padding: 0.5rem;">⬇️</div>
            <div class="detail-row" style="display: block;">
                <span class="detail-label">To:</span>
                <div class="detail-value" title="${esc(meta.to_path || 'N/A')}" style="text-align: left; margin-top: 0.3rem; color: var(--success);">📁 ${esc(meta.to_path || 'N/A')}</div>
            </div>
            ${meta.cover_art_saved ? `
            <div class="detail-row" style="margin-top: 0.5rem;">
                <span class="detail-value" style="color: var(--success);">✓ Cover art saved</span>
            </div>
            ` : ''}
        </div>
        ` : ''}
        
        ${meta.action === 'edit_tags' ? `
        <div class="detail-section">
            <h4>🏷️ Tag Changes</h4>
            ${Object.entries(meta.changes || {}).map(([key, change]) => `
                <div class="detail-row" style="display: block; margin-bottom: 0.5rem;">
                    <span class="detail-label" style="text-transform: capitalize;">${esc(key.replace('_', ' '))}:</span>
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.3rem;">
                        <span style="color: var(--danger); text-decoration: line-through; font-size: 0.85rem;">${esc(change.old || 'N/A')}</span>
                        <span style="color: var(--text-dim);">→</span>
                        <span style="color: var(--success); font-weight: 600;">${esc(change.new || 'N/A')}</span>
                    </div>
                </div>
            `).join('')}
        </div>
        ` : ''}
        
        ${meta.action === 'move_back' ? `
        <div class="detail-section">
            <h4>↩️ Move Back Details</h4>
            <div class="detail-row" style="display: block;">
                <span class="detail-value" style="font-family: monospace; font-size: 0.85rem;">${esc(detail.details)}</span>
            </div>
        </div>
        ` : ''}
        
        ${detail.related_file ? `
        <div class="detail-section">
            <h4>📁 Related File</h4>
            <div class="detail-row">
                <span class="detail-label">Filename</span>
                <span class="detail-value">${esc(detail.related_file.filename)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Status</span>
                <span class="detail-value">${esc(detail.related_file.status)}</span>
            </div>
            ${detail.related_file.original_filepath ? `
            <div class="path-move" style="margin-top: 0.5rem;">
                <div class="path-move-item">
                    <span class="path-move-icon">📂</span>
                    <span class="detail-label">From:</span>
                    <span class="detail-value" title="${esc(detail.related_file.original_filepath)}" style="flex:1;">${esc(detail.related_file.original_filepath)}</span>
                </div>
                <div class="path-move-item">
                    <span class="path-move-icon">⬇️</span>
                </div>
                <div class="path-move-item">
                    <span class="path-move-icon">📁</span>
                    <span class="detail-label">To:</span>
                    <span class="detail-value" title="${esc(detail.related_file.filepath)}" style="flex:1;">${esc(detail.related_file.filepath)}</span>
                </div>
            </div>
            ` : ''}
            <div class="detail-row" style="margin-top: 0.5rem;">
                <button class="btn primary" onclick="showFileDetail(${detail.related_file.id}); logDetailModal.style.display='none';" style="width: 100%;">View File Details</button>
            </div>
        </div>
        ` : ''}
    `;
}

// Close log detail modal
logDetailModal?.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
        logDetailModal.style.display = 'none';
    });
});

// Close modal on outside click
logDetailModal?.addEventListener('click', (e) => {
    if (e.target === logDetailModal) {
        logDetailModal.style.display = 'none';
    }
});

// Settings
async function loadSettings() {
    try {
        const cfg = await api('GET', '/api/config');
        document.getElementById('cfg-source').value = cfg.source_dir || '';
        document.getElementById('cfg-output').value = cfg.output_dir || '';
        document.getElementById('cfg-template').value = cfg.path_template || '';
        document.getElementById('cfg-extensions').value = (cfg.extensions || []).join(', ');
        document.getElementById('cfg-gotify-url').value = cfg.gotify_url || '';
        document.getElementById('cfg-gotify-token').value = cfg.gotify_token || '';
        document.getElementById('cfg-acoustid-key').value = cfg.acoustid_api_key || '';
        document.getElementById('cfg-ollama-url').value = cfg.ollama_url || 'http://localhost:11434';
        document.getElementById('cfg-ollama-model').value = cfg.ollama_model || 'llama3.2';
        document.getElementById('cfg-proxy-url').value = cfg.proxy_url || '';
        document.getElementById('cfg-proxy-type').value = cfg.proxy_type || 'http';
        document.getElementById('cfg-proxy-host').value = cfg.proxy_host || '';
        document.getElementById('cfg-proxy-port').value = cfg.proxy_port || 0;
        document.getElementById('cfg-proxy-username').value = cfg.proxy_username || '';
        document.getElementById('cfg-proxy-password').value = cfg.proxy_password || '';
        document.getElementById('cfg-interval').value = cfg.scan_interval || 30;
        if (cfgMobilePlayerOnly) {
            cfgMobilePlayerOnly.checked = Boolean(cfg.mobile_player_only);
            mobilePlayerOverrideFullUi = false;
            applyMobilePlayerOnlyMode();
        }
    } catch (e) {
        toast('Failed to load config: ' + e.message, 'error');
    }
}

document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        source_dir: document.getElementById('cfg-source').value,
        output_dir: document.getElementById('cfg-output').value,
        path_template: document.getElementById('cfg-template').value,
        extensions: document.getElementById('cfg-extensions').value.split(',').map(s => s.trim()).filter(Boolean),
        gotify_url: document.getElementById('cfg-gotify-url').value,
        gotify_token: document.getElementById('cfg-gotify-token').value,
        acoustid_api_key: document.getElementById('cfg-acoustid-key').value,
        ollama_url: document.getElementById('cfg-ollama-url').value,
        ollama_model: document.getElementById('cfg-ollama-model').value,
        proxy_url: document.getElementById('cfg-proxy-url').value,
        proxy_type: document.getElementById('cfg-proxy-type').value,
        proxy_host: document.getElementById('cfg-proxy-host').value,
        proxy_port: parseInt(document.getElementById('cfg-proxy-port').value) || 0,
        proxy_username: document.getElementById('cfg-proxy-username').value,
        proxy_password: document.getElementById('cfg-proxy-password').value,
        scan_interval: parseInt(document.getElementById('cfg-interval').value) || 0,
        mobile_player_only: Boolean(cfgMobilePlayerOnly?.checked),
    };
    try {
        await api('PUT', '/api/config', data);
        toast('Settings saved', 'success');
        mobilePlayerOverrideFullUi = false;
        applyMobilePlayerOnlyMode();
    } catch (e) {
        toast('Save failed: ' + e.message, 'error');
    }
});

cfgMobilePlayerOnly?.addEventListener('change', () => {
    mobilePlayerOverrideFullUi = false;
    applyMobilePlayerOnlyMode();
});

mobilePlayerToggleUiBtn?.addEventListener('click', () => {
    mobilePlayerOverrideFullUi = !mobilePlayerOverrideFullUi;
    applyMobilePlayerOnlyMode();
});

mobilePlayerCollapseBtn?.addEventListener('click', () => {
    mobilePlayerCollapsed = !mobilePlayerCollapsed;
    applyMobilePlayerOnlyMode();
});

window.addEventListener('resize', debounce(() => {
    applyMobilePlayerOnlyMode();
}, 120));

// Test Gotify notifications
document.getElementById('btn-test-gotify').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-gotify');
    btn.disabled = true;
    btn.textContent = 'Testing...';
    try {
        const res = await api('POST', '/api/gotify/test');
        if (res.success) {
            toast(res.message, 'success');
        } else {
            toast(res.message, 'error');
        }
    } catch (e) {
        toast('Test failed: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'Test Notifications';
});

// Test Ollama connection
document.getElementById('btn-test-ollama').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-ollama');
    btn.disabled = true;
    btn.textContent = 'Testing...';
    try {
        const res = await api('GET', '/api/ollama/status');
        if (res.available && res.configured) {
            toast(`Ollama connected! Model: ${res.model}`, 'success');
        } else if (res.configured) {
            toast(`Ollama configured but not available. Check if Ollama is running on ${res.url}`, 'error');
        } else {
            toast('Ollama not configured. Set URL and model in settings.', 'error');
        }
    } catch (e) {
        toast('Test failed: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'Test Ollama Connection';
});

// Directory Browser Modal
async function openDirModal(target) {
    currentBrowseTarget = target;
    selectedDirPath = '';
    btnSelectDir.disabled = true;
    await loadDirectories('');
    dirModal.style.display = 'flex';
}

function activateSettingsPane(tabName) {
    settingsSubtabs.forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.settingsTab === tabName);
    });
    settingsPanes.forEach((pane) => {
        pane.classList.toggle('active', pane.dataset.settingsPane === tabName);
    });
}

settingsSubtabs.forEach((btn) => {
    btn.addEventListener('click', () => {
        activateSettingsPane(btn.dataset.settingsTab);
    });
});

async function closeDirModal() {
    dirModal.style.display = 'none';
    currentBrowseTarget = null;
}

async function loadDirectories(path) {
    try {
        const data = await api('GET', '/api/directories?path=' + encodeURIComponent(path));
        if (data.error) {
            toast(data.error, 'error');
            return;
        }
        currentDirPath = data.path;
        dirPathInput.value = data.path;
        
        dirList.innerHTML = '';
        data.directories.forEach(dir => {
            const item = document.createElement('div');
            item.className = 'dir-item';
            item.innerHTML = `
                <span class="dir-item-icon">📁</span>
                <span class="dir-item-name">${esc(dir.name)}</span>
            `;
            item.addEventListener('click', () => {
                // Deselect previous
                dirList.querySelectorAll('.dir-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                selectedDirPath = dir.path;
                btnSelectDir.disabled = false;
            });
            item.addEventListener('dblclick', () => {
                loadDirectories(dir.path);
            });
            dirList.appendChild(item);
        });
        
        // Store parent for up button
        dirModal.querySelector('.btn-up').dataset.parent = data.parent || '';
        dirModal.querySelector('.btn-up').disabled = !data.parent;
    } catch (e) {
        toast('Failed to load directories: ' + e.message, 'error');
    }
}

// Up button
dirModal.querySelector('.btn-up').addEventListener('click', () => {
    const parent = dirModal.querySelector('.btn-up').dataset.parent;
    if (parent) loadDirectories(parent);
});

// Close buttons
dirModal.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
    btn.addEventListener('click', closeDirModal);
});

// Select button
btnSelectDir.addEventListener('click', () => {
    if (currentBrowseTarget && selectedDirPath) {
        document.getElementById(currentBrowseTarget).value = selectedDirPath;
    }
    closeDirModal();
});

// Browse buttons
document.querySelectorAll('.btn-browse').forEach(btn => {
    btn.addEventListener('click', () => openDirModal(btn.dataset.target));
});

// Close modal on outside click
dirModal.addEventListener('click', (e) => {
    if (e.target === dirModal) closeDirModal();
});

// Processed Action Modal
btnProcessedAction.addEventListener('click', () => {
    if (processedFilesCache.length === 0) return;
    document.getElementById('processed-count').textContent = processedFilesCache.length;
    processedActionModal.style.display = 'flex';
});

// Auto-fill tags for selected files
btnAutoFill.addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Auto-fill tags from filename for ${selectedIds.size} file(s)?`)) return;
    
    try {
        const result = await api('POST', '/api/files/batch/auto-fill', [...selectedIds]);
        const ok = result.results.filter(r => r.status === 'ok').length;
        const skipped = result.results.filter(r => r.status === 'skipped').length;
        const errors = result.results.filter(r => r.status === 'error').length;
        toast(`Auto-fill: ${ok} ok, ${skipped} skipped, ${errors} errors`, 'success');
        loadFiles();
    } catch (e) {
        toast('Batch auto-fill failed: ' + e.message, 'error');
    }
});

// Batch auto-identify tags for selected files
btnBatchAcoustid.addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Batch AcoustID identify for ${selectedIds.size} file(s)?`)) return;
    const ids = [...selectedIds];
    btnBatchAcoustid.disabled = true;
    try {
        const res = await api('POST', '/api/files/batch/identify-acoustid', { ids });
        toast(`Batch AcoustID queued: task #${res.task_id} (${res.count} files)`, 'success');
        loadFiles();
    } catch (e) {
        toast('Batch AcoustID failed: ' + e.message, 'error');
    } finally {
        btnBatchAcoustid.disabled = false;
    }
});

btnBatchOllama.addEventListener('click', async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Batch Ollama metadata generation for ${selectedIds.size} file(s)?`)) return;
    const ids = [...selectedIds];
    btnBatchOllama.disabled = true;
    setOllamaBusyHint('Preparing batch Ollama recognition');
    try {
        const res = await api('POST', '/api/files/batch/generate-metadata-ollama', { ids });
        toast(`Batch Ollama queued: task #${res.task_id} (${res.count} files)`, 'success');
        loadFiles();
    } catch (e) {
        toast('Batch Ollama failed: ' + e.message, 'error');
    } finally {
        btnBatchOllama.disabled = false;
        clearOllamaBusyHint();
    }
});

// Move processed to output
document.getElementById('btn-move-processed').addEventListener('click', async () => {
    const ids = processedFilesCache.map(f => f.id);
    if (ids.length === 0) return;
    const mode = moveMode?.value || 'move';
    
    processedActionModal.style.display = 'none';
    
    // Mark files as pending_move and start move task
    await api('POST', '/api/files/move', { ids, mode });
    toast(`${mode}: task queued for ${ids.length} files`, 'success');
    loadFiles();
});

// Mark processed as new
document.getElementById('btn-mark-new').addEventListener('click', async () => {
    const ids = processedFilesCache.map(f => f.id);
    if (ids.length === 0) return;
    
    try {
        for (const id of ids) {
            await api('PUT', `/api/files/${id}/status`, { status: 'new' });
        }
        toast(`Marked ${ids.length} files as new`, 'success');
        processedActionModal.style.display = 'none';
        loadFiles();
    } catch (e) {
        toast('Failed to mark as new: ' + e.message, 'error');
    }
});

// Delete processed from DB
document.getElementById('btn-delete-processed').addEventListener('click', async () => {
    const ids = processedFilesCache.map(f => f.id);
    if (ids.length === 0) return;
    
    if (!confirm(`Delete ${ids.length} file(s) from database? This won't delete the actual files.`)) return;
    
    try {
        for (const id of ids) {
            await api('DELETE', `/api/files/${id}`);
        }
        toast(`Deleted ${ids.length} records from database`, 'success');
        processedActionModal.style.display = 'none';
        loadFiles();
    } catch (e) {
        toast('Failed to delete: ' + e.message, 'error');
    }
});

// Close processed action modal
processedActionModal?.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
        processedActionModal.style.display = 'none';
    });
});

processedActionModal?.addEventListener('click', (e) => {
    if (e.target === processedActionModal) {
        processedActionModal.style.display = 'none';
    }
});

// Init
configureMoveModesByOs();
loadWaveformStylePreference();
initMobilePlayerOnlyMode();
loadFiles();
loadStats();
loadFilterOptions();
loadTasks();
startTaskPolling();
startOllamaPolling();

fileListContainer?.addEventListener('scroll', debounce(maybeRenderMoreFiles, 100));
mobileTrackList?.addEventListener('scroll', debounce(maybeRenderMoreMobileTracks, 100));
mobileTrackSearch?.addEventListener('input', debounce(() => applyMobileTrackFilter(true), 250));

function startTaskPolling() {
    if (taskPollInterval) clearInterval(taskPollInterval);
    taskPollInterval = setInterval(loadTasks, 2000); // Poll every 2 seconds
}

function startOllamaPolling() {
    if (ollamaPollInterval) clearInterval(ollamaPollInterval);
    if (ollamaActivityInterval) clearInterval(ollamaActivityInterval);
    updateOllamaIndicator();
    ollamaPollInterval = setInterval(updateOllamaIndicator, 3000);
    ollamaActivityInterval = setInterval(animateOllamaStateView, 700);
}

// Tasks
async function loadTasks() {
    try {
        const tasks = await api('GET', '/api/tasks?limit=10');
        renderTasks(tasks);
    } catch (e) {
        console.error('Failed to load tasks:', e);
    }
}

function taskAgeMinutes(task) {
    const updated = Date.parse(task.updated_at || task.created_at || '');
    if (!Number.isFinite(updated)) return 0;
    return Math.max(0, (Date.now() - updated) / 60000);
}

function isTaskStuck(task) {
    if (!task) return false;
    if (!(task.status === 'pending' || task.status === 'running')) return false;
    return taskAgeMinutes(task) >= 3;
}

function renderTasks(tasks) {
    if (!taskList) return;
    
    const activeTasks = tasks.filter(t => t.status === 'pending' || t.status === 'running');
    
    if (activeTasks.length === 0) {
        taskList.innerHTML = '<div class="task-item"><span class="task-item-status">No active tasks</span></div>';
        return;
    }
    
    taskList.innerHTML = '';
    activeTasks.forEach(task => {
        const item = document.createElement('div');
        item.className = `task-item ${task.status}`;
        
        const progress = task.total_items > 0 
            ? Math.round((task.processed_items / task.total_items) * 100) 
            : 0;
        
        const ageMin = Math.floor(taskAgeMinutes(task));
        const stuck = isTaskStuck(task);
        item.innerHTML = `
            <div class="task-item-info">
                <div class="task-item-type">${esc(task.task_type)} #${task.id}</div>
                <div class="task-item-status ${stuck ? 'stuck' : ''}">${task.status} - ${task.processed_items}/${task.total_items}${ageMin > 0 ? ` (${ageMin}m)` : ''}${stuck ? ' - seems stuck' : ''}</div>
            </div>
            <div class="task-item-progress">
                <div class="task-item-progress-bar" style="width: ${progress}%"></div>
            </div>
            <div class="task-item-actions">
                ${task.status === 'running' || task.status === 'pending' 
                    ? `<button class="btn" onclick="cancelTask(${task.id})">Cancel</button>` 
                    : ''}
                ${stuck ? `<button class="btn" onclick="cancelTask(${task.id})">Force Stop</button>` : ''}
            </div>
        `;
        taskList.appendChild(item);
    });
}

function deriveOllamaState(tasks, statusInfo) {
    const activeTasks = (tasks || []).filter(t => t.status === 'pending' || t.status === 'running');
    const ollamaTasks = activeTasks.filter(t => String(t.task_type || '').includes('ollama'));

    if (!statusInfo.configured) {
        return { state: 'unconfigured', details: 'Ollama is not configured in settings' };
    }
    if (ollamaBusyHintCount > 0) {
        return {
            state: 'working',
            details: ollamaBusyHintText || 'Recognizing title and artist',
        };
    }
    if (ollamaTasks.length > 0) {
        const running = ollamaTasks.find(t => t.status === 'running') || ollamaTasks[0];
        return {
            state: running.status === 'running' ? 'working' : 'queued',
            details: `Task #${running.id}: ${running.processed_items}/${running.total_items}`,
        };
    }
    if (!statusInfo.available) {
        return { state: 'offline', details: `No response from ${statusInfo.url || 'configured URL'}` };
    }
    return { state: 'idle', details: `Ready: ${statusInfo.model || 'model not set'}` };
}

function applyOllamaStateView(statePayload) {
    if (!ollamaStateLabel || !ollamaStateDetails || !ollamaEmoji) return;
    const map = {
        unconfigured: { label: 'not configured', mood: 'warning', emoji: '🤔' },
        queued: { label: 'queued', mood: 'loading', emoji: '⏳' },
        working: { label: 'working', mood: 'working', emoji: '🧠' },
        offline: { label: 'offline', mood: 'error', emoji: '😵' },
        idle: { label: 'idle', mood: 'idle', emoji: '😴' },
    };
    const view = map[statePayload.state] || map.idle;
    ollamaCurrentView = {
        state: statePayload.state,
        details: statePayload.details,
        label: view.label,
        emoji: view.emoji,
        mood: view.mood,
    };
    animateOllamaStateView();
}

function animateOllamaStateView() {
    if (!ollamaStateLabel || !ollamaStateDetails || !ollamaEmoji || !ollamaCurrentView) return;
    ollamaActivityTick += 1;
    const dots = '.'.repeat((ollamaActivityTick % 3) + 1);
    const sparkle = ['·', '•', '◦', '•'][ollamaActivityTick % 4];

    let label = ollamaCurrentView.label || 'idle';
    let details = ollamaCurrentView.details || '';
    let emoji = ollamaCurrentView.emoji || '😴';

    if (currentPlayingId !== null) {
        label = currentPlayingLabel || `listening${dots}`;
        details = `In headphones ${sparkle} 🤘`;
        emoji = ['🎧', '🤘', '🎧'][ollamaActivityTick % 3];
    } else if (ollamaCurrentView.state === 'idle') {
        label = `idle${dots}`;
        details = `${details} ${sparkle}`;
        emoji = ['😴', '🙂', '😌'][ollamaActivityTick % 3];
    } else if (ollamaCurrentView.state === 'working') {
        label = `working${dots}`;
        details = `${details}${dots}`;
        emoji = ['🧠', '🤖', '🧠'][ollamaActivityTick % 3];
    } else if (ollamaCurrentView.state === 'queued') {
        label = `queued${dots}`;
        details = `${details}${dots}`;
    }

    const useMarquee = currentPlayingId !== null && Boolean(currentPlayingLabel);
    if (useMarquee) {
        ollamaStateLabel.classList.add('is-marquee');
        let textEl = ollamaStateLabel.querySelector('.ollama-state-label-text');
        if (!textEl) {
            ollamaStateLabel.innerHTML = '<span class="ollama-state-label-text"></span>';
            textEl = ollamaStateLabel.querySelector('.ollama-state-label-text');
        }
        if (textEl && textEl.textContent !== label) {
            textEl.textContent = label;
        }
    } else {
        ollamaStateLabel.classList.remove('is-marquee');
        ollamaStateLabel.textContent = label;
    }
    ollamaStateDetails.textContent = details.trim();
    ollamaEmoji.textContent = emoji;
    ollamaEmoji.className = `ollama-emoji ${ollamaCurrentView.mood || 'idle'}`;
    updateNowPlayingCover();
}

function updateNowPlayingCover() {
    if (!nowPlayingCoverWrap || !nowPlayingCover) return;
    const hasCover = currentPlayingId !== null && Boolean(currentPlayingCoverUrl);
    const showWaveform = currentPlayingId !== null && !hasCover && isMobileViewport();
    const showPlaceholder = currentPlayingId === null;
    const playing = currentPlayingId !== null && !audioPlayer.paused;
    const makeVinyl = playing;

    const applyCoverPlaybackState = (el) => {
        if (!el) return;
        el.classList.toggle('is-vinyl', makeVinyl);
        el.classList.toggle('is-spinning', playing);
    };

    applyCoverPlaybackState(nowPlayingCover);
    applyCoverPlaybackState(nowPlayingCoverNext);
    nowPlayingCoverWrap.classList.toggle('is-vinyl', makeVinyl);
    nowPlayingCoverWrap.classList.toggle('is-waveform', showWaveform);
    nowPlayingCoverWrap.classList.toggle('is-placeholder', showPlaceholder);

    if (showWaveform) {
        if (nowPlayingCoverSwapTimer) {
            clearTimeout(nowPlayingCoverSwapTimer);
            nowPlayingCoverSwapTimer = null;
        }
        nowPlayingCoverWrap.classList.remove('is-switching');
        nowPlayingCover.removeAttribute('src');
        nowPlayingCoverNext?.removeAttribute('src');
        nowPlayingCoverWrap.style.display = '';
        startWaveformAnimation();
        return;
    }
    stopWaveformAnimation();

    if (!hasCover) {
        if (nowPlayingCoverSwapTimer) {
            clearTimeout(nowPlayingCoverSwapTimer);
            nowPlayingCoverSwapTimer = null;
        }
        nowPlayingCoverWrap.classList.remove('is-switching');
        nowPlayingCoverWrap.style.display = '';
        nowPlayingCover.removeAttribute('src');
        nowPlayingCoverNext?.removeAttribute('src');
        return;
    }
    if (nowPlayingCover.getAttribute('src') === currentPlayingCoverUrl) {
        nowPlayingCoverWrap.style.display = '';
        return;
    }
    const requestedCoverUrl = currentPlayingCoverUrl;
    const probe = new Image();
    probe.onload = () => {
        if (currentPlayingCoverUrl !== requestedCoverUrl) return;
        nowPlayingCoverWrap.style.display = '';
        if (!nowPlayingCoverNext || !nowPlayingCover.getAttribute('src')) {
            nowPlayingCover.src = requestedCoverUrl;
            return;
        }
        if (nowPlayingCoverSwapTimer) clearTimeout(nowPlayingCoverSwapTimer);
        nowPlayingCoverNext.src = requestedCoverUrl;
        applyCoverPlaybackState(nowPlayingCoverNext);
        nowPlayingCoverWrap.classList.add('is-switching');
        nowPlayingCoverSwapTimer = setTimeout(() => {
            nowPlayingCover.src = requestedCoverUrl;
            applyCoverPlaybackState(nowPlayingCover);
            nowPlayingCoverWrap.classList.remove('is-switching');
            nowPlayingCoverNext.removeAttribute('src');
            nowPlayingCoverSwapTimer = null;
        }, 620);
    };
    probe.onerror = () => {
        if (currentPlayingCoverUrl === requestedCoverUrl) {
            currentPlayingCoverUrl = '';
            nowPlayingCover.removeAttribute('src');
            nowPlayingCoverNext?.removeAttribute('src');
            nowPlayingCoverWrap.classList.remove('is-switching');
            updateNowPlayingCover();
        }
    };
    probe.src = requestedCoverUrl;
}

function ensureWaveformAnalyser() {
    if (nowPlayingAnalyser && nowPlayingDataArray) return true;
    try {
        if (!nowPlayingAudioCtx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return false;
            nowPlayingAudioCtx = new AudioCtx();
        }
        if (!nowPlayingSourceNode) {
            nowPlayingSourceNode = nowPlayingAudioCtx.createMediaElementSource(audioPlayer);
            nowPlayingAnalyser = nowPlayingAudioCtx.createAnalyser();
            nowPlayingAnalyser.fftSize = 256;
            nowPlayingAnalyser.smoothingTimeConstant = 0.85;
            nowPlayingSourceNode.connect(nowPlayingAnalyser);
            nowPlayingAnalyser.connect(nowPlayingAudioCtx.destination);
            nowPlayingDataArray = new Uint8Array(nowPlayingAnalyser.frequencyBinCount);
        }
        return Boolean(nowPlayingAnalyser && nowPlayingDataArray);
    } catch (e) {
        return false;
    }
}

function startWaveformAnimation() {
    if (!nowPlayingWaveform) return;
    if (!ensureWaveformAnalyser()) return;
    if (nowPlayingAudioCtx?.state === 'suspended') {
        nowPlayingAudioCtx.resume().catch(() => {});
    }
    if (nowPlayingWaveformRaf !== null) return;
    const draw = () => {
        if (!nowPlayingWaveform || !nowPlayingCoverWrap?.classList.contains('is-waveform')) {
            nowPlayingWaveformRaf = null;
            return;
        }
        const rect = nowPlayingWaveform.getBoundingClientRect();
        const width = Math.max(1, Math.floor(rect.width));
        const height = Math.max(1, Math.floor(rect.height || rect.width));
        if (nowPlayingWaveform.width !== width || nowPlayingWaveform.height !== height) {
            nowPlayingWaveform.width = width;
            nowPlayingWaveform.height = height;
        }
        const ctx = nowPlayingWaveform.getContext('2d');
        if (!ctx) {
            nowPlayingWaveformRaf = null;
            return;
        }

        nowPlayingAnalyser.getByteFrequencyData(nowPlayingDataArray);
        ctx.clearRect(0, 0, width, height);

        const style = nowPlayingWaveformStyle;
        const barCount = (style === 2 || style === 4) ? 40 : 26;
        const gap = style === 2 ? 2 : 3;
        const barWidth = Math.max(style === 2 ? 2 : 3, (width - gap * (barCount - 1)) / barCount);
        const maxH = height * (style === 1 ? 0.95 : 0.88);
        const centerY = height / 2;
        const baselineY = height - 2;
        const minLevel = audioPlayer.paused ? 0.05 : 0.09;

        for (let i = 0; i < barCount; i += 1) {
            const idx = Math.floor((i / barCount) * nowPlayingDataArray.length);
            const raw = (nowPlayingDataArray[idx] || 0) / 255;
            const amp = Math.max(minLevel, raw);
            const x = i * (barWidth + gap);
            const mirrorDistance = Math.abs((i / (barCount - 1 || 1)) - 0.5) * 2;

            if (style === 1) {
                const barH = Math.max(2, amp * maxH);
                const y = baselineY - barH;
                const grad = ctx.createLinearGradient(0, y, 0, baselineY);
                grad.addColorStop(0, 'rgba(80, 200, 120, 0.95)');
                grad.addColorStop(1, 'rgba(148, 136, 245, 0.85)');
                ctx.fillStyle = grad;
                ctx.fillRect(x, y, barWidth, barH);
                continue;
            }

            if (style === 2) {
                const boosted = amp * (1.1 + (1 - mirrorDistance) * 0.6);
                const barH = Math.max(2, boosted * maxH * 0.7);
                const y = centerY - (barH / 2);
                ctx.fillStyle = `rgba(148, 136, 245, ${0.55 + (1 - mirrorDistance) * 0.4})`;
                ctx.fillRect(x, y, barWidth, barH);
                continue;
            }

            if (style === 3) {
                const dotCount = Math.max(3, Math.floor((amp * maxH) / 7));
                const dotSize = Math.max(2, Math.min(5, barWidth));
                for (let d = 0; d < dotCount; d += 1) {
                    const y = centerY - ((dotCount - 1) * (dotSize + 2)) / 2 + d * (dotSize + 2);
                    ctx.fillStyle = `rgba(80, 200, 120, ${0.35 + (d / dotCount) * 0.6})`;
                    ctx.fillRect(x, y, dotSize, dotSize);
                }
                continue;
            }

            if (style === 4) {
                const pulse = amp * (0.7 + mirrorDistance * 0.8);
                const barH = Math.max(2, pulse * maxH * 0.85);
                const y = centerY - (barH / 2);
                const grad = ctx.createLinearGradient(0, y, 0, y + barH);
                grad.addColorStop(0, 'rgba(80, 200, 120, 0.55)');
                grad.addColorStop(0.5, 'rgba(148, 136, 245, 0.92)');
                grad.addColorStop(1, 'rgba(80, 200, 120, 0.55)');
                ctx.fillStyle = grad;
                ctx.fillRect(x, y, barWidth, barH);
                continue;
            }

            const barH = Math.max(2, amp * maxH);
            const y = centerY - (barH / 2);
            const grad = ctx.createLinearGradient(0, y, 0, y + barH);
            grad.addColorStop(0, 'rgba(148, 136, 245, 0.95)');
            grad.addColorStop(1, 'rgba(80, 200, 120, 0.88)');
            ctx.fillStyle = grad;
            ctx.fillRect(x, y, barWidth, barH);
        }
        nowPlayingWaveformRaf = window.requestAnimationFrame(draw);
    };
    nowPlayingWaveformRaf = window.requestAnimationFrame(draw);
}

function stopWaveformAnimation() {
    if (nowPlayingWaveformRaf !== null) {
        window.cancelAnimationFrame(nowPlayingWaveformRaf);
        nowPlayingWaveformRaf = null;
    }
    if (nowPlayingWaveform) {
        const ctx = nowPlayingWaveform.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, nowPlayingWaveform.width, nowPlayingWaveform.height);
    }
}

if (nowPlayingCover) {
    nowPlayingCover.addEventListener('error', () => {
        currentPlayingCoverUrl = '';
        nowPlayingCover.removeAttribute('src');
        nowPlayingCoverNext?.removeAttribute('src');
        nowPlayingCoverWrap?.classList.remove('is-switching');
        updateNowPlayingCover();
    });
}

nowPlayingWaveform?.addEventListener('click', () => {
    if (!isMobileViewport()) return;
    if (currentPlayingId === null) return;
    cycleWaveformStyle();
});

function setOllamaBusyHint(text) {
    ollamaBusyHintCount += 1;
    ollamaBusyHintText = text || 'Recognizing title and artist';
    updateOllamaIndicator();
}

function clearOllamaBusyHint() {
    ollamaBusyHintCount = Math.max(0, ollamaBusyHintCount - 1);
    if (ollamaBusyHintCount === 0) {
        ollamaBusyHintText = '';
    }
    updateOllamaIndicator();
}

function formatServiceEmoji(service) {
    if (!service.configured) return '😶';
    return service.ok ? '😄' : '😵';
}

function renderServicesHealth(services) {
    if (!ollamaServicesState) return;
    if (!Array.isArray(services) || services.length === 0) {
        ollamaServicesState.textContent = 'Services not checked yet';
        return;
    }
    ollamaServicesState.innerHTML = services.map((s) => `
        <div class="service-row">
            <span>${formatServiceEmoji(s)}</span>
            <span class="service-row-name">${esc(s.name)}</span>
            <span class="service-row-msg" title="${escAttr(s.message || '')}">${esc(s.message || '')}</span>
        </div>
    `).join('');
}

async function checkConfiguredServices() {
    if (!btnCheckServices) return;
    btnCheckServices.disabled = true;
    btnCheckServices.textContent = '⏳';
    try {
        const result = await api('GET', '/api/services/check');
        renderServicesHealth(result.services || []);
        toast('Service check completed', 'success');
    } catch (e) {
        toast('Service check failed: ' + e.message, 'error');
    } finally {
        btnCheckServices.disabled = false;
        btnCheckServices.textContent = '🔎';
    }
}

async function updateOllamaIndicator() {
    try {
        const [statusInfo, tasks] = await Promise.all([
            api('GET', '/api/ollama/status'),
            api('GET', '/api/tasks?limit=10'),
        ]);
        const statePayload = deriveOllamaState(tasks, statusInfo);
        applyOllamaStateView(statePayload);
    } catch (e) {
        applyOllamaStateView({ state: 'offline', details: 'Failed to get Ollama status' });
    }
}

ollamaIndicatorToggle?.addEventListener('click', () => {
    ollamaIndicatorExpanded = !ollamaIndicatorExpanded;
    if (ollamaIndicatorDetails) {
        ollamaIndicatorDetails.style.display = ollamaIndicatorExpanded ? 'block' : 'none';
    }
    scrollMobileTrackListToPlaying();
});
btnCheckServices?.addEventListener('click', checkConfiguredServices);

window.cancelTask = async function(taskId) {
    try {
        await api('POST', `/api/tasks/${taskId}/cancel`);
        toast(`Task #${taskId} cancelled`, 'success');
        loadTasks();
    } catch (e) {
        toast('Failed to cancel task: ' + e.message, 'error');
    }
};

btnCancelStuckTasks?.addEventListener('click', async () => {
    try {
        const tasks = await api('GET', '/api/tasks?limit=50');
        const stuckTasks = tasks.filter(isTaskStuck);
        if (stuckTasks.length === 0) {
            toast('No stuck tasks', 'success');
            return;
        }
        for (const task of stuckTasks) {
            await api('POST', `/api/tasks/${task.id}/cancel`);
        }
        toast(`Cancelled stuck tasks: ${stuckTasks.length}`, 'success');
        loadTasks();
    } catch (e) {
        toast('Failed to cancel stuck tasks: ' + e.message, 'error');
    }
});

// File Detail Modal
window.showFileDetail = async function(fileId) {
    try {
        const detail = await api('GET', `/api/files/${fileId}/detail`);
        renderFileDetail(detail);
        fileDetailModal.style.display = 'flex';
    } catch (e) {
        toast('Failed to load file details: ' + e.message, 'error');
    }
};

function renderFileDetail(detail) {
    const statusClass = detail.status === 'moved' ? 'success' : 
                        detail.status === 'error' ? 'error' : 
                        detail.status === 'processed' ? 'primary' : '';
    
    const canMoveBack = detail.status === 'moved' && detail.original_filepath;
    const hasTags = detail.artist || detail.album || detail.title;
    const extension = detail.extension ? detail.extension.toUpperCase() : 'Unknown';
    
    fileDetailContent.innerHTML = `
        <div class="detail-section">
            <h4>📁 File Information</h4>
            <div class="detail-row">
                <span class="detail-label">Filename</span>
                <span class="detail-value">${esc(detail.filename)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Extension</span>
                <span class="detail-value">${esc(extension)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Size</span>
                <span class="detail-value">${detail.file_size_formatted}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Status</span>
                <span class="detail-value ${statusClass}">${esc(detail.status)}</span>
            </div>
            ${canMoveBack ? `
            <div class="detail-row" style="margin-top: 0.5rem;">
                <button class="btn" onclick="moveFileBack(${detail.id})" style="width: 100%;">↩️ Move Back</button>
            </div>
            ` : ''}
            <div class="detail-row" style="margin-top: 0.5rem;">
                <button class="btn primary" onclick="identifyTrack(${detail.id})" style="width: 100%;">🎵 Auto-Identify (AcoustID)</button>
            </div>
            <div class="detail-row" style="margin-top: 0.25rem;">
                <button class="btn" onclick="searchMusicBrainzInModal(${detail.id})" style="width: 100%;">🔎 MusicBrainz (Title + Artist)</button>
            </div>
            <div class="detail-row" style="margin-top: 0.25rem;">
                <button class="btn" onclick="autoFillTags(${detail.id})" style="width: 100%;">✨ Parse Filename</button>
            </div>
            <div class="detail-row" style="margin-top: 0.25rem;">
                <button class="btn" onclick="generateMetadataOllama(${detail.id})" style="width: 100%;">🤖 AI Generate (Ollama)</button>
            </div>
            ${hasTags ? `
            <div class="detail-row" style="margin-top: 0.25rem;">
                <small style="color: var(--text-dim);">ℹ️ File already has tags. New tags will fill the form for review.</small>
            </div>
            ` : ''}
        </div>
 
        
        <div class="detail-section">
            <h4>🎵 Audio Information</h4>
            <div class="detail-row">
                <span class="detail-label">Title</span>
                <span class="detail-value">${esc(detail.title)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Artist</span>
                <span class="detail-value">${esc(detail.artist)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Album</span>
                <span class="detail-value">${esc(detail.album)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Track #</span>
                <span class="detail-value">${detail.track_number || '-'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Year</span>
                <span class="detail-value">${detail.year || '-'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Duration</span>
                <span class="detail-value">${detail.duration || '-'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Bitrate</span>
                <span class="detail-value">${detail.bitrate || '-'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Sample Rate</span>
                <span class="detail-value">${detail.sample_rate || '-'}</span>
            </div>
        </div>
        
        <div class="detail-section" style="grid-column: 1 / -1;">
            <h4>📍 File Location</h4>
            <div class="detail-row">
                <span class="detail-label">Current Path</span>
                <span class="detail-value" title="${esc(detail.filepath)}">${esc(detail.filepath)}</span>
            </div>
            ${detail.original_filepath ? `
            <div class="detail-row">
                <span class="detail-label">Original Path</span>
                <span class="detail-value" title="${esc(detail.original_filepath)}">${esc(detail.original_filepath)}</span>
            </div>
            <div class="path-move" style="margin-top: 0.5rem;">
                <div class="path-move-item">
                    <span class="path-move-icon">📂</span>
                    <span class="detail-label">From:</span>
                    <span class="detail-value" title="${esc(detail.original_filepath)}" style="flex:1;">${esc(detail.original_filepath)}</span>
                </div>
                <div class="path-move-item">
                    <span class="path-move-icon">⬇️</span>
                </div>
                <div class="path-move-item">
                    <span class="path-move-icon">📁</span>
                    <span class="detail-label">To:</span>
                    <span class="detail-value" title="${esc(detail.filepath)}" style="flex:1;">${esc(detail.filepath)}</span>
                </div>
            </div>
            ` : ''}
        </div>
        
        <div class="detail-section" style="grid-column: 1 / -1;">
            <h4>📅 Timestamps</h4>
            <div class="detail-row">
                <span class="detail-label">Created</span>
                <span class="detail-value">${new Date(detail.created_at).toLocaleString()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Updated</span>
                <span class="detail-value">${new Date(detail.updated_at).toLocaleString()}</span>
            </div>
        </div>
        
        <div class="detail-section" style="grid-column: 1 / -1;">
            <h4>🏷️ Edit Tags</h4>
            <form id="detail-tag-form" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem;">
                <div>
                    <label>Artist</label>
                    <input type="text" id="detail-tag-artist" value="${esc(detail.artist)}">
                </div>
                <div>
                    <label>Album</label>
                    <input type="text" id="detail-tag-album" value="${esc(detail.album)}">
                </div>
                <div>
                    <label>Title</label>
                    <input type="text" id="detail-tag-title" value="${esc(detail.title)}">
                </div>
                <div>
                    <label>Track #</label>
                    <input type="number" id="detail-tag-track" value="${detail.track_number || 0}">
                </div>
                <div>
                    <label>Year</label>
                    <input type="text" id="detail-tag-year" value="${esc(detail.year)}">
                </div>
                <div>
                    <label>Medium Format</label>
                    <input type="text" id="detail-tag-format" value="${esc(detail.medium_format)}">
                </div>
                <div>
                    <label>Medium #</label>
                    <input type="number" id="detail-tag-medium" value="${detail.medium_number || 1}">
                </div>
                <div style="display: flex; align-items: flex-end;">
                    <button type="submit" class="btn primary" style="width: 100%;">💾 Save Tags</button>
                </div>
            </form>
        </div>
    `;
    
    // Add form submit handler
    const form = fileDetailContent.querySelector('#detail-tag-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveDetailTags(detail.id);
    });
}

async function saveDetailTags(fileId) {
    const tags = {
        artist: document.getElementById('detail-tag-artist').value,
        album: document.getElementById('detail-tag-album').value,
        title: document.getElementById('detail-tag-title').value,
        track_number: parseInt(document.getElementById('detail-tag-track').value) || 0,
        year: document.getElementById('detail-tag-year').value,
        medium_format: document.getElementById('detail-tag-format').value,
        medium_number: parseInt(document.getElementById('detail-tag-medium').value) || 1,
    };
    
    try {
        const result = await api('PUT', `/api/files/${fileId}/tags`, tags);
        toast('Tags saved', 'success');
        // Refresh detail view
        renderFileDetail(result);
        // Refresh file list
        loadFiles();
    } catch (e) {
        toast('Save failed: ' + e.message, 'error');
    }
}

window.moveFileBack = async function(fileId) {
    if (!confirm('Move this file back to its original location?')) return;
    
    try {
        const result = await api('POST', `/api/files/${fileId}/move-back`);
        toast(result.message, 'success');
        fileDetailModal.style.display = 'none';
        loadFiles();
    } catch (e) {
        toast('Move back failed: ' + e.message, 'error');
    }
};

// Parse Filename - fills tag form in modal, user decides to save
window.autoFillTags = async function(fileId) {
    currentFileId = fileId;

    try {
        const result = await api('POST', `/api/files/${fileId}/tags/auto-fill?preview=1`);
        if (result.status === 'ok') {
            fillTagForm(result.tags);
            highlightDetailForm();
            toast(`Parsed: ${result.tags.artist || ''} - ${result.tags.title || ''}`, 'success');
        } else if (result.status === 'no_data') {
            toast(result.message || 'Could not parse filename', 'error');
        } else if (result.status === 'skipped') {
            toast(result.message || 'Skipped', 'error');
        } else {
            toast(result.message || 'Could not extract tags', 'error');
        }
    } catch (e) {
        toast('Parse failed: ' + e.message, 'error');
    }
};

// Highlight detail tag form to attract attention
function highlightDetailForm() {
    const form = document.getElementById('detail-tag-form');
    if (form) {
        form.style.transition = 'background 0.3s';
        form.style.background = 'var(--bg-hover)';
        setTimeout(() => {
            form.style.background = '';
        }, 1500);
    }
}

// Fill tag form fields in modal with provided tags
function fillTagForm(tags) {
    if (tags.artist !== undefined) document.getElementById('detail-tag-artist').value = tags.artist || '';
    if (tags.album !== undefined) document.getElementById('detail-tag-album').value = tags.album || '';
    if (tags.title !== undefined) document.getElementById('detail-tag-title').value = tags.title || '';
    if (tags.track_number !== undefined) document.getElementById('detail-tag-track').value = tags.track_number || 0;
    if (tags.year !== undefined) document.getElementById('detail-tag-year').value = tags.year || '';
    if (tags.medium_format !== undefined) document.getElementById('detail-tag-format').value = tags.medium_format || '';
    if (tags.medium_number !== undefined) document.getElementById('detail-tag-medium').value = tags.medium_number || 1;
}

// Auto-Identify using AcoustID - fills tag form, user decides to save
window.identifyTrack = async function(fileId) {
    currentFileId = fileId;

    try {
        const result = await api('POST', `/api/files/${fileId}/identify?debug=1`);

        if (result.status === 'error') {
            toast(result.message || 'Auto-Identify failed', 'error');
            return;
        }
        if (result.status === 'identified' || result.status === 'parsed_from_filename') {
            const suggestedTags = result.suggested_tags || {};
            fillTagForm(suggestedTags);
            highlightDetailForm();
            toast(`Auto-Identify: ${suggestedTags.artist || ''} - ${suggestedTags.title || ''}`, 'success');
            if (result.debug_release_candidates) {
                console.log('AcoustID debug_release_candidates:', result.debug_release_candidates);
            }
        } else {
            toast(result.message || 'Could not identify track', 'error');
        }
    } catch (e) {
        toast('Auto-Identify failed: ' + e.message, 'error');
    }
};

function pickBestAlbumYear(candidates) {
    if (!Array.isArray(candidates) || !candidates.length) return { album: '', year: '' };
    const withYear = candidates.filter(x => x && x.year);
    if (withYear.length) {
        const sorted = withYear.sort((a, b) => {
            const ay = parseInt(String(a.year || ''), 10) || 0;
            const by = parseInt(String(b.year || ''), 10) || 0;
            return by - ay;
        });
        const best = sorted[0] || {};
        return { album: best.title || '', year: String(best.year || '').slice(0, 4) };
    }
    const withDate = candidates.filter(x => x && x.date);
    if (withDate.length) {
        const best = withDate.sort((a, b) => String(a.date || '').localeCompare(String(b.date || ''))).slice(-1)[0] || {};
        return { album: best.title || '', year: String(best.date || '').slice(0, 4) };
    }
    return { album: '', year: '' };
}

// Search MusicBrainz by current title+artist from detail form and fill tags.
window.searchMusicBrainzInModal = async function(fileId) {
    currentFileId = fileId;
    const title = (document.getElementById('detail-tag-title')?.value || '').trim();
    const artist = (document.getElementById('detail-tag-artist')?.value || '').trim();

    if (!title && !artist) {
        toast('Fill Title and/or Artist first', 'error');
        return;
    }

    try {
        const params = new URLSearchParams({ limit: '10' });
        if (title) params.set('title', title);
        if (artist) params.set('artist', artist);
        if (!title || !artist) params.set('query', `${artist} ${title}`.trim());

        const result = await api('POST', `/api/files/${fileId}/search?${params.toString()}`);
        const rows = result.results || [];
        if (!rows.length) {
            toast('MusicBrainz: nothing found', 'error');
            return;
        }

        const best = rows[0] || {};
        const relPick = pickBestAlbumYear(best.releases || []);
        const rgPick = (!relPick.album || !relPick.year) ? pickBestAlbumYear(best.release_groups || []) : { album: '', year: '' };

        fillTagForm({
            artist: best.artist || artist,
            title: best.title || title,
            album: relPick.album || rgPick.album || '',
            year: relPick.year || rgPick.year || '',
            track_number: best.track_number || 0,
        });
        highlightDetailForm();
        toast(`MusicBrainz: ${best.artist || ''} - ${best.title || ''}`, 'success');
    } catch (e) {
        toast('MusicBrainz search failed: ' + e.message, 'error');
    }
};

// Close file detail modal
fileDetailModal?.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
        fileDetailModal.style.display = 'none';
    });
});

// Close modal on outside click
fileDetailModal?.addEventListener('click', (e) => {
    if (e.target === fileDetailModal) {
        fileDetailModal.style.display = 'none';
    }
});

// AI Generate (Ollama) - fills tag form, user decides to save
window.generateMetadataOllama = async function(fileId) {
    currentFileId = fileId;
    setOllamaBusyHint('Recognizing title and artist via Ollama');

    try {
        const result = await api('POST', `/api/files/${fileId}/generate-metadata`);

        if (result.status === 'ok') {
            const suggestedTags = result.suggested_tags || {};
            fillTagForm(suggestedTags);
            highlightDetailForm();
            toast(`AI: ${suggestedTags.artist || ''} - ${suggestedTags.title || ''}`, 'success');
        } else {
            toast(result.message || 'Could not generate metadata', 'error');
        }
    } catch (e) {
        toast('AI Generate failed: ' + e.message, 'error');
    } finally {
        clearOllamaBusyHint();
    }
};
