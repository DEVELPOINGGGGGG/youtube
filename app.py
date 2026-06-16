# ==============================================================================
# YOUTUBE DOWNLOADER (V22 - RECOVERY PROTOCOL & BULK QUEUE)
# ==============================================================================

from flask import Flask, request, jsonify, render_template_string, send_file, Response
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

# Global Task Queue
active_tasks = {}

def cleanup_worker():
    # 10-Minute Aggressive Ghost Wipe for Files and Tasks
    while True:
        time.sleep(60) 
        now = time.time()
        try:
            for filename in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - 600:
                    try: 
                        os.remove(filepath)
                        logger.info(f"Ghost Wipe: Deleted expired file {filename}")
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
# MASSIVE FRONTEND UI TEMPLATE (HTML, CSS, JS)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>YouTube Downloader</title>
    
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#1e3c72">
    <meta name="apple-mobile-web-app-capable" content="yes">
    
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body { background: linear-gradient(-45deg, #1e3c72, #2a5298, #ff758c, #ff7eb3, #4facfe, #00f2fe); background-size: 600% 600%; animation: gradientBG 20s ease infinite; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; color: #333; padding: 20px; padding-bottom: 100px; overflow-x: hidden; }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        
        .glass-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(20px); border-radius: 24px; padding: 30px; width: 100%; max-width: 800px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); position: relative; z-index: 10; }
        .header-area { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .header-left { display: flex; align-items: center; gap: 15px; }
        
        .hamburger-btn { font-size: 1.8rem; cursor: pointer; color: #1e3c72; background: none; border: none; transition: 0.2s; }
        .hamburger-btn:hover { transform: scale(1.1); }
        .settings-btn { font-size: 1.5rem; cursor: pointer; color: #1e3c72; background: #e2e8f0; border: none; border-radius: 50%; width: 45px; height: 45px; display: flex; justify-content: center; align-items: center; transition: 0.2s; }
        .settings-btn:hover { background: #cbd5e0; transform: rotate(45deg); }
        
        h2 { font-weight: 800; font-size: 1.8rem; margin: 0; background: linear-gradient(45deg, #1e3c72, #ff0844); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .side-nav { position: fixed; top: 0; left: -300px; width: 280px; height: 100%; background: white; box-shadow: 5px 0 25px rgba(0,0,0,0.5); z-index: 9999; transition: left 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); display: flex; flex-direction: column; padding: 30px 20px; }
        .side-nav.open { left: 0; }
        .side-nav-close { align-self: flex-end; font-size: 2rem; cursor: pointer; border: none; background: none; color: #ff0844; margin-bottom: 20px; }
        .side-nav a { text-decoration: none; color: #333; font-weight: 800; font-size: 1.2rem; padding: 15px; border-radius: 12px; margin-bottom: 10px; transition: 0.2s; background: #f4f7f6; display: flex; align-items: center; justify-content: space-between; }
        .side-nav a:hover { background: #e0f2fe; color: #1e3c72; transform: translateX(10px); }
        .side-nav a.external { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; }
        .nav-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 9998; }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; }
        .tabs::-webkit-scrollbar { display: none; }
        .tab-btn { flex-shrink: 0; padding: 12px 25px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.3s; }
        .tab-btn.active { background: #4facfe; color: white; box-shadow: 0 5px 15px rgba(79, 172, 254, 0.4); }
        
        .input-group { position: relative; margin-bottom: 20px; display:flex; gap:10px;}
        input[type="text"] { flex: 1; padding: 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; background: #f8f9fa; }
        input[type="text"]:focus { border-color: #4facfe; box-shadow: 0 0 15px rgba(79, 172, 254, 0.4); background: white; }
        
        .paste-btn { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: #e2e8f0; border: none; padding: 10px 15px; border-radius: 8px; font-weight: 800; cursor: pointer; color: #1e3c72; transition: 0.2s; }
        .paste-btn:hover { background: #cbd5e0; }
        
        .action-btn { flex-shrink: 0; padding: 15px 25px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; transition: transform 0.2s; background: #333; }
        .action-btn:hover:not(:disabled) { transform: translateY(-3px); }
        .action-btn:disabled { background: #ccc !important; cursor: not-allowed; opacity: 0.7; }
        .btn-mp4 { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); } 
        .btn-mp3 { background: linear-gradient(135deg, #ff0844 0%, #ffb199 100%); }
        
        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center; transition: 0.3s; }
        
        #single-ui { display: none; }
        .list-container { display: none; flex-direction: column; gap: 10px; }
        .list-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; border: 1px solid transparent; overflow:hidden;}
        .list-item img { width: 150px; border-radius: 8px; cursor: pointer; transition: 0.2s; box-shadow: 0 5px 10px rgba(0,0,0,0.1); }
        .list-item img:hover { filter: brightness(0.7); transform: scale(1.05); }
        
        .item-info { flex: 1; min-width: 0; display:flex; flex-direction:column; justify-content:center;}
        .scrolling-title { font-size: 0.95rem; margin-bottom: 5px; white-space: nowrap; overflow-x: auto; scrollbar-width: none; -webkit-overflow-scrolling: touch; padding-bottom:3px;}
        .scrolling-title::-webkit-scrollbar { display: none; }
        
        .btn-scroll-container { display: flex; gap: 10px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; }
        .btn-scroll-container::-webkit-scrollbar { display: none; }
        
        .progress-container { background: #fff; padding: 12px; border-radius: 12px; margin-top: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #eee;}
        .progress-bar-bg { width: 100%; height: 10px; background: #e2e8f0; border-radius: 10px; overflow: hidden; margin: 8px 0; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); transition: width 0.3s ease; }
        .progress-stats { display: flex; justify-content: space-between; font-size: 0.75rem; color: #666; font-weight: 700; }
        
        .image-wrapper { border-radius: 16px; overflow: hidden; margin-bottom: 20px; position: relative; cursor: pointer; }
        .image-wrapper::after { content: "▶ PLAY"; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.8); color: white; padding: 10px 25px; border-radius: 30px; font-weight: 800; font-size: 1.2rem; opacity: 0; transition: 0.3s; }
        .image-wrapper:hover::after { opacity: 1; }
        .image-wrapper img { width: 100%; display: block; }
        
        .fab { position: fixed; bottom: 30px; right: 30px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 15px 25px; border-radius: 50px; font-weight: 800; box-shadow: 0 10px 25px rgba(17, 153, 142, 0.5); cursor: pointer; z-index: 1000; display: flex; align-items: center; gap: 10px; }
        .fab:hover { transform: scale(1.05); }
        .badge { background: #ff0844; padding: 2px 8px; border-radius: 20px; font-size: 0.8rem; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); backdrop-filter: blur(8px); z-index: 3000; justify-content: center; align-items: center; padding: 20px; }
        .modal-box { background: white; width: 100%; max-width: 600px; border-radius: 24px; padding: 30px; position: relative; max-height: 85vh; overflow-y: auto; }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; font-size: 1.2rem; cursor: pointer; display: flex; justify-content: center; align-items: center; }
        .btn-close:hover { transform: scale(1.1) rotate(90deg); }

        .quality-item { background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .quality-item:hover { background: #e0f2fe; border-color: #4facfe; }
        .quality-item.best { border-color: #ff0844; background: #fff0f2; }
        
        .task-item { background: #f8f9fa; border: 1px solid #e9ecef; padding: 20px; border-radius: 16px; margin-bottom: 15px; }
        .task-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 15px; font-size: 0.95rem; border-bottom: 1px solid #eee; padding-bottom: 10px;}
        
        .video-modal-content { position: relative; width: 100%; max-width: 900px; background: #000; border-radius: 16px; overflow: hidden; aspect-ratio: 16 / 9; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
        .video-modal-content iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }
        
        .switch-container { display: flex; align-items: center; justify-content: space-between; background: #e0f2fe; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 2px solid #a1c4fd;}
        input[type="checkbox"] { width: 20px; height: 20px; cursor: pointer; accent-color: #4facfe; }

        @media (max-width: 600px) { 
            .list-item { flex-direction: column; align-items: stretch; } 
            .list-item img { width: 100%; height: auto; aspect-ratio: 16/9; object-fit: cover;} 
            .action-btn { flex: 1; text-align: center; justify-content: center; display: flex;}
            .paste-btn { position: relative; right: auto; top: auto; transform: none; width: 100%; padding: 15px; margin-top: 10px; }
            .input-group { flex-direction: column; }
            .side-nav { width: 250px; }
        }
    </style>
</head>
<body>

    <div class="nav-overlay" id="navOverlay" onclick="toggleMenu()"></div>
    <div class="side-nav" id="sideNav">
        <button class="side-nav-close" onclick="toggleMenu()">×</button>
        <h2 style="margin-bottom: 30px; text-align: center;">YOUTUBE DOWNLOADER</h2>
        <a href="#" onclick="switchTab('single'); toggleMenu()">🎬 Single Video</a>
        <a href="#" onclick="switchTab('playlist'); toggleMenu()">📂 Playlist Mode</a>
        <a href="#" onclick="switchTab('search'); toggleMenu()">🔍 Search YouTube</a>
        <div style="height: 1px; background: #ddd; margin: 20px 0;"></div>
        <a href="https://translator-l3x0.onrender.com" target="_blank" class="external">🌐 Translator App <span>↗</span></a>
    </div>

    <div class="glass-card">
        <div class="header-area">
            <div class="header-left">
                <button class="hamburger-btn" onclick="toggleMenu()">☰</button>
                <h2>YT DOWNLOADER</h2>
            </div>
            <button class="settings-btn" onclick="document.getElementById('settingsModal').style.display='flex'">⚙️</button>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('single')">Single Video</button>
            <button class="tab-btn" onclick="switchTab('playlist')">Playlist Mode</button>
            <button class="tab-btn" onclick="switchTab('search')">Search YouTube</button>
        </div>

        <div class="input-group" id="inputWrapper">
            <input type="text" id="url" placeholder="Paste URL..." autocomplete="off">
            <button class="paste-btn" id="pasteBtn" onclick="pasteLink()">PASTE</button>
            <button class="action-btn" id="goBtn" style="display:none; padding:15px 30px;" onclick="handleInput()">GO</button>
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <div id="single-ui">
            <div class="image-wrapper" onclick="openPlayer(currentVideoId, -1)"><img id="s-thumb" src=""></div>
            <h3 id="s-title" class="scrolling-title" style="margin-bottom: 15px;"></h3>
            <div class="btn-scroll-container" id="s-btns" style="display:none; margin-bottom:15px;">
                <button class="action-btn btn-mp4" onclick="openQuality(-1, 'mp4')">DOWNLOAD MP4</button>
                <button class="action-btn btn-mp3" onclick="openQuality(-1, 'mp3')">DOWNLOAD MP3</button>
            </div>
            
            <div class="progress-container" id="progBox-single" style="display:none;">
                <div class="progress-stats"><span id="progStatus-single">Downloading...</span><span id="progPercent-single">0%</span></div>
                <div class="progress-bar-bg"><div class="progress-fill" id="progFill-single"></div></div>
                <div class="progress-stats"><span id="progSpeed-single">0 MB/s</span><span id="progEta-single">ETA: 00:00</span></div>
            </div>
        </div>

        <div id="list-container" class="list-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:10px;" id="bulk-actions">
                <div style="display:flex; align-items:center; gap:8px;">
                    <input type="checkbox" id="selectAll" onclick="toggleAll()"> 
                    <strong>Select All</strong>
                </div>
                <div class="btn-scroll-container">
                    <button class="action-btn btn-mp4" style="padding: 10px 20px;" onclick="downloadBulk('mp4')">DL SELECTED MP4</button>
                    <button class="action-btn btn-mp3" style="padding: 10px 20px;" onclick="downloadBulk('mp3')">DL SELECTED MP3</button>
                </div>
            </div>
            <div id="items-wrapper" style="display:flex; flex-direction:column; gap:12px;"></div>
        </div>
    </div>

    <div class="fab" onclick="document.getElementById('taskModal').style.display='flex'">
        📥 Queue <span class="badge" id="taskBadge">0</span>
    </div>

    <div class="modal-overlay" id="recoveryModal" style="z-index: 4000;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h2 style="font-size:1.5rem; color:#d32f2f;">⚠️ Unsaved Downloads</h2>
                <button class="btn-close" onclick="document.getElementById('recoveryModal').style.display='none'">X</button>
            </div>
            <p style="margin-bottom:15px; font-size:0.9rem; color:#555;">These videos finished processing while the app was closed. You have less than 5 minutes to save them before they are permanently deleted.</p>
            <div id="recoveryList" style="display:flex; flex-direction:column; gap:10px; margin-bottom:20px; max-height:200px; overflow-y:auto;"></div>
            <button class="action-btn btn-mp4" style="width:100%; padding:15px; font-size:1.1rem; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);" onclick="downloadRecovered()">⬇ DOWNLOAD ALL SAVED VIDEOS</button>
        </div>
    </div>

    <div class="modal-overlay" id="settingsModal" style="z-index: 3500;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                <h2 style="font-size:1.5rem;">App Settings</h2>
                <button class="btn-close" onclick="document.getElementById('settingsModal').style.display='none'">X</button>
            </div>
            <div class="switch-container">
                <div>
                    <label for="audioConvToggle" style="font-weight:800; color:#1e3c72; display:block; cursor:pointer;">Strict Audio Conversion</label>
                    <p style="font-size:0.75rem; color:#666; margin-top:5px;">
                        <strong>ON:</strong> Uses FFmpeg to perfectly encode MP3s (Slower).<br>
                        <strong>OFF:</strong> Downloads raw audio, injects Metadata, and renames to .mp3 (Blazing Fast).
                    </p>
                </div>
                <input type="checkbox" id="audioConvToggle" onchange="saveSettings()">
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="taskModal" style="z-index: 2500;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                <h2 style="font-size:1.5rem;">Background Tasks</h2>
                <button class="btn-close" onclick="document.getElementById('taskModal').style.display='none'">X</button>
            </div>
            <div id="tasksWrapper"><p style="text-align:center; color:#888; font-weight:600;">No active downloads.</p></div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h3 id="modalTitle">Select Quality</h3>
                <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            </div>
            <div id="subToggle" class="switch-container" style="display:none;">
                <label for="burnSubs" style="font-weight:700; color:#1e3c72; cursor:pointer;">💬 Burn English Subtitles</label>
                <input type="checkbox" id="burnSubs">
            </div>
            <div id="id3Notice" class="switch-container" style="display:none; background:#d4edda; border-color:#28a745;">
                <label style="font-weight:700; color:#155724;">🎵 Metadata & Cover Art Included</label>
            </div>
            <div id="qualityList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
    </div>

    <div class="modal-overlay" id="videoModal" style="flex-direction: column;">
        <div style="display:flex; gap:15px; margin-bottom:20px; flex-wrap:wrap; justify-content:center;">
            <button class="action-btn btn-mp4" id="playerDownloadBtn" style="padding: 12px 30px; font-size:1.1rem; box-shadow: 0 10px 20px rgba(0,0,0,0.5);">⬇ DOWNLOAD VIDEO</button>
            <button class="action-btn btn-mp3" style="padding: 12px 30px; font-size:1.1rem; box-shadow: 0 10px 20px rgba(0,0,0,0.5);" onclick="closePlayer()">✖ CLOSE PLAYER</button>
        </div>
        <div class="video-modal-content">
            <iframe id="ytIframe" src="" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
    </div>

    <script>
        // PERSISTENT SESSION ID
        let clientId = localStorage.getItem('yt_dl_client_id');
        if (!clientId) {
            clientId = Math.random().toString(36).substring(2) + Date.now().toString(36);
            localStorage.setItem('yt_dl_client_id', clientId);
        }

        function loadSettings() {
            let audioConv = localStorage.getItem('audio_conversion_enabled');
            if (audioConv === null) {
                audioConv = 'true';
                localStorage.setItem('audio_conversion_enabled', 'true');
            }
            document.getElementById('audioConvToggle').checked = (audioConv === 'true');
        }
        function saveSettings() {
            const isChecked = document.getElementById('audioConvToggle').checked;
            localStorage.setItem('audio_conversion_enabled', isChecked ? 'true' : 'false');
        }
        
        function requestNotificationPermission() {
            if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
                Notification.requestPermission();
            }
        }
        window.addEventListener('click', requestNotificationPermission, {once: true});
        function showNotification(title, bodyText) {
            if ("Notification" in window && Notification.permission === "granted") {
                new Notification(title, { body: bodyText, icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%231e3c72'/%3E%3Ctext y='70' x='25' font-size='60'%3E⚡%3C/text%3E%3C/svg%3E" });
            }
        }

        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');

        let notifiedTasks = { started: [], completed: [] };
        let currentMode = 'single';
        let currentData = []; 
        let currentVideoId = ""; 
        let handledDownloads = [];
        let pendingDownloadTarget = null; 
        let taskDOMMap = {}; 
        let typingTimer; 
        
        // V22 Flags & Queues
        let initialLoad = true;
        let recoveredToDownload = [];
        let deliveryQueue = [];
        let isDelivering = false;

        window.addEventListener('DOMContentLoaded', () => {
            loadSettings(); 
            setTimeout(() => showNotification("YouTube Downloader", "Ready to fetch videos!"), 3000);
            
            const params = new URLSearchParams(window.location.search);
            const sharedData = params.get('url') || params.get('text') || params.get('title');
            if (sharedData) {
                const urlMatch = sharedData.match(/(https?:\/\/[^\s]+)/);
                if (urlMatch) {
                    switchTab('single');
                    document.getElementById('url').value = urlMatch[0];
                    handleInput(urlMatch[0]);
                }
            }
        });

        // 1-by-1 Smart Delivery System
        function processDeliveryQueue() {
            if(isDelivering || deliveryQueue.length === 0) return;
            isDelivering = true;
            
            const fileUrl = deliveryQueue.shift();
            const link = document.createElement('a');
            link.href = fileUrl;
            link.download = ''; 
            document.body.appendChild(link); 
            link.click(); 
            document.body.removeChild(link);
            
            setTimeout(() => {
                isDelivering = false;
                processDeliveryQueue();
            }, 1500); 
        }

        function showRecoveryModal(files) {
            const list = document.getElementById('recoveryList');
            list.innerHTML = '';
            files.forEach(f => {
                list.innerHTML += `<div style="padding:10px; background:#e0f2fe; border-radius:8px; font-weight:bold; font-size:0.85rem; border: 1px solid #a1c4fd;">${f.title}</div>`;
                recoveredToDownload.push(f.file);
            });
            document.getElementById('recoveryModal').style.display = 'flex';
        }

        function downloadRecovered() {
            document.getElementById('recoveryModal').style.display = 'none';
            recoveredToDownload.forEach(fUrl => {
                deliveryQueue.push('/api/serve?file=' + encodeURIComponent(fUrl));
            });
            processDeliveryQueue();
            recoveredToDownload = []; // Clear queue
        }

        function toggleMenu() {
            const nav = document.getElementById('sideNav');
            const overlay = document.getElementById('navOverlay');
            nav.classList.toggle('open');
            overlay.style.display = nav.classList.contains('open') ? 'block' : 'none';
        }

        function switchTab(mode) {
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const buttons = document.querySelectorAll('.tab-btn');
            if(mode === 'single') buttons[0].classList.add('active');
            if(mode === 'playlist') buttons[1].classList.add('active');
            if(mode === 'search') buttons[2].classList.add('active');
            
            const input = document.getElementById('url');
            input.placeholder = mode === 'search' ? "Type query..." : "Paste YouTube URL...";
            input.value = ''; 
            
            document.getElementById('list-container').style.display = 'none';
            document.getElementById('single-ui').style.display = 'none';
            
            if(mode === 'search') {
                document.getElementById('pasteBtn').style.display = 'none';
                document.getElementById('goBtn').style.display = 'block';
                input.style.paddingRight = "20px";
            } else {
                document.getElementById('pasteBtn').style.display = 'block';
                document.getElementById('goBtn').style.display = 'none';
                input.style.paddingRight = "90px";
            }
            setStatus(mode === 'search' ? "Ready to search YouTube." : "Awaiting Link...");
        }

        function setStatus(msg, isError=false) {
            const b = document.getElementById('statusBadge');
            b.innerText = msg; b.style.background = isError ? '#ffebee' : '#eee'; b.style.color = isError ? '#c62828' : '#333';
        }

        function isValidYouTubeUrl(url) { return url.includes('youtube.com') || url.includes('youtu.be'); }

        document.getElementById('url').addEventListener('input', (e) => {
            clearTimeout(typingTimer);
            let val = e.target.value.trim();
            if(!val) {
                document.getElementById('single-ui').style.display = 'none';
                document.getElementById('list-container').style.display = 'none';
                setStatus("Awaiting Input...");
                return;
            }
            setStatus("Waiting 3 seconds after typing to Auto-Fetch...");
            typingTimer = setTimeout(() => { handleInput(val); }, 3000); 
        });

        async function pasteLink() {
            try {
                const text = await navigator.clipboard.readText();
                document.getElementById('url').value = text;
                clearTimeout(typingTimer); 
                handleInput(text); 
            } catch (err) { alert("Clipboard denied."); }
        }

        function formatViews(views) {
            if(!views) return '0 Views';
            if(views >= 1000000) return (views/1000000).toFixed(1) + 'M Views';
            if(views >= 1000) return (views/1000).toFixed(1) + 'K Views';
            return views + ' Views';
        }

        async function handleInput(forcedValue = null) {
            let val = forcedValue || document.getElementById('url').value.trim();
            if(!val) return setStatus("Input empty.", true);
            
            if(currentMode !== 'search' && !isValidYouTubeUrl(val)) {
                return setStatus("Error: Unsupported Link. Only YouTube is supported.", true);
            }

            setStatus("Extracting Data...");
            document.getElementById('single-ui').style.display = 'none';
            document.getElementById('list-container').style.display = 'none';
            
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: val, mode: currentMode}) });
                const data = await res.json();
                
                if(data.error) return setStatus("Server Error: " + data.error, true);

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
                }
                setStatus("Data Ready.");
            } catch(e) { setStatus("Communication Error.", true); }
        }

        function renderItems() {
            const wrapper = document.getElementById('items-wrapper');
            wrapper.innerHTML = '';
            
            currentData.forEach((item, i) => {
                const videoId = item.id || (item.url ? item.url.split('v=')[1] : '');
                const uploader = item.uploader || 'Unknown Channel';
                const viewsStr = formatViews(item.views);
                const duration = item.duration || '--:--';
                
                const html = `
                    <div class="list-item">
                        <input type="checkbox" class="pl-checkbox" value="${i}">
                        
                        <div class="image-wrapper" onclick="openPlayer('${videoId}', ${i})" style="margin-bottom:0; min-width: 150px; width:150px;">
                            <img src="${item.thumbnail}" onerror="this.src='https://via.placeholder.com/150x84?text=No+Thumb'">
                        </div>
                        
                        <div class="item-info">
                            <h4 class="scrolling-title" title="${item.title}">${item.title}</h4>
                            <p style="font-size:0.8rem; color:#666; margin-bottom:5px;">
                                👤 <strong>${uploader}</strong><br>
                                ⏱️ ${duration} | 👁️ ${viewsStr}
                            </p>
                            
                            <div class="btn-scroll-container" style="padding-bottom:0; margin-top:5px;">
                                <button class="action-btn btn-mp4" style="padding:8px 15px; font-size:0.9rem;" onclick="openQuality(${i}, 'mp4')">MP4</button>
                                <button class="action-btn btn-mp3" style="padding:8px 15px; font-size:0.9rem;" onclick="openQuality(${i}, 'mp3')">MP3</button>
                            </div>

                            <div class="progress-container" id="progBox-${i}" style="display:none;">
                                <div class="progress-stats"><span id="progStatus-${i}">Downloading...</span><span id="progPercent-${i}">0%</span></div>
                                <div class="progress-bar-bg"><div class="progress-fill" id="progFill-${i}"></div></div>
                                <div class="progress-stats"><span id="progSpeed-${i}">0 MB/s</span><span id="progEta-${i}">ETA: 00:00</span></div>
                            </div>
                        </div>
                    </div>
                `;
                wrapper.innerHTML += html;
            });
        }

        function toggleAll() {
            const checked = document.getElementById('selectAll').checked;
            document.querySelectorAll('.pl-checkbox').forEach(cb => cb.checked = checked);
        }

        function openPlayer(id, index) {
            if(!id) return;
            document.getElementById('ytIframe').src = `https://www.youtube.com/embed/${id}?autoplay=1`;
            document.getElementById('videoModal').style.display = 'flex';
            
            document.getElementById('playerDownloadBtn').onclick = () => {
                closePlayer();
                openQuality(index, 'mp4');
            };
        }
        function closePlayer() {
            document.getElementById('videoModal').style.display = 'none';
            document.getElementById('ytIframe').src = ""; 
        }

        async function openQuality(index, type, isBulk=false) {
            pendingDownloadTarget = { index: index, type: type, isBulk: isBulk };
            
            const list = document.getElementById('qualityList');
            const subToggle = document.getElementById('subToggle');
            const id3Notice = document.getElementById('id3Notice');
            list.innerHTML = '';
            
            if (type === 'mp4') {
                document.getElementById('modalTitle').innerText = "Select MP4 Video Quality";
                subToggle.style.display = 'flex'; 
                id3Notice.style.display = 'none'; 
                
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('best')"><span>⭐ AUTO BEST</span></div>`;
                
                if (isBulk) {
                    list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('1080p')"><span>📽️ 1080p MAX</span></div>`;
                    list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('720p')"><span>📽️ 720p HIGH</span></div>`;
                    list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('480p')"><span>📽️ 480p MED</span></div>`;
                } else {
                    let actualIndex = index === -1 ? 0 : index;
                    if (!currentData[actualIndex].formats) {
                        setStatus("Fetching formats...");
                        try {
                            const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: currentData[actualIndex].url, mode: 'single'}) });
                            const data = await res.json();
                            if(data.formats) currentData[actualIndex].formats = data.formats;
                            setStatus("Formats ready.");
                        } catch(e) {}
                    }
                    if(currentData[actualIndex].formats) {
                        currentData[actualIndex].formats.forEach(f => {
                            let sz = f.filesize ? `~${f.filesize}MB` : '';
                            list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('${f.format_id}')"><span>📽️ ${f.resolution}</span> <span class="size-badge">${sz}</span></div>`;
                        });
                    }
                }
            } else {
                document.getElementById('modalTitle').innerText = "Select MP3 Audio Quality";
                subToggle.style.display = 'none'; 
                id3Notice.style.display = 'flex'; 
                
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('320')"><span>⭐ 320 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('192')"><span>🎵 192 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('128')"><span>📱 128 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }

        function downloadBulk(type) {
            const checkboxes = document.querySelectorAll('.pl-checkbox:checked');
            if(checkboxes.length === 0) return alert("Select at least one video!");
            openQuality(null, type, true);
        }

        async function startBackgroundDownload(quality) {
            document.getElementById('qualityModal').style.display = 'none';
            const burnSubs = document.getElementById('burnSubs') ? document.getElementById('burnSubs').checked : false;
            const useAudioConv = document.getElementById('audioConvToggle').checked;

            if (pendingDownloadTarget.isBulk) {
                const checkboxes = document.querySelectorAll('.pl-checkbox:checked');
                checkboxes.forEach(async (cb) => {
                    let idx = parseInt(cb.value);
                    let item = currentData[idx];
                    
                    const res = await fetch('/api/download', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ client_id: clientId, url: item.url, title: item.title, type: pendingDownloadTarget.type, quality: quality, burn_subs: burnSubs, use_conversion: useAudioConv })
                    });
                    const data = await res.json();
                    
                    if(data.task_id) {
                        taskDOMMap[data.task_id] = { isSingle: false, index: idx };
                        document.getElementById(`progBox-${idx}`).style.display = 'block';
                    }
                });
                setStatus(`Dispatched ${checkboxes.length} items.`);
                
            } else {
                let actualIndex = pendingDownloadTarget.index === -1 ? 0 : pendingDownloadTarget.index; 
                const item = currentData[actualIndex];
                
                const reqData = {
                    client_id: clientId, 
                    url: item.url || item.webpage_url || document.getElementById('url').value,
                    title: item.title || "Unknown Task",
                    type: pendingDownloadTarget.type,
                    quality: quality,
                    burn_subs: burnSubs,
                    use_conversion: useAudioConv
                };
                
                setStatus("Task dispatched.");
                const res = await fetch('/api/download', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(reqData) });
                const data = await res.json();
                
                if(data.task_id) {
                    taskDOMMap[data.task_id] = { isSingle: pendingDownloadTarget.index === -1, index: actualIndex };
                    if(pendingDownloadTarget.index === -1) {
                        document.getElementById('progBox-single').style.display = 'block';
                    } else {
                        document.getElementById(`progBox-${actualIndex}`).style.display = 'block';
                    }
                }
            }
            document.getElementById('taskModal').style.display = 'flex'; 
        }

        // V22: REAL-TIME SYNC & RECOVERY ENGINE
        setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks?client_id=${clientId}`);
                const tasks = await res.json();
                
                const wrapper = document.getElementById('tasksWrapper');
                const badge = document.getElementById('taskBadge');
                
                let html = '';
                let activeCount = 0;
                let nowSec = Date.now() / 1000; 
                
                let newlyRecovered = [];

                for (const [id, t] of Object.entries(tasks)) {
                    activeCount++;
                    let sCol = t.status==='completed' ? '#155724' : (t.status==='error' ? '#721c24' : '#004085');
                    let sBg = t.status==='completed' ? '#d4edda' : (t.status==='error' ? '#f8d7da' : '#cce5ff');
                    
                    if ((t.status === 'downloading' || t.status === 'processing') && !notifiedTasks.started.includes(id)) {
                        notifiedTasks.started.push(id);
                        showNotification("Download Processing 🔄", `Server is working on: ${t.title}`);
                    }

                    let isExpired = false;
                    let saveBtnHtml = `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px;" onclick="window.location.href='/api/serve?file=${encodeURIComponent(t.file)}'">💾 SAVE FILE NOW</button>`;
                    
                    if (t.status === 'completed' && t.completed_at) {
                        if ((nowSec - t.completed_at) > 300) { // Over 5 mins
                            isExpired = true;
                            saveBtnHtml = `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px; background:#e67e22;" onclick="window.location.href='/api/serve?file=${encodeURIComponent(t.file)}'">💾 AUTO-SAVE EXPIRED (CLICK TO MANUAL SAVE)</button>`;
                        }
                    }

                    html += `
                        <div class="task-item" style="background: ${sBg}; border-color: ${sCol}44;">
                            <div class="task-header" style="color: ${sCol};">
                                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:75%;">${t.type.toUpperCase()}: ${t.title}</span>
                                <span>${t.status.toUpperCase()}</span>
                            </div>
                            ${(t.status === 'downloading' || t.status === 'processing') ? `
                                <div class="progress-bar-bg"><div class="progress-fill" style="width: ${t.percent}%"></div></div>
                                <div class="progress-stats"><span>${t.percent}%</span> <span>${t.speed}</span> <span>ETA: ${t.eta}</span></div>
                            ` : ''}
                            ${t.status === 'error' ? `<div style="font-size:0.85rem; color:red;">${t.error_msg}</div>` : ''}
                            ${t.status === 'completed' ? saveBtnHtml : ''}
                        </div>
                    `;

                    // Update Inline UI
                    const mapData = taskDOMMap[id];
                    if (mapData) {
                        const prefix = mapData.isSingle ? '-single' : `-${mapData.index}`;
                        const progBox = document.getElementById(`progBox${prefix}`);
                        if (progBox) {
                            const fill = document.getElementById(`progFill${prefix}`);
                            const percent = document.getElementById(`progPercent${prefix}`);
                            const status = document.getElementById(`progStatus${prefix}`);
                            const speed = document.getElementById(`progSpeed${prefix}`);
                            const eta = document.getElementById(`progEta${prefix}`);

                            if (t.status === 'downloading' || t.status === 'processing') {
                                fill.style.width = t.percent + '%';
                                percent.innerText = t.percent + '%';
                                status.innerText = t.status === 'processing' ? 'Merging...' : 'Downloading...';
                                speed.innerText = t.speed;
                                eta.innerText = 'ETA: ' + t.eta;
                            } else if (t.status === 'completed' || t.status === 'error') {
                                status.innerText = t.status === 'completed' ? 'Done!' : 'Error';
                                status.style.color = t.status === 'completed' ? 'green' : 'red';
                                fill.style.width = t.status === 'completed' ? '100%' : '0%';
                                fill.style.background = t.status === 'completed' ? '#38ef7d' : 'red';
                                speed.innerText = ''; eta.innerText = '';
                            }
                        }
                    }

                    // V22: RECOVERY OR AUTO-DELIVERY
                    if (t.status === 'completed' && !handledDownloads.includes(id)) {
                        
                        if (initialLoad && !isExpired) {
                            // Recovered from closed app state
                            newlyRecovered.push({ id: id, title: t.title, file: t.file });
                        } else if (!initialLoad && !isExpired) {
                            // Standard auto-delivery (app was open during completion)
                            handledDownloads.push(id);
                            
                            if (!notifiedTasks.completed.includes(id)) {
                                notifiedTasks.completed.push(id);
                                showNotification("Download Ready! ✅", `${t.title} is being sent to your device.`);
                            }
                            deliveryQueue.push('/api/serve?file=' + encodeURIComponent(t.file));
                            processDeliveryQueue();
                        } else if (isExpired) {
                            // It's too old to auto-deliver or recover via pop-up, mark as handled so we stop checking
                            handledDownloads.push(id);
                        }
                    }
                }
                
                // V22 Trigger Recovery Modal
                if (initialLoad && newlyRecovered.length > 0) {
                    showRecoveryModal(newlyRecovered);
                }
                initialLoad = false; // Turn off initial load flag after first poll
                
                if(html === '') html = '<p style="text-align:center; color:#888;">No active downloads.</p>';
                wrapper.innerHTML = html;
                badge.innerText = activeCount;
                
            } catch(e) {}
        }, 1000); 
    </script>
</body>
</html>
"""

# ==============================================================================
# PWA ROUTING
# ==============================================================================
@app.route('/manifest.json')
def serve_manifest():
    return jsonify({
        "name": "YouTube Downloader", "short_name": "YT Downloader", "start_url": "/?source=pwa", "display": "standalone",
        "background_color": "#1e3c72", "theme_color": "#1e3c72",
        "icons": [{"src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%231e3c72'/%3E%3Ctext y='70' x='25' font-size='60'%3E⚡%3C/text%3E%3C/svg%3E", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"}],
        "share_target": { "action": "/", "method": "GET", "enctype": "application/x-www-form-urlencoded", "params": { "title": "title", "text": "text", "url": "url" } }
    })

@app.route('/sw.js')
def serve_sw():
    return Response("self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });", mimetype='application/javascript')

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    client_id = request.args.get('client_id')
    filtered_tasks = {k: v for k, v in active_tasks.items() if v.get('client_id') == client_id}
    return jsonify(filtered_tasks)

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    
    if mode != 'search' and 'list=RD' in url: 
        return jsonify({'error': 'YouTube Mixes are infinite loops.'})

    ydl_opts = {
        'quiet': True, 'color': 'no_color', 'proxy': 'socks5://127.0.0.1:40000', 
        'extract_flat': True if mode in ['playlist', 'search'] else False,
        'noplaylist': mode in ['single', 'search']
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            fetch_url = f"ytsearch10:{url}" if mode == 'search' else url
            info = ydl.extract_info(fetch_url, download=False)
            
            if mode in ['playlist', 'search']:
                entries = []
                for e in info.get('entries', []):
                    if not e: continue
                    thumb = e.get('thumbnails', [{'url': ''}])[-1]['url'] if e.get('thumbnails') else ''
                    uploader = e.get('uploader') or e.get('channel') or 'Unknown Channel'
                    view_count = e.get('view_count') or 0
                    duration_sec = e.get('duration')
                    if duration_sec:
                        m, s = divmod(int(duration_sec), 60)
                        h, m = divmod(m, 60)
                        duration_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                    else: duration_str = "--:--"

                    entries.append({'id': e.get('id'), 'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': thumb, 'uploader': uploader, 'views': view_count, 'duration': duration_str})
                return jsonify({'entries': entries})
            else:
                formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
                        res = f.get('format_note', f.get('resolution', 'Unknown'))
                        if res in ['2160p', '1440p', '1080p', '1080p60', '720p', '720p60', '480p', '360p']:
                            formats.append({'format_id': f['format_id'], 'resolution': res, 'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None})
                seen = set()
                uniq = [f for f in reversed(formats) if not (f['resolution'] in seen or seen.add(f['resolution']))]
                uniq.sort(key=lambda f: int(f['resolution'].replace('p60', '').replace('p', '')) if f['resolution'].replace('p60', '').replace('p', '').isdigit() else 0, reverse=True)
                return jsonify({'id': info.get('id'), 'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': uniq})
    except Exception as e:
        return jsonify({'error': str(e).replace('\x1b[0;31m', '').replace('\x1b[0m', '')})

def background_downloader(task_id, url, dl_type, quality, burn_subs, use_conversion):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True, 'color': 'no_color', 'proxy': 'socks5://127.0.0.1:40000', 
        'geo_bypass': True, 'nocheckcertificate': True,
        'progress_hooks': [get_progress_hook(task_id)], 'noplaylist': True,
        'ffmpeg_location': '/usr/bin/ffmpeg', 
        'external_downloader': 'aria2c', 'external_downloader_args': ['-j', '16', '-x', '16', '-s', '16', '-k', '1M'],
        'postprocessor_args': ['-threads', '0', '-preset', 'ultrafast', '-strict', 'experimental'],
    }

    if dl_type == 'mp4':
        if quality == 'best': ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        elif quality.endswith('p') and quality[:-1].isdigit():
            height = quality[:-1]
            ydl_opts['format'] = f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f"{quality}+bestaudio[ext=m4a]/best"
            
        if burn_subs:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['en']
            ydl_opts['postprocessors'] = [{'key': 'FFmpegEmbedSubtitle'}]
            
    elif dl_type == 'mp3':
        ydl_opts['writethumbnail'] = True 
        if use_conversion:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}, {'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
        else:
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            ydl_opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]

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
        active_tasks[task_id]['status'] = 'error'
        active_tasks[task_id]['error_msg'] = str(e)

@app.route('/api/download', methods=['POST'])
def trigger_download():
    task_id = str(uuid.uuid4())
    client_id = request.json.get('client_id', 'unknown')
    
    active_tasks[task_id] = {
        'client_id': client_id,
        'title': request.json.get('title', 'Unknown Task'), 'type': request.json.get('type'),
        'status': 'starting', 'percent': 0, 'speed': '0 MB/s', 'eta': '--:--', 'file': None, 'error_msg': None,
        'created_at': time.time()
    }
    
    threading.Thread(
        target=background_downloader, 
        args=(
            task_id, request.json.get('url'), request.json.get('type'), request.json.get('quality'), 
            request.json.get('burn_subs', False), request.json.get('use_conversion', True)
        ), 
        daemon=True
    ).start()
    
    return jsonify({'task_id': task_id})

@app.route('/api/serve', methods=['GET'])
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    return send_file(os.path.abspath(file_path), as_attachment=True)

if __name__ == '__main__':
    print("\n" + "="*50 + "\n 🔥 YOUTUBE DOWNLOADER V22 ONLINE 🔥\n" + "="*50 + "\n")
    app.run(host="0.0.0.0", port=5000)
