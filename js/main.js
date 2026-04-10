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

// Scroll Animations (staggered)
document.addEventListener('DOMContentLoaded', () => {
    const targets = document.querySelectorAll(
        '.news-card, .event-card, .travel-card, .food-feature, ' +
        '.picks-card, .word-banner, .headline-section, .dashboard, ' +
        '.featured-news, .section-title, .section-intro'
    );
    targets.forEach(el => el.classList.add('fade-up'));

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    targets.forEach(el => observer.observe(el));
});

// Smooth scroll for nav links
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('a[href^="#"]').forEach(link => {
        link.addEventListener('click', (e) => {
            const target = document.querySelector(link.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // Close mobile menu if open
                const navLinks = document.querySelector('.nav-links');
                const menuBtn = document.querySelector('.mobile-menu-btn');
                if (navLinks.classList.contains('open')) {
                    navLinks.classList.remove('open');
                    menuBtn.classList.remove('active');
                }
            }
        });
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
        deferredPrompt.userChoice.then(() => {
            deferredPrompt = null;
        });
    }
}
