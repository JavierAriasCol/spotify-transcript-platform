const API_BASE_URL = 'http://127.0.0.1:8000';

let elements = {};
let selectedFile = null;
let downloadUrl = null;
let urlDownloadUrl = null;

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
        cleanTranscription: document.getElementById('cleanTranscription'),
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
        urlCleanTranscription: document.getElementById('urlCleanTranscription'),
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
    elements.downloadBtn.addEventListener('click', () => downloadFile(downloadUrl));
    elements.newTranscriptionBtn.addEventListener('click', resetAudioTab);
    elements.retryBtn.addEventListener('click', () => hideAllSections('audio'));

    // Spotify URL
    elements.urlLanguageSelect.addEventListener('change', updateUrlButton);
    elements.spotifyUrl.addEventListener('input', updateUrlButton);
    elements.transcribeUrlBtn.addEventListener('click', startUrlTranscription);
    elements.urlDownloadBtn.addEventListener('click', () => downloadFile(urlDownloadUrl));
    elements.urlNewBtn.addEventListener('click', resetSpotifyTab);
    elements.urlRetryBtn.addEventListener('click', () => hideAllSections('spotify'));

    console.log('[init] Event listeners attached');
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
    const enabled = !!(selectedFile && elements.languageSelect.value);
    elements.transcribeBtn.disabled = !enabled;
    console.log(`[audio] Button enabled: ${enabled}`);
}

async function startTranscription() {
    if (!selectedFile || !elements.languageSelect.value) return;

    console.log('[audio] Starting transcription...');
    console.log(`[audio] File: ${selectedFile.name}, Lang: ${elements.languageSelect.value}, Clean: ${elements.cleanTranscription.checked}`);

    hideAllSections('audio');
    elements.progressSection.style.display = 'block';

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('language', elements.languageSelect.value);
    formData.append('transcription_type', elements.cleanTranscription.checked ? 'clean' : 'vtt');

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

function updateUrlButton() {
    const url = elements.spotifyUrl.value;
    const hasUrl = url.includes('open.spotify.com/episode');
    const hasLang = elements.urlLanguageSelect.value !== '';
    elements.transcribeUrlBtn.disabled = !(hasUrl && hasLang);
    console.log(`[spotify] Button enabled: ${hasUrl && hasLang} (url valid: ${hasUrl}, lang: ${hasLang})`);
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
    console.log(`[spotify] Lang: ${language}, Clean: ${elements.urlCleanTranscription.checked}`);

    hideAllSections('spotify');
    elements.urlProgressSection.style.display = 'block';

    const formData = new FormData();
    formData.append('url', url);
    formData.append('language', language);
    formData.append('transcription_type', elements.urlCleanTranscription.checked ? 'clean' : 'vtt');

    // Start simulated progress — Spotify takes longer (download + transcribe)
    // Steps advance every 15s for longer episodes
    startProgressSimulation('spotify', [
        { step: 1, pct: 5,  text: 'Descargando podcast de Spotify...', delay: 15000 },
        { step: 2, pct: 25, text: 'Procesando audio...' },
        { step: 3, pct: 50, text: 'Transcribiendo con Whisper...' },
        { step: 4, pct: 75, text: 'Generando transcripcion...' },
    ]);

    try {
        console.log('[spotify] Sending POST /transcribe-url...');
        const response = await fetch(`${API_BASE_URL}/transcribe-url`, {
            method: 'POST',
            body: formData
        });

        console.log(`[spotify] Response status: ${response.status}`);

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Error en la transcripcion');
        }

        const result = await response.json();
        console.log('[spotify] Result:', JSON.stringify(result));

        stopProgressSimulation();
        console.log('[spotify] Showing results...');
        showResults('spotify', result);
        console.log('[spotify] Results displayed');

    } catch (error) {
        console.error('[spotify] Error:', error);
        stopProgressSimulation();
        showError('spotify', error.message || 'Error inesperado');
    }
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

        const isClean = result.transcription_type === 'clean';
        const btnText = isClean ? 'Descargar TXT' : 'Descargar VTT';

        if (tab === 'audio') {
            elements.resultsSection.style.display = 'block';
            elements.resultDuration.textContent = `${result.duration} segundos`;
            elements.resultLanguage.textContent = getLanguageDisplay(result.language);
            elements.resultSegments.textContent = `${result.original_segments_count} segmentos`;
            elements.downloadBtn.textContent = btnText;
            downloadUrl = `${API_BASE_URL}${result.download_url}`;
        } else {
            console.log('[results] urlResultsSection element:', elements.urlResultsSection);
            elements.urlResultsSection.style.display = 'block';
            elements.urlResultDuration.textContent = `${result.duration} segundos`;
            elements.urlResultLanguage.textContent = getLanguageDisplay(result.language);
            elements.urlResultSegments.textContent = `${result.original_segments_count} segmentos`;
            elements.urlDownloadBtn.textContent = btnText;
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
    elements.cleanTranscription.checked = false;
    hideAllSections('audio');
    downloadUrl = null;
    stopProgressSimulation();
    for (let i = 1; i <= 4; i++) updateStep('step', i, '');
    updateProgress('audio', 0, '');
}

function resetSpotifyTab() {
    elements.spotifyUrl.value = '';
    elements.urlLanguageSelect.value = '';
    elements.urlCleanTranscription.checked = false;
    hideAllSections('spotify');
    urlDownloadUrl = null;
    stopProgressSimulation();
    for (let i = 1; i <= 4; i++) updateStep('urlStep', i, '');
    updateProgress('spotify', 0, '');
    updateUrlButton();
}

function downloadFile(url) {
    if (!url) return;
    console.log(`[download] ${url}`);
    const link = document.createElement('a');
    link.href = url;
    const ext = url.includes('.txt') ? '.txt' : '.vtt';
    link.download = `transcription_${Date.now()}${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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
