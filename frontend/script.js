const API_BASE_URL = 'http://127.0.0.1:8000';

let elements = {};
let selectedFile = null;
let downloadUrl = null;
let urlDownloadUrl = null;
let audioDirHandle = null;
let spotifyDirHandle = null;
let spotifyEpisodeTitle = null;

function sanitizeFilename(name) {
    return name
        .replace(/[<>:"/\\|?*;@!'[\]{}()]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('[init] DOMContentLoaded fired');

    elements = {
        // Tabs
        audioTab: document.getElementById('audioTab'),
        spotifyTab: document.getElementById('spotifyTab'),
        audioContent: document.getElementById('audioContent'),
        spotifyContent: document.getElementById('spotifyContent'),

        // Audio upload
        languageSelect: document.getElementById('language'),
        folderBtn: document.getElementById('folderBtn'),
        folderName: document.getElementById('folderName'),
        uploadArea: document.getElementById('uploadArea'),
        audioFile: document.getElementById('audioFile'),
        fileInfo: document.getElementById('fileInfo'),
        fileName: document.getElementById('fileName'),
        fileSize: document.getElementById('fileSize'),
        fileDuration: document.getElementById('fileDuration'),
        removeFile: document.getElementById('removeFile'),
        transcribeBtn: document.getElementById('transcribeBtn'),
        progressSection: document.getElementById('progressSection'),
        resultsSection: document.getElementById('resultsSection'),
        errorSection: document.getElementById('errorSection'),
        progressFill: document.getElementById('progressFill'),
        progressText: document.getElementById('progressText'),
        resultDuration: document.getElementById('resultDuration'),
        resultLanguage: document.getElementById('resultLanguage'),
        resultSegments: document.getElementById('resultSegments'),
        downloadBtn: document.getElementById('downloadBtn'),
        newTranscriptionBtn: document.getElementById('newTranscriptionBtn'),
        errorMessage: document.getElementById('errorMessage'),
        retryBtn: document.getElementById('retryBtn'),

        // Spotify URL
        urlLanguageSelect: document.getElementById('urlLanguage'),
        urlFolderBtn: document.getElementById('urlFolderBtn'),
        urlFolderName: document.getElementById('urlFolderName'),
        spotifyUrl: document.getElementById('spotifyUrl'),
        transcribeUrlBtn: document.getElementById('transcribeUrlBtn'),
        urlProgressSection: document.getElementById('urlProgressSection'),
        urlResultsSection: document.getElementById('urlResultsSection'),
        urlErrorSection: document.getElementById('urlErrorSection'),
        urlProgressFill: document.getElementById('urlProgressFill'),
        urlProgressText: document.getElementById('urlProgressText'),
        urlResultDuration: document.getElementById('urlResultDuration'),
        urlResultLanguage: document.getElementById('urlResultLanguage'),
        urlResultSegments: document.getElementById('urlResultSegments'),
        urlDownloadBtn: document.getElementById('urlDownloadBtn'),
        urlNewBtn: document.getElementById('urlNewBtn'),
        urlErrorMessage: document.getElementById('urlErrorMessage'),
        urlRetryBtn: document.getElementById('urlRetryBtn'),
    };

    // Verify critical elements
    const missing = Object.entries(elements).filter(([k, v]) => !v).map(([k]) => k);
    if (missing.length > 0) {
        console.error('[init] Missing DOM elements:', missing);
    } else {
        console.log('[init] All DOM elements found');
    }

    initializeEventListeners();
    checkAPIConnection();
});

function initializeEventListeners() {
    // Tabs
    elements.audioTab.addEventListener('click', () => switchTab('audio'));
    elements.spotifyTab.addEventListener('click', () => switchTab('spotify'));

    // Audio upload
    elements.languageSelect.addEventListener('change', updateTranscribeButton);
    elements.uploadArea.addEventListener('click', () => elements.audioFile.click());
    elements.uploadArea.addEventListener('dragover', handleDragOver);
    elements.uploadArea.addEventListener('dragleave', handleDragLeave);
    elements.uploadArea.addEventListener('drop', handleDrop);
    elements.audioFile.addEventListener('change', handleFileSelect);
    elements.removeFile.addEventListener('click', removeSelectedFile);
    elements.transcribeBtn.addEventListener('click', startTranscription);
    elements.downloadBtn.addEventListener('click', () => downloadFile(downloadUrl, 'audio'));
    elements.newTranscriptionBtn.addEventListener('click', resetAudioTab);
    elements.retryBtn.addEventListener('click', () => hideAllSections('audio'));

    // Spotify URL
    elements.urlLanguageSelect.addEventListener('change', updateUrlButton);
    elements.spotifyUrl.addEventListener('input', updateUrlButton);
    elements.transcribeUrlBtn.addEventListener('click', startUrlTranscription);
    elements.urlDownloadBtn.addEventListener('click', () => downloadFile(urlDownloadUrl, 'spotify'));
    elements.urlNewBtn.addEventListener('click', resetSpotifyTab);
    elements.urlRetryBtn.addEventListener('click', () => hideAllSections('spotify'));

    // Folder pickers
    elements.folderBtn.addEventListener('click', () => pickFolder('audio'));
    elements.urlFolderBtn.addEventListener('click', () => pickFolder('spotify'));

    console.log('[init] Event listeners attached');
}

async function pickFolder(tab) {
    try {
        let suggestedName = 'transcription.md';
        if (tab === 'audio' && selectedFile) {
            const base = selectedFile.name.replace(/\.[^.]+$/, '');
            suggestedName = sanitizeFilename(base) + '.md';
        } else if (tab === 'spotify' && spotifyEpisodeTitle) {
            suggestedName = sanitizeFilename(spotifyEpisodeTitle) + '.md';
        }

        const handle = await window.showSaveFilePicker({
            suggestedName,
            types: [{ description: 'Markdown', accept: { 'text/markdown': ['.md'] } }],
        });

        if (tab === 'audio') {
            audioDirHandle = handle;
            elements.folderName.textContent = handle.name;
            elements.folderBtn.textContent = 'Cambiar destino';
        } else {
            spotifyDirHandle = handle;
            elements.urlFolderName.textContent = handle.name;
            elements.urlFolderBtn.textContent = 'Cambiar destino';
        }
        tab === 'audio' ? updateTranscribeButton() : updateUrlButton();
    } catch (err) {
        if (err.name !== 'AbortError') console.error('[folder]', err);
    }
}

async function checkAPIConnection() {
    try {
        const response = await fetch(`${API_BASE_URL}/`);
        if (!response.ok) throw new Error('API no disponible');
        const data = await response.json();
        console.log('[api] Connected:', data);
    } catch (error) {
        console.error('[api] Connection failed:', error);
        showError('audio', 'No se puede conectar con el servidor. Asegurate de que el backend este ejecutandose en http://127.0.0.1:8000');
    }
}

// --- Simulated progress timer ---
// The backend processes everything in one request, so we simulate
// progress steps while waiting for the response to keep the UI alive.

let progressTimer = null;

function startProgressSimulation(tab, steps) {
    let currentStep = 0;
    const prefix = tab === 'audio' ? 'step' : 'urlStep';

    // Show first step immediately
    updateProgress(tab, steps[0].pct, steps[0].text);
    updateStep(prefix, steps[0].step, 'active');
    console.log(`[progress] ${tab} step ${steps[0].step}: ${steps[0].text}`);

    currentStep = 1;

    progressTimer = setInterval(() => {
        if (currentStep >= steps.length) {
            // All steps shown — keep last step active, pulse the bar
            updateProgress(tab, 85, 'Procesando, por favor espera...');
            return;
        }

        const prev = steps[currentStep - 1];
        const curr = steps[currentStep];

        updateStep(prefix, prev.step, 'completed');
        updateStep(prefix, curr.step, 'active');
        updateProgress(tab, curr.pct, curr.text);
        console.log(`[progress] ${tab} step ${curr.step}: ${curr.text}`);

        currentStep++;
    }, steps[0].delay || 3000);
}

function stopProgressSimulation() {
    if (progressTimer) {
        clearInterval(progressTimer);
        progressTimer = null;
    }
}

function completeProgress(tab) {
    stopProgressSimulation();
    const prefix = tab === 'audio' ? 'step' : 'urlStep';
    for (let i = 1; i <= 4; i++) updateStep(prefix, i, 'completed');
    updateProgress(tab, 100, 'Completado');
    console.log(`[progress] ${tab} completed`);
}

// --- Tab switching ---

function switchTab(tab) {
    document.querySelectorAll('.nav-tab').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    if (tab === 'audio') {
        elements.audioTab.classList.add('active');
        elements.audioContent.classList.add('active');
    } else {
        elements.spotifyTab.classList.add('active');
        elements.spotifyContent.classList.add('active');
    }
    console.log(`[tab] Switched to: ${tab}`);
}

// --- Audio file upload ---

function handleDragOver(e) {
    e.preventDefault();
    elements.uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    elements.uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    elements.uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFileSelection(e.dataTransfer.files[0]);
    }
}

