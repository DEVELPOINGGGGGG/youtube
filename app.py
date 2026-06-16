from flask import Flask, request, jsonify, render_template_string, send_file
import yt_dlp
import os
import time
import threading

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==========================================
# BACKGROUND CLEANUP THREAD (1 HOUR AUTO-DELETE)
# ==========================================
def cleanup_worker():
    while True:
        time.sleep(3600)
        now = time.time()
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                if os.stat(filepath).st_mtime < now - 3600:
                    try:
                        os.remove(filepath)
                    except:
                        pass

threading.Thread(target=cleanup_worker, daemon=True).start()

download_state = {"percent": 0, "speed": "0 MB/s", "eta": "00:00", "status": "idle"}

def progress_hook(d):
    global download_state
    if d['status'] == 'downloading':
        download_state['status'] = 'downloading'
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0: download_state['percent'] = round((downloaded / total) * 100, 1)

# ==========================================
# THE MASSIVE FRONTEND UI (AUTO-FETCH ENABLED)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ultimate Downloader V5</title>
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
        }

        h2 { font-weight: 800; font-size: 2rem; margin-bottom: 20px; text-align: center; }

        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { flex: 1; padding: 15px; border: none; background: #e2e8f0; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.3s; }
        .tab-btn.active { background: #4facfe; color: white; }

        /* INPUT FIELD UPDATED */
        .input-group { display: flex; gap: 10px; margin-bottom: 20px; position: relative; }
        input[type="text"] { width: 100%; padding: 18px 20px; border-radius: 12px; border: 2px solid #ddd; outline: none; font-size: 1.1rem; transition: 0.3s;}
        input[type="text"]:focus { border-color: #4facfe; box-shadow: 0 0 15px rgba(79, 172, 254, 0.4); }

        .status-badge { display: inline-block; padding: 8px 16px; border-radius: 50px; background: #eee; font-weight: 600; margin-bottom: 20px; width: 100%; text-align: center;}

        #single-ui { display: none; }
        select { width: 100%; padding: 15px; margin-bottom: 15px; border-radius: 12px; border: 2px solid #ddd; font-size: 1rem; outline: none; }
        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .action-btn { padding: 15px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; transition: 0.2s; }
        .btn-mp4 { background: #667eea; } .btn-mp3 { background: #ff0844; }

        #playlist-ui { display: none; }
        .pl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #f8f9fa; padding: 15px; border-radius: 12px; }
        .pl-controls button { padding: 10px 20px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; color: white; background: #333;}
        
        .pl-item { display: flex; align-items: center; gap: 15px; padding: 15px; background: #f4f7f6; border-radius: 12px; margin-bottom: 10px; }
        .pl-item img { width: 120px; border-radius: 8px; }
        .pl-info { flex: 1; }
        .pl-info h4 { font-size: 1rem; margin-bottom: 5px; }
        .pl-actions button { padding: 8px 15px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; color: white; }
        
        .load-more { width: 100%; padding: 15px; margin-top: 10px; background: #e2e8f0; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>

    <div class="glass-card">
        <h2>⚡ NEXUS V5 [WARP PROXY]</h2>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('single')">Single Video</button>
            <button class="tab-btn" onclick="switchTab('playlist')">Playlist Mode</button>
        </div>

        <div class="input-group">
            <input type="text" id="url" placeholder="Paste YouTube Link Here (Auto-Fetches)..." autocomplete="off">
        </div>
        
        <div class="status-badge" id="statusBadge">Awaiting Input...</div>

        <div id="single-ui">
            <img id="s-thumb" src="" style="width: 100%; border-radius: 12px; margin-bottom: 15px; display: none;">
            <h3 id="s-title" style="margin-bottom: 15px;"></h3>
            
            <select id="mp4-qualities" style="display:none;"></select>
            <select id="mp3-qualities" style="display:none;">
                <option value="320">VERY BEST (320kbps)</option>
                <option value="256">BEST (256kbps)</option>
                <option value="192">NORMAL (192kbps)</option>
                <option value="128">LOW (128kbps)</option>
                <option value="64">VERY LOW (64kbps)</option>
            </select>

            <div class="btn-grid" id="s-btns" style="display:none;">
                <button class="action-btn btn-mp4" onclick="downloadSingle('mp4')">DOWNLOAD MP4</button>
                <button class="action-btn btn-mp3" onclick="downloadSingle('mp3')">DOWNLOAD MP3</button>
            </div>
        </div>

        <div id="playlist-ui">
            <div class="pl-header" id="pl-header" style="display:none;">
                <div><strong>Select All</strong> <input type="checkbox" id="selectAll" onclick="toggleAll()"></div>
                <div class="pl-controls">
                    <button style="background: #667eea;" onclick="downloadPlaylist('mp4')">DL Selected MP4</button>
                    <button style="background: #ff0844;" onclick="downloadPlaylist('mp3')">DL Selected MP3</button>
                </div>
            </div>
            <div id="pl-container"></div>
            <button class="load-more" id="btnLoadMore" style="display:none;" onclick="loadMore()">LOAD MORE +15</button>
        </div>
    </div>

    <script>
        let currentMode = 'single';
        let playlistData = [];
        let loadedCount = 0;
        let fetchTimeout = null;

        function switchTab(mode) {
            currentMode = mode;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('single-ui').style.display = mode === 'single' ? 'block' : 'none';
            document.getElementById('playlist-ui').style.display = mode === 'playlist' ? 'block' : 'none';
        }

        function setStatus(msg, isError=false) { 
            const badge = document.getElementById('statusBadge');
            badge.innerText = msg; 
            badge.style.background = isError ? '#ffebee' : '#eee';
            badge.style.color = isError ? '#c62828' : '#333';
        }

        // ==========================================
        // AUTO-FETCH LOGIC (Replaces Search Button)
        // ==========================================
        document.getElementById('url').addEventListener('input', (e) => {
            clearTimeout(fetchTimeout);
            const url = e.target.value.trim();
            
            // Hide UI if empty
            if(!url) {
                document.getElementById('single-ui').style.display = 'none';
                document.getElementById('playlist-ui').style.display = 'none';
                setStatus("Awaiting Input...");
                return;
            }

            setStatus("Extracting Data...");
            fetchTimeout = setTimeout(() => { fetchData(url); }, 800); // 800ms debounce
        });

        async function fetchData(url) {
            try {
                const res = await fetch('/api/info', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, mode: currentMode})
                });
                const data = await res.json();
                
                if(data.error) {
                    setStatus("Error: " + data.error, true);
                    return;
                }

                if(currentMode === 'single') renderSingle(data);
                else {
                    playlistData = data.entries;
                    loadedCount = 0;
                    document.getElementById('pl-container').innerHTML = '';
                    document.getElementById('pl-header').style.display = 'flex';
                    loadMore();
                    setStatus(`Playlist Loaded: ${playlistData.length} Videos`);
                }
            } catch(e) { setStatus("Server Error.", true); }
        }

        function renderSingle(data) {
            setStatus("Ready to Download.");
            document.getElementById('single-ui').style.display = 'block';
            document.getElementById('s-thumb').src = data.thumbnail;
            document.getElementById('s-thumb').style.display = 'block';
            document.getElementById('s-title').innerText = data.title;
            
            const mp4Select = document.getElementById('mp4-qualities');
            mp4Select.innerHTML = '';
            data.formats.forEach(f => {
                let opt = document.createElement('option');
                opt.value = f.format_id;
                opt.innerText = `${f.resolution} - ${f.ext.toUpperCase()} (approx ${f.filesize || 'Unknown'} MB)`;
                mp4Select.appendChild(opt);
            });
            
            mp4Select.style.display = 'block';
            document.getElementById('mp3-qualities').style.display = 'block';
            document.getElementById('s-btns').style.display = 'grid';
        }

        async function downloadSingle(type) {
            const url = document.getElementById('url').value;
            let format_val = type === 'mp4' ? document.getElementById('mp4-qualities').value : document.getElementById('mp3-qualities').value;
            
            setStatus(`Downloading ${type.toUpperCase()}... Please Wait.`);
            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, type: type, quality: format_val})
                });
                const data = await res.json();
                if(data.error) setStatus("Error: " + data.error, true);
                else {
                    setStatus("Complete! Pushing to browser.");
                    window.location.href = '/api/serve?file=' + encodeURIComponent(data.file);
                }
            } catch(e) { setStatus("Download Failed.", true); }
        }

        // --- PLAYLIST LOGIC ---
        function loadMore() {
            const container = document.getElementById('pl-container');
            const end = Math.min(loadedCount + 15, playlistData.length);
            
            for(let i = loadedCount; i < end; i++) {
                const item = playlistData[i];
                const div = document.createElement('div');
                div.className = 'pl-item';
                div.innerHTML = `
                    <input type="checkbox" class="pl-checkbox" value="${item.url}">
                    <img src="${item.thumbnail}" onerror="this.src='https://via.placeholder.com/120x67?text=No+Thumb'">
                    <div class="pl-info">
                        <h4>${item.title}</h4>
                        <span id="stat-${i}" style="font-size:0.8rem; color: #666;">Ready</span>
                    </div>
                    <div class="pl-actions">
                        <button style="background: #667eea;" onclick="dlItem('${item.url}', 'mp4', ${i})">MP4</button>
                        <button style="background: #ff0844;" onclick="dlItem('${item.url}', 'mp3', ${i})">MP3</button>
                    </div>
                `;
                container.appendChild(div);
            }
            loadedCount = end;
            document.getElementById('btnLoadMore').style.display = loadedCount < playlistData.length ? 'block' : 'none';
        }

        function toggleAll() {
            const isChecked = document.getElementById('selectAll').checked;
            document.querySelectorAll('.pl-checkbox').forEach(cb => cb.checked = isChecked);
        }

        async function downloadPlaylist(type) {
            const checkboxes = document.querySelectorAll('.pl-checkbox:checked');
            if(checkboxes.length === 0) return alert("Select at least one video!");
            
            for(let i=0; i<checkboxes.length; i++) {
                let url = checkboxes[i].value;
                setStatus(`Bulk Downloading: ${i+1} of ${checkboxes.length}`);
                
                try {
                    const res = await fetch('/api/download', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({url: url, type: type, quality: type === 'mp3' ? '320' : 'best'})
                    });
                    const data = await res.json();
                    if(!data.error) {
                        const link = document.createElement('a');
                        link.href = '/api/serve?file=' + encodeURIComponent(data.file);
                        link.download = '';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }
                } catch(e) { console.log("Failed item", url); }
            }
            setStatus("Bulk Download Complete!");
        }

        async function dlItem(url, type, index) {
            const statText = document.getElementById(`stat-${index}`);
            statText.innerText = "Downloading..."; statText.style.color = "blue";
            
            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, type: type, quality: type === 'mp3' ? '320' : 'best'})
                });
                const data = await res.json();
                if(data.error) { statText.innerText = "Error"; statText.style.color = "red"; }
                else {
                    statText.innerText = "Success! Saved."; statText.style.color = "green";
                    window.location.href = '/api/serve?file=' + encodeURIComponent(data.file);
                }
            } catch(e) { statText.innerText = "Failed."; statText.style.color = "red"; }
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

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    
    if 'list=RD' in url:
        return jsonify({'error': 'YouTube Mixes are infinite loops and cannot be downloaded.'})

    ydl_opts = {
        'quiet': True, 
        'extract_flat': mode == 'playlist',
        'color': 'no_color', # Blocks the [0;31m terminal colors
        'proxy': 'socks5://127.0.0.1:40000' # CLOUDFLARE WARP PROXY
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if mode == 'playlist':
                if 'entries' not in info:
                    return jsonify({'error': 'Not a valid playlist link.'})
                entries = [{'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': e.get('thumbnails', [{'url': ''}])[0]['url'] if e.get('thumbnails') else ''} for e in info['entries']]
                return jsonify({'entries': entries})
                
            else:
                formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none': 
                        formats.append({'format_id': f['format_id'], 'ext': f['ext'], 'resolution': f.get('format_note', f.get('resolution', 'Unknown')), 'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None})
                formats.reverse() 
                return jsonify({'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': formats[:15]})
    except Exception as e:
        # Strip ANSI codes from errors before sending to frontend
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
        'proxy': 'socks5://127.0.0.1:40000', # CLOUDFLARE WARP PROXY
        'concurrent_fragment_downloads': 5,
        'geo_bypass': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',
    }

    if dl_type == 'mp4':
        ydl_opts['format'] = quality if quality != 'best' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
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
    print(" 🔥 V5 WARP PROXY SERVER ONLINE 🔥")
    print(" OPEN: http://127.0.0.1:5000")
    print("=====================================\n")
    app.run(debug=True, port=5000)
