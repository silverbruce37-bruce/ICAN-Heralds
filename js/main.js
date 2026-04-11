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

// ── Archive Preview ──
const archiveTagColors = {
    'Security': '#ff1744', 'Economy': '#2979ff', 'Culture': '#aa00ff',
    'Diplomacy': '#00bfa5', 'Cooperation': '#00bfa5', 'Safety': '#00e676',
};

document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('archivePreviewGrid');
    if (!grid) return;

    fetch('data/archive-index.json')
        .then(r => r.json())
        .then(data => {
            data.sort((a, b) => b.date.localeCompare(a.date));
            const recent = data.slice(0, 6);

            if (recent.length === 0) {
                grid.innerHTML = '<p style="color:var(--muted);text-align:center;grid-column:1/-1;padding:40px;">Archive will grow as editions are published daily.</p>';
                return;
            }

            grid.innerHTML = recent.map(ed => {
                const d = new Date(ed.date + 'T00:00:00');
                const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];

                const tagsHTML = (ed.tags || []).slice(0, 4).map(t => {
                    const c = archiveTagColors[t] || '#888';
                    return `<span class="apc-tag" style="background:${c}22;color:${c};">${t}</span>`;
                }).join('');

                return `
                    <div class="archive-preview-card" onclick="window.location.href='archive.html'">
                        <div class="apc-date">
                            <span class="apc-date-day">${d.getDate()}</span>
                            <span class="apc-date-rest">${months[d.getMonth()]} ${d.getFullYear()}</span>
                        </div>
                        <div class="apc-vol">VOL. ${String(ed.vol || 1).padStart(2, '0')}</div>
                        <div class="apc-title">
                            <span class="en-content">${ed.cover_en}</span>
                            <span class="kr-content">${ed.cover_kr}</span>
                        </div>
                        <div class="apc-tags">${tagsHTML}</div>
                    </div>`;
            }).join('');
        })
        .catch(() => {
            grid.innerHTML = '<p style="color:var(--muted);text-align:center;grid-column:1/-1;padding:40px;"><span class="en-content">Archive coming soon — editions will appear here daily.</span><span class="kr-content">아카이브 준비 중 — 매일 발행되는 기사가 여기에 쌓입니다.</span></p>';
        });
});