function handleFileSelect(e) {
    if (e.target.files[0]) handleFileSelection(e.target.files[0]);
}

async function handleFileSelection(file) {
    console.log(`[file] Selected: ${file.name}, type: ${file.type}, size: ${file.size}`);

    if (!file.type.startsWith('audio/')) {
        showError('audio', 'Selecciona un archivo de audio valido.');
        return;
    }

    if (file.size > 100 * 1024 * 1024) {
        showError('audio', 'El archivo es demasiado grande. Maximo 100MB.');
        return;
    }

    selectedFile = file;
    elements.fileName.textContent = file.name;
    elements.fileSize.textContent = formatFileSize(file.size);

    try {
        const duration = await getAudioDuration(file);
        console.log(`[file] Duration: ${duration}s`);
        elements.fileDuration.textContent = formatDuration(duration);
        if (duration > 1800) {
            showError('audio', 'El audio debe durar menos de 30 minutos.');
            removeSelectedFile();
            return;
        }
    } catch (err) {
        console.warn('[file] Could not get duration:', err);
        elements.fileDuration.textContent = 'Duracion no disponible';
    }

    elements.uploadArea.style.display = 'none';
    elements.fileInfo.style.display = 'flex';
    updateTranscribeButton();
}

function getAudioDuration(file) {
    return new Promise((resolve, reject) => {
        const audio = document.createElement('audio');
        audio.preload = 'metadata';
        audio.onloadedmetadata = function() {
            URL.revokeObjectURL(audio.src);
            resolve(audio.duration);
        };
        audio.onerror = () => reject(new Error('No se pudo obtener duracion'));
        audio.src = URL.createObjectURL(file);
    });
}

