from flask import Flask, request, jsonify, render_template_string, send_file, Response
import yt_dlp
import os
import time
import threading
import uuid

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==========================================
# V11: MULTI-THREADED TASK MANAGER
# ==========================================
# active_tasks stores the progress of all background downloads
active_tasks = {}

def cleanup_worker():
    while True:
        time.sleep(3600)
        now = time.time()
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - 3600:
                try: os.remove(filepath)
                except: pass

threading.Thread(target=cleanup_worker, daemon=True).start()

# Custom hook factory so each download updates its own specific progress bar
def get_progress_hook(task_id):
    def progress_hook(d):
        task = active_tasks.get(task_id)
        if not task: return
        
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
    return progress_hook

# ==========================================
# V11: THE FRONTEND OS (SEARCH + QUEUE UI)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Nexus OS Downloader</title>
    
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#1e3c72">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }
        body {
            background: linear-gradient(-45deg, #1e3c72, #2a5298, #ff758c, #ff7eb3);
            background-size: 400% 400%; animation: gradientBG 15s ease infinite;
            display: flex; justify-content: center; align-items: flex-start; min-height: 100vh;
            color: #333; padding: 20px; padding-bottom: 100px; /* Space for FAB */
        }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        
        .glass-card {
            background: rgba(255, 255, 255, 0.95); border-radius: 24px; padding: 30px;
            width: 100%; max-width: 800px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); position: relative;
        }
        
        .header-area { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        h2 { font-weight: 800; font-size: 1.8rem; text-align: left; margin: 0;}
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;}
        .tab-btn { flex: 1; padding: 12px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.3s; min-width: 100px;}
        .tab-btn.active { background: #4facfe; color: white; }
        
        .input-group { position: relative; margin-bottom: 20px; display:flex; gap:10px;}
        input[type="text"] { flex: 1; padding: 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; transition: 0.3s;}
        input[type="text"]:focus { border-color: #4facfe; box-shadow: 0 0 15px rgba(79, 172, 254, 0.4); }
        .action-btn { padding: 15px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; transition: 0.2s; background: #333; }
        .btn-mp4 { background: #667eea; } .btn-mp3 { background: #ff0844; }
        
        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center;}
        
        /* ITEM LISTS (Search & Playlist) */
        .list-container { display: none; flex-direction: column; gap: 10px; }
        .list-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; }
        .list-item img { width: 120px; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        .list-item img:hover { filter: brightness(0.7); }
        .item-info { flex: 1; }
        .item-info h4 { font-size: 0.95rem; margin-bottom: 5px; }
        
        /* FLOATING TASK MANAGER BUTTON */
        .fab {
            position: fixed; bottom: 30px; right: 30px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white; padding: 15px 25px; border-radius: 50px; font-weight: 800; box-shadow: 0 10px 25px rgba(17, 153, 142, 0.5);
            cursor: pointer; z-index: 1000; transition: 0.3s; display: flex; align-items: center; gap: 10px;
        }
        .fab:hover { transform: scale(1.05); }
        .badge { background: #ff0844; padding: 2px 8px; border-radius: 20px; font-size: 0.8rem; }

        /* TASK MANAGER MODAL */
        .task-modal {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 2000; justify-content: center; align-items: center; padding: 20px;
        }
        .task-box {
            background: white; width: 100%; max-width: 600px; border-radius: 20px; padding: 25px;
            max-height: 80vh; overflow-y: auto; position: relative;
        }
        .task-item { background: #f8f9fa; border: 1px solid #ddd; padding: 15px; border-radius: 12px; margin-bottom: 15px; }
        .task-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 10px; font-size: 0.9rem;}
        
        /* UNIVERSAL PROGRESS BAR */
        .progress-bar-bg { width: 100%; height: 12px; background: #e9ecef; border-radius: 10px; overflow: hidden; margin: 10px 0; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); transition: width 0.3s ease; }
        .progress-stats { display: flex; justify-content: space-between; font-size: 0.8rem; color: #666; font-weight: bold;}

        /* OTHER MODALS */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.7); z-index: 3000; justify-content: center; align-items: center; padding: 20px;}
        .modal-box { background: white; width: 100%; max-width: 450px; border-radius: 20px; padding: 30px; }
        .quality-item { background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; margin-bottom: 10px; display: flex; justify-content: space-between;}
        .quality-item:hover { background: #e0f2fe; border-color: #4facfe; }
        
        .video-modal-content { position: relative; width: 100%; max-width: 800px; background: #000; border-radius: 12px; aspect-ratio: 16 / 9; }
        .video-modal-content iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; cursor: pointer;}
        
        @media (max-width: 600px) { .list-item { flex-direction: column; align-items: flex-start; } .list-item img { width: 100%; } }
    </style>
</head>
<body>

    <div class="glass-card">
        <div class="header-area">
            <h2>⚡ NEXUS OS</h2>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('single')">Single Video</button>
            <button class="tab-btn" onclick="switchTab('playlist')">Playlist Mode</button>
            <button class="tab-btn" onclick="switchTab('search')">Search YouTube</button>
        </div>

        <div class="input-group">
            <input type="text" id="url" placeholder="Paste URL or Type Search Query..." autocomplete="off">
            <button class="action-btn" onclick="handleInput()">GO</button>
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <div id="list-container" class="list-container">
            <div style="display:flex; justify-content:space-between; margin-bottom:10px;" id="bulk-actions">
                <div><input type="checkbox" id="selectAll" onclick="toggleAll()"> Select All</div>
                <div style="display: flex; gap: 10px;">
                    <button class="action-btn btn-mp4" style="padding: 8px 15px;" onclick="downloadBulk('mp4')">DL MP4</button>
                    <button class="action-btn btn-mp3" style="padding: 8px 15px;" onclick="downloadBulk('mp3')">DL MP3</button>
                </div>
            </div>
            <div id="items-wrapper"></div>
        </div>
    </div>

    <div class="fab" onclick="document.getElementById('taskModal').style.display='flex'">
        📥 Downloads <span class="badge" id="taskBadge">0</span>
    </div>

    <div class="task-modal" id="taskModal">
        <div class="task-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                <h2>Task Manager</h2>
                <button class="btn-close" onclick="document.getElementById('taskModal').style.display='none'">X</button>
            </div>
            <div id="tasksWrapper">
                <p style="text-align:center; color:#888;">No active downloads.</p>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h3 id="modalTitle">Select Quality</h3>
                <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            </div>
            <div id="qualityList"></div>
        </div>
    </div>

    <div class="modal-overlay" id="videoModal" style="flex-direction: column;">
        <button class="action-btn btn-mp3" style="margin-bottom: 20px;" onclick="closePlayer()">✖ CLOSE PLAYER</button>
        <div class="video-modal-content">
            <iframe id="ytIframe" src="" allowfullscreen></iframe>
        </div>
    </div>

    <script>
        let currentMode = 'single';
        let currentData = []; 
        let handledDownloads = []; // To track which files we already pushed to browser
        let pendingDownloadTarget = null; // Stores info when modal is open

        // =====================================
        // UI SWITCHING & FETCHING
        // =====================================
        function switchTab(mode) {
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            
            const input = document.getElementById('url');
            input.placeholder = mode === 'search' ? "Type to search YouTube..." : "Paste YouTube Link...";
            
            document.getElementById('list-container').style.display = 'none';
            setStatus(mode === 'search' ? "Ready to search." : "Awaiting Link...");
        }

        function setStatus(msg, isError=false) {
            const b = document.getElementById('statusBadge');
            b.innerText = msg; b.style.background = isError ? '#ffebee' : '#eee'; b.style.color = isError ? '#c62828' : '#333';
        }

        async function handleInput() {
            const val = document.getElementById('url').value.trim();
            if(!val) return setStatus("Input empty.");
            
            if(currentMode !== 'search' && !val.includes('youtube.com') && !val.includes('youtu.be')) {
                return setStatus("Error: Not a valid YouTube link.", true);
            }

            setStatus("Fetching Data...");
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: val, mode: currentMode}) });
                const data = await res.json();
                if(data.error) return setStatus("Error: " + data.error, true);

                if(currentMode === 'single') {
                    currentData = [data];
                    document.getElementById('bulk-actions').style.display = 'none';
                } else {
                    currentData = data.entries;
                    document.getElementById('bulk-actions').style.display = 'flex';
                }
                
                renderItems();
                document.getElementById('list-container').style.display = 'flex';
                setStatus("Ready.");
            } catch(e) { setStatus("Server Error.", true); }
        }

        function renderItems() {
            const wrapper = document.getElementById('items-wrapper');
            wrapper.innerHTML = '';
            
            currentData.forEach((item, i) => {
                const html = `
                    <div class="list-item">
                        ${currentMode !== 'single' ? `<input type="checkbox" class="pl-checkbox" value="${i}">` : ''}
                        <img src="${item.thumbnail}" onclick="openPlayer('${item.id || item.url.split('v=')[1]}')" onerror="this.src='https://via.placeholder.com/120x67'">
                        <div class="item-info">
                            <h4>${item.title}</h4>
                        </div>
                        <div style="display: flex; gap: 5px;">
                            <button class="action-btn btn-mp4" style="padding:8px 12px;" onclick="openQuality('${i}', 'mp4')">MP4</button>
                            <button class="action-btn btn-mp3" style="padding:8px 12px;" onclick="openQuality('${i}', 'mp3')">MP3</button>
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

        function openPlayer(id) {
            if(!id) return;
            document.getElementById('ytIframe').src = `https://www.youtube.com/embed/${id}?autoplay=1`;
            document.getElementById('videoModal').style.display = 'flex';
        }
        function closePlayer() {
            document.getElementById('videoModal').style.display = 'none';
            document.getElementById('ytIframe').src = "";
        }

        // =====================================
        // DOWNLOAD INITIATION
        // =====================================
        function openQuality(index, type) {
            pendingDownloadTarget = { item: currentData[index], type: type };
            const list = document.getElementById('qualityList');
            list.innerHTML = '';
            
            if (type === 'mp4') {
                document.getElementById('modalTitle').innerText = "Select MP4 Quality";
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('best')"><span>⭐ Auto Best</span></div>`;
                
                // If single mode, show exact formats
                if(currentMode === 'single' && currentData[index].formats) {
                    currentData[index].formats.forEach(f => {
                        let sz = f.filesize ? `~${f.filesize}MB` : '';
                        list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('${f.format_id}')"><span>📽️ ${f.resolution}</span> <span class="size-badge">${sz}</span></div>`;
                    });
                } else {
                     list.innerHTML += `<p style="font-size:0.8rem; color:#666; padding:10px;">Specific qualities are only available in Single Link mode. Using Auto-Best.</p>`;
                }
            } else {
                document.getElementById('modalTitle').innerText = "Select MP3 Quality";
                list.innerHTML += `<div class="quality-item best" onclick="startBackgroundDownload('320')"><span>⭐ 320 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('192')"><span>🎵 192 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="startBackgroundDownload('128')"><span>📱 128 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }

        async function startBackgroundDownload(quality) {
            document.getElementById('qualityModal').style.display = 'none';
            const reqData = {
                url: pendingDownloadTarget.item.url || pendingDownloadTarget.item.webpage_url || document.getElementById('url').value,
                title: pendingDownloadTarget.item.title,
                type: pendingDownloadTarget.type,
                quality: quality
            };
            
            setStatus("Sent to Background Task Manager.");
            fetch('/api/download', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(reqData) });
            // Open task manager automatically to show it started
            document.getElementById('taskModal').style.display = 'flex'; 
        }

        async function downloadBulk(type) {
            const checkboxes = document.querySelectorAll('.pl-checkbox:checked');
            if(checkboxes.length === 0) return alert("Select videos first!");
            
            checkboxes.forEach(cb => {
                let item = currentData[cb.value];
                fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: item.url, title: item.title, type: type, quality: type === 'mp3' ? '320' : 'best'})
                });
            });
            setStatus(`Sent ${checkboxes.length} items to Background Tasks.`);
            document.getElementById('taskModal').style.display = 'flex';
        }

        // =====================================
        // BACKGROUND TASK MANAGER SYNC
        // =====================================
        setInterval(async () => {
            try {
                const res = await fetch('/api/tasks');
                const tasks = await res.json();
                
                const wrapper = document.getElementById('tasksWrapper');
                const badge = document.getElementById('taskBadge');
                
                let html = '';
                let activeCount = 0;

                for (const [id, t] of Object.entries(tasks)) {
                    activeCount++;
                    
                    // The UI for each background task
                    html += `
                        <div class="task-item">
                            <div class="task-header">
                                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70%;">${t.title} [${t.type.toUpperCase()}]</span>
                                <span style="color: ${t.status === 'completed' ? 'green' : (t.status === 'error' ? 'red' : 'blue')}">${t.status.toUpperCase()}</span>
                            </div>
                            
                            ${t.status === 'downloading' || t.status === 'processing' ? `
                                <div class="progress-bar-bg"><div class="progress-fill" style="width: ${t.percent}%"></div></div>
                                <div class="progress-stats">
                                    <span>${t.percent}%</span> <span>${t.speed}</span> <span>ETA: ${t.eta}</span>
                                </div>
                            ` : ''}

                            ${t.status === 'completed' ? `
                                <button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px;" onclick="window.location.href='/api/serve?file=${encodeURIComponent(t.file)}'">💾 SAVE TO DEVICE</button>
                            ` : ''}
                        </div>
                    `;

                    // AUTO-DOWNLOAD FEATURE
                    // If task is completed and we haven't pushed it to the browser yet
                    if (t.status === 'completed' && !handledDownloads.includes(id)) {
                        handledDownloads.push(id);
                        
                        // Create a hidden link to trigger the browser download natively
                        const link = document.createElement('a');
                        link.href = '/api/serve?file=' + encodeURIComponent(t.file);
                        link.download = ''; 
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }
                }
                
                if(html === '') html = '<p style="text-align:center; color:#888;">No active downloads.</p>';
                wrapper.innerHTML = html;
                badge.innerText = activeCount;
                
            } catch(e) {}
        }, 1000); // Syncs every 1 second
    </script>
</body>
</html>
"""

# ==========================================
# BACKEND API
# ==========================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    # Frontend polls this to draw the Task Manager UI
    return jsonify(active_tasks)

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    
    if mode != 'search' and 'list=RD' in url: 
        return jsonify({'error': 'YouTube Mixes are infinite loops.'})

    ydl_opts = {
        'quiet': True, 'color': 'no_color', 
        'proxy': 'socks5://127.0.0.1:40000', 
        'extract_flat': True if mode in ['playlist', 'search'] else False,
        'noplaylist': mode in ['single', 'search']
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # If search mode, format string as ytsearch:
            fetch_url = f"ytsearch10:{url}" if mode == 'search' else url
            info = ydl.extract_info(fetch_url, download=False)
            
            if mode in ['playlist', 'search']:
                entries = []
                for e in info.get('entries', []):
                    if not e: continue
                    thumb = e.get('thumbnails', [{'url': ''}])[-1]['url'] if e.get('thumbnails') else ''
                    entries.append({'id': e.get('id'), 'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': thumb})
                return jsonify({'entries': entries})
            else:
                formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
                        res = f.get('format_note', f.get('resolution', 'Unknown'))
                        if res in ['2160p', '1440p', '1080p', '1080p60', '720p', '720p60', '480p', '360p']:
                            formats.append({'format_id': f['format_id'], 'resolution': res, 'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None})
                
                # Sort and remove dupes
                seen = set()
                uniq = []
                for f in reversed(formats):
                    if f['resolution'] not in seen:
                        uniq.append(f)
                        seen.add(f['resolution'])
                uniq.sort(key=lambda f: int(f['resolution'].replace('p60', '').replace('p', '')) if f['resolution'].replace('p60', '').replace('p', '').isdigit() else 0, reverse=True)
                
                return jsonify({'id': info.get('id'), 'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': uniq})
    except Exception as e:
        return jsonify({'error': str(e).replace('\x1b[0;31m', '').replace('\x1b[0m', '')})

# BACKGROUND THREAD WORKER
def background_downloader(task_id, url, dl_type, quality):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True, 'color': 'no_color',
        'proxy': 'socks5://127.0.0.1:40000', 
        'concurrent_fragment_downloads': 10,
        'geo_bypass': True,
        'ffmpeg_location': '/usr/bin/ffmpeg', 
        'progress_hooks': [get_progress_hook(task_id)], # Attach specific task hook
        'noplaylist': True,
        'external_downloader': 'aria2c',
        'external_downloader_args': ['-j', '16', '-x', '16', '-s', '16', '-k', '1M'],
        'postprocessor_args': ['-threads', '0', '-preset', 'ultrafast', '-strict', 'experimental'],
    }

    if dl_type == 'mp4':
        ydl_opts['format'] = f"{quality}+bestaudio[ext=m4a]/best" if quality != 'best' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
    elif dl_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            actual_file = ydl.prepare_filename(info)
            ext = os.path.splitext(actual_file)[1]
            if dl_type == 'mp3': actual_file = actual_file.replace(ext, '.mp3')
            elif dl_type == 'mp4': actual_file = actual_file.replace(ext, '.mp4')
            
            # Update state to completed and save final file path
            active_tasks[task_id]['status'] = 'completed'
            active_tasks[task_id]['file'] = actual_file
    except Exception as e:
        active_tasks[task_id]['status'] = 'error'
        active_tasks[task_id]['error_msg'] = str(e)

@app.route('/api/download', methods=['POST'])
def trigger_download():
    # Instead of waiting, create a task and spawn a thread
    url = request.json.get('url')
    dl_type = request.json.get('type')
    quality = request.json.get('quality')
    title = request.json.get('title', 'Unknown Video')
    
    task_id = str(uuid.uuid4())
    
    # Initialize task state in the dictionary
    active_tasks[task_id] = {
        'title': title,
        'type': dl_type,
        'status': 'starting',
        'percent': 0,
        'speed': '0 MB/s',
        'eta': '--:--',
        'file': None
    }
    
    # Start the download in the background
    threading.Thread(target=background_downloader, args=(task_id, url, dl_type, quality)).start()
    
    return jsonify({'message': 'Task queued', 'task_id': task_id})

@app.route('/api/serve', methods=['GET'])
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    return send_file(os.path.abspath(file_path), as_attachment=True)

if __name__ == '__main__':
    print("\n=====================================")
    print(" 🔥 V11 OS BACKGROUND MANAGER ONLINE 🔥")
    print("=====================================\n")
    app.run(debug=True, port=5000)
