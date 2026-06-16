# ==============================================================================
# YOUTUBE DOWNLOADER (V17 - REDIS + CELERY + ID3 TAGS + SUBTITLES)
# ==============================================================================

from flask import Flask, request, jsonify, render_template_string, send_file
from celery import Celery
import yt_dlp
import os
import time
import uuid

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ==============================================================================
# REDIS & CELERY CONFIGURATION
# ==============================================================================
# Tells Celery to use the Redis database defined in docker-compose.yml
app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# ==============================================================================
# THE DISTRIBUTED CELERY WORKER TASK
# ==============================================================================
@celery.task(bind=True)
def background_downloader(self, client_id, url, dl_type, quality, burn_subs=False, title="Unknown"):
    """
    This function no longer runs on the web server. It runs inside the isolated
    Celery Worker container, streaming its progress back to Redis.
    """
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
            downloaded = d.get('downloaded_bytes', 0)
            percent = round((downloaded / total) * 100, 1) if total > 0 else 0
            speed = str(d.get('_speed_str', '0 MB/s')).replace('\x1b[0;94m', '').replace('\x1b[0m', '').strip()
            eta = str(d.get('_eta_str', '00:00')).replace('\x1b[0;93m', '').replace('\x1b[0m', '').strip()
            
            # Write progress to Redis Database
            self.update_state(state='DOWNLOADING', meta={
                'status': 'downloading', 'percent': percent, 'speed': speed, 'eta': eta, 
                'title': title, 'type': dl_type, 'client_id': client_id
            })
            
        elif d['status'] == 'finished':
            self.update_state(state='PROCESSING', meta={
                'status': 'processing', 'percent': 100, 'speed': 'Processing (FFmpeg)', 'eta': '--:--', 
                'title': title, 'type': dl_type, 'client_id': client_id
            })

    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True, 'color': 'no_color',
        'progress_hooks': [progress_hook], 'noplaylist': True,
        'ffmpeg_location': '/usr/bin/ffmpeg', 
        'external_downloader': 'aria2c', 
        'external_downloader_args': ['-j', '16', '-x', '16', '-s', '16', '-k', '1M'],
        'postprocessor_args': ['-threads', '0', '-preset', 'ultrafast'],
    }

    # ==========================================
    # MEDIA ENGINE UPGRADES (ID3 & SUBTITLES)
    # ==========================================
    if dl_type == 'mp4':
        ydl_opts['format'] = f"{quality}+bestaudio[ext=m4a]/best" if quality != 'best' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        
        # BURN SUBTITLES LOGIC
        if burn_subs:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['en'] # Grabs English
            ydl_opts['postprocessors'] = [{'key': 'FFmpegEmbedSubtitle'}] # Burns into MP4 track
            
    elif dl_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        
        # ID3 TAG METADATA INJECTION
        ydl_opts['writethumbnail'] = True # Downloads the cover art
        ydl_opts['postprocessors'] = [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality},
            {'key': 'EmbedThumbnail'}, # Embeds Cover Art into MP3 file
            {'key': 'FFmpegMetadata'}, # Embeds Title, Uploader, etc. into MP3 metadata
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            actual_file = ydl.prepare_filename(info)
            ext = os.path.splitext(actual_file)[1]
            if dl_type == 'mp3': actual_file = actual_file.replace(ext, '.mp3')
            elif dl_type == 'mp4': actual_file = actual_file.replace(ext, '.mp4')
            
            return {
                'status': 'completed', 'file': actual_file, 'title': title, 
                'type': dl_type, 'client_id': client_id, 'percent': 100
            }
    except Exception as e:
        return {'status': 'error', 'error_msg': str(e), 'title': title, 'type': dl_type, 'client_id': client_id}

