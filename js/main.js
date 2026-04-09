let isKR = false;

function toggleLanguage() {
    isKR = !isKR;
    document.body.classList.toggle('lang-kr', isKR);
    const langBtn = document.getElementById('langBtn');
    if (langBtn) {
        langBtn.innerText = isKR ? "한국어 | English" : "English | 한국어";
    }
}

// SOS Modal
function openSOS() {
    document.getElementById('sosModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeSOS(e) {
    if (e && e.target !== e.currentTarget) return;
    document.getElementById('sosModal').classList.remove('active');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSOS();
});

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sos-btn').forEach(btn => {
        btn.addEventListener('click', openSOS);
    });
});

// PWA
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('sw.js');
    });
}

let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const installBanner = document.getElementById('installBanner');
    if (installBanner) {
        installBanner.style.display = 'block';
    }
});

function installApp() {
    const installBanner = document.getElementById('installBanner');
    if (installBanner) {
        installBanner.style.display = 'none';
    }
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((result) => {
            deferredPrompt = null;
        });
    }
}
