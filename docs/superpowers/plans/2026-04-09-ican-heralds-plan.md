# ICAN Heralds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the ICAN Heralds news platform into a free, installable Progressive Web App (PWA), automate daily publication at 7 AM via GitHub Actions, and generate a main article image using Nano Banana Pro.

**Architecture:** A static PWA using HTML/CSS/JS. Hosted on a free static host (e.g., GitHub Pages) with a GitHub Actions cron job for the 7 AM automated update. Images generated locally via Gemini 2.5 Flash (Nano Banana Pro) and embedded directly into the article.

**Tech Stack:** HTML5, CSS3, JavaScript, PWA Manifest, Service Worker, GitHub Actions, Nano Banana Pro (Gemini Image Gen).

---

### Task 1: Generate Main Article Image

**Files:**
- Create: `images/main_article.png`

- [ ] **Step 1: Run Nano Banana Pro script**
Run: `uv run /Users/worker64/.gemini/extensions/buildatscale-gemini-skills/skills/nano-banana-pro/scripts/image.py --prompt "A cinematic, editorial-style photograph of the Mt. Samat National Shrine cross in the Philippines on the Day of Valor (Araw ng Kagitingan), featuring subtle elements of Philippine and South Korean friendship (e.g., small flags or a diverse crowd of Korean tourists), high resolution, professional newspaper quality." --output ~/Desktop/ICAN-Heralds/images/main_article.png`

### Task 2: PWA Setup (App Transformation)

**Files:**
- Create: `manifest.json`
- Create: `sw.js`
- Modify: `ican_news.html`

- [ ] **Step 1: Create manifest.json**
Create a web app manifest defining the app name (ICAN Heralds), display mode (standalone), and theme colors to allow users to "Install" the site for free as a native app on iOS/Android.
- [ ] **Step 2: Create Service Worker (sw.js)**
Write a minimal caching service worker to allow offline reading of the daily news.
- [ ] **Step 3: Update HTML to link PWA assets**
Add `<link rel="manifest" href="manifest.json">` and register the service worker via `<script>` at the end of the body in `ican_news.html`.

### Task 3: Insert Image & Implement Toggle Logic

**Files:**
- Modify: `ican_news.html`

- [ ] **Step 1: Update main image**
Replace the `[Main Hero Image...]` placeholder text inside the `.main-image` div with an actual `<img src="images/main_article.png">` tag.
- [ ] **Step 2: Add JS for EN/KR Toggle**
Implement the JavaScript logic for the `.toggle-btn` to instantly switch visibility between the English and Korean text blocks (e.g., toggling `.kr-block` and `.column` content).

### Task 4: Automate Daily 7 AM Publication

**Files:**
- Create: `.github/workflows/daily-publish.yml`

- [ ] **Step 1: Create GitHub Actions Workflow**
Set up a cron job (`cron: '0 23 * * *'`) which corresponds to 7 AM Philippine Standard Time (PHT). The workflow will automate content updates (e.g., fetching new articles via an API or script in the future) and committing/deploying to GitHub Pages.