# ==============================================================================
# MASSIVE FRONTEND UI TEMPLATE (HTML, CSS, JS)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>YouTube Downloader V17</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body { background: linear-gradient(-45deg, #1e3c72, #2a5298, #ff758c, #ff7eb3); background-size: 400% 400%; animation: gradientBG 20s ease infinite; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; color: #333; padding: 20px; padding-bottom: 100px; }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .glass-card { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(20px); border-radius: 24px; padding: 30px; width: 100%; max-width: 800px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
        .header-area { margin-bottom: 25px; text-align: center; }
        h2 { font-weight: 800; font-size: 1.8rem; margin: 0; background: linear-gradient(45deg, #1e3c72, #ff0844); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; }
        .tabs::-webkit-scrollbar { display: none; }
        .tab-btn { flex-shrink: 0; padding: 12px 25px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.3s; }
        .tab-btn.active { background: #4facfe; color: white; }
        
        .input-group { position: relative; margin-bottom: 20px; display:flex; gap:10px;}
        input[type="text"] { flex: 1; padding: 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; background: #f8f9fa; }
        input[type="text"]:focus { border-color: #4facfe; background: white; }
        .paste-btn { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: #e2e8f0; border: none; padding: 10px 15px; border-radius: 8px; font-weight: 800; cursor: pointer; color: #1e3c72; }
        .action-btn { flex-shrink: 0; padding: 15px 25px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; background: #333; }
        .btn-mp4 { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); } 
        .btn-mp3 { background: linear-gradient(135deg, #ff0844 0%, #ffb199 100%); }
        
        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center; }
        
        #single-ui, .list-container { display: none; flex-direction: column; gap: 10px; }
        .list-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; }
        .list-item img { width: 150px; border-radius: 8px; }
        .item-info { flex: 1; min-width: 0; }
        .item-info h4 { font-size: 0.95rem; margin-bottom: 5px; white-space: nowrap; overflow-x: auto; scrollbar-width: none; }
        .item-info h4::-webkit-scrollbar { display: none; }
        
        .btn-scroll-container { display: flex; gap: 10px; overflow-x: auto; white-space: nowrap; padding-bottom: 10px; scrollbar-width: none; }
        .btn-scroll-container::-webkit-scrollbar { display: none; }
        
        .image-wrapper { border-radius: 16px; overflow: hidden; margin-bottom: 20px; position: relative; cursor: pointer; }
        .image-wrapper img { width: 100%; display: block; }
        
        .fab { position: fixed; bottom: 30px; right: 30px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 15px 25px; border-radius: 50px; font-weight: 800; cursor: pointer; z-index: 1000; display: flex; align-items: center; gap: 10px; }
        .badge { background: #ff0844; padding: 2px 8px; border-radius: 20px; font-size: 0.8rem; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); z-index: 3000; justify-content: center; align-items: center; padding: 20px; }
        .modal-box { background: white; width: 100%; max-width: 600px; border-radius: 24px; padding: 30px; position: relative; max-height: 85vh; overflow-y: auto; }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; cursor: pointer; display: flex; justify-content: center; align-items: center; }

        .quality-item { background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .quality-item.best { border-color: #ff0844; background: #fff0f2; }
        
        .task-item { background: #f8f9fa; border: 1px solid #e9ecef; padding: 20px; border-radius: 16px; margin-bottom: 15px; }
        .task-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 15px; font-size: 0.95rem; border-bottom: 1px solid #eee; padding-bottom: 10px;}
        .progress-bar-bg { width: 100%; height: 10px; background: #e2e8f0; border-radius: 10px; overflow: hidden; margin: 8px 0; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); transition: width 0.3s ease; }
        .progress-stats { display: flex; justify-content: space-between; font-size: 0.75rem; color: #666; font-weight: 700; }
        
        /* Toggle Switch Styling */
        .switch-container { display: flex; align-items: center; justify-content: space-between; background: #e0f2fe; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 2px solid #a1c4fd;}
        input[type="checkbox"] { width: 20px; height: 20px; cursor: pointer; accent-color: #4facfe; }

        @media (max-width: 600px) { 
            .list-item { flex-direction: column; align-items: stretch; } 
            .list-item img { width: 100%; } 
            .action-btn { flex: 1; text-align: center; justify-content: center; display: flex;}
            .paste-btn { position: relative; right: auto; top: auto; transform: none; width: 100%; padding: 15px; margin-top: 10px; }
            .input-group { flex-direction: column; }
        }
    </style>
</head>
<body>

    <div class="glass-card">
        <div class="header-area"><h2>YT DOWNLOADER v17 (DISTRIBUTED)</h2></div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('single')">Single</button>
            <button class="tab-btn" onclick="switchTab('playlist')">Playlist</button>
            <button class="tab-btn" onclick="switchTab('search')">Search</button>
        </div>

        <div class="input-group">
            <input type="text" id="url" placeholder="Paste URL or Type Search..." autocomplete="off">
            <button class="paste-btn" id="pasteBtn" onclick="pasteLink()">PASTE</button>
            <button class="action-btn" id="goBtn" style="display:none; padding:15px 30px;" onclick="handleInput()">GO</button>
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <div id="single-ui">
            <div class="image-wrapper"><img id="s-thumb" src=""></div>
            <h3 id="s-title" style="margin-bottom: 15px; white-space:nowrap; overflow-x:auto; scrollbar-width:none;"></h3>
            <div class="btn-scroll-container" id="s-btns" style="display:none; margin-bottom:15px;">
                <button class="action-btn btn-mp4" onclick="openQuality(-1, 'mp4')">DOWNLOAD MP4</button>
                <button class="action-btn btn-mp3" onclick="openQuality(-1, 'mp3')">DOWNLOAD MP3</button>
            </div>
        </div>

        <div id="list-container" class="list-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:10px;" id="bulk-actions">
                <div><input type="checkbox" id="selectAll" onclick="toggleAll()"> <strong>Select All</strong></div>
                <div class="btn-scroll-container">
                    <button class="action-btn btn-mp4" style="padding: 10px 20px;" onclick="downloadBulk('mp4')">DL MP4</button>
                    <button class="action-btn btn-mp3" style="padding: 10px 20px;" onclick="downloadBulk('mp3')">DL MP3</button>
                </div>
            </div>
            <div id="items-wrapper" style="display:flex; flex-direction:column; gap:12px;"></div>
        </div>
    </div>

    <div class="fab" onclick="document.getElementById('taskModal').style.display='flex'">
        📥 Queue <span class="badge" id="taskBadge">0</span>
    </div>

    <div class="modal-overlay" id="taskModal" style="z-index: 2500;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                <h2 style="font-size:1.5rem;">Celery Tasks</h2>
                <button class="btn-close" onclick="document.getElementById('taskModal').style.display='none'">X</button>
            </div>
            <div id="tasksWrapper"><p style="text-align:center; color:#888;">No active background tasks.</p></div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h3 id="modalTitle">Select Quality</h3>
                <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            </div>
            
            <div id="subToggle" class="switch-container" style="display:none;">
                <label for="burnSubs" style="font-weight:700; color:#1e3c72; cursor:pointer;">
                    💬 Burn English Subtitles
                </label>
                <input type="checkbox" id="burnSubs">
            </div>
            <div id="id3Notice" class="switch-container" style="display:none; background:#d4edda; border-color:#28a745;">
                <label style="font-weight:700; color:#155724;">
                    🎵 ID3 Tags & Cover Art Auto-Embedded
                </label>
            </div>

            <div id="qualityList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
    </div>

    <script>
        const clientId = Math.random().toString(36).substring(2) + Date.now().toString(36);
        let currentMode = 'single';
        let currentData = []; 
        let handledDownloads = [];
        let pendingDownloadTarget = null; 

        function switchTab(mode) {
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const buttons = document.querySelectorAll('.tab-btn');
            if(mode === 'single') buttons[0].classList.add('active');
            if(mode === 'playlist') buttons[1].classList.add('active');
            if(mode === 'search') buttons[2].classList.add('active');
            
            const input = document.getElementById('url');
            input.placeholder = mode === 'search' ? "Type query and hit GO..." : "Paste YouTube URL...";
            input.value = ''; 
            
            document.getElementById('list-container').style.display = 'none';
            document.getElementById('single-ui').style.display = 'none';
            document.getElementById('pasteBtn').style.display = mode === 'search' ? 'none' : 'block';
            document.getElementById('goBtn').style.display = mode === 'search' ? 'block' : 'none';
            setStatus(mode === 'search' ? "Ready to search." : "Awaiting Link...");
        }

        function setStatus(msg, isError=false) {
            const b = document.getElementById('statusBadge');
            b.innerText = msg; b.style.background = isError ? '#ffebee' : '#eee'; b.style.color = isError ? '#c62828' : '#333';
        }

        async function pasteLink() {
            try {
                const text = await navigator.clipboard.readText();
                document.getElementById('url').value = text;
                handleInput(); 
            } catch (err) { alert("Clipboard denied."); }
        }

        async function handleInput() {
            let val = document.getElementById('url').value.trim();
            if(!val) return setStatus("Input empty.", true);
            
            setStatus("Extracting Data...");
            document.getElementById('single-ui').style.display = 'none';
            document.getElementById('list-container').style.display = 'none';
            
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: val, mode: currentMode}) });
                const data = await res.json();
                
                if(data.error) return setStatus("Server Error: " + data.error, true);

                if(currentMode === 'single') {
                    currentData = [data];
                    document.getElementById('s-thumb').src = data.thumbnail;
                    document.getElementById('s-title').innerText = data.title;
                    document.getElementById('s-btns').style.display = 'flex';
                    document.getElementById('single-ui').style.display = 'block';
                    document.getElementById('bulk-actions').style.display = 'none';
                } else {
                    currentData = data.entries;
                    document.getElementById('bulk-actions').style.display = currentMode === 'search' ? 'none' : 'flex';
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
                const uploader = item.uploader || 'Unknown Channel';
                const html = `
                    <div class="list-item">
                        ${currentMode !== 'single' && currentMode !== 'search' ? `<input type="checkbox" class="pl-checkbox" value="${i}">` : ''}
                        <img src="${item.thumbnail}" style="width:150px; border-radius:8px;">
                        <div class="item-info">
                            <h4 style="white-space:nowrap; overflow-x:auto; scrollbar-width:none;">${item.title}</h4>
                            <p style="font-size:0.8rem; color:#666;">👤 ${uploader}</p>
                            <div class="btn-scroll-container" style="margin-top:5px;">
                                <button class="action-btn btn-mp4" style="padding:8px 15px;" onclick="openQuality(${i}, 'mp4')">MP4</button>
                                <button class="action-btn btn-mp3" style="padding:8px 15px;" onclick="openQuality(${i}, 'mp3')">MP3</button>
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

        async function openQuality(index, type) {
            let actualIndex = index === -1 ? 0 : index; 
            pendingDownloadTarget = { index: index, type: type, actualIndex: actualIndex };
            
            const list = document.getElementById('qualityList');
            const subToggle = document.getElementById('subToggle');
            const id3Notice = document.getElementById('id3Notice');
            list.innerHTML = '';
            
            if (type === 'mp4') {
                document.getElementById('modalTitle').innerText = "Select MP4 Video Quality";
                subToggle.style.display = 'flex'; // Show subtitle toggle
                id3Notice.style.display = 'none'; // Hide ID3
                
                if (!currentData[actualIndex].formats) {
                    setStatus("Fetching formats...");
                    try {
                        const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: currentData[actualIndex].url, mode: 'single'}) });
                        const data = await res.json();
                        if(data.formats) currentData[actualIndex].formats = data.formats;
                        setStatus("Ready.");
                    } catch(e) {}
                }

                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('best')"><span>⭐ AUTO BEST</span></div>`;
                if(currentData[actualIndex].formats) {
                    currentData[actualIndex].formats.forEach(f => {
                        let sz = f.filesize ? `~${f.filesize}MB` : '';
                        list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('${f.format_id}')"><span>📽️ ${f.resolution}</span> <span class="size-badge">${sz}</span></div>`;
                    });
                }
            } else {
                document.getElementById('modalTitle').innerText = "Select MP3 Audio Quality";
                subToggle.style.display = 'none'; // Hide subtitle toggle
                id3Notice.style.display = 'flex'; // Show ID3 Notice
                
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('320')"><span>⭐ 320 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('192')"><span>🎵 192 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('128')"><span>📱 128 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }

        async function startBackgroundDownload(quality) {
            document.getElementById('qualityModal').style.display = 'none';
            const item = currentData[pendingDownloadTarget.actualIndex];
            
            // Grab subtitle checkbox state
            const burnSubs = document.getElementById('burnSubs').checked;
            
            const reqData = {
                client_id: clientId, 
                url: item.url || item.webpage_url || document.getElementById('url').value,
                title: item.title || "Unknown Task",
                type: pendingDownloadTarget.type,
                quality: quality,
                burn_subs: burnSubs // V17 SEND SUBS FLAG TO CELERY
            };
            
            setStatus("Task dispatched to Celery Worker.");
            await fetch('/api/download', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(reqData) });
            document.getElementById('taskModal').style.display = 'flex'; 
        }

        async function downloadBulk(type) {
            const checkboxes = document.querySelectorAll('.pl-checkbox:checked');
            if(checkboxes.length === 0) return alert("Select at least one video!");
            
            checkboxes.forEach(async (cb) => {
                let idx = parseInt(cb.value);
                let item = currentData[idx];
                await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ client_id: clientId, url: item.url, title: item.title, type: type, quality: type === 'mp3' ? '320' : 'best', burn_subs: false })
                });
            });
            setStatus(`Dispatched ${checkboxes.length} items to Tasks.`);
            document.getElementById('taskModal').style.display = 'flex';
        }

        // ---------------------------------------------------------
        // REAL-TIME CELERY REDIS POLLING
        // ---------------------------------------------------------
        setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks?client_id=${clientId}`);
                const tasks = await res.json();
                
                const wrapper = document.getElementById('tasksWrapper');
                const badge = document.getElementById('taskBadge');
                
                let html = '';
                let activeCount = 0;

                for (const [id, t] of Object.entries(tasks)) {
                    // Access meta data from Celery Task Info
                    const state = t.state;
                    const meta = t.meta || {};
                    
                    if (state === 'PENDING') continue; // Not started yet
                    activeCount++;
                    
                    let sCol = state==='SUCCESS' ? '#155724' : (state==='FAILURE' ? '#721c24' : '#004085');
                    let sBg = state==='SUCCESS' ? '#d4edda' : (state==='FAILURE' ? '#f8d7da' : '#cce5ff');
                    
                    const title = meta.title || "Task";
                    const type = meta.type || "Media";
                    const percent = meta.percent || 0;
                    const speed = meta.speed || "0 MB/s";
                    const eta = meta.eta || "--:--";

                    html += `
                        <div class="task-item" style="background: ${sBg}; border-color: ${sCol}44;">
                            <div class="task-header" style="color: ${sCol};">
                                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:75%;">${type.toUpperCase()}: ${title}</span>
                                <span>${state}</span>
                            </div>
                            ${(state === 'DOWNLOADING' || state === 'PROCESSING') ? `
                                <div class="progress-bar-bg"><div class="progress-fill" style="width: ${percent}%"></div></div>
                                <div class="progress-stats"><span>${percent}%</span> <span>${speed}</span> <span>ETA: ${eta}</span></div>
                            ` : ''}
                            ${state === 'FAILURE' ? `<div style="font-size:0.85rem; color:red;">${meta.error_msg || "Unknown Error"}</div>` : ''}
                            ${state === 'SUCCESS' ? `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px;" onclick="window.location.href='/api/serve?file=${encodeURIComponent(meta.file)}'">💾 SAVE FILE</button>` : ''}
                        </div>
                    `;

                    // AUTO-DOWNLOAD IF SUCCESS
                    if (state === 'SUCCESS' && !handledDownloads.includes(id)) {
                        handledDownloads.push(id);
                        const link = document.createElement('a');
                        link.href = '/api/serve?file=' + encodeURIComponent(meta.file);
                        link.download = ''; document.body.appendChild(link); link.click(); document.body.removeChild(link);
                    }
                }
                
                if(html === '') html = '<p style="text-align:center; color:#888;">No active tasks.</p>';
                wrapper.innerHTML = html;
                badge.innerText = activeCount;
                
            } catch(e) {}
        }, 1000); 
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    # In a real Celery app, we query the active tasks from Redis via Flower or a direct inspector.
    # To bridge the gap safely without requiring deep Celery inspection APIs, we check AsyncResult.
    client_id = request.args.get('client_id')
    
    # We maintain a lightweight mapping in Flask just to know WHICH task IDs belong to WHICH client
    # to query Celery for them.
    from celery.result import AsyncResult
    
    # Note: In production, you would map task_ids to clients in a DB. 
    # For this script, we query the locally held active_task dictionary and fetch live Celery status.
    filtered_results = {}
    for task_id, client in list(active_tasks.items()):
        if client == client_id:
            res = AsyncResult(task_id, app=celery)
            filtered_results[task_id] = {
                'state': res.state,
                'meta': res.info if isinstance(res.info, dict) else {}
            }
            # Clean up memory if done
            if res.state in ['SUCCESS', 'FAILURE']:
                # We leave it so the UI can show the success button. 
                # (A real DB would handle persistence).
                pass
                
    return jsonify(filtered_results)

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    
    ydl_opts = {
        'quiet': True, 'extract_flat': True if mode in ['playlist', 'search'] else False,
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
                    entries.append({'id': e.get('id'), 'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': thumb, 'uploader': e.get('uploader')})
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
                return jsonify({'id': info.get('id'), 'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': uniq})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/download', methods=['POST'])
def trigger_download():
    client_id = request.json.get('client_id')
    
    # Send the job to the Celery Background Worker!
    task = background_downloader.delay(
        client_id=client_id,
        url=request.json.get('url'),
        dl_type=request.json.get('type'),
        quality=request.json.get('quality'),
        burn_subs=request.json.get('burn_subs', False),
        title=request.json.get('title', 'Unknown Task')
    )
    
    # Track the ownership
    active_tasks[task.id] = client_id
    
    return jsonify({'task_id': task.id})

@app.route('/api/serve', methods=['GET'])
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    return send_file(os.path.abspath(file_path), as_attachment=True)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