function removeSelectedFile() {
    selectedFile = null;
    elements.audioFile.value = '';
    elements.uploadArea.style.display = 'block';
    elements.fileInfo.style.display = 'none';
    updateTranscribeButton();
}

function updateTranscribeButton() {
    const enabled = !!(selectedFile && elements.languageSelect.value && audioDirHandle);
    elements.transcribeBtn.disabled = !enabled;
    console.log(`[audio] Button enabled: ${enabled}`);
}

async function startTranscription() {
    if (!selectedFile || !elements.languageSelect.value) return;

    console.log('[audio] Starting transcription...');
    console.log(`[audio] File: ${selectedFile.name}, Lang: ${elements.languageSelect.value}`);

    hideAllSections('audio');
    elements.progressSection.style.display = 'block';

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('language', elements.languageSelect.value);

    // Start simulated progress — steps advance every 5s while waiting
    startProgressSimulation('audio', [
        { step: 1, pct: 5,  text: 'Subiendo archivo...', delay: 5000 },
        { step: 2, pct: 25, text: 'Procesando audio...' },
        { step: 3, pct: 50, text: 'Transcribiendo con Whisper...' },
        { step: 4, pct: 75, text: 'Generando transcripcion...' },
    ]);

    try {
        console.log('[audio] Sending POST /transcribe...');
        const response = await fetch(`${API_BASE_URL}/transcribe`, {
            method: 'POST',
            body: formData
        });

        console.log(`[audio] Response status: ${response.status}`);

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Error en la transcripcion');
        }

        const result = await response.json();
        console.log('[audio] Result:', JSON.stringify(result));

        stopProgressSimulation();
        console.log('[audio] Showing results...');
        showResults('audio', result);
        console.log('[audio] Results displayed');

    } catch (error) {
        console.error('[audio] Error:', error);
        stopProgressSimulation();
        showError('audio', error.message || 'Error inesperado');
    }
}

// --- Spotify URL ---

let _resolveTimer = null;
let _lastResolvedUrl = null;

