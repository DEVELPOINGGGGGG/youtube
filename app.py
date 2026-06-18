# ==============================================================================
# YOUTUBE DOWNLOADER (V33 - SPOTIFY CLONE, INSTANT LOAD & BG AUDIO FIX)
# ==============================================================================

from flask import Flask, request, jsonify, send_file, Response
import yt_dlp
import os
import time
import threading
import uuid
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("YouTubeDownloader")

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

active_tasks = {}

def cleanup_worker():
    while True:
        time.sleep(60) 
        now = time.time()
        try:
            for filename in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - 600:
                    try: os.remove(filepath)
                    except: pass
        except: pass

        try:
            for tid in list(active_tasks.keys()):
                task = active_tasks.get(tid)
                if task:
                    if task.get('completed_at') and (now - task['completed_at'] > 600):
                        del active_tasks[tid]
                    elif task.get('status') == 'error' and task.get('created_at') and (now - task['created_at'] > 600):
                        del active_tasks[tid]
        except: pass

threading.Thread(target=cleanup_worker, daemon=True).start()

def get_progress_hook(task_id):
    def progress_hook(d):
        task = active_tasks.get(task_id)
        if not task: return
        try:
            if d['status'] == 'downloading':
                task['status'] = 'downloading'
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0: task['percent'] = round((downloaded / total) * 100, 1)
                task['speed'] = str(d.get('_speed_str', '0 MB/s')).replace('\x1b[0;94m', '').replace('\x1b[0m', '').strip()
                task['eta'] = str(d.get('_eta_str', '00:00')).replace('\x1b[0;93m', '').replace('\x1b[0m', '').strip()
            elif d['status'] == 'finished':
                task['status'] = 'processing'
                task['percent'] = 100
                task['speed'] = "Processing"
                task['eta'] = "--:--"
        except: pass
    return progress_hook

