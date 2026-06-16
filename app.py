from flask import Flask, request, jsonify, render_template_string, send_file
import yt_dlp
import os
import time
import threading

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==========================================
# BACKGROUND CLEANUP THREAD
# ==========================================
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

download_state = {"percent": 0, "speed": "0 MB/s", "eta": "00:00", "status": "idle"}

def progress_hook(d):
    global download_state
    if d['status'] == 'downloading':
        download_state['status'] = 'downloading'
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0: download_state['percent'] = round((downloaded / total) * 100, 1)
        
        # Clean terminal color codes
        download_state['speed'] = str(d.get('_speed_str', '0 MB/s')).replace('\x1b[0;94m', '').replace('\x1b[0m', '').strip()
        download_state['eta'] = str(d.get('_eta_str', '00:00')).replace('\x1b[0;93m', '').replace('\x1b[0m', '').strip()
        
    elif d['status'] == 'finished':
        # FIX: Reset stats when merging starts
        download_state['status'] = 'processing'
        download_state['percent'] = 100
        download_state['speed'] = "0 MB/s"
        download_state['eta'] = "--:--"

# ==========================================
# V7: SUCCESS GUI + IFRAME PLAYER
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ultimate Downloader V7</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; }

        body {
            background: linear-gradient(-45deg, #1e3c72, #2a5298, #ff758c, #ff7eb3);
            background-size: 400% 400%; animation: gradientBG 15s ease infinite;
            display: flex; justify-content: center; align-items: flex-start; min-height: 100vh;
            color: #333; padding: 40px 20px;
        }

        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }

        .glass-card {
            background: rgba(255, 255, 255, 0.95); border-radius: 24px; padding: 30px;
            width: 100%; max-width: 800px; box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            position: relative;
        }

        h2 { font-weight: 800; font-size: 2rem; margin-bottom: 20px; text-align: center; }

        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { flex: 1; padding: 15px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.3s; }
        .tab-btn.active { background: #4facfe; color: white; }

        .input-group { display: flex; gap: 10px; margin-bottom: 20px; position: relative; }
        input[type="text"] { width: 100%; padding: 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; transition: 0.3s;}
        input[type="text"]:focus { border-color: #4facfe; box-shadow: 0 0 15px rgba(79, 172, 254, 0.4); }

        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center;}

        #single-ui { display: none; }
        
        /* CLICKABLE THUMBNAIL CSS */
        .image-wrapper { 
            border-radius: 16px; overflow: hidden; margin-bottom: 20px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.1); position: relative; cursor: pointer;
        }
        .image-wrapper::after {
            content: "▶ PLAY"; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.8); color: white; padding: 10px 25px; border-radius: 30px;
            font-weight: 800; font-size: 1.2rem; opacity: 0; transition: 0.3s;
        }
        .image-wrapper:hover::after { opacity: 1; }
        .image-wrapper:hover img { transform: scale(1.05); filter: brightness(0.7); }
        .image-wrapper img { width: 100%; display: block; transition: all 0.3s; }

        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .action-btn { padding: 15px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; transition: 0.2s; }
        .btn-mp4 { background: #667eea; } .btn-mp3 { background: #ff0844; }
        .action-btn:disabled { background: #ccc !important; cursor: not-allowed; opacity: 0.7; }

        /* ALL MODALS (Quality, Success, Video) */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(5px); z-index: 1000;
            justify-content: center; align-items: center; padding: 20px;
        }
        .modal-box {
            background: white; width: 100%; max-width: 450px; border-radius: 20px; padding: 30px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.3); position: relative;
            animation: popUp 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        @keyframes popUp { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        
        .btn-close { 
            background: #ff0844; color: white; border: none; width: 35px; height: 35px; 
            border-radius: 50%; font-weight: bold; font-size: 1.2rem; cursor: pointer; transition: 0.2s;
        }
        .btn-close:hover { transform: scale(1.1); background: #d00030; }

        .quality-list { display: flex; flex-direction: column; gap: 10px; max-height: 400px; overflow-y: auto; padding-right: 5px; margin-top: 15px;}
        .quality-item {
            background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px;
            font-weight: 700; color: #333; cursor: pointer; transition: 0.2s; text-align: left;
            display: flex; justify-content: space-between; align-items: center;
        }
        .quality-item:hover { background: #e0f2fe; border-color: #4facfe; transform: translateY(-2px); }
        .quality-item.best { border-color: #ff0844; background: #fff0f2; }
        .size-badge { background: #ddd; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; color: #555; }

        /* IFRAME VIDEO MODAL */
        .video-modal-content {
            position: relative; width: 100%; max-width: 800px; background: #000; border-radius: 12px; 
            overflow: hidden; aspect-ratio: 16 / 9; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        .video-modal-content iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none; }

        /* PROGRESS BAR */
        .progress-container { display: none; margin-top: 20px; background: #f8f9fa; padding: 20px; border-radius: 16px; }
        .progress-bar-bg { width: 100%; height: 16px; background: #e9ecef; border-radius: 10px; overflow: hidden; margin: 10px 0; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); transition: width 0.3s ease; }
        .progress-stats { display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: 600; color: #555; }

        #playlist-ui { display: none; }
        .pl-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; margin-bottom: 10px; }
        .pl-item img { width: 120px; border-radius: 8px; }
    </style>
</head>
<body>

    <div class="glass-card">
        <h2>⚡ NEXUS V7 [AUTO & FIXES]</h2>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('single')">Single Video</button>
            <button class="tab-btn" onclick="switchTab('playlist')">Playlist Mode</button>
        </div>

        <div class="input-group">
            <input type="text" id="url" placeholder="Paste YouTube Link Here (Auto-Fetches)..." autocomplete="off">
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <div id="single-ui">
            <div class="image-wrapper" onclick="openPlayer()">
                <img id="s-thumb" src="" alt="Thumbnail">
            </div>
            
            <h3 id="s-title" style="margin-bottom: 15px;"></h3>
            
            <div class="btn-grid" id="s-btns" style="display:none;">
                <button id="mainMp4Btn" class="action-btn btn-mp4" onclick="openQualityModal('mp4')">DOWNLOAD MP4</button>
                <button id="mainMp3Btn" class="action-btn btn-mp3" onclick="openQualityModal('mp3')">DOWNLOAD MP3</button>
            </div>

            <div class="progress-container" id="progBox">
                <div class="progress-stats"><span id="progStatus">Downloading...</span><span id="progPercent">0%</span></div>
                <div class="progress-bar-bg"><div class="progress-fill" id="progFill"></div></div>
                <div class="progress-stats"><span id="progSpeed">0 MB/s</span><span id="progEta">ETA: 00:00</span></div>
            </div>
        </div>

        <div id="playlist-ui">
            <div style="display:flex; justify-content:space-between; margin-bottom: 15px;" id="pl-header">
                <div><input type="checkbox" id="selectAll" onclick="toggleAll()"> Select All</div>
                <button class="action-btn" style="background:#333; padding: 8px 15px;" onclick="downloadPlaylist('mp3')">DL Selected MP3</button>
            </div>
            <div id="pl-container"></div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 id="modalTitle">Select Quality</h3>
                <button class="btn-close" onclick="closeModal('qualityModal')">X</button>
            </div>
            <div class="quality-list" id="qualityList"></div>
        </div>
    </div>

    <div class="modal-overlay" id="videoModal" style="flex-direction: column;">
        <button class="action-btn btn-mp3" style="margin-bottom: 20px; align-self: center;" onclick="closePlayer()">✖ CLOSE PLAYER</button>
        <div class="video-modal-content">
            <iframe id="ytIframe" src="" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
        </div>
    </div>

    <div class="modal-overlay" id="successModal">
        <div class="modal-box" style="text-align: center;">
            <button class="btn-close" style="position: absolute; top: 15px; right: 15px;" onclick="closeModal('successModal')">X</button>
            <div style="font-size: 4rem; margin-bottom: 10px;">✅</div>
            <h3 style="margin-bottom: 10px;">Download Ready!</h3>
            <p style="color: #666; margin-bottom: 20px;">Your file is being pushed to your browser.</p>
            
            <a id="manualDownloadLink" href="#" style="display: block; margin-bottom: 25px; color: #4facfe; font-weight: bold; text-decoration: underline;">
                Download not started? Click here.
            </a>
            
            <button class="action-btn btn-mp4" style="width: 100%;" onclick="window.location.reload()">DOWNLOAD NEW VIDEO</button>
        </div>
    </div>

    <script>
        let currentMode = 'single';
        let currentMp4Formats = [];
        let currentVideoId = "";
        let playlistData = [];
        let fetchTimeout = null;
        let progressInterval = null;

        function switchTab(mode) {
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('single-ui').style.display = mode === 'single' ? 'block' : 'none';
            document.getElementById('playlist-ui').style.display = mode === 'playlist' ? 'block' : 'none';
            document.getElementById('pl-header').style.display = mode === 'playlist' ? 'flex' : 'none';
        }

        function setStatus(msg, isError=false) { 
            const badge = document.getElementById('statusBadge');
            badge.innerText = msg; 
            badge.style.background = isError ? '#ffebee' : '#eee';
            badge.style.color = isError ? '#c62828' : '#333';
        }

        function closeModal(id) { document.getElementById(id).style.display = 'none'; }

        // AUTO-FETCH
        document.getElementById('url').addEventListener('input', (e) => {
            clearTimeout(fetchTimeout);
            const url = e.target.value.trim();
            if(!url) return setStatus("Awaiting Input...");
            setStatus("Extracting Video Data...");
            fetchTimeout = setTimeout(() => { fetchData(url); }, 800);
        });

        async function fetchData(url) {
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: url, mode: currentMode}) });
                const data = await res.json();
                
                if(data.error) return setStatus("Error: " + data.error, true);

                if(currentMode === 'single') {
                    currentMp4Formats = data.formats;
                    currentVideoId = data.id; // SAVE ID FOR IFRAME
                    
                    setStatus("Ready to Download.");
                    document.getElementById('single-ui').style.display = 'block';
                    document.getElementById('s-thumb').src = data.thumbnail;
                    document.getElementById('s-title').innerText = data.title;
                    document.getElementById('s-btns').style.display = 'grid';
                } else {
                    playlistData = data.entries;
                    renderPlaylist();
                    setStatus(`Playlist Loaded: ${playlistData.length} Videos`);
                }
            } catch(e) { setStatus("Server Error.", true); }
        }

        // ==========================================
        // V7 MODAL & PLAYER CONTROLS
        // ==========================================
        function openPlayer() {
            if(!currentVideoId) return;
            document.getElementById('ytIframe').src = `https://www.youtube.com/embed/${currentVideoId}?autoplay=1`;
            document.getElementById('videoModal').style.display = 'flex';
        }

        function closePlayer() {
            document.getElementById('videoModal').style.display = 'none';
            document.getElementById('ytIframe').src = ""; // STOPS BACKGROUND AUDIO
        }

        function openQualityModal(type) {
            const list = document.getElementById('qualityList');
            list.innerHTML = ''; 

            if (type === 'mp4') {
                document.getElementById('modalTitle').innerText = "Select MP4 Quality";
                list.innerHTML += `<button class="quality-item best" onclick="startSingleDownload('mp4', 'best')"><span>⭐ BEST AVAILABLE (Auto)</span></button>`;
                currentMp4Formats.forEach(f => {
                    let size = f.filesize ? `~${f.filesize} MB` : "Unknown Size";
                    list.innerHTML += `<button class="quality-item" onclick="startSingleDownload('mp4', '${f.format_id}')"><span>📽️ ${f.resolution}</span> <span class="size-badge">${size}</span></button>`;
                });
            } else {
                document.getElementById('modalTitle').innerText = "Select MP3 Quality";
                list.innerHTML += `<button class="quality-item best" onclick="startSingleDownload('mp3', '320')"><span>⭐ VERY BEST (320 kbps)</span></button>`;
                list.innerHTML += `<button class="quality-item" onclick="startSingleDownload('mp3', '192')"><span>🎵 NORMAL (192 kbps)</span></button>`;
                list.innerHTML += `<button class="quality-item" onclick="startSingleDownload('mp3', '128')"><span>📱 LOW (128 kbps)</span></button>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }

        async function startSingleDownload(type, qualityId) {
            closeModal('qualityModal');
            const url = document.getElementById('url').value;
            
            document.getElementById('mainMp4Btn').disabled = true;
            document.getElementById('mainMp3Btn').disabled = true;
            document.getElementById('progBox').style.display = 'block';
            setStatus(`Downloading ${type.toUpperCase()}...`);
            
            progressInterval = setInterval(updateProgressUI, 500);

            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, type: type, quality: qualityId})
                });
                const data = await res.json();
                
                clearInterval(progressInterval);
                
                if(data.error) {
                    setStatus("Error: " + data.error, true);
                } else {
                    setStatus("Complete! Pushing to browser.");
                    document.getElementById('progBox').style.display = 'none';
                    
                    // V7: POPUP SUCCESS GUI
                    const dlUrl = '/api/serve?file=' + encodeURIComponent(data.file);
                    document.getElementById('manualDownloadLink').href = dlUrl;
                    document.getElementById('successModal').style.display = 'flex';
                    
                    // AUTO-TRIGGER BROWSER DOWNLOAD
                    window.location.href = dlUrl;
                }
            } catch(e) { 
                clearInterval(progressInterval);
                setStatus("Download Failed.", true); 
            }
        }

        async function updateProgressUI() {
            try {
                const res = await fetch('/api/progress');
                const data = await res.json();
                
                const fill = document.getElementById('progFill');
                const statusTxt = document.getElementById('progStatus');
                const percentTxt = document.getElementById('progPercent');
                const speedTxt = document.getElementById('progSpeed');
                const etaTxt = document.getElementById('progEta');

                if (data.status === 'downloading') {
                    fill.style.width = data.percent + '%';
                    percentTxt.innerText = data.percent + '%';
                    speedTxt.innerText = data.speed;
                    etaTxt.innerText = 'ETA: ' + data.eta;
                    statusTxt.innerText = "Downloading...";
                } else if (data.status === 'processing') {
                    fill.style.width = '100%';
                    percentTxt.innerText = "100%";
                    // V7 FIX: SPEED AND ETA ARE ZEROED OUT DURING MERGE
                    speedTxt.innerText = "Processing";
                    etaTxt.innerText = "--:--";
                    statusTxt.innerText = "Merging Audio/Video (FFmpeg)...";
                }
            } catch(e) {}
        }

        // --- PLAYLIST RENDERER ---
        function renderPlaylist() {
            const container = document.getElementById('pl-container');
            container.innerHTML = '';
            playlistData.forEach((item, i) => {
                container.innerHTML += `
                    <div class="pl-item">
                        <input type="checkbox" class="pl-checkbox" value="${item.url}">
                        <img src="${item.thumbnail}" onerror="this.src='https://via.placeholder.com/120x67?text=No+Thumb'">
                        <div style="flex:1;">
                            <h4 style="font-size:0.95rem; margin-bottom:5px;">${item.title}</h4>
                            <span id="stat-${i}" style="font-size:0.8rem; color:#666;">Ready</span>
                        </div>
                        <button class="action-btn" style="background:#ff0844; padding:8px 12px; font-size:0.9rem;" onclick="dlItem('${item.url}', ${i})">MP3</button>
                    </div>
                `;
            });
        }
        function toggleAll() {
            const isChecked = document.getElementById('selectAll').checked;
            document.querySelectorAll('.pl-checkbox').forEach(cb => cb.checked = isChecked);
        }
        async function dlItem(url, index) {
            const stat = document.getElementById(`stat-${index}`);
            stat.innerText = "Downloading..."; stat.style.color = "blue";
            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, type: 'mp3', quality: '320'})
                });
                const data = await res.json();
                if(data.error) { stat.innerText = "Failed"; stat.style.color = "red"; }
                else { stat.innerText = "Saved!"; stat.style.color = "green"; window.location.href = '/api/serve?file=' + encodeURIComponent(data.file); }
            } catch(e) { stat.innerText = "Error"; }
        }
    </script>
</body>
</html>
"""

# ==========================================
# SUPERCHARGED BACKEND ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/progress', methods=['GET'])
def get_progress():
    global download_state
    return jsonify(download_state)

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    
    if 'list=RD' in url:
        return jsonify({'error': 'YouTube Mixes are infinite loops and cannot be downloaded.'})

    ydl_opts = {
        'quiet': True, 
        'color': 'no_color', 
        'proxy': 'socks5://127.0.0.1:40000', # WARP PROXY
        # V7 FIX: Explicitly handle Playlist vs Single modes
        'extract_flat': 'in_playlist' if mode == 'playlist' else False,
        'noplaylist': mode == 'single' 
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if mode == 'playlist':
                if 'entries' not in info: return jsonify({'error': 'Not a valid playlist link.'})
                entries = []
                for e in info.get('entries', []):
                    if not e: continue
                    thumb_url = e.get('thumbnails', [{'url': ''}])[-1]['url'] if e.get('thumbnails') else ''
                    entries.append({'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': thumb_url})
                return jsonify({'entries': entries})
                
            else:
                formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
                        res = f.get('format_note', f.get('resolution', 'Unknown'))
                        if res in ['2160p', '1440p', '1080p', '1080p60', '720p', '720p60', '480p', '360p']:
                            formats.append({'format_id': f['format_id'], 'resolution': res, 'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None})
                
                unique_formats = []
                seen_res = set()
                for f in reversed(formats):
                    if f['resolution'] not in seen_res:
                        unique_formats.append(f)
                        seen_res.add(f['resolution'])
                
                def sort_res(f):
                    res_str = f['resolution'].replace('p60', '').replace('p', '')
                    return int(res_str) if res_str.isdigit() else 0
                
                unique_formats.sort(key=sort_res, reverse=True)
                return jsonify({'id': info.get('id'), 'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': unique_formats})
    except Exception as e:
        error_msg = str(e).replace('\x1b[0;31m', '').replace('\x1b[0m', '')
        return jsonify({'error': error_msg})

@app.route('/api/download', methods=['POST'])
def run_download():
    url = request.json.get('url')
    dl_type = request.json.get('type')
    quality = request.json.get('quality')
    
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True,
        'color': 'no_color',
        'proxy': 'socks5://127.0.0.1:40000', # WARP PROXY
        'concurrent_fragment_downloads': 5,
        'geo_bypass': True,
        'ffmpeg_location': '/usr/bin/ffmpeg', # LINUX DOCKER PATH
        'progress_hooks': [progress_hook],
        'noplaylist': True # Always download just the single selected target here
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
            
        return jsonify({'file': actual_file})
    except Exception as e:
        error_msg = str(e).replace('\x1b[0;31m', '').replace('\x1b[0m', '')
        return jsonify({'error': error_msg})

@app.route('/api/serve', methods=['GET'])
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    return send_file(os.path.abspath(file_path), as_attachment=True)

if __name__ == '__main__':
    print("\n=====================================")
    print(" 🔥 V7 SUCCESS GUI SERVER ONLINE 🔥")
    print("=====================================\n")
    app.run(debug=True, port=5000)
