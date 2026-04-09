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

// Mobile Menu
function toggleMenu() {
    const btn = document.querySelector('.mobile-menu-btn');
    const links = document.querySelector('.nav-links');
    btn.classList.toggle('active');
    links.classList.toggle('open');
}

// Scroll Animations
document.addEventListener('DOMContentLoaded', () => {
    const targets = document.querySelectorAll('.news-card, .event-card, .gem-card, .word-banner, .headline-section, .dashboard');
    targets.forEach(el => el.classList.add('fade-up'));

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    targets.forEach(el => observer.observe(el));
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