function updateUrlButton() {
    const url = elements.spotifyUrl.value.trim();
    const hasUrl = url.includes('open.spotify.com/episode');
    const hasLang = elements.urlLanguageSelect.value !== '';
    const hasFolder = !!spotifyDirHandle;
    elements.transcribeUrlBtn.disabled = !(hasUrl && hasLang && hasFolder);
    console.log(`[spotify] Button enabled: ${hasUrl && hasLang && hasFolder}`);

    if (!hasUrl) {
        spotifyEpisodeTitle = null;
        _lastResolvedUrl = null;
        return;
    }

    if (url === _lastResolvedUrl) return;

    clearTimeout(_resolveTimer);
    _resolveTimer = setTimeout(async () => {
        if (url !== elements.spotifyUrl.value.trim()) return;
        try {
            const resp = await fetch(`${API_BASE_URL}/resolve?url=${encodeURIComponent(url)}`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.title) {
                spotifyEpisodeTitle = data.title;
                _lastResolvedUrl = url;
                console.log(`[resolve] Episode title: ${spotifyEpisodeTitle}`);
            }
        } catch (e) {
            console.warn('[resolve] Failed:', e);
        }
    }, 600);
}

const STATUS_STEP = {
    resolving:    { step: 1, text: 'Resolviendo episodio...' },
    downloading:  { step: 2, text: 'Descargando audio...' },
    transcribing: { step: 3, text: 'Transcribiendo con Whisper...' },
    done:         { step: 4, text: 'Completado' },
};

let _pollTimer = null;

function stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function startUrlTranscription() {
    const url = elements.spotifyUrl.value.trim();
    const language = elements.urlLanguageSelect.value;

    if (!url || !language) return;

    if (!url.includes('open.spotify.com/episode')) {
        showError('spotify', 'URL invalida. Debe ser un enlace de episodio de Spotify.');
        return;
    }

    console.log(`[spotify] Starting transcription for: ${url}`);

    stopPolling();
    stopProgressSimulation();
    hideAllSections('spotify');
    elements.urlProgressSection.style.display = 'block';
    for (let i = 1; i <= 4; i++) updateStep('urlStep', i, '');
    updateProgress('spotify', 2, 'Iniciando...');

    const formData = new FormData();
    formData.append('url', url);
    formData.append('language', language);

    let jobId;
    try {
        const response = await fetch(`${API_BASE_URL}/transcribe-url`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Error iniciando trabajo');
        }
        const data = await response.json();
        jobId = data.job_id;
        console.log(`[spotify] Job created: ${jobId}`);
    } catch (error) {
        showError('spotify', error.message || 'Error iniciando transcripcion');
        return;
    }

    // Poll /jobs/{jobId} every 2s for real progress
    _pollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
            if (!resp.ok) return;
            const job = await resp.json();

            console.log(`[spotify] Job ${jobId}: status=${job.status} progress=${job.progress} msg=${job.message}`);

            const info = STATUS_STEP[job.status];
            if (info) {
                updateStep('urlStep', info.step, 'active');
                // Mark previous steps completed
                for (let s = 1; s < info.step; s++) updateStep('urlStep', s, 'completed');
            }
            updateProgress('spotify', job.progress, job.message);

            if (job.status === 'done') {
                stopPolling();
                completeProgress('spotify');
                showResults('spotify', job.result);
            } else if (job.status === 'error') {
                stopPolling();
                showError('spotify', job.error || 'Error en la transcripcion');
            }
        } catch (err) {
            console.error('[spotify] Poll error:', err);
        }
    }, 2000);
}

// --- Shared UI functions ---

function updateProgress(tab, percentage, text) {
    if (tab === 'audio') {
        elements.progressFill.style.width = `${percentage}%`;
        elements.progressText.textContent = text;
    } else {
        elements.urlProgressFill.style.width = `${percentage}%`;
        elements.urlProgressText.textContent = text;
    }
}

function updateStep(prefix, num, status) {
    const step = document.getElementById(`${prefix}${num}`);
    if (step) step.className = `step ${status}`;
}

