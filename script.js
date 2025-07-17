// Get DOM elements for splash screen
const splashScreen = document.getElementById('splashScreen');
const goToProjectBtn = document.getElementById('goToProjectBtn');
const appContainer = document.getElementById('appContainer');

// Get DOM elements for main app
const fileInput = document.getElementById('fileInput');
const urlInputGroup = document.getElementById('urlInputGroup');
const urlInput = document.getElementById('urlInput');
const urlCheckbox = document.getElementById('urlCheckbox');
const processBtn = document.getElementById('processBtn');
const videoOutput = document.getElementById('videoOutput');
const videoMessage = document.getElementById('videoMessage');
const transcriptOutput = document.getElementById('transcriptOutput');
const loadingIndicator = document.getElementById('loadingIndicator');
const statusMessage = document.getElementById('statusMessage');

// Function to hide splash screen and show main app
function showMainApp() {
    splashScreen.classList.remove('active'); // Start fading out splash screen
    setTimeout(() => {
        splashScreen.classList.add('hidden'); // Fully hide after transition
        appContainer.classList.remove('hidden'); // Make app container visible
        setTimeout(() => {
            appContainer.classList.add('opacity-100'); // Fade in app container
        }, 50); // Small delay to allow 'hidden' class removal to register
    }, 500); // Match transition duration in CSS
}

// Event listener for "Go to Project" button
goToProjectBtn.addEventListener('click', showMainApp);

// Function to toggle input visibility based on checkbox (already existing)
function toggleInputVisibility() {
    if (urlCheckbox.checked) {
        fileInput.closest('.input-group').classList.add('hidden');
        urlInputGroup.classList.remove('hidden');
    } else {
        fileInput.closest('.input-group').classList.remove('hidden');
        urlInputGroup.classList.add('hidden');
    }
    // Clear inputs and outputs when switching modes
    fileInput.value = '';
    urlInput.value = '';
    videoOutput.src = '';
    videoMessage.classList.add('hidden');
    transcriptOutput.value = '';
    hideStatusMessage();
}

// Event listener for checkbox change (already existing)
urlCheckbox.addEventListener('change', toggleInputVisibility);

// Initialize input visibility on page load (ensure correct initial state)
// This will run only after the main app is visible
document.addEventListener('DOMContentLoaded', toggleInputVisibility);


// Function to display status messages (error or success) (already existing)
function showStatusMessage(message, type = 'error') {
    statusMessage.textContent = message;
    statusMessage.className = `status-message show ${type}`;
    statusMessage.classList.remove('hidden');
}

// Function to hide status messages (already existing)
function hideStatusMessage() {
    statusMessage.classList.add('hidden');
    statusMessage.classList.remove('show', 'error', 'success');
    statusMessage.textContent = '';
}

// Event listener for the process button click (already existing)
processBtn.addEventListener('click', async () => {
    hideStatusMessage();
    loadingIndicator.classList.remove('hidden');
    processBtn.disabled = true;
    videoOutput.src = '';
    videoMessage.classList.add('hidden');
    transcriptOutput.value = '';

    const isUrl = urlCheckbox.checked;
    const formData = new FormData();
    formData.append('is_url', isUrl);

    let mediaSource = null;

    if (isUrl) {
        mediaSource = urlInput.value.trim();
        if (!mediaSource) {
            showStatusMessage("Please enter a URL.", 'error');
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;
            return;
        }
        if (!mediaSource.startsWith('http://') && !mediaSource.startsWith('https://')) {
            showStatusMessage("Please enter a valid URL starting with http:// or https://", 'error');
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;
            return;
        }
        formData.append('url_input', mediaSource);
    } else {
        if (fileInput.files.length === 0) {
            showStatusMessage("Please upload a file.", 'error');
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;
            return;
        }
        mediaSource = fileInput.files[0];
        formData.append('file_input', mediaSource);
    }

    try {
        const response = await fetch('/api/process-media', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Server responded with status ${response.status}`);
        }

        const data = await response.json();

        if (data.video_path) {
            videoOutput.src = data.video_path;
            videoOutput.load();
            videoMessage.classList.remove('hidden');
            videoMessage.textContent = "Media loaded. Click play to watch.";
        } else {
            videoOutput.src = '';
            videoMessage.classList.remove('hidden');
            videoMessage.textContent = "No direct video stream could be loaded for this media. Transcription is still available.";
        }

        if (data.transcript) {
            transcriptOutput.value = data.transcript;
        } else {
            transcriptOutput.value = 'No transcription available.';
        }
        showStatusMessage("Processing complete!", 'success');

    } catch (error) {
        console.error('Error processing media:', error);
        showStatusMessage(`Error: ${error.message}`, 'error');
        transcriptOutput.value = 'Failed to transcribe media.';
        videoOutput.src = '';
        videoMessage.classList.add('hidden');
    } finally {
        loadingIndicator.classList.add('hidden');
        processBtn.disabled = false;
    }
});