# ==============================================================================
# HTML 1: THE STRICT DOWNLOADER DASHBOARD (ROUTE: "/")
# ==============================================================================
DOWNLOADER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>YouTube Downloader</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#1e3c72">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body { background: linear-gradient(-45deg, #1e3c72, #2a5298, #ff758c, #ff7eb3, #4facfe, #00f2fe); background-size: 600% 600%; animation: gradientBG 20s ease infinite; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; color: #333; padding: 20px; padding-bottom: 100px; overflow-x: hidden; }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        
        .glass-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(20px); border-radius: 24px; padding: 30px; width: 100%; max-width: 800px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
        .header-area { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .header-left { display: flex; align-items: center; gap: 15px; }
        .hamburger-btn { font-size: 1.8rem; cursor: pointer; color: #1e3c72; background: none; border: none; transition: 0.2s; flex-shrink:0;}
        .settings-btn { font-size: 1.5rem; cursor: pointer; color: #1e3c72; background: #e2e8f0; border: none; border-radius: 50%; width: 45px; height: 45px; display: flex; justify-content: center; align-items: center; }
        h2 { font-weight: 800; font-size: 1.8rem; margin: 0; background: linear-gradient(45deg, #1e3c72, #ff0844); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .side-nav { position: fixed; top: 0; left: -300px; width: 280px; height: 100%; background: white; box-shadow: 5px 0 25px rgba(0,0,0,0.5); z-index: 9999; transition: left 0.3s; display: flex; flex-direction: column; padding: 30px 20px; }
        .side-nav.open { left: 0; }
        .side-nav-close { align-self: flex-end; font-size: 2rem; cursor: pointer; border: none; background: none; color: #ff0844; margin-bottom: 20px; }
        .side-nav a { text-decoration: none; color: #333; font-weight: 800; font-size: 1.1rem; padding: 15px; border-radius: 12px; margin-bottom: 10px; background: #f4f7f6; }
        .nav-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 9998; }
        
        #toast-container { position: fixed; top: 20px; right: 20px; z-index: 10000; display: flex; flex-direction: column; gap: 10px; pointer-events: none;}
        .toast { background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(10px); color: white; padding: 15px 25px; border-radius: 12px; font-weight: 600; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border-left: 5px solid #4facfe; animation: slideIn 0.4s forwards; }
        .toast.success { border-left-color: #1db954; }
        .toast.error { border-left-color: #ff0844; }
        @keyframes slideIn { from { transform: translateX(120%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(120%); opacity: 0; } }

        .tabs { display: flex; gap: 10px; margin-bottom: 20px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; }
        .tab-btn { flex-shrink: 0; padding: 12px 25px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; }
        .tab-btn.active { background: #4facfe; color: white; }
        
        .choice-btn { width: 100%; padding: 18px; border-radius: 16px; border: none; font-size: 1.1rem; font-weight: 800; cursor: pointer; color: white; margin-bottom: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .btn-dash-player { background: linear-gradient(135deg, #1db954 0%, #1ed760 100%); }
        .btn-dash-single { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
        .btn-dash-playlist { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .btn-dash-search { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }

        .input-group { position: relative; margin-bottom: 20px; display:flex; gap:10px; flex-wrap:wrap;}
        .search-wrapper { position: relative; flex: 1; min-width: 250px;}
        input[type="text"] { width: 100%; padding: 18px 120px 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; background: #f8f9fa; }
        
        .paste-btn, .action-btn-inline { position: absolute; right: 5px; top: 50%; transform: translateY(-50%); border: none; padding: 12px 20px; border-radius: 8px; font-weight: 800; cursor: pointer; }
        .paste-btn { background: #e2e8f0; color: #1e3c72; }
        .action-btn-inline { background: #333; color: white; }

        .action-btn { flex-shrink: 0; padding: 15px 25px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; background: #333; }
        .action-btn:disabled { opacity: 0.7; cursor: not-allowed; }
        .btn-mp4 { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); } 
        .btn-mp3 { background: linear-gradient(135deg, #ff0844 0%, #ffb199 100%); }
        
        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center; }
        
        #single-ui, #list-container, #dashboard-ui { display: none; flex-direction: column; gap: 10px; }
        
        .dash-task-header { margin-top: 20px; font-weight: 800; color: #1e3c72; border-bottom: 2px solid #eee; padding-bottom: 10px;}
        #dashboardTasksWrapper { max-height: 400px; overflow-y: auto; padding-right: 5px;}

        .list-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; border: 1px solid transparent; overflow:hidden;}
        .list-item img { width: 150px; border-radius: 8px; cursor: pointer; }
        .item-info { flex: 1; min-width: 0; display:flex; flex-direction:column; justify-content:center;}
        .scrolling-title { font-size: 0.95rem; margin-bottom: 5px; white-space: nowrap; overflow-x: auto; scrollbar-width: none; }
        .btn-scroll-container { display: flex; gap: 10px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; align-items:center;}
        
        .progress-container { background: #fff; padding: 12px; border-radius: 12px; margin-top: 10px; border: 1px solid #eee;}
        .progress-bar-bg { width: 100%; height: 10px; background: #e2e8f0; border-radius: 10px; overflow: hidden; margin: 8px 0; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); transition: width 0.3s ease; }
        .progress-stats { display: flex; justify-content: space-between; font-size: 0.75rem; color: #666; font-weight: 700; }
        
        .fab { display: none; position: fixed; bottom: 30px; right: 30px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 15px 25px; border-radius: 50px; font-weight: 800; box-shadow: 0 10px 25px rgba(17, 153, 142, 0.5); cursor: pointer; z-index: 1000; align-items: center; gap: 10px; }
        .badge { background: #ff0844; padding: 2px 8px; border-radius: 20px; font-size: 0.8rem; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); z-index: 3000; justify-content: center; align-items: center; padding: 20px; }
        .modal-box { background: white; width: 100%; max-width: 600px; border-radius: 24px; padding: 30px; position: relative; max-height: 85vh; overflow-y: auto; }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; font-size: 1.2rem; cursor: pointer; display: flex; justify-content: center; align-items: center; position:absolute; top: 15px; right: 15px;}
        
        .quality-item { background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; color:#333; }
        .task-item { background: #f8f9fa; border: 1px solid #e9ecef; padding: 20px; border-radius: 16px; margin-bottom: 15px; }
        .task-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 15px; font-size: 0.95rem; border-bottom: 1px solid #eee; padding-bottom: 10px;}
        .switch-container { display: flex; align-items: center; justify-content: space-between; background: #e0f2fe; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 2px solid #a1c4fd; color:#333;}
        .load-more-btn { background: #334155; color: white; border: none; padding: 15px; border-radius: 12px; width: 100%; font-weight: 800; cursor: pointer; margin-top: 15px; }

        @media (max-width: 600px) { 
            .list-item { flex-direction: column; align-items: stretch; } 
            .list-item img { width: 100%; } 
            .side-nav { width: 250px; } 
        }
    </style>
</head>
<body>
    <div id="toast-container"></div>
    <div class="nav-overlay" id="navOverlay" onclick="toggleMenu()"></div>
    <div class="side-nav" id="sideNav">
        <button class="side-nav-close" onclick="toggleMenu()">×</button>
        <h2 style="margin-bottom: 30px; text-align: center;">MENU</h2>
        <a href="#" onclick="switchTab('dashboard'); toggleMenu()">🏠 Dashboard</a>
        <a href="/player">▶️ Premium Player</a>
        <div style="height: 1px; background: #ddd; margin: 15px 0;"></div>
        <a href="#" onclick="switchTab('single'); toggleMenu()">🎬 Single Video DL</a>
        <a href="#" onclick="switchTab('playlist'); toggleMenu()">📂 Playlist DL</a>
        <a href="#" onclick="switchTab('search'); toggleMenu()">🔍 Search YouTube</a>
    </div>

    <div class="glass-card">
        <div class="header-area">
            <div style="display:flex; align-items:center; gap:15px;"><button class="hamburger-btn" onclick="toggleMenu()">☰</button><h2>YT DOWNLOADER</h2></div>
            <button class="settings-btn" onclick="document.getElementById('settingsModal').style.display='flex'">⚙️</button>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" id="tab-dashboard" onclick="switchTab('dashboard')">Dashboard</button>
            <button class="tab-btn" id="tab-single" onclick="switchTab('single')">Single</button>
            <button class="tab-btn" id="tab-playlist" onclick="switchTab('playlist')">Playlist</button>
            <button class="tab-btn" id="tab-search" onclick="switchTab('search')">Search</button>
        </div>

        <div id="dashboard-ui">
            <h3 style="margin-bottom: 10px; color: #1e3c72; text-align: center;">What do you want to do?</h3>
            <button class="choice-btn btn-dash-player" onclick="window.location.href='/player'">▶️ OPEN PREMIUM PLAYER</button>
            <button class="choice-btn btn-dash-single" onclick="switchTab('single')">🎬 Download YouTube Video</button>
            <button class="choice-btn btn-dash-playlist" onclick="switchTab('playlist')">📂 Download Playlist</button>
            <button class="choice-btn btn-dash-search" onclick="switchTab('search')">🔍 Search & Download</button>
            
            <div class="dash-task-header">ACTIVE DOWNLOADS</div>
            <div id="dashboardTasksWrapper"><p style="color:#888; font-size:0.9rem;">No active downloads.</p></div>
        </div>

        <div class="input-group" id="inputWrapper">
            <div class="search-wrapper">
                <input type="text" id="url" placeholder="Paste URL..." autocomplete="off">
                <button class="paste-btn" id="pasteBtn" onclick="pasteLink()">PASTE</button>
                <button class="action-btn-inline" id="goBtn" style="display:none;" onclick="handleInput(null, true)">SEARCH</button>
            </div>
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <!-- SINGLE DL -->
        <div id="single-ui">
            <div class="image-wrapper" onclick="window.location.href='/player'"><img id="s-thumb" src=""></div>
            <h3 id="s-title" class="scrolling-title" style="margin-bottom: 15px;"></h3>
            <div class="btn-scroll-container" id="s-btns" style="display:none; margin-bottom:15px;">
                <button class="action-btn btn-mp4" onclick="openQuality(-1, 'mp4')">DOWNLOAD MP4</button>
                <button class="action-btn btn-mp3" onclick="openQuality(-1, 'mp3')">DOWNLOAD MP3</button>
            </div>
            <div class="progress-container" id="progBox-single" style="display:none;">
                <div class="progress-stats"><span id="progStatus-single">Downloading...</span><span id="progPercent-single">0%</span></div>
                <div class="progress-bar-bg"><div class="progress-fill" id="progFill-single"></div></div>
            </div>
        </div>

        <!-- LIST DL -->
        <div id="list-container" class="list-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div><input type="checkbox" id="selectAll" onclick="toggleAll()"> Select All</div>
                <div class="btn-scroll-container">
                    <button class="action-btn btn-mp4" onclick="downloadBulk('mp4')">DL SELECTED MP4</button>
                    <button class="action-btn btn-mp3" onclick="downloadBulk('mp3')">DL SELECTED MP3</button>
                </div>
            </div>
            <div id="items-wrapper" style="display:flex; flex-direction:column; gap:12px;"></div>
            <button class="action-btn" id="loadMoreBtn" style="display:none; width:100%; margin-top:15px;" onclick="loadMore()">🔄 LOAD MORE</button>
        </div>
    </div>

    <!-- BACKGROUND FAB -->
    <div class="fab" id="fabBtn" onclick="document.getElementById('taskModal').style.display='flex'">📥 Queue <span class="badge" id="taskBadge">0</span></div>

    <!-- MODALS -->
    <div class="modal-overlay" id="recoveryModal" style="z-index: 4000;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h2 style="font-size:1.5rem; color:#d32f2f;">⚠️ Unsaved Downloads</h2>
                <button class="btn-close" onclick="document.getElementById('recoveryModal').style.display='none'">X</button>
            </div>
            <p style="margin-bottom:15px; font-size:0.9rem; color:#555;">These videos finished processing while the app was closed.</p>
            <div id="recoveryList" style="display:flex; flex-direction:column; gap:10px; margin-bottom:20px; max-height:200px; overflow-y:auto;"></div>
            <button class="action-btn btn-mp4" style="width:100%; padding:15px; font-size:1.1rem; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);" onclick="downloadRecovered()">⬇ DOWNLOAD ALL</button>
        </div>
    </div>

    <div class="modal-overlay" id="settingsModal" style="z-index: 3500;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                <h2>Settings</h2>
                <button class="btn-close" onclick="document.getElementById('settingsModal').style.display='none'">X</button>
            </div>
            <div class="switch-container">
                <div><label style="font-weight:800; color:#1e3c72;">Strict Audio Conversion</label><p style="font-size:0.75rem; color:#666;">ON: Perfect MP3.<br>OFF: Instant metadata injection.</p></div>
                <input type="checkbox" id="audioConvToggle" onchange="saveSettings()">
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="taskModal" style="z-index: 2500;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                <h2>Background Tasks</h2>
                <button class="btn-close" onclick="document.getElementById('taskModal').style.display='none'">X</button>
            </div>
            <div id="tasksWrapper"><p style="text-align:center; color:#888;">No active downloads.</p></div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal" style="z-index: 4000;">
        <div class="modal-box">
            <h3 id="modalTitle" style="margin-bottom:15px;">Select Quality</h3>
            <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            <div id="subToggle" class="switch-container" style="display:none;"><label style="font-weight:700; color:#1e3c72;">💬 Burn Subtitles</label><input type="checkbox" id="burnSubs"></div>
            <div id="qualityList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
    </div>

    <script>
        function showToast(msg, type='info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`; toast.innerText = msg;
            container.appendChild(toast);
            setTimeout(() => { toast.style.animation = 'slideOut 0.4s forwards'; setTimeout(() => toast.remove(), 400); }, 3000);
        }

        let clientId = localStorage.getItem('yt_dl_client_id') || (Math.random().toString(36).substring(2) + Date.now().toString(36));
        localStorage.setItem('yt_dl_client_id', clientId);
        let handledDownloads = JSON.parse(localStorage.getItem('yt_dl_handled') || '[]');
        function markHandled(id) { if (!handledDownloads.includes(id)) { handledDownloads.push(id); localStorage.setItem('yt_dl_handled', JSON.stringify(handledDownloads.slice(-50))); } }

        function loadSettings() { document.getElementById('audioConvToggle').checked = (localStorage.getItem('audio_conversion_enabled') ?? 'true') === 'true'; }
        function saveSettings() { localStorage.setItem('audio_conversion_enabled', document.getElementById('audioConvToggle').checked); showToast("Settings Saved", "success"); }
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');

        let currentMode = 'dashboard';
        let currentData = []; 
        let currentSearchLimit = 10;
        let pendingDownloadTarget = null; 
        let taskDOMMap = {}; 
        let typingTimer; 
        let isFetchingMore = false; 
        
        let initialLoad = true;
        let recoveredToDownload = [];
        let deliveryQueue = [];
        let isDelivering = false;
        let notifiedSet = new Set(); 

        window.addEventListener('DOMContentLoaded', () => {
            loadSettings(); 
            const params = new URLSearchParams(window.location.search);
            const sharedData = params.get('url') || params.get('text') || params.get('title');
            if (sharedData) {
                const urlMatch = sharedData.match(/(https?:\/\/[^\s]+)/);
                if (urlMatch) { switchTab('single'); document.getElementById('url').value = urlMatch[0]; handleInput(urlMatch[0], true); return; }
            }
            switchTab('dashboard');
        });

        window.addEventListener('scroll', () => {
            if(currentMode === 'search' && document.getElementById('loadMoreBtn').style.display === 'block') {
                if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
                    if(!isFetchingMore) { isFetchingMore = true; loadMore(); }
                }
            }
        });

        function processDeliveryQueue() {
            if(isDelivering || deliveryQueue.length === 0) return;
            isDelivering = true;
            const link = document.createElement('a'); link.href = deliveryQueue.shift(); link.download = ''; 
            document.body.appendChild(link); link.click(); document.body.removeChild(link);
            setTimeout(() => { isDelivering = false; processDeliveryQueue(); }, 1500); 
        }

        function showRecoveryModal(files) {
            const list = document.getElementById('recoveryList'); list.innerHTML = '';
            files.forEach(f => { list.innerHTML += `<div style="padding:10px; background:#e0f2fe; border-radius:8px;">${f.title}</div>`; recoveredToDownload.push(f); });
            document.getElementById('recoveryModal').style.display = 'flex';
        }
        function downloadRecovered() { document.getElementById('recoveryModal').style.display = 'none'; recoveredToDownload.forEach(f => { deliveryQueue.push('/api/serve?file=' + encodeURIComponent(f.file)); }); processDeliveryQueue(); recoveredToDownload = []; }

        function toggleMenu() {
            const nav = document.getElementById('sideNav');
            nav.classList.toggle('open');
            document.getElementById('navOverlay').style.display = nav.classList.contains('open') ? 'block' : 'none';
        }

        function switchTab(mode) {
            if (currentMode !== mode && mode !== 'dashboard') showToast(`Switched to ${mode.toUpperCase()} mode`);
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if(document.getElementById(`tab-${mode}`)) document.getElementById(`tab-${mode}`).classList.add('active');
            ['dashboard-ui', 'inputWrapper', 'statusBadge', 'list-container', 'single-ui'].forEach(id => document.getElementById(id).style.display = 'none');
            
            if(mode === 'dashboard') {
                document.getElementById('dashboard-ui').style.display = 'flex';
            } else {
                document.getElementById('inputWrapper').style.display = 'flex';
                document.getElementById('statusBadge').style.display = 'inline-block';
                const input = document.getElementById('url');
                input.placeholder = mode === 'search' ? "Type query..." : "Paste YouTube URL...";
                document.getElementById('pasteBtn').style.display = mode === 'search' ? 'none' : 'block';
                document.getElementById('goBtn').style.display = mode === 'search' ? 'block' : 'none';
                input.style.paddingRight = mode === 'search' ? '120px' : '90px';
                setStatus(mode === 'search' ? "Ready to search." : "Awaiting Link...");
            }
        }

        function setStatus(msg, isErr=false) {
            const b = document.getElementById('statusBadge');
            b.innerText = msg; b.style.background = isErr ? '#ffebee' : '#eee'; b.style.color = isErr ? '#c62828' : '#333';
        }

        document.getElementById('url').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(typingTimer);
                handleInput(this.value.trim(), true);
                this.blur();
            }
        });

        document.getElementById('url').addEventListener('input', (e) => {
            clearTimeout(typingTimer);
            if(!e.target.value.trim()) return setStatus("Awaiting Input...");
            setStatus("Waiting 3 seconds...");
            typingTimer = setTimeout(() => { handleInput(e.target.value.trim(), true); }, 3000); 
        });

        async function pasteLink() { try { document.getElementById('url').value = await navigator.clipboard.readText(); clearTimeout(typingTimer); handleInput(null, true); } catch (err) {} }

        function loadMore() { currentSearchLimit += 20; handleInput(null, false); }

        async function handleInput(forcedValue = null, isNewSearch = true) {
            let val = forcedValue || document.getElementById('url').value.trim();
            if(!val) { isFetchingMore = false; return; }
            setStatus("Extracting Data...");
            if(isNewSearch) {
                currentSearchLimit = 10;
                document.getElementById('single-ui').style.display = 'none';
                document.getElementById('list-container').style.display = 'none';
                document.getElementById('loadMoreBtn').style.display = 'none';
            }
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: val, mode: currentMode, limit: currentSearchLimit}) });
                const data = await res.json();
                
                if(data.error) { isFetchingMore = false; showToast(data.error, "error"); return setStatus("Error. See notification.", true); }

                if(currentMode === 'single') {
                    currentData = [data];
                    currentVideoId = data.id || val.split('v=')[1];
                    document.getElementById('s-thumb').src = data.thumbnail;
                    document.getElementById('s-title').innerText = data.title;
                    document.getElementById('s-btns').style.display = 'flex';
                    document.getElementById('single-ui').style.display = 'block';
                } else {
                    currentData = data.entries;
                    renderItems();
                    document.getElementById('list-container').style.display = 'flex';
                    if (currentMode === 'search') document.getElementById('loadMoreBtn').style.display = 'block';
                }
                setStatus("Data Ready.");
            } catch(e) { showToast("Network Error: " + e.message, "error"); setStatus("Error.", true); }
            isFetchingMore = false; 
        }

        function renderItems() {
            const wrapper = document.getElementById('items-wrapper'); wrapper.innerHTML = '';
            currentData.forEach((item, i) => {
                const videoId = item.id || (item.url ? item.url.split('v=')[1] : '');
                wrapper.innerHTML += `
                    <div class="list-item">
                        <input type="checkbox" class="pl-checkbox" value="${i}" style="width:20px;height:20px;flex-shrink:0;">
                        <img src="${item.thumbnail}">
                        <div class="item-info">
                            <h4 class="scrolling-title">${item.title}</h4>
                            <p style="font-size:0.8rem; color:#666;">👤 ${item.uploader || 'Unknown'} | ⏱️ ${item.duration || '--'}</p>
                            <div class="btn-scroll-container" style="margin-top:5px;">
                                <button class="action-btn btn-mp4" style="padding:8px 15px;" onclick="openQuality(${i}, 'mp4')">DL MP4</button>
                                <button class="action-btn btn-mp3" style="padding:8px 15px;" onclick="openQuality(${i}, 'mp3')">DL MP3</button>
                            </div>
                            <div class="progress-container" id="progBox-${i}" style="display:none;">
                                <div class="progress-stats"><span id="progStatus-${i}">Wait...</span><span id="progPercent-${i}">0%</span></div>
                                <div class="progress-bar-bg"><div class="progress-fill" id="progFill-${i}"></div></div>
                            </div>
                        </div>
                    </div>`;
            });
        }

        function toggleAll() { const c = document.getElementById('selectAll').checked; document.querySelectorAll('.pl-checkbox').forEach(cb => cb.checked = c); }

        async function openQuality(index, type, isBulk=false) {
            pendingDownloadTarget = { index, type, isBulk };
            const list = document.getElementById('qualityList'); list.innerHTML = '';
            if (type === 'mp4') {
                document.getElementById('modalTitle').innerText = "MP4 Quality";
                document.getElementById('subToggle').style.display = 'flex'; 
                document.getElementById('id3Notice').style.display = 'none'; 
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('best')"><span>⭐ AUTO BEST</span></div>`;
                if (isBulk) {
                    list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('1080p')"><span>📽️ 1080p</span></div><div class="quality-item" onclick="startBackgroundDownload('720p')"><span>📽️ 720p</span></div>`;
                } else {
                    let actualIndex = index === -1 ? 0 : index;
                    if (!currentData[actualIndex].formats) {
                        try {
                            const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: currentData[actualIndex].url || currentData[actualIndex].id, mode: 'single'}) });
                            const data = await res.json();
                            if(data.formats) currentData[actualIndex].formats = data.formats;
                        } catch(e) {}
                    }
                    if(currentData[actualIndex].formats) {
                        currentData[actualIndex].formats.forEach(f => { list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('${f.format_id}')"><span>📽️ ${f.resolution}</span></div>`; });
                    }
                }
            } else {
                document.getElementById('modalTitle').innerText = "MP3 Quality";
                document.getElementById('subToggle').style.display = 'none'; 
                document.getElementById('id3Notice').style.display = 'flex'; 
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('320')"><span>⭐ 320 kbps</span></div><div class="quality-item" onclick="startBackgroundDownload('192')"><span>🎵 192 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }

        function downloadBulk(type) { openQuality(null, type, true); }

        async function startBackgroundDownload(quality) {
            document.getElementById('qualityModal').style.display = 'none';
            showToast("Download Started!", "info");
            const burnSubs = document.getElementById('burnSubs') ? document.getElementById('burnSubs').checked : false;
            const useAudioConv = document.getElementById('audioConvToggle').checked;

            const dispatch = async (idx) => {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ client_id: clientId, url: currentData[idx].url || currentData[idx].id || document.getElementById('url').value, title: currentData[idx].title, type: pendingDownloadTarget.type, quality: quality, burn_subs: burnSubs, use_conversion: useAudioConv })
                });
                const data = await res.json();
                if(data.task_id) {
                    taskDOMMap[data.task_id] = { isSingle: pendingDownloadTarget.index === -1, index: idx };
                    document.getElementById(pendingDownloadTarget.index === -1 ? 'progBox-single' : `progBox-${idx}`).style.display = 'block';
                }
            };

            if (pendingDownloadTarget.isBulk) { document.querySelectorAll('.pl-checkbox:checked').forEach(cb => dispatch(parseInt(cb.value))); } 
            else { dispatch(pendingDownloadTarget.index === -1 ? 0 : pendingDownloadTarget.index); }
        }

        setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks?client_id=${clientId}`);
                const tasks = await res.json();
                let html = ''; let activeCount = 0; let nowSec = Date.now() / 1000; let newlyRecovered = [];

                for (const [id, t] of Object.entries(tasks)) {
                    activeCount++;
                    let sCol = t.status==='completed' ? '#155724' : (t.status==='error' ? '#721c24' : '#004085');
                    let sBg = t.status==='completed' ? '#d4edda' : (t.status==='error' ? '#f8d7da' : '#cce5ff');
                    
                    let isExpired = false;
                    let saveBtnHtml = `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px;" onclick="markHandled('${id}'); window.location.href='/api/serve?file=${encodeURIComponent(t.file)}'">💾 SAVE</button>`;
                    if (t.status === 'completed' && t.completed_at && (nowSec - t.completed_at) > 300) { 
                        isExpired = true;
                        saveBtnHtml = `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px; background:#e67e22;" onclick="markHandled('${id}'); window.location.href='/api/serve?file=${encodeURIComponent(t.file)}'">💾 SAVE (EXPIRED)</button>`;
                    }

                    html += `<div class="task-item" style="background: ${sBg}; border-color: ${sCol}44;"><div class="task-header" style="color: ${sCol};"><span>${t.type.toUpperCase()}: ${t.title}</span><span>${t.status.toUpperCase()}</span></div>
                            ${(t.status === 'downloading' || t.status === 'processing') ? `<div class="progress-bar-bg"><div class="progress-fill" style="width: ${t.percent}%"></div></div><div class="progress-stats"><span>${t.percent}%</span></div>` : ''}
                            ${t.status === 'error' ? `<div style="font-size:0.85rem; color:red;">${t.error_msg}</div>` : ''}
                            ${t.status === 'completed' ? saveBtnHtml : ''}</div>`;

                    const mapData = taskDOMMap[id];
                    if (mapData) {
                        const progBox = document.getElementById(mapData.isSingle ? 'progBox-single' : `progBox-${mapData.index}`);
                        if (progBox) {
                            if (t.status === 'downloading' || t.status === 'processing') {
                                progBox.querySelector('.progress-fill').style.width = t.percent + '%';
                                progBox.querySelector('.progress-stats span:first-child').innerText = t.status + '... ' + t.percent + '%';
                            } else if (t.status === 'completed') {
                                progBox.querySelector('.progress-fill').style.width = '100%';
                                progBox.querySelector('.progress-fill').style.background = '#38ef7d';
                                progBox.querySelector('.progress-stats span:first-child').innerText = 'Done!';
                            }
                        }
                    }

                    if (t.status === 'completed' && !handledDownloads.includes(id)) {
                        if (initialLoad && !isExpired) { newlyRecovered.push({ id, title: t.title, file: t.file }); markHandled(id); } 
                        else if (!initialLoad && !isExpired) { 
                            markHandled(id); 
                            if(!notifiedSet.has(id)) {
                                notifiedSet.add(id);
                                showToast(`Finished: ${t.title}`, "success");
                            }
                            deliveryQueue.push('/api/serve?file=' + encodeURIComponent(t.file)); 
                            processDeliveryQueue(); 
                        } 
                        else if (isExpired) { markHandled(id); }
                    }
                }
                
                if (initialLoad && newlyRecovered.length > 0) showRecoveryModal(newlyRecovered);
                initialLoad = false; 
                
                const fab = document.getElementById('fabBtn');
                if (activeCount > 0) { fab.style.display = 'flex'; } else { fab.style.display = 'none'; }
                
                const finalHtml = html || '<p style="text-align:center; color:#888;">No active downloads.</p>';
                document.getElementById('tasksWrapper').innerHTML = finalHtml;
                document.getElementById('dashboardTasksWrapper').innerHTML = finalHtml; 
                document.getElementById('taskBadge').innerText = activeCount;
            } catch(e) {}
        }, 1000); 
    </script>
</body>
</html>
"""

# ==============================================================================
# HTML 2: THE STRICT PREMIUM PLAYER (ROUTE: "/player")
# ==============================================================================
PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Premium Player</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body { background: #121212; color: white; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 20px; overflow-x: hidden; }
        
        .side-nav { position: fixed; top: 0; left: -300px; width: 280px; height: 100%; background: #000; box-shadow: 5px 0 25px rgba(0,0,0,0.5); z-index: 9999; transition: left 0.3s; display: flex; flex-direction: column; padding: 30px 20px; }
        .side-nav.open { left: 0; }
        .side-nav-close { align-self: flex-end; font-size: 2rem; cursor: pointer; border: none; background: none; color: #1db954; margin-bottom: 20px; }
        .side-nav a { text-decoration: none; color: white; font-weight: 800; font-size: 1.1rem; padding: 15px; border-radius: 12px; margin-bottom: 10px; background: #282828; display: flex; align-items: center; justify-content: space-between;}
        .side-nav a:hover { background: #1db954; transform: translateX(10px); }
        .nav-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9998; }

        /* TOASTS */
        #toast-container { position: fixed; top: 20px; right: 20px; z-index: 10000; display: flex; flex-direction: column; gap: 10px; pointer-events: none;}
        .toast { background: #282828; color: white; padding: 15px 25px; border-radius: 8px; font-weight: 600; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border-left: 5px solid #1db954; animation: slideIn 0.4s forwards; }
        .toast.error { border-left-color: #ff0844; }
        @keyframes slideIn { from { transform: translateX(120%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(120%); opacity: 0; } }

        .container { width: 100%; max-width: 600px; padding-bottom: 150px; }
        
        /* V32 MOBILE TOP BAR FIX */
        .top-bar { display: flex; gap: 10px; margin-bottom: 20px; align-items:center;}
        .menu-btn { background: none; border: none; color: white; font-size: 1.8rem; cursor: pointer; flex-shrink: 0;}
        .search-wrapper { position: relative; flex: 1; width: 100%; }
        input[type="text"] { width: 100%; padding: 15px 120px 15px 20px; border-radius: 30px; border: none; background: #282828; color: white; font-size: 1.1rem; outline: none; }
        input[type="text"]:focus { background: #333; }
        .search-btn { position: absolute; right: 5px; top: 50%; transform: translateY(-50%); background: #1db954; color: black; border: none; padding: 10px 20px; border-radius: 20px; font-weight: 800; cursor: pointer; margin: 0;}

        #choice-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 70vh; gap: 20px; }
        .choice-btn { width: 100%; padding: 25px; border-radius: 30px; border: none; font-size: 1.5rem; font-weight: 800; cursor: pointer; color: white; }
        .btn-music { background: #1db954; color: black;}
        .btn-video { background: #282828; color: white;}

        #search-screen { display: none; }
        #results { display: flex; flex-direction: column; gap: 15px; }

        .queue-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #282828; padding: 10px 15px; border-radius: 12px;}
        .play-selected-btn { background: #1db954; color: black; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; cursor: pointer; }

        .card { background: #181818; border-radius: 12px; padding: 15px; display: flex; gap: 15px; align-items: center; transition: background 0.3s;}
        .card:hover { background: #282828; }
        .card.audio-mode img { width: 60px; height: 60px; border-radius: 8px; object-fit: cover; cursor:pointer;}
        .card.video-mode { flex-direction: column; align-items: stretch; padding: 0; overflow:hidden;}
        .card.video-mode img { width: 100%; aspect-ratio: 16/9; object-fit: cover; cursor:pointer;}
        .card.video-mode .info { padding: 15px; }
        
        .info { flex: 1; min-width: 0; }
        .info h4 { font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 5px; color:white;}
        .info p { font-size: 0.75rem; color: #b3b3b3; }
        
        .action-row { display: flex; gap: 10px; margin-top: 10px;}
        .play-action-btn { flex: 1; background: #1db954; color: black; border: none; padding: 10px 15px; border-radius: 20px; font-weight: bold; cursor: pointer; }
        .card.video-mode .play-action-btn { background: #fff; padding: 15px; }
        .dl-icon-btn { background: #282828; color: white; border: none; padding: 10px 15px; border-radius: 20px; font-size: 1.2rem; cursor: pointer; display:flex; align-items:center; justify-content:center;}
        .dl-icon-btn:hover { background: #333; }

        /* SPOTIFY STYLE GOD-MODE AUDIO PLAYER */
        #audio-player-bar { position: fixed; top: 100vh; left: 0; width: 100%; height: 100vh; background: linear-gradient(to bottom, #2a2a2a, #121212); padding: 25px; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: top 0.4s; z-index: 2000; overflow-y: auto;}
        #audio-player-bar.active { top: 0; }
        #audio-player-bar.mini { top: auto; bottom: 0; height: 80px; flex-direction: row; padding: 10px 15px; justify-content: space-between; border-radius: 8px; background: #181818; box-shadow: 0 -5px 20px rgba(0,0,0,0.5); width: 96%; left: 2%; margin-bottom:10px; cursor:pointer;}
        
        .full-only { display: flex; width: 100%; justify-content: space-between; position: absolute; top: 20px; padding: 0 25px; z-index: 3000; pointer-events: auto;}
        .mini .full-only { display: none !important; }
        
        /* V32 SPOTIFY DOWN ARROW */
        .top-ctrl-btn { background: transparent; border: none; color: white; font-size: 2rem; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        
        .mini-close { display: none; }
        .mini .mini-close { display: flex; align-items:center; justify-content:center; font-size: 1.8rem; background:none; border:none; color:#b3b3b3; margin-left:10px; cursor:pointer; z-index: 3000; position:relative; pointer-events:auto;}

        #ap-cover { width: 85%; max-width: 350px; aspect-ratio: 1; border-radius: 8px; object-fit: cover; margin-top: 50px; margin-bottom: 30px; transition: 0.3s; box-shadow: 0 10px 30px rgba(0,0,0,0.5);}
        .mini #ap-cover { width: 55px; height: 55px; margin: 0; border-radius:4px; box-shadow:none;}
        
        .marquee-wrapper { width: 100%; overflow: hidden; text-align: left; margin-bottom: 5px; color: white; }
        .mini .marquee-wrapper { margin-left: 15px; flex: 1; }
        .marquee-text { font-size: 1.5rem; font-weight: 800; white-space: nowrap; display: inline-block; }
        .mini .marquee-text { font-size: 0.95rem; }
        .marquee-text.scroll { animation: marquee 12s linear infinite; padding-left: 100%; }
        @keyframes marquee { 0% { transform: translateX(0); } 100% { transform: translateX(-100%); } }
        
        #ap-artist { color: #b3b3b3; font-size: 1rem; margin-bottom: 20px; width:100%; text-align:left;}
        .mini #ap-artist { display: block; font-size: 0.8rem; margin:0; margin-left: 15px;}

        .progress-row { width: 100%; display: flex; align-items: center; gap: 10px; margin-bottom: 20px; font-size: 0.75rem; color: #b3b3b3; }
        .mini .progress-row { display: none; }
        input[type="range"] { flex: 1; -webkit-appearance: none; background: #4d4d4d; height: 4px; border-radius: 2px; outline: none; transition: 0.1s;}
        input[type="range"]:hover::-webkit-slider-thumb { opacity: 1; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #fff; cursor: pointer; opacity: 0; transition: 0.1s;}

        .advanced-controls { display: flex; width: 100%; justify-content: space-between; margin-bottom: 10px; color: #b3b3b3; align-items:center;}
        .mini .advanced-controls { display: none; }
        .adv-btn { background: none; border: none; color: #b3b3b3; font-size: 1.2rem; cursor: pointer; font-weight: bold; transition: 0.2s; display:flex; justify-content:center; align-items:center;}
        .adv-btn.active { color: #1db954; }

        .sleep-wrapper { position: relative; display: flex; justify-content: center; align-items: center; width: 40px; height: 40px; border-radius: 50%; }
        .sleep-ring { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 50%; background: transparent; z-index: 1; pointer-events: none; }
        .sleep-wrapper .adv-btn { z-index: 2; position: relative;}

        .controls { display: flex; align-items: center; justify-content: center; gap: 25px; width: 100%; margin-bottom: 20px;}
        .mini .controls { width: auto; gap: 15px; margin-bottom: 0;}
        .ctrl-btn { background: none; border: none; color: white; font-size: 1.8rem; cursor: pointer; }
        .ctrl-play { background: white; color: black; width: 65px; height: 65px; border-radius: 50%; font-size: 2rem; display: flex; justify-content: center; align-items: center; }
        .mini .ctrl-play { width: 40px; height: 40px; font-size: 1.2rem; background: transparent; color: white;}
        
        .bottom-action-row { display: flex; align-items: center; justify-content: space-between; gap: 15px; width: 100%; margin-top: auto; padding-bottom: 20px;}
        .mini .bottom-action-row { display: none; }
        
        .open-yt-btn, .dl-mp3-btn { text-decoration: none; font-size: 0.9rem; font-weight: bold; padding: 12px 20px; border-radius: 30px; cursor: pointer; border: none; display:flex; align-items:center; justify-content:center;}
        .open-yt-btn { color: white; background: transparent; border: 1px solid #727272; }
        .dl-mp3-btn { color: black; background: #1db954; flex:1;}
        .dl-mp3-btn:disabled { background: #333; color:#888; cursor: not-allowed;}

        /* VIDEO PIP & SANDBOX */
        #video-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: black; z-index: 2500; flex-direction: column; justify-content: center; align-items: center; transition: 0.3s;}
        #video-modal.mini-video { top: auto; left: auto; bottom: 100px; right: 20px; width: 320px; height: auto; padding: 0; background: transparent; box-shadow: 0 10px 30px rgba(0,0,0,0.8); border-radius: 12px; }
        .video-container { width: 100%; max-width: 100vw; aspect-ratio: 16/9; background: black; position: relative; border-radius: inherit; overflow:hidden;}
        .video-container iframe { width: 100%; height: 100%; border: none; pointer-events: auto; }
        .vid-controls { position: absolute; top: 20px; right: 20px; display: flex; gap: 10px; z-index: 2501; }
        #video-modal.mini-video .vid-controls { top: -15px; right: -10px; }
        .close-video, .min-video { background: rgba(255,8,68,0.9); color: white; border: none; padding: 10px; border-radius: 50%; font-weight: 800; cursor: pointer; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center;}
        .min-video { background: rgba(51, 65, 85, 0.9); }
        #video-modal.mini-video .min-video { display: none; }

        .load-more-btn { background: #282828; color: white; border: none; padding: 15px; border-radius: 30px; width: 100%; font-weight: 800; cursor: pointer; margin-top: 15px; }

        /* MODALS */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); z-index: 4000; justify-content: center; align-items: center; padding: 20px; }
        .modal-box { background: #282828; width: 100%; max-width: 600px; border-radius: 16px; padding: 30px; position: relative; color: white; }
        .quality-item { background: #181818; border: 1px solid #333; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; margin-bottom: 10px; }
        .quality-item.best { border-color: #1db954; }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; cursor: pointer; display: flex; justify-content: center; align-items: center; position:absolute; top: 15px; right: 15px; z-index:10;}
        input[type="number"] { width: 100%; padding: 15px 20px; border-radius: 12px; border: none; outline: none; font-size: 1.1rem; background: #333; color:white; margin-bottom: 15px;}

        @media (max-width: 600px) { .side-nav { width: 250px; } #video-modal.mini-video { width: 90%; right: 5%; bottom: 20px; } }
    </style>
</head>
<body>
    <div id="toast-container"></div>

    <div class="nav-overlay" id="navOverlay" onclick="toggleMenu()"></div>
    <div class="side-nav" id="sideNav">
        <button class="side-nav-close" onclick="toggleMenu()">×</button>
        <h2 style="margin-bottom: 30px; text-align: center; color:white;">MENU</h2>
        <a href="/">🏠 Back to Downloader</a>
        <div style="height: 1px; background: #333; margin: 15px 0;"></div>
        <a href="#" onclick="setMode('audio'); toggleMenu()">🎵 Audio Search</a>
        <a href="#" onclick="setMode('video'); toggleMenu()">🎬 Video Search</a>
    </div>

    <div class="container">
        <div id="choice-screen">
            <h1 style="font-size: 2.5rem; text-align:center;">Spotify Mode</h1>
            <button class="choice-btn btn-music" onclick="setMode('audio')">🎵 Music Search</button>
            <button class="choice-btn btn-video" onclick="setMode('video')">🎬 Video Search</button>
            <button style="margin-top:20px; background:none; border:none; color:#b3b3b3; font-size:1.1rem; text-decoration:underline; cursor:pointer;" onclick="window.location.href='/'">Switch to Downloader</button>
        </div>

        <div id="search-screen">
            <div class="top-bar">
                <button class="menu-btn" onclick="toggleMenu()">☰</button>
                <div class="search-wrapper">
                    <input type="text" id="searchInput" placeholder="What do you want to listen to?">
                    <button class="search-btn" onclick="search(true)">Search</button>
                </div>
            </div>
            <div id="queue-actions" class="queue-actions" style="display:none;">
                <div><input type="checkbox" id="selectAll" onclick="toggleAll()" style="width:20px;height:20px;vertical-align:middle; accent-color:#1db954;"> Select All</div>
                <button class="play-selected-btn" onclick="playSelected()">▶ PLAY SELECTED</button>
            </div>
            <div id="status" style="text-align:center; color:#b3b3b3; margin-bottom:15px;"></div>
            <div id="results"></div>
            <button id="loadMoreBtn" class="load-more-btn" style="display:none;" onclick="loadMore()">LOAD MORE</button>
        </div>
    </div>

    <!-- GOD-MODE SPOTIFY AUDIO PLAYER -->
    <div id="audio-player-bar" onclick="openPlayerUI(event)">
        <div class="full-only">
            <button class="top-ctrl-btn" onclick="toggleMiniPlayer(event)" title="Minimize">🔽</button>
        </div>
        
        <img id="ap-cover" src="" onclick="openFullThumb(event)">
        
        <div style="width:100%; display:flex; flex-direction:column; justify-content:center;">
            <div class="marquee-wrapper">
                <span class="marquee-text" id="ap-title">Loading...</span>
            </div>
            <div id="ap-artist">Nexus Audio</div>
        </div>
        
        <div class="advanced-controls">
            <button class="adv-btn" id="speedBtn" onclick="toggleSpeed(event)">1x</button>
            <button class="adv-btn" id="loopBtn" onclick="toggleLoop(event)">🔁</button>
            <div class="sleep-wrapper">
                <div class="sleep-ring" id="sleepRing"></div>
                <button class="adv-btn" id="sleepBtn" onclick="openSleepModal(event)">🌙</button>
            </div>
            <button class="adv-btn" onclick="shareSong(event)">📤</button>
        </div>

        <div class="progress-row">
            <span id="currTime">0:00</span>
            <input type="range" id="seekSlider" value="0" min="0" max="100">
            <span id="durTime">0:00</span>
        </div>

        <div class="controls">
            <button class="ctrl-btn" onclick="prevSong(event)">⏮</button>
            <button class="ctrl-btn ctrl-play" id="playPauseBtn" onclick="togglePlay(event)">⏸</button>
            <button class="ctrl-btn" onclick="nextSong(event)">⏭</button>
            <button class="mini-close" onclick="stopAudio(event)">✖</button>
        </div>
        
        <div class="bottom-action-row">
            <a id="ap-yt-link" class="open-yt-btn" href="#" target="_blank">↗ YouTube</a>
            <button id="mainPlayerDlBtn" class="dl-mp3-btn" onclick="downloadCurrentSong(event)">📥 Download</button>
        </div>
        <audio id="audioEngine" autoplay></audio>
    </div>

    <!-- VIDEO MODAL -->
    <div id="video-modal">
        <div class="video-container">
            <div class="vid-controls">
                <button class="min-video" onclick="toggleMiniVideo()">🗕</button>
                <button class="close-video" onclick="closeVideo()">✖</button>
            </div>
            <iframe id="ytIframe" src="" sandbox="allow-scripts allow-same-origin allow-presentation" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
    </div>

    <!-- THUMBNAIL MODAL -->
    <div class="modal-overlay" id="thumbModal" style="z-index: 6000;" onclick="this.style.display='none'">
        <div style="position: relative; max-width: 90vw; max-height: 90vh;">
            <button class="btn-close" style="position:absolute; top:-15px; right:-15px; z-index: 6001;">X</button>
            <img id="fullThumbImg" src="" style="width:100%; height:auto; max-height:85vh; border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.8); object-fit:contain;">
        </div>
    </div>

    <div class="modal-overlay" id="sleepModal" style="z-index: 5000;">
        <div class="modal-box" style="text-align: center;">
            <button class="btn-close" onclick="document.getElementById('sleepModal').style.display='none'">X</button>
            <h3 style="margin-bottom: 15px;">Set Sleep Timer</h3>
            <input type="number" id="sleepInput" placeholder="Minutes..." style="width: 100%; margin-bottom: 15px;">
            <button class="play-selected-btn" style="width: 100%; padding:15px; border-radius:30px;" onclick="setSleepTimer()">START TIMER</button>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            <h3 id="modalTitle" style="margin-bottom:15px;">Select Quality</h3>
            <div id="qualityList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
    </div>

    <script>
        function showToast(msg, type='info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`; toast.innerText = msg;
            container.appendChild(toast);
            setTimeout(() => { toast.style.animation = 'slideOut 0.4s forwards'; setTimeout(() => toast.remove(), 400); }, 3000);
        }

        let clientId = localStorage.getItem('yt_dl_client_id') || (Math.random().toString(36).substring(2) + Date.now().toString(36));
        localStorage.setItem('yt_dl_client_id', clientId);

        let currentMode = '';
        let currentResults = [];
        let currentSearchLimit = 10;
        
        let audioQueue = [];
        let currentIndex = -1;
        
        const audioEngine = document.getElementById('audioEngine');
        const playPauseBtn = document.getElementById('playPauseBtn');
        const seekSlider = document.getElementById('seekSlider');
        const audioBar = document.getElementById('audio-player-bar');

        let loopMode = 0; 
        let currentSpeed = 1.0;
        let sleepTimer = null;
        let sleepTimeLeft = 0;
        let totalSleepTime = 0;
        let isFetchingMore = false; 

        // V30: CROSSFADE VARIABLES
        let isFadingOut = false;
        let fadeInterval = null;
        
        // V30: Persistent VideoID Download Map
        let activeSongDownloads = {}; // Maps videoId -> taskId

        function toggleMenu() {
            const nav = document.getElementById('sideNav');
            nav.classList.toggle('open');
            document.getElementById('navOverlay').style.display = nav.classList.contains('open') ? 'block' : 'none';
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('choice-screen').style.display = 'none';
            document.getElementById('search-screen').style.display = 'block';
            document.getElementById('queue-actions').style.display = mode === 'audio' ? 'flex' : 'none';
            document.getElementById('searchInput').focus();
            document.getElementById('results').innerHTML = '';
        }

        window.addEventListener('scroll', () => {
            if(currentMode === 'search' && document.getElementById('loadMoreBtn').style.display === 'block') {
                if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
                    if(!isFetchingMore) { isFetchingMore = true; loadMore(); }
                }
            }
        });

        function loadMore() { currentSearchLimit += 20; search(false); }

        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); search(true); this.blur(); }
        });

        async function search(isNew = true) {
            const query = document.getElementById('searchInput').value.trim();
            if(!query) return;
            
            document.getElementById('status').innerText = 'Searching YouTube...';
            if(isNew) { currentSearchLimit = 10; document.getElementById('results').innerHTML = ''; document.getElementById('loadMoreBtn').style.display = 'none'; }

            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: query, mode: 'search', limit: currentSearchLimit}) });
                const data = await res.json();
                
                if(data.error) { isFetchingMore = false; showToast(data.error, "error"); return document.getElementById('status').innerText = 'Error searching.'; }
                
                currentResults = data.entries;
                renderResults();
                document.getElementById('status').innerText = '';
                document.getElementById('loadMoreBtn').style.display = 'block';
            } catch (err) { showToast(err.message, "error"); document.getElementById('status').innerText = 'Network Error.'; }
            isFetchingMore = false; 
        }

        function renderResults() {
            const container = document.getElementById('results'); container.innerHTML = '';
            currentResults.forEach((item, index) => {
                const uploader = item.uploader || 'Unknown';
                if(currentMode === 'audio') {
                    container.innerHTML += `
                        <div class="card audio-mode">
                            <input type="checkbox" class="song-checkbox" value="${index}" style="width:20px;height:20px; accent-color:#1db954;">
                            <img src="${item.thumbnail}" onclick="openFullThumbList('${item.thumbnail}')" style="cursor:pointer;">
                            <div class="info">
                                <h4 title="${item.title}">${item.title}</h4>
                                <p>${uploader} | ${item.duration}</p>
                                <div class="action-row">
                                    <button class="play-action-btn" onclick="playSingleAudio(${index})">▶ HEAR</button>
                                    <button class="dl-icon-btn" onclick="triggerDownload(${index}, 'mp3')">📥</button>
                                </div>
                            </div>
                        </div>`;
                } else {
                    container.innerHTML += `
                        <div class="card video-mode">
                            <img src="${item.thumbnail}" onclick="openFullThumbList('${item.thumbnail}')" style="cursor:pointer;">
                            <div class="info">
                                <h4>${item.title}</h4>
                                <p>${uploader} • ${item.duration}</p>
                                <div class="action-row">
                                    <button class="play-action-btn" onclick="startVideo('${item.url || item.id}')">▶ PLAY VIDEO</button>
                                    <button class="dl-icon-btn" onclick="triggerDownload(${index}, 'mp4')">📥</button>
                                </div>
                            </div>
                        </div>`;
                }
            });
        }

        function toggleAll() { const c = document.getElementById('selectAll').checked; document.querySelectorAll('.song-checkbox').forEach(cb => cb.checked = c); }

        function openFullThumb(e) {
            if(e) e.stopPropagation();
            if(audioBar.classList.contains('mini')) return; 
            document.getElementById('fullThumbImg').src = document.getElementById('ap-cover').src;
            document.getElementById('thumbModal').style.display = 'flex';
        }
        
        function openFullThumbList(src) {
            document.getElementById('fullThumbImg').src = src;
            document.getElementById('thumbModal').style.display = 'flex';
        }

        let pendingDlUrl = ""; let pendingDlTitle = ""; let pendingDlType = ""; let pendingDlVidId = "";
        
        function triggerDownload(index, type) {
            const item = currentResults[index];
            pendingDlUrl = item.url || item.id; pendingDlTitle = item.title; pendingDlType = type;
            pendingDlVidId = item.id || pendingDlUrl.split('v=')[1];
            
            const list = document.getElementById('qualityList'); list.innerHTML = '';
            document.getElementById('modalTitle').innerText = type === 'mp4' ? "Select MP4 Quality" : "Select MP3 Quality";
            
            if(type === 'mp4') {
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('best')"><span>⭐ AUTO BEST</span></div><div class="quality-item" onclick="fireBgTask('1080p')"><span>📽️ 1080p</span></div><div class="quality-item" onclick="fireBgTask('720p')"><span>📽️ 720p</span></div>`;
            } else {
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('320')"><span>⭐ 320 kbps</span></div><div class="quality-item" onclick="fireBgTask('192')"><span>🎵 192 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }
        
        function downloadCurrentSong(e) {
            if(e) e.stopPropagation();
            if(currentIndex >= 0 && currentIndex < audioQueue.length) {
                const item = audioQueue[currentIndex];
                const currentVidId = item.id || (item.url ? item.url.split('v=')[1] : null);
                
                // V30: Check persistent dictionary
                if(activeSongDownloads[currentVidId]) return; // Already downloading
                
                pendingDlUrl = item.url || item.id; pendingDlTitle = item.title; pendingDlType = 'mp3';
                pendingDlVidId = currentVidId;
                const list = document.getElementById('qualityList'); list.innerHTML = '';
                document.getElementById('modalTitle').innerText = "Select MP3 Quality";
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('320', true)"><span>⭐ 320 kbps</span></div><div class="quality-item" onclick="fireBgTask('192', true)"><span>🎵 192 kbps</span></div>`;
                document.getElementById('qualityModal').style.display = 'flex';
            }
        }

        async function fireBgTask(quality, isFromPlayer = false) {
            document.getElementById('qualityModal').style.display = 'none';
            showToast("Download Sent to Server!", "info");
            let useAudioConv = localStorage.getItem('audio_conversion_enabled') ?? 'true'; useAudioConv = (useAudioConv === 'true');

            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ client_id: clientId, url: pendingDlUrl, title: pendingDlTitle, type: pendingDlType, quality: quality, burn_subs: false, use_conversion: useAudioConv }) 
                });
                const data = await res.json();
                if (data.task_id && pendingDlVidId) {
                    activeSongDownloads[pendingDlVidId] = data.task_id; // Register in persistent dict
                    checkCurrentSongDownloadState(); // Update UI instantly
                }
            } catch(e) { showToast("Download failed to start: " + e.message, "error");}
        }

        // Updates the main player button based on dictionary state
        function checkCurrentSongDownloadState() {
            if(currentIndex < 0 || currentIndex >= audioQueue.length) return;
            const item = audioQueue[currentIndex];
            const vidId = item.id || (item.url ? item.url.split('v=')[1] : null);
            const btn = document.getElementById('mainPlayerDlBtn');
            
            if (activeSongDownloads[vidId]) {
                btn.disabled = true; 
                // The polling interval will fill in the text and background
            } else {
                btn.innerText = '📥 Download';
                btn.style.background = '#1db954'; 
                btn.style.color = 'black';
                btn.disabled = false;
            }
        }

        setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks?client_id=${clientId}`);
                const tasks = await res.json();
                
                // V30: Loop through all active song downloads in the dict
                for (let vidId in activeSongDownloads) {
                    let tid = activeSongDownloads[vidId];
                    let t = tasks[tid];
                    
                    // If the task was cleared from backend or missing
                    if (!t) {
                        delete activeSongDownloads[vidId];
                        checkCurrentSongDownloadState();
                        continue;
                    }
                    
                    // If this task belongs to the CURRENTLY PLAYING song, update the UI button
                    if (currentIndex >= 0 && currentIndex < audioQueue.length) {
                        const currentItem = audioQueue[currentIndex];
                        const currentVidId = currentItem.id || (currentItem.url ? currentItem.url.split('v=')[1] : null);
                        
                        if (vidId === currentVidId) {
                            const btn = document.getElementById('mainPlayerDlBtn');
                            if (t.status === 'downloading' || t.status === 'processing') {
                                btn.innerText = t.status === 'processing' ? '⏳ Merging...' : `⏳ ${t.percent}%`;
                                btn.style.background = `linear-gradient(90deg, #1db954 ${t.percent}%, #333 ${t.percent}%)`;
                                btn.style.color = 'white';
                            } else if (t.status === 'completed') {
                                btn.innerText = '✅ SAVED'; btn.style.background = '#1db954'; btn.style.color='black';
                                showToast(`Finished: ${t.title}`, "success");
                                setTimeout(() => { delete activeSongDownloads[vidId]; checkCurrentSongDownloadState(); }, 4000);
                            } else if (t.status === 'error') {
                                btn.innerText = '❌ Error'; btn.style.background = '#ff0844'; btn.style.color='white';
                                showToast(t.error_msg, "error");
                                setTimeout(() => { delete activeSongDownloads[vidId]; checkCurrentSongDownloadState(); }, 3000);
                            }
                        }
                    }
                    
                    // Global logic for completed stuff (even if not playing)
                    if (t.status === 'completed') {
                        // Keep task in dict for 4 seconds then delete
                        setTimeout(() => { delete activeSongDownloads[vidId]; }, 4000);
                    }
                }
            } catch(e) {}
        }, 1000);

        // ==========================================
        // V30 VIDEO LOGIC
        // ==========================================
        async function startVideo(id) {
            stopAudio(null); 
            const modal = document.getElementById('video-modal');
            modal.classList.remove('mini-video');
            modal.style.display = 'flex';
            document.getElementById('ytIframe').src = `https://www.youtube.com/embed/${id}?autoplay=1&enablejsapi=1`;
            try { if (screen.orientation && screen.orientation.lock) await screen.orientation.lock("landscape"); } catch(e) {}
        }
        function toggleMiniVideo() {
            const modal = document.getElementById('video-modal');
            modal.classList.toggle('mini-video');
            try {
                if (modal.classList.contains('mini-video') && screen.orientation && screen.orientation.unlock) screen.orientation.unlock();
                else if (screen.orientation && screen.orientation.lock) screen.orientation.lock("landscape");
            } catch(e) {}
        }
        async function closeVideo() {
            document.getElementById('video-modal').style.display = 'none';
            document.getElementById('ytIframe').src = "";
            try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch(e) {}
        }

        // ==========================================
        // V30 AUDIO PLAYER ENGINE WITH CROSSFADE
        // ==========================================
        function openPlayerUI(e) {
            if(audioBar.classList.contains('mini')) {
                audioBar.classList.remove('mini');
            }
        }
        
        function toggleMiniPlayer(e) { 
            if(e) e.stopPropagation(); 
            audioBar.classList.toggle('mini'); 
        }

        function playSingleAudio(index) { audioQueue = currentResults; currentIndex = index; loadQueueItem(); }
        function playSelected() {
            const checked = document.querySelectorAll('.song-checkbox:checked');
            if(checked.length === 0) return alert("Select songs first!");
            audioQueue = Array.from(checked).map(cb => currentResults[parseInt(cb.value)]);
            currentIndex = 0; loadQueueItem();
        }

        function startFadeIn() {
            clearInterval(fadeInterval); isFadingOut = false; audioEngine.volume = 0;
            let targetVol = 1.0; 
            let step = targetVol / 30; 
            fadeInterval = setInterval(() => { if (audioEngine.volume + step < targetVol) { audioEngine.volume += step; } else { audioEngine.volume = targetVol; clearInterval(fadeInterval); } }, 100);
        }

        function startFadeOutAndNext() {
            if (isFadingOut) return;
            isFadingOut = true;
            let startVol = audioEngine.volume;
            let step = startVol / 30; 
            fadeInterval = setInterval(() => {
                if (audioEngine.volume > step) { audioEngine.volume -= step; } else { audioEngine.volume = 0; clearInterval(fadeInterval); nextSong(null); }
            }, 100);
        }

        async function loadQueueItem() {
            if(currentIndex < 0 || currentIndex >= audioQueue.length) return stopAudio(null);
            const item = audioQueue[currentIndex];
            const titleEl = document.getElementById('ap-title');
            
            audioBar.classList.add('active'); audioBar.classList.remove('mini');
            document.getElementById('ap-cover').src = item.thumbnail;
            document.getElementById('ap-artist').innerText = item.uploader || "Nexus Audio";
            document.getElementById('ap-yt-link').href = item.url || `https://youtube.com/watch?v=${item.id}`;
            
            titleEl.innerText = "Loading stream... "; titleEl.classList.remove('scroll');
            seekSlider.value = 0; seekSlider.style.background = `#4d4d4d`;
            
            checkCurrentSongDownloadState(); // V30 Check if already downloading
            
            try {
                const res = await fetch('/api/stream_audio', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: item.url || item.id}) });
                const data = await res.json();
                
                if(data.error) { showToast(data.error, "error"); nextSong(null); return; }
                
                if(data.stream_url) {
                    audioEngine.src = data.stream_url; audioEngine.playbackRate = currentSpeed; titleEl.innerText = item.title;
                    startFadeIn(); 
                    
                    setTimeout(() => { const wrapper = document.querySelector('.marquee-wrapper'); if (titleEl.scrollWidth > wrapper.clientWidth + 10) titleEl.classList.add('scroll'); }, 100);

                    if ('mediaSession' in navigator) {
                        navigator.mediaSession.metadata = new MediaMetadata({ title: item.title, artist: item.uploader || "Nexus Audio", artwork: [ { src: item.thumbnail, sizes: '512x512', type: 'image/jpeg' } ] });
                        navigator.mediaSession.setActionHandler('play', () => togglePlay(null)); navigator.mediaSession.setActionHandler('pause', () => togglePlay(null));
                        navigator.mediaSession.setActionHandler('previoustrack', () => prevSong(null)); navigator.mediaSession.setActionHandler('nexttrack', () => nextSong(null));
                    }
                }
            } catch (err) { showToast("Error loading stream.", "error"); nextSong(null); }
        }

        function togglePlay(e) { if(e) e.stopPropagation(); if(audioEngine.paused) audioEngine.play(); else audioEngine.pause(); }
        function nextSong(e) { 
            if(e) e.stopPropagation(); 
            clearInterval(fadeInterval); isFadingOut = false; 
            if (loopMode === 2) { audioEngine.currentTime = 0; audioEngine.play(); startFadeIn(); return; }
            if (currentIndex < audioQueue.length - 1) { currentIndex++; loadQueueItem(); }
            else if (loopMode === 1) { currentIndex = 0; loadQueueItem(); }
            else stopAudio(null);
        }
        function prevSong(e) { 
            if(e) e.stopPropagation();
            clearInterval(fadeInterval); isFadingOut = false;
            if(audioEngine.currentTime > 3 || loopMode === 2) { audioEngine.currentTime = 0; startFadeIn(); } 
            else if (currentIndex > 0) { currentIndex--; loadQueueItem(); } 
            else if (loopMode === 1) { currentIndex = audioQueue.length - 1; loadQueueItem(); }
        }
        function stopAudio(e) { 
            if(e) e.stopPropagation();
            clearInterval(fadeInterval); isFadingOut = false;
            audioEngine.pause(); audioEngine.src = ""; audioBar.classList.remove('active'); 
        }

        audioEngine.onended = () => { if(!isFadingOut) nextSong(null); };
        audioEngine.onplay = () => { playPauseBtn.innerText = '⏸'; };
        audioEngine.onpause = () => { playPauseBtn.innerText = '▶'; };

        function formatTimeDetailed(sec) {
            if(isNaN(sec)) return "0:00";
            let h = Math.floor(sec / 3600); let m = Math.floor((sec % 3600) / 60); let s = Math.floor(sec % 60);
            if (h > 0) return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
            return `${m}:${s < 10 ? '0' : ''}${s}`;
        }

        audioEngine.ontimeupdate = () => {
            let val = (audioEngine.currentTime / audioEngine.duration) * 100 || 0;
            seekSlider.value = val; seekSlider.style.background = `linear-gradient(to right, #1db954 ${val}%, #4d4d4d ${val}%)`;
            document.getElementById('currTime').innerText = formatTimeDetailed(audioEngine.currentTime);
            document.getElementById('durTime').innerText = formatTimeDetailed(audioEngine.duration);
            
            let timeLeft = audioEngine.duration - audioEngine.currentTime;
            if (timeLeft <= 3.0 && timeLeft > 0 && !isFadingOut && loopMode !== 2 && (currentIndex < audioQueue.length - 1 || loopMode === 1)) { startFadeOutAndNext(); }
        };
        seekSlider.oninput = (e) => { let val = e.target.value; audioEngine.currentTime = (val / 100) * audioEngine.duration; seekSlider.style.background = `linear-gradient(to right, #1db954 ${val}%, #4d4d4d ${val}%)`; };

        function toggleSpeed(e) {
            if(e) e.stopPropagation();
            if(currentSpeed === 1.0) currentSpeed = 1.25; else if(currentSpeed === 1.25) currentSpeed = 1.5; else if(currentSpeed === 1.5) currentSpeed = 2.0; else currentSpeed = 1.0;
            audioEngine.playbackRate = currentSpeed; document.getElementById('speedBtn').innerText = currentSpeed + 'x'; document.getElementById('speedBtn').classList.toggle('active', currentSpeed !== 1.0);
            showToast(`Speed: ${currentSpeed}x`, "info");
        }

        function toggleLoop(e) {
            if(e) e.stopPropagation();
            loopMode = (loopMode + 1) % 3;
            const btn = document.getElementById('loopBtn');
            if (loopMode === 0) { btn.innerText = '🔁'; btn.classList.remove('active'); showToast("Loop Off", "info"); }
            if (loopMode === 1) { btn.innerText = '🔁'; btn.classList.add('active'); showToast("Looping Queue", "info");} 
            if (loopMode === 2) { btn.innerText = '🔂'; btn.classList.add('active'); showToast("Looping Song", "info");} 
        }

        function openSleepModal(e) {
            if(e) e.stopPropagation();
            const btn = document.getElementById('sleepBtn');
            if(sleepTimer) {
                clearInterval(sleepTimer); sleepTimer = null;
                btn.classList.remove('active'); document.getElementById('sleepRing').style.background = 'transparent';
                showToast("Sleep timer cancelled", "info"); return;
            }
            document.getElementById('sleepModal').style.display = 'flex';
        }

        function setSleepTimer() {
            const mins = parseInt(document.getElementById('sleepInput').value);
            if(isNaN(mins) || mins <= 0) return showToast("Enter a valid time", "error");
            
            document.getElementById('sleepModal').style.display = 'none';
            totalSleepTime = mins * 60; sleepTimeLeft = totalSleepTime;
            document.getElementById('sleepBtn').classList.add('active');
            showToast(`Pausing in ${mins} minutes`, "success");
            
            sleepTimer = setInterval(() => {
                sleepTimeLeft--;
                let pct = (sleepTimeLeft / totalSleepTime) * 100;
                document.getElementById('sleepRing').style.background = `conic-gradient(#1db954 ${pct}%, transparent ${pct}%)`;
                
                if(sleepTimeLeft <= 0) {
                    clearInterval(sleepTimer); sleepTimer = null;
                    document.getElementById('sleepBtn').classList.remove('active');
                    document.getElementById('sleepRing').style.background = 'transparent';
                    
                    audioEngine.pause();
                    try { document.getElementById('ytIframe').contentWindow.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*'); } catch(e) {}
                    showToast("Sleep Timer finished. Paused.", "info");
                }
            }, 1000);
        }

        function shareSong(e) {
            if(e) e.stopPropagation();
            if(currentIndex >= 0 && currentIndex < audioQueue.length) {
                const item = audioQueue[currentIndex];
                if (navigator.share) { navigator.share({ title: item.title, text: 'Check out this song!', url: item.url || `https://youtube.com/watch?v=${item.id}` }); } 
                else { navigator.clipboard.writeText(item.url || `https://youtube.com/watch?v=${item.id}`); showToast("Link copied!"); }
            }
        }
    </script>
</body>
</html>
"""

# ==============================================================================
# BACKEND ROUTING
# ==============================================================================
@app.route('/manifest.json')
def serve_manifest():
    return jsonify({"name": "YouTube Downloader", "short_name": "YT Downloader", "start_url": "/", "display": "standalone", "background_color": "#1e3c72", "theme_color": "#1e3c72", "icons": [{"src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%231e3c72'/%3E%3Ctext y='70' x='25' font-size='60'%3E⚡%3C/text%3E%3C/svg%3E", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"}], "share_target": { "action": "/", "method": "GET", "enctype": "application/x-www-form-urlencoded", "params": { "title": "title", "text": "text", "url": "url" } }})

@app.route('/sw.js')
def serve_sw(): return Response("self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });", mimetype='application/javascript')

@app.route('/')
def index(): return DOWNLOADER_HTML

@app.route('/player')
def media_player(): return PLAYER_HTML

@app.route('/api/stream_audio', methods=['POST'])
def stream_audio():
    url = request.json.get('url')
    # PROXY REMOVED FOR MAXIMUM SPEED
    ydl_opts = { 'quiet': True, 'format': 'bestaudio[ext=m4a]/bestaudio/best', 'noplaylist': True, 'geo_bypass': True, 'geo_bypass_country': 'US'}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url') 
            if stream_url: return jsonify({'stream_url': stream_url})
            else: return jsonify({'error': 'No stream found.'}), 400
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    client_id = request.args.get('client_id')
    return jsonify({k: v for k, v in active_tasks.items() if v.get('client_id') == client_id})

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    limit = request.json.get('limit', 10) 
    if mode != 'search' and 'list=RD' in url: return jsonify({'error': 'Infinite loop detected.'})

    # PROXY REMOVED
    ydl_opts = {'quiet': True, 'color': 'no_color', 'extract_flat': True if mode in ['playlist', 'search'] else False, 'noplaylist': mode in ['single', 'search'], 'geo_bypass': True, 'geo_bypass_country': 'US'}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            fetch_url = f"ytsearch{limit}:{url}" if mode == 'search' else url
            info = ydl.extract_info(fetch_url, download=False)
            
            if mode in ['playlist', 'search']:
                entries = []
                for e in info.get('entries', []):
                    if not e: continue
                    thumb = e.get('thumbnails', [{'url': ''}])[-1]['url'] if e.get('thumbnails') else ''
                    duration_sec = e.get('duration')
                    if duration_sec:
                        m, s = divmod(int(duration_sec), 60); h, m = divmod(m, 60)
                        duration_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                    else: duration_str = "--:--"
                    entries.append({'id': e.get('id'), 'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': thumb, 'uploader': e.get('uploader') or e.get('channel') or 'Unknown Channel', 'views': e.get('view_count') or 0, 'duration': duration_str})
                return jsonify({'entries': entries})
            else:
                formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
                        res = f.get('format_note', f.get('resolution', 'Unknown'))
                        if res in ['2160p', '1440p', '1080p', '1080p60', '720p', '720p60', '480p', '360p']:
                            formats.append({'format_id': f['format_id'], 'resolution': res, 'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None})
                seen = set(); uniq = [f for f in reversed(formats) if not (f['resolution'] in seen or seen.add(f['resolution']))]
                uniq.sort(key=lambda f: int(f['resolution'].replace('p60', '').replace('p', '')) if f['resolution'].replace('p60', '').replace('p', '').isdigit() else 0, reverse=True)
                return jsonify({'id': info.get('id'), 'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': uniq})
    except Exception as e: return jsonify({'error': str(e).replace('\x1b[0;31m', '').replace('\x1b[0m', '')})

def background_downloader(task_id, url, dl_type, quality, burn_subs, use_conversion):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s', 'quiet': True, 'color': 'no_color', 
        'geo_bypass': True, 'geo_bypass_country': 'US', 'nocheckcertificate': True,
        'progress_hooks': [get_progress_hook(task_id)], 'noplaylist': True, 'ffmpeg_location': '/usr/bin/ffmpeg', 
        'external_downloader': 'aria2c', 'external_downloader_args': ['-j', '16', '-x', '16', '-s', '16', '-k', '1M'],
        'postprocessor_args': ['-threads', '0', '-preset', 'ultrafast', '-strict', 'experimental'],
    }

    if dl_type == 'mp4':
        if quality == 'best': ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        elif quality.endswith('p') and quality[:-1].isdigit(): ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}][ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else: ydl_opts['format'] = f"{quality}+bestaudio[ext=m4a]/best"
        if burn_subs: ydl_opts['writesubtitles'] = True; ydl_opts['subtitleslangs'] = ['en']; ydl_opts['postprocessors'] = [{'key': 'FFmpegEmbedSubtitle'}]
            
    elif dl_type == 'mp3':
        ydl_opts['writethumbnail'] = True 
        if use_conversion: ydl_opts['format'] = 'bestaudio/best'; ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}, {'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
        else: ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'; ydl_opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base_filename = ydl.prepare_filename(info)
            name_without_ext = os.path.splitext(base_filename)[0]
            actual_file = base_filename
            for possible_ext in ['.mp3', '.m4a', '.webm', '.opus', '.mp4', '.mkv']:
                if os.path.exists(name_without_ext + possible_ext):
                    actual_file = name_without_ext + possible_ext
                    break
            if dl_type == 'mp3' and not use_conversion:
                final_mp3_path = name_without_ext + '.mp3'
                if actual_file != final_mp3_path and os.path.exists(actual_file):
                    os.replace(actual_file, final_mp3_path) 
                    actual_file = final_mp3_path

            active_tasks[task_id]['status'] = 'completed'
            active_tasks[task_id]['file'] = actual_file
            active_tasks[task_id]['completed_at'] = time.time() 
    except Exception as e:
        active_tasks[task_id]['status'] = 'error'; active_tasks[task_id]['error_msg'] = str(e)

@app.route('/api/download', methods=['POST'])
def trigger_download():
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = {'client_id': request.json.get('client_id', 'unknown'), 'title': request.json.get('title', 'Unknown Task'), 'type': request.json.get('type'), 'status': 'starting', 'percent': 0, 'speed': '0 MB/s', 'eta': '--:--', 'file': None, 'error_msg': None, 'created_at': time.time()}
    threading.Thread(target=background_downloader, args=(task_id, request.json.get('url'), request.json.get('type'), request.json.get('quality'), request.json.get('burn_subs', False), request.json.get('use_conversion', True)), daemon=True).start()
    return jsonify({'task_id': task_id})

@app.route('/api/serve', methods=['GET'])
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    return send_file(os.path.abspath(file_path), as_attachment=True)

if __name__ == '__main__':
    print("\n" + "="*50 + "\n 🔥 YOUTUBE DOWNLOADER V33 ONLINE 🔥\n" + "="*50 + "\n")
    app.run(host="0.0.0.0", port=5000)
