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

# ==========================================
# V6: MODAL POPUP UI FRONTEND
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ultimate Downloader V6</title>
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
        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .action-btn { padding: 15px; border: none; border-radius: 12px; font-weight: 800; color: white; cursor: pointer; transition: 0.2s; }
        .btn-mp4 { background: #667eea; } .btn-mp3 { background: #ff0844; }
        .action-btn:disabled { background: #ccc !important; cursor: not-allowed; opacity: 0.7; }

        /* V6 QUALITY MODAL CSS */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(5px); z-index: 1000;
            justify-content: center; align-items: center;
        }
        .modal-box {
            background: white; width: 90%; max-width: 450px; border-radius: 20px; padding: 25px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.3); position: relative;
            animation: popUp 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        @keyframes popUp { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-header h3 { font-size: 1.4rem; font-weight: 800; color: #333; }
        .btn-close { 
            background: #ff0844; color: white; border: none; width: 35px; height: 35px; 
            border-radius: 50%; font-weight: bold; font-size: 1.2rem; cursor: pointer; transition: 0.2s;
        }
        .btn-close:hover { transform: scale(1.1); background: #d00030; }

        .quality-list { display: flex; flex-direction: column; gap: 10px; max-height: 400px; overflow-y: auto; padding-right: 5px; }
        .quality-item {
            background: #f4f7f6; border: 2px solid #e2e8f0; padding: 15px; border-radius: 12px;
            font-weight: 700; color: #333; cursor: pointer; transition: 0.2s; text-align: left;
            display: flex; justify-content: space-between; align-items: center;
        }
        .quality-item:hover { background: #e0f2fe; border-color: #4facfe; transform: translateY(-2px); }
        .quality-item.best { border-color: #ff0844; background: #fff0f2; }
        .size-badge { background: #ddd; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; color: #555; }

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
        <h2>⚡ NEXUS V6 [GUI MODAL]</h2>
        
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
            <p><i>Playlist mode uses Auto-Best quality for bulk downloading.</i></p>
            <div id="pl-container" style="margin-top: 15px;"></div>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <div class="modal-header">
                <h3 id="modalTitle">Select Quality</h3>
                <button class="btn-close" onclick="closeQualityModal()">X</button>
            </div>
            <div class="quality-list" id="qualityList">
                </div>
        </div>
    </div>

    <script>
        let currentMode = 'single';
        let currentMp4Formats = [];
        let fetchTimeout = null;
        let progressInterval = null;

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

        // AUTO-FETCH
        document.getElementById('url').addEventListener('input', (e) => {
            clearTimeout(fetchTimeout);
            const url = e.target.value.trim();
            if(!url) { document.getElementById('single-ui').style.display = 'none'; setStatus("Awaiting Input..."); return; }
            setStatus("Extracting Video Data...");
            fetchTimeout = setTimeout(() => { fetchData(url); }, 800);
        });

        async function fetchData(url) {
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: url, mode: currentMode}) });
                const data = await res.json();
                
                if(data.error) return setStatus("Error: " + data.error, true);

                if(currentMode === 'single') {
                    currentMp4Formats = data.formats; // Save formats for the Modal
                    setStatus("Ready to Download.");
                    document.getElementById('single-ui').style.display = 'block';
                    document.getElementById('s-thumb').src = data.thumbnail;
                    document.getElementById('s-thumb').style.display = 'block';
                    document.getElementById('s-title').innerText = data.title;
                    document.getElementById('s-btns').style.display = 'grid';
                    
                    // Reset UI if previous download finished
                    document.getElementById('progBox').style.display = 'none';
                    document.getElementById('mainMp4Btn').disabled = false;
                    document.getElementById('mainMp3Btn').disabled = false;
                }
            } catch(e) { setStatus("Server Error.", true); }
        }

        // ==========================================
        // V6 MODAL LOGIC
        // ==========================================
        function openQualityModal(type) {
            const modal = document.getElementById('qualityModal');
            const title = document.getElementById('modalTitle');
            const list = document.getElementById('qualityList');
            list.innerHTML = ''; // Clear old buttons

            if (type === 'mp4') {
                title.innerText = "Select MP4 Video Quality";
                
                // Add the "Auto Best" option at the top
                list.innerHTML += `
                    <button class="quality-item best" onclick="startSingleDownload('mp4', 'best')">
                        <span>⭐ BEST AVAILABLE (Auto)</span> <span class="size-badge">Max Res</span>
                    </button>
                `;

                // Add specific formats dynamically
                currentMp4Formats.forEach(f => {
                    let sizeText = f.filesize ? `~${f.filesize} MB` : "Unknown Size";
                    list.innerHTML += `
                        <button class="quality-item" onclick="startSingleDownload('mp4', '${f.format_id}')">
                            <span>📽️ ${f.resolution} - MP4</span> <span class="size-badge">${sizeText}</span>
                        </button>
                    `;
                });
            } else if (type === 'mp3') {
                title.innerText = "Select MP3 Audio Quality";
                // Fixed Audio Options
                const audioOpts = [
                    {val: '320', label: '⭐ VERY BEST (320 kbps)', isBest: true},
                    {val: '256', label: '🎧 HIGH (256 kbps)', isBest: false},
                    {val: '192', label: '🎵 NORMAL (192 kbps)', isBest: false},
                    {val: '128', label: '📱 LOW (128 kbps)', isBest: false}
                ];

                audioOpts.forEach(opt => {
                    let bestClass = opt.isBest ? "best" : "";
                    list.innerHTML += `
                        <button class="quality-item ${bestClass}" onclick="startSingleDownload('mp3', '${opt.val}')">
                            <span>${opt.label}</span> <span class="size-badge">Audio Only</span>
                        </button>
                    `;
                });
            }

            modal.style.display = 'flex';
        }

        function closeQualityModal() {
            document.getElementById('qualityModal').style.display = 'none';
        }

        async function startSingleDownload(type, qualityId) {
            closeQualityModal(); // 1. Close the popup
            const url = document.getElementById('url').value;
            
            // 2. BLOCK THE MAIN BUTTONS
            document.getElementById('mainMp4Btn').disabled = true;
            document.getElementById('mainMp3Btn').disabled = true;
            
            // 3. SHOW PROGRESS UI
            document.getElementById('progBox').style.display = 'block';
            setStatus(`Downloading ${type.toUpperCase()}... Please Wait.`);
            
            progressInterval = setInterval(updateProgressUI, 500);

            try {
                // 4. INITIATE DOWNLOAD
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, type: type, quality: qualityId})
                });
                const data = await res.json();
                
                clearInterval(progressInterval);
                document.getElementById('progFill').style.width = '100%';
                
                if(data.error) {
                    setStatus("Error: " + data.error, true);
                    document.getElementById('mainMp4Btn').disabled = false;
                    document.getElementById('mainMp3Btn').disabled = false;
                } else {
                    setStatus("Complete! Pushing to browser.");
                    document.getElementById('progStatus').innerText = "File Saved!";
                    window.location.href = '/api/serve?file=' + encodeURIComponent(data.file);
                    
                    // Reset buttons after 3 seconds
                    setTimeout(() => {
                        document.getElementById('mainMp4Btn').disabled = false;
                        document.getElementById('mainMp3Btn').disabled = false;
                        document.getElementById('progBox').style.display = 'none';
                        document.getElementById('progFill').style.width = '0%';
                    }, 3000);
                }
            } catch(e) { 
                clearInterval(progressInterval);
                setStatus("Download Failed.", true); 
                document.getElementById('mainMp4Btn').disabled = false;
                document.getElementById('mainMp3Btn').disabled = false;
            }
        }

        async function updateProgressUI() {
            try {
                const res = await fetch('/api/progress');
                const data = await res.json();
                if (data.status === 'downloading') {
                    document.getElementById('progFill').style.width = data.percent + '%';
                    document.getElementById('progPercent').innerText = data.percent + '%';
                    document.getElementById('progSpeed').innerText = data.speed;
                    document.getElementById('progEta').innerText = 'ETA: ' + data.eta;
                }
            } catch(e) {}
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
        'extract_flat': mode == 'playlist',
        'color': 'no_color', 
        'proxy': 'socks5://127.0.0.1:40000' # WARP PROXY
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if mode == 'playlist':
                if 'entries' not in info: return jsonify({'error': 'Not a valid playlist link.'})
                entries = [{'title': e.get('title', 'Unknown'), 'url': e.get('url'), 'thumbnail': e.get('thumbnails', [{'url': ''}])[0]['url'] if e.get('thumbnails') else ''} for e in info['entries']]
                return jsonify({'entries': entries})
                
            else:
                # V6 EXTRACTOR: Hunt for specific Video resolutions to list in the Modal
                formats = []
                for f in info.get('formats', []):
                    # We want video streams. Usually vcodec != 'none'
                    if f.get('vcodec') != 'none':
                        res = f.get('format_note', f.get('resolution', 'Unknown'))
                        # Only keep recognizable HD/SD formats so the UI isn't cluttered with garbage
                        if res in ['2160p', '1440p', '1080p', '1080p60', '720p', '720p60', '480p', '360p']:
                            formats.append({
                                'format_id': f['format_id'],
                                'resolution': res,
                                'filesize': round(f.get('filesize', 0) / 1048576, 1) if f.get('filesize') else None
                            })
                
                # Remove duplicates (sometimes there are multiple 1080p streams, keep the first one found)
                unique_formats = []
                seen_res = set()
                for f in reversed(formats): # Reversed prioritizes better codecs usually at the bottom of the list
                    if f['resolution'] not in seen_res:
                        unique_formats.append(f)
                        seen_res.add(f['resolution'])
                
                # Sort from highest quality to lowest
                def sort_res(f):
                    res_str = f['resolution'].replace('p60', '').replace('p', '')
                    return int(res_str) if res_str.isdigit() else 0
                
                unique_formats.sort(key=sort_res, reverse=True)

                return jsonify({'title': info.get('title'), 'thumbnail': info.get('thumbnail'), 'formats': unique_formats})
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
    }

    if dl_type == 'mp4':
        # If user selected a specific quality (like '137' for 1080p), we must append +bestaudio to it!
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
    print(" 🔥 V6 GUI MODAL SERVER ONLINE 🔥")
    print("=====================================\n")
    app.run(debug=True, port=5000)