function showResults(tab, result) {
    console.log(`[results] showResults called for ${tab}`);

    try {
        hideAllSections(tab);

        if (tab === 'audio') {
            elements.resultsSection.style.display = 'block';
            elements.resultDuration.textContent = `${result.duration} segundos`;
            elements.resultLanguage.textContent = getLanguageDisplay(result.language);
            elements.resultSegments.textContent = `${result.original_segments_count} segmentos`;
            downloadUrl = `${API_BASE_URL}${result.download_url}`;
        } else {
            elements.urlResultsSection.style.display = 'block';
            elements.urlResultDuration.textContent = `${result.duration} segundos`;
            elements.urlResultLanguage.textContent = getLanguageDisplay(result.language);
            elements.urlResultSegments.textContent = `${result.original_segments_count} segmentos`;
            urlDownloadUrl = `${API_BASE_URL}${result.download_url}`;
        }

        console.log(`[results] ${tab} — duration: ${result.duration}s, segments: ${result.original_segments_count}, url: ${result.download_url}`);
    } catch (err) {
        console.error('[results] Error in showResults:', err);
        showError(tab, 'Transcripcion completada pero hubo un error mostrando resultados. Revisa la consola.');
    }
}

function showError(tab, message) {
    hideAllSections(tab);
    if (tab === 'audio') {
        elements.errorSection.style.display = 'block';
        elements.errorMessage.textContent = message;
    } else {
        elements.urlErrorSection.style.display = 'block';
        elements.urlErrorMessage.textContent = message;
    }
    console.error(`[error] ${tab}: ${message}`);
}

function hideAllSections(tab) {
    if (tab === 'audio') {
        elements.progressSection.style.display = 'none';
        elements.resultsSection.style.display = 'none';
        elements.errorSection.style.display = 'none';
    } else {
        elements.urlProgressSection.style.display = 'none';
        elements.urlResultsSection.style.display = 'none';
        elements.urlErrorSection.style.display = 'none';
    }
}

function resetAudioTab() {
    removeSelectedFile();
    elements.languageSelect.value = '';
    hideAllSections('audio');
    downloadUrl = null;
    audioDirHandle = null;
    elements.folderName.textContent = 'Sin seleccionar';
    elements.folderBtn.textContent = 'Seleccionar carpeta';
    stopPolling();
    stopProgressSimulation();
    for (let i = 1; i <= 4; i++) updateStep('step', i, '');
    updateProgress('audio', 0, '');
}

function resetSpotifyTab() {
    elements.spotifyUrl.value = '';
    elements.urlLanguageSelect.value = '';
    hideAllSections('spotify');
    urlDownloadUrl = null;
    spotifyDirHandle = null;
    elements.urlFolderName.textContent = 'Sin seleccionar';
    elements.urlFolderBtn.textContent = 'Seleccionar carpeta';
    stopPolling();
    stopProgressSimulation();
    for (let i = 1; i <= 4; i++) updateStep('urlStep', i, '');
    updateProgress('spotify', 0, '');
    updateUrlButton();
}

async function downloadFile(url, tab) {
    if (!url) return;
    console.log(`[download] ${url}`);

    const fileHandle = tab === 'audio' ? audioDirHandle : spotifyDirHandle;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Error obteniendo archivo');
        const content = await response.text();

        if (fileHandle) {
            const writable = await fileHandle.createWritable();
            await writable.write(content);
            await writable.close();
            console.log(`[download] Guardado en ${fileHandle.name}`);
            showToast({ title: 'Archivo guardado', desc: fileHandle.name, type: 'success' });
        } else {
            const blob = new Blob([content], { type: 'text/markdown' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            const filename = url.split('/').pop() || `transcription_${Date.now()}.md`;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
            showToast({ title: 'Descarga iniciada', desc: filename, type: 'success' });
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error('[download] Error:', err);
            showToast({ title: 'Error al guardar', desc: err.message, type: 'error' });
        }
    }
}

// --- Toast ---

function showToast({ title, desc = '', type = 'success' }) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✓' : '✕';
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-body">
            <span class="toast-title">${title}</span>
            ${desc ? `<span class="toast-desc">${desc}</span>` : ''}
        </div>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3400);
}

// --- Utilities ---

function getLanguageDisplay(language) {
    const map = { 'spanish': 'Espanol', 'english': 'English' };
    return map[language] || language;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

window.addEventListener('error', e => console.error('[global error]', e.error));
window.addEventListener('unhandledrejection', e => console.error('[unhandled rejection]', e.reason));
