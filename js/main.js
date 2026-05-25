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

// Dashboard: auto-update today's date (client-side)
document.addEventListener('DOMContentLoaded', () => {
    const dateEl = document.getElementById('dashDate');
    if (dateEl) {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const d = String(now.getDate()).padStart(2, '0');
        dateEl.textContent = `${y}.${m}.${d}`;
    }
});

function formatHeraldDate(value) {
    const published = value ? new Date(value) : null;
    return published && !Number.isNaN(published.getTime())
        ? `Published ${published.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
        : 'Updated daily from The Korea Herald';
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderHeraldCover(story) {
    const titleEl = document.getElementById('coverStoryTitle');
    const subtitleEl = document.getElementById('coverStorySubtitle');
    const briefEl = document.getElementById('coverStoryBrief');
    const imageEl = document.getElementById('coverStoryImage');
    const captionEl = document.getElementById('coverStoryCaption');
    const sourceEl = document.getElementById('coverStorySource');
    const publishedEl = document.getElementById('coverStoryPublished');
    const bodyEl = document.getElementById('coverStoryBody');
    const readLinks = [
        document.getElementById('coverStoryReadLink'),
        document.getElementById('coverStoryMetaLink')
    ].filter(Boolean);

    if (!titleEl || !story || !story.title || !story.link) return;

    const safeTitle = escapeHtml(story.title);
    const safeDescription = escapeHtml(story.description || 'Read the full Korea Herald world top story for today.');
    titleEl.innerHTML = `<span class="en-content">${safeTitle}</span><span class="kr-content">${safeTitle}</span>`;
    if (subtitleEl) {
        subtitleEl.innerHTML = `<span class="en-content">${safeDescription}</span><span class="kr-content">${safeDescription}</span>`;
    }
    if (briefEl) briefEl.textContent = story.description || 'Read the full Korea Herald world top story for today.';
    if (imageEl && story.imageUrl) {
        imageEl.src = story.imageUrl;
        imageEl.removeAttribute('data-secondary-src');
        imageEl.removeAttribute('data-fallback-src');
        imageEl.alt = story.title;
    }
    if (captionEl) captionEl.textContent = 'Image and story source: The Korea Herald World desk.';
    if (sourceEl) sourceEl.textContent = `${story.source || 'The Korea Herald'} · ${story.section || 'World'}`;
    if (publishedEl) publishedEl.textContent = formatHeraldDate(story.publishedAt);
    readLinks.forEach(link => { link.href = story.link; });
    if (bodyEl) {
        bodyEl.innerHTML = `
            <div class="column herald-cover-note">
                <p>${safeDescription}</p>
                <p>ICAN Heralds shows the headline, short summary, and source link for learning context. Please continue to The Korea Herald for the full original article.</p>
            </div>`;
    }
}

// Korea Herald World top story: rendered through our API to avoid browser CORS.
document.addEventListener('DOMContentLoaded', () => {
    const coverTitleEl = document.getElementById('coverStoryTitle');
    if (!coverTitleEl) return;

    fetch('/api/herald-top')
        .then(response => {
            if (!response.ok) throw new Error('Korea Herald feed unavailable');
            return response.json();
        })
        .then(story => {
            if (!story || !story.title || !story.link) return;
            renderHeraldCover(story);
        })
        .catch(() => {});
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
