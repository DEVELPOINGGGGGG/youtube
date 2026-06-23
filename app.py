# ==============================================================================
# YOUTUBE MEDIA APP (V52 - PHANTOM NODE: PIPED API DECENTRALIZED FALLBACK)
# ==============================================================================

from flask import Flask, request, jsonify, render_template_string, send_file, Response, redirect
import yt_dlp
import os
import time
import threading
import uuid
import logging
import urllib.parse
import requests
import re

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("YouTubeDownloader")

app = Flask(__name__)
DOWNLOAD_DIR = 'downloads'

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

active_tasks = {}

def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else url

def get_piped_stream(vid_id):
    """V52: Ultimate decentralized API fallback to bypass Datacenter IP Bans."""
    instances = ['https://pipedapi.kavin.rocks', 'https://pipedapi.lunar.icu', 'https://pipedapi.smnz.de', 'https://api.piped.projectsegfau.lt']
    for inst in instances:
        try:
            res = requests.get(f"{inst}/streams/{vid_id}", timeout=6)
            if res.status_code == 200:
                data = res.json()
                streams = data.get('audioStreams', [])
                if streams:
                    streams.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                    return streams[0]['url']
        except:
            continue
    return None

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
# FRONTEND: THE ULTIMATE SOLO PLAYER 
# ==============================================================================
PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Music Player and Downloader</title>
    <link rel="manifest" href="/manifest.json">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Poppins', sans-serif; -webkit-tap-highlight-color: transparent; }
        
        body { background: linear-gradient(-45deg, #0f172a, #1e293b, #0f172a, #020617); background-size: 400% 400%; animation: ambientDrift 15s ease infinite; color: white; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 20px; overflow-x: hidden; position: relative; }
        @keyframes ambientDrift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        
        body.theme-cyberpunk { background: linear-gradient(-45deg, #2a0845, #6441A5, #ff0844, #1a0b2e); background-size: 400% 400%; }
        body.theme-sunset { background: linear-gradient(-45deg, #ff7eb3, #ff758c, #ff9a44, #fc6076); background-size: 400% 400%; }

        .bg-orb { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; z-index: -1; animation: floatOrb 10s ease-in-out infinite alternate; pointer-events: none;}
        .orb-1 { width: 300px; height: 300px; top: -100px; left: -100px; background: #4facfe; }
        .orb-2 { width: 400px; height: 400px; bottom: 10vh; right: -150px; background: #ff0844; animation-delay: -5s; }
        @keyframes floatOrb { 0% { transform: translateY(0) scale(1); } 100% { transform: translateY(50px) scale(1.1); } }

        .container { width: 100%; max-width: 800px; padding-bottom: 150px; position: relative; z-index: 10; }
        
        #global-loader { position: fixed; top: -100px; left: 50%; transform: translateX(-50%); background: linear-gradient(135deg, #ff0844 0%, #ffb199 100%); color: white; padding: 10px 25px; border-radius: 50px; font-weight: 800; box-shadow: 0 10px 30px rgba(255,8,68,0.5); z-index: 10000; transition: top 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); display: flex; align-items: center; gap: 10px; }
        #global-loader.active { top: 20px; }
        .spinner { width: 20px; height: 20px; border: 3px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: white; animation: spin 1s ease-in-out infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        .side-nav { position: fixed; top: 0; left: -300px; width: 280px; height: 100%; background: rgba(30, 41, 59, 0.95); backdrop-filter: blur(20px); box-shadow: 5px 0 25px rgba(0,0,0,0.8); z-index: 9999; transition: left 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); display: flex; flex-direction: column; padding: 30px 20px; border-right: 1px solid rgba(255,255,255,0.1); }
        .side-nav.open { left: 0; }
        .side-nav-close { align-self: flex-end; font-size: 2rem; cursor: pointer; border: none; background: none; color: #ff0844; margin-bottom: 20px; }
        .side-nav a { text-decoration: none; color: white; font-weight: 800; font-size: 1.1rem; padding: 15px; border-radius: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: space-between; transition: 0.2s;}
        
        .side-nav a:hover, .search-btn:hover, .play-action-btn:hover, .dl-icon-btn:hover { transform: translateY(-3px) scale(1.02); }
        .nav-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9998; backdrop-filter: blur(5px);}

        #toast-container { position: fixed; top: 80px; right: 20px; z-index: 10000; display: flex; flex-direction: column; gap: 10px; pointer-events: none;}
        .toast { background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(10px); color: white; padding: 15px 25px; border-radius: 12px; font-weight: 600; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border-left: 5px solid #ff0844; animation: slideIn 0.4s forwards; }
        .toast.success { border-left-color: #1db954; }
        .toast.error { border-left-color: #ff0844; background: rgba(30, 0, 0, 0.95);}
        @keyframes slideIn { from { transform: translateX(120%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(120%); opacity: 0; } }

        .top-bar { display: flex; gap: 10px; margin-bottom: 20px; align-items:center; flex-wrap: wrap;}
        .menu-btn { background: none; border: none; color: white; font-size: 1.8rem; cursor: pointer; transition:0.2s; flex-shrink: 0;}
        .menu-btn:hover { transform: scale(1.1); }
        h2.brand { font-weight: 800; font-size: 1.3rem; margin: 0; background: linear-gradient(90deg, #4facfe, #00f2fe, #4facfe); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-right:auto; animation: textShimmer 3s linear infinite;}
        @keyframes textShimmer { to { background-position: 200% center; } }
        
        .theme-btn { font-size: 1.2rem; cursor: pointer; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 12px; padding: 8px 15px; display: flex; justify-content: center; align-items: center; transition: 0.3s; flex-shrink:0;}
        .theme-btn:hover { background: rgba(255,255,255,0.2); }

        .search-container { display: flex; gap: 10px; width: 100%; margin-bottom: 20px;}
        input[type="text"] { flex: 1; padding: 15px 20px; border-radius: 12px; border: 2px solid #334155; background: #1e293b; color: white; font-size: 1.1rem; outline: none; transition: 0.3s;}
        input[type="text"]:focus { border-color: #ff0844; }
        .search-btn { background: #ff0844; color: white; border: none; padding: 15px 25px; border-radius: 12px; font-weight: 800; cursor: pointer; transition: 0.2s; box-shadow: 0 5px 15px rgba(255,8,68,0.4); flex-shrink: 0; white-space: nowrap;}
        .search-btn:hover { transform: translateY(-3px); }

        .mode-toggles { display: flex; gap: 10px; margin-bottom: 20px; }
        .mode-btn { flex:1; padding: 12px; border-radius: 12px; font-weight: 800; border:none; background:#1e293b; color:#94a3b8; cursor:pointer; transition:0.3s;}
        .mode-btn.active { background: #ff0844; color: white; box-shadow: 0 5px 15px rgba(255,8,68,0.4);}

        #results { display: flex; flex-direction: column; gap: 15px; }

        .queue-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: #1e293b; padding: 10px 15px; border-radius: 12px; border: 1px solid #334155; flex-wrap: wrap; gap: 10px;}
        .play-selected-btn { background: #1db954; color: white; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; flex-shrink: 0; white-space: nowrap;}

        .card { background: #1e293b; border-radius: 12px; padding: 15px; display: flex; gap: 15px; align-items: center; border: 1px solid #334155; transition: 0.3s; animation: popIn 0.4s ease-out; flex-wrap: wrap;}
        .card:hover { border-color: #ff0844; transform: translateY(-3px); box-shadow: 0 10px 20px rgba(0,0,0,0.5); }
        @keyframes popIn { 0% { opacity: 0; transform: translateY(20px) scale(0.95); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
        
        .card.audio-mode img { width: 80px; height: 80px; border-radius: 8px; object-fit: cover; cursor:pointer; flex-shrink: 0;}
        .card.video-mode { flex-direction: column; align-items: stretch; padding: 0; overflow:hidden;}
        .card.video-mode img { width: 100%; aspect-ratio: 16/9; object-fit: cover; cursor:pointer;}
        .card.video-mode .info { padding: 15px; }
        
        .info { flex: 1; min-width: 0; width: 100%;}
        .info h4 { font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 5px; color: white;}
        .info p { font-size: 0.8rem; color: #94a3b8; }
        
        .action-row { display: flex; gap: 10px; margin-top: 10px; width: 100%;}
        .play-action-btn { flex: 1; background: #334155; color: white; border: none; padding: 10px 15px; border-radius: 8px; font-weight: bold; cursor: pointer; transition: 0.2s; flex-shrink: 0; white-space: nowrap;}
        .play-action-btn:hover { background: #1db954; }
        .card.video-mode .play-action-btn { background: #ff0844; padding: 15px; }
        .card.video-mode .play-action-btn:hover { background: #ffb199; color: black; }
        
        .dl-icon-btn { background: #334155; color: white; border: none; padding: 10px 15px; border-radius: 8px; font-size: 1.2rem; cursor: pointer; transition: 0.2s; flex-shrink: 0;}
        .dl-icon-btn:hover { background: #ff0844; transform: scale(1.1); }

        /* FULLSCREEN AUDIO PLAYER */
        #audio-player-bar { position: fixed; top: 100vh; left: 0; width: 100%; height: 100vh; background: #0f172a; padding: 25px; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: top 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 2000; overflow-y: auto;}
        #audio-player-bar.active { top: 0; }
        #audio-player-bar.mini { top: auto; bottom: 0; height: 90px; flex-direction: row; padding: 10px 20px; justify-content: space-between; border-radius: 20px 20px 0 0; background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(10px); box-shadow: 0 -5px 20px rgba(0,0,0,0.5); border-top: 1px solid #334155;}
        
        .full-only { display: flex; width: 100%; justify-content: space-between; position: absolute; top: 20px; padding: 0 25px; z-index: 3000; pointer-events: auto;}
        .mini .full-only { display: none !important; }
        
        .top-ctrl-btn { background: rgba(255,255,255,0.1); border: none; color: white; width: 45px; height: 45px; border-radius: 50%; font-size: 1.5rem; cursor: pointer; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(5px); transition: 0.2s; font-family: monospace; font-weight:bold;}
        .top-ctrl-btn:hover { background: rgba(255,255,255,0.2); transform: scale(1.1); }
        
        .mini-close { display: none; }
        .mini .mini-close { display: block; font-size: 1.5rem; background:none; border:none; color:white; margin-left:10px; cursor:pointer; z-index: 3000; position:relative; pointer-events:auto; font-family: monospace; font-weight:bold;}

        #ap-cover { width: 75%; max-width: 380px; aspect-ratio: 1; border-radius: 16px; object-fit: cover; margin-top: 30px; margin-bottom: 30px; transition: all 0.3s ease; cursor: pointer; box-shadow: 0 20px 50px rgba(0,0,0,0.6);}
        .playing-glow { animation: pulseGlow 2s infinite alternate; }
        @keyframes pulseGlow { 0% { box-shadow: 0 0 20px #1db954; } 100% { box-shadow: 0 0 50px #4facfe, 0 0 80px #1db954; } }
        .mini #ap-cover { width: 60px; height: 60px; margin: 0; animation: none; border-radius:8px; box-shadow:none;}
        .vinyl-mode { border-radius: 50% !important; animation: recordSpin 10s linear infinite; box-shadow: 0 0 0 10px rgba(0,0,0,0.8), 0 0 30px #1db954 !important;}
        @keyframes recordSpin { 100% { transform: rotate(360deg); } }
        
        .marquee-wrapper { width: 100%; overflow: hidden; text-align: center; margin-bottom: 5px; color: white; cursor:pointer;}
        .mini .marquee-wrapper { text-align: left; margin-left: 15px; flex: 1; }
        .marquee-text { font-size: 1.5rem; font-weight: 800; white-space: nowrap; display: inline-block; color: white;}
        .mini .marquee-text { font-size: 1rem; }
        .marquee-text.scroll { animation: marquee 12s linear infinite; padding-left: 100%; }
        
        #ap-artist { color: #94a3b8; font-size: 1rem; margin-bottom: 20px; display: block;}
        .mini #ap-artist { display: none; }

        .progress-row { width: 100%; max-width: 400px; display: flex; align-items: center; gap: 10px; margin-bottom: 20px; font-size: 0.8rem; color: #94a3b8; }
        .mini .progress-row { display: none; }
        input[type="range"] { flex: 1; -webkit-appearance: none; background: #334155; height: 6px; border-radius: 3px; outline: none; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%; background: #1db954; cursor: pointer; box-shadow: 0 0 10px #1db954;}

        .advanced-controls { display: flex; width: 100%; max-width: 400px; justify-content: space-between; margin-bottom: 10px; color: #94a3b8; align-items:center;}
        .mini .advanced-controls { display: none; }
        .adv-btn { background: none; border: none; color: #94a3b8; font-size: 1.2rem; cursor: pointer; font-weight: bold; transition: 0.2s; display:flex; justify-content:center; align-items:center;}
        .adv-btn.active { color: #1db954; text-shadow: 0 0 10px #1db954; }

        .sleep-wrapper { position: relative; display: flex; justify-content: center; align-items: center; width: 40px; height: 40px; border-radius: 50%; }
        .sleep-ring { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 50%; background: transparent; z-index: 1; pointer-events: none; }
        .sleep-wrapper .adv-btn { z-index: 2; position: relative;}

        .controls { display: flex; align-items: center; justify-content: center; gap: 20px; width: 100%; margin-bottom: 20px;}
        .mini .controls { width: auto; gap: 15px; margin-bottom: 0;}
        .ctrl-btn { background: none; border: none; color: white; font-size: 1.8rem; cursor: pointer; transition: 0.2s;}
        .ctrl-btn:hover { transform: scale(1.1); }
        .ctrl-play { background: white; color: black; width: 65px; height: 65px; border-radius: 50%; font-size: 2rem; display: flex; justify-content: center; align-items: center; box-shadow: 0 5px 15px rgba(255,255,255,0.2);}
        .mini .ctrl-play { width: 45px; height: 45px; font-size: 1.5rem; background: transparent; color: white; box-shadow: none;}
        
        .volume-row { display: flex; align-items: center; gap: 10px; width: 80%; max-width: 300px; color: #94a3b8; margin-bottom: 20px;}
        .mini .volume-row { display: none; }
        
        .bottom-action-row { display: flex; align-items: center; justify-content: center; gap: 15px; width: 100%; margin-top: auto; padding-bottom: 20px;}
        .mini .bottom-action-row { display: none; }
        
        .open-yt-btn, .dl-mp3-btn { text-decoration: none; font-size: 0.9rem; font-weight: bold; padding: 10px 20px; border-radius: 20px; transition: 0.2s; cursor: pointer; border: none; display:flex; align-items:center; gap:5px; justify-content:center;}
        .open-yt-btn { color: #ff0844; border: 2px solid #ff0844; background: transparent; flex-shrink: 0;}
        .open-yt-btn:hover { background: #ff0844; color: white; }
        .dl-mp3-btn { color: white; background: #334155; border: 2px solid #334155; transition: 0.3s; flex-shrink: 0; white-space: nowrap;}
        .dl-mp3-btn:hover:not(:disabled) { background: transparent; color: #4facfe; transform: translateY(-3px);}
        .dl-mp3-btn:disabled { opacity: 0.8; cursor: not-allowed; }

        /* VIDEO MODAL (NO SANDBOX, CUSTOM REFERRER) */
        #video-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: black; z-index: 5000; flex-direction: column; justify-content: center; align-items: center; transition: 0.3s;}
        .video-container { width: 100%; height: 100%; max-width: 100vw; background: black; position: relative; display: flex; justify-content: center; align-items: center;}
        .video-container iframe { width: 100%; height: 100%; border: none; pointer-events: auto; }
        
        .vid-controls { position: absolute; top: 20px; right: 20px; display: flex; gap: 10px; z-index: 5001; }
        .close-video { background: rgba(255,8,68,0.9); color: white; border: none; padding: 10px; border-radius: 50%; font-weight: 800; cursor: pointer; width: 45px; height: 45px; display: flex; justify-content: center; align-items: center; transition: 0.2s; font-size:1.2rem; font-family: monospace;}
        .close-video:hover { transform: scale(1.1); }
        
        .yt-fallback-btn { position: absolute; bottom: 30px; background: rgba(255,255,255,0.1); color: white; border: 1px solid white; padding: 10px 20px; border-radius: 20px; font-weight: bold; text-decoration: none; backdrop-filter: blur(5px); z-index: 5001; transition: 0.2s;}
        .yt-fallback-btn:hover { background: white; color: black; }

        .load-more-btn { background: #334155; color: white; border: none; padding: 15px; border-radius: 12px; width: 100%; font-weight: 800; cursor: pointer; margin-top: 15px; transition: 0.2s; flex-shrink: 0;}
        .load-more-btn:hover { background: #ff0844; }

        /* MODALS */
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); z-index: 4000; justify-content: center; align-items: center; padding: 20px; backdrop-filter: blur(5px);}
        .modal-box { background: #1e293b; width: 100%; max-width: 600px; border-radius: 24px; padding: 30px; position: relative; color: white; border: 1px solid #334155; box-shadow: 0 20px 50px rgba(0,0,0,0.8); animation: popIn 0.3s ease-out;}
        .quality-item { background: #0f172a; border: 2px solid #334155; padding: 15px; border-radius: 12px; font-weight: 700; cursor: pointer; display: flex; justify-content: space-between; margin-bottom: 10px; transition: 0.2s;}
        .quality-item:hover { border-color: #ff0844; }
        .quality-item.best { border-color: #ff0844; background: rgba(255,8,68,0.1); }
        .btn-close { background: #ff0844; color: white; border: none; width: 35px; height: 35px; border-radius: 50%; font-weight: bold; cursor: pointer; display: flex; justify-content: center; align-items: center; position:absolute; top: 15px; right: 15px; z-index:10; transition: 0.2s;}
        .btn-close:hover { transform: rotate(90deg); }
        input[type="number"] { width: 100%; padding: 15px 20px; border-radius: 12px; border: 2px solid #334155; outline: none; font-size: 1.1rem; background: #0f172a; color: white; margin-bottom: 15px; transition: 0.3s;}
        input[type="number"]:focus { border-color: #ff0844; }
        
        #thumbModal .modal-box { background: transparent; border: none; box-shadow: none; padding: 0; max-width: 90vw; max-height: 90vh; display: flex; flex-direction: column; justify-content: center; align-items:center;}
        #thumbModal img { width: 100%; height: auto; max-height: 70vh; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.8); object-fit: contain; margin-bottom:20px;}
        
        .history-card { background: #0f172a; padding: 15px; border-radius: 12px; border: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; transition: 0.2s;}
        .history-card:hover { border-color: #ff0844; }
        .history-btn { background: #ff0844; color: white; border: none; padding: 10px 15px; border-radius: 8px; font-weight: bold; cursor: pointer; transition: 0.2s;}

        .task-item { background: #0f172a; border: 1px solid #334155; padding: 20px; border-radius: 16px; margin-bottom: 15px; }
        .task-header { display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 10px;}
        
        /* SETTINGS RADIO */
        .radio-group { display: flex; flex-direction: column; gap: 15px; margin-top: 15px; }
        .radio-item { display: flex; align-items: center; gap: 15px; background: #0f172a; padding: 15px; border-radius: 12px; border: 1px solid #334155; cursor: pointer; transition: 0.2s;}
        .radio-item:hover { border-color: #ff0844; }
        .radio-item input { width: 20px; height: 20px; accent-color: #ff0844; flex-shrink:0;}
        .radio-desc { font-size: 0.8rem; color: #94a3b8; font-weight: normal; margin-top: 5px; }

        @media (max-width: 600px) { 
            .side-nav { width: 250px; } 
            #ap-cover { width: 85%; } 
            .card.audio-mode { flex-direction: column; align-items: center; text-align: center; }
            .card.audio-mode img { width: 100%; max-width: 250px; height: auto; aspect-ratio: 1; margin: 0 auto;}
            .card.audio-mode .action-row { width: 100%; display: flex; flex-wrap: wrap; justify-content: center;}
            .search-container { flex-wrap: wrap; }
            .search-btn { width: 100%; }
            .queue-actions { flex-direction: column; align-items: flex-start; gap: 10px;}
            .play-selected-btn { width: 100%; margin-top: 5px;}
        }
    </style>
</head>
<body>
    <div id="global-loader"><div class="spinner"></div> <span>Loading...</span></div>
    <div id="toast-container"></div>

    <div class="nav-overlay" id="navOverlay" onclick="toggleMenu()"></div>
    <div class="side-nav" id="sideNav">
        <button class="side-nav-close" onclick="toggleMenu()">×</button>
        <h2 style="margin-bottom: 30px; text-align: center; color:white;">MENU</h2>
        
        <a href="#" id="installAppBtn" style="display:none; background: linear-gradient(135deg, #1db954 0%, #1ed760 100%); color: black;" onclick="installPWA(); toggleMenu()">📲 Install App</a>
        
        <a href="#" onclick="document.getElementById('historyModal').style.display='flex'; toggleMenu()">🕒 My History</a>
        <a href="#" onclick="document.getElementById('taskModal').style.display='flex'; toggleMenu()">📥 Downloads Queue</a>
        <div style="height: 1px; background: #334155; margin: 15px 0;"></div>
        <a href="#" onclick="document.getElementById('settingsModal').style.display='flex'; toggleMenu()">⚙️ Settings</a>
    </div>

    <div class="container">
        <div class="top-bar">
            <button class="menu-btn" onclick="toggleMenu()">☰</button>
            <h2 class="brand">Music Player</h2>
            <button class="theme-btn" onclick="cycleTheme()" title="Change Theme">🎨</button>
        </div>

        <div class="mode-toggles">
            <button id="mode-audio" class="mode-btn active" onclick="setMode('audio')">🎵 Music</button>
            <button id="mode-video" class="mode-btn" onclick="setMode('video')">🎬 Videos</button>
        </div>

        <div class="search-container">
            <input type="text" id="searchInput" placeholder="Search for songs or artists..." autocomplete="off">
            <button class="search-btn" onclick="search(true)">Search</button>
        </div>

        <div id="queue-actions" class="queue-actions" style="display:none;">
            <div style="white-space:nowrap;"><input type="checkbox" id="selectAll" onclick="toggleAll()" style="width:20px;height:20px;vertical-align:middle;accent-color:#ff0844;"> <strong style="vertical-align:middle; margin-left:5px;">Select All</strong></div>
            <button class="play-selected-btn" onclick="playSelected()">▶ PLAY SELECTED</button>
        </div>
        
        <div id="status" style="text-align:center; color:#94a3b8; margin-bottom:15px; font-weight:bold;">Search to begin.</div>
        <div id="results"></div>
        <button id="loadMoreBtn" class="load-more-btn" style="display:none;" onclick="loadMore()">🔄 LOAD 20 MORE</button>
    </div>

    <div id="audio-player-bar">
        <div class="full-only">
            <button class="top-ctrl-btn" onclick="toggleMiniPlayer(event)" title="Minimize" style="font-family: monospace;">—</button>
            <button class="top-ctrl-btn" onclick="stopAudio(event)" title="Close">✖</button>
        </div>
        
        <img id="ap-cover" src="" onclick="toggleVinylMode()">
        
        <div class="marquee-wrapper" onclick="toggleMiniPlayer(event)">
            <span class="marquee-text" id="ap-title">Loading...</span>
        </div>
        <div id="ap-artist" style="display:block;">Unknown Artist</div>
        
        <div class="advanced-controls">
            <button class="adv-btn" id="speedBtn" onclick="toggleSpeed()" title="Playback Speed">1x</button>
            <button class="adv-btn" id="loopBtn" onclick="toggleLoop()" title="Repeat Mode">🔁</button>
            <div class="sleep-wrapper">
                <div class="sleep-ring" id="sleepRing"></div>
                <button class="adv-btn" id="sleepBtn" onclick="openSleepModal()">🌙</button>
            </div>
            <button class="adv-btn" onclick="shareSong()" title="Share">📤</button>
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
            <button class="mini-close" onclick="stopAudio(event); event.stopPropagation();" style="font-family: monospace;">✖</button>
        </div>
        
        <div class="volume-row">
            <span>🔈</span><input type="range" id="volSlider" value="100" min="0" max="100"><span>🔊</span>
        </div>
        
        <div class="bottom-action-row">
            <a id="ap-yt-link" class="open-yt-btn" href="#" target="_blank">↗ YouTube App</a>
            <button id="mainPlayerDlBtn" class="dl-mp3-btn" onclick="downloadCurrentSong(event)">📥 Download MP3</button>
        </div>
        <audio id="audioEngine" autoplay></audio>
    </div>

    <div id="video-modal">
        <div class="video-container" id="videoContainer">
            <div class="vid-controls">
                <button class="close-video" onclick="closeVideo()">✖</button>
            </div>
            <iframe id="ytIframe" src="" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
            <a id="ytFallbackLink" class="yt-fallback-btn" href="#" target="_blank" style="display:none;">Watch in YouTube App</a>
        </div>
    </div>

    <div class="modal-overlay" id="thumbModal" style="z-index: 6000;" onclick="this.style.display='none'">
        <div class="modal-box" onclick="event.stopPropagation()">
            <button class="btn-close" style="top:-15px; right:-15px; z-index: 6001;" onclick="document.getElementById('thumbModal').style.display='none'">X</button>
            <img id="fullThumbImg" src="">
            <button class="play-action-btn" style="width:100%; padding:15px; font-size:1.2rem; background:#ff0844; border-radius:12px;" onclick="playFromLightbox()">▶ PLAY VIDEO IN LANDSCAPE</button>
        </div>
    </div>

    <div class="modal-overlay" id="qualityModal">
        <div class="modal-box">
            <button class="btn-close" onclick="document.getElementById('qualityModal').style.display='none'">X</button>
            <h3 id="modalTitle" style="margin-bottom:15px;">Select Quality</h3>
            <div id="qualityList" style="display:flex; flex-direction:column; gap:10px;"></div>
        </div>
    </div>

    <div class="modal-overlay" id="sleepModal" style="z-index: 5000;">
        <div class="modal-box" style="text-align: center;">
            <button class="btn-close" onclick="document.getElementById('sleepModal').style.display='none'">X</button>
            <h3 style="margin-bottom: 15px; color:white;">Set Sleep Timer</h3>
            <input type="number" id="sleepInput" placeholder="Minutes..." style="width: 100%; margin-bottom: 15px;">
            <button class="dl-mp3-btn" style="width: 100%; padding:15px; border-radius:12px; font-weight:bold; font-size:1.1rem; background:#ff0844; border:none;" onclick="setSleepTimer()">START TIMER</button>
        </div>
    </div>

    <div class="modal-overlay" id="settingsModal" style="z-index: 3500;">
        <div class="modal-box">
            <h2 style="font-size:1.5rem; margin-bottom:5px; color:white;">App Settings</h2>
            <button class="btn-close" onclick="document.getElementById('settingsModal').style.display='none'">X</button>
            
            <h3 style="margin-top:20px; color:#ff0844; font-size:1.1rem;">MP3 Conversion Engine</h3>
            <div class="radio-group">
                <label class="radio-item">
                    <input type="radio" name="convMode" value="full" onchange="saveSettings()">
                    <div><strong>Full FFmpeg</strong><div class="radio-desc">Perfectly encodes MP3, injects cover art. (Slow)</div></div>
                </label>
                <label class="radio-item">
                    <input type="radio" name="convMode" value="fast" onchange="saveSettings()">
                    <div><strong>Fast Metadata</strong><div class="radio-desc">Downloads native M4A, injects cover art. (Fast)</div></div>
                </label>
                <label class="radio-item" style="border-color:#ff0844; background:rgba(255,8,68,0.1);">
                    <input type="radio" name="convMode" value="rename" onchange="saveSettings()">
                    <div><strong>Rename Only</strong><div class="radio-desc">Raw download, instantly renames to .mp3. (⚡ Instant)</div></div>
                </label>
            </div>
        </div>
    </div>

    <div class="modal-overlay" id="historyModal" style="z-index: 4000;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                <h2 style="font-size:1.5rem; color:white;">🕒 My History</h2>
                <button class="btn-close" onclick="document.getElementById('historyModal').style.display='none'">X</button>
            </div>
            <div id="history-list" style="display:flex; flex-direction:column; gap:10px; max-height:60vh; overflow-y:auto; padding-right:5px;"></div>
        </div>
    </div>

    <div class="modal-overlay" id="taskModal" style="z-index: 4000;">
        <div class="modal-box">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                <h2 style="font-size:1.5rem; color:white;">📥 Downloads</h2>
                <button class="btn-close" onclick="document.getElementById('taskModal').style.display='none'">X</button>
            </div>
            <div id="tasksWrapper"><p style="text-align:center; color:#666;">No active downloads.</p></div>
        </div>
    </div>

    <script>
        function createRipple(event) {
            const button = event.currentTarget;
            const circle = document.createElement("span");
            const diameter = Math.max(button.clientWidth, button.clientHeight);
            const radius = diameter / 2;
            circle.style.width = circle.style.height = `${diameter}px`;
            const rect = button.getBoundingClientRect();
            circle.style.left = `${event.clientX - rect.left - radius}px`;
            circle.style.top = `${event.clientY - rect.top - radius}px`;
            circle.classList.add("ripple");
            const existingRipple = button.querySelector('.ripple');
            if (existingRipple) { existingRipple.remove(); }
            button.appendChild(circle);
        }
        
        function attachRipples() {
            const buttons = document.querySelectorAll('button, .action-btn, .play-action-btn, .dl-btn, .dl-btn-full, .play-btn-full, .play-btn, .dl-icon-btn');
            for (const button of buttons) {
                button.addEventListener('click', createRipple);
            }
        }

        let themes = ['', 'theme-cyberpunk', 'theme-sunset'];
        let themeIndex = 0;
        function cycleTheme() {
            document.body.classList.remove(...themes);
            themeIndex = (themeIndex + 1) % themes.length;
            if(themes[themeIndex] !== '') document.body.classList.add(themes[themeIndex]);
        }

        let isVinylMode = false;
        function toggleVinylMode() {
            isVinylMode = !isVinylMode;
            const cover = document.getElementById('ap-cover');
            if(isVinylMode && !audioEngine.paused) {
                cover.classList.add('vinyl-mode');
            } else {
                cover.classList.remove('vinyl-mode');
            }
        }

        // V52 PWA LOGIC
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js').catch(err => {});
            });
        }

        let deferredPrompt;
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            const installBtn = document.getElementById('installAppBtn');
            if(installBtn) installBtn.style.display = 'flex';
        });

        function installPWA() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        document.getElementById('installAppBtn').style.display = 'none';
                    }
                    deferredPrompt = null;
                });
            } else {
                showToast("App is installable from your browser menu (Add to Home Screen)", "info");
            }
        }

        let currentMode = 'audio';
        let currentResults = [];
        let currentSearchLimit = 10;
        let pendingDownloadTarget = null; 
        let taskDOMMap = {}; 
        let typingTimer; 
        let isFetchingMore = false; 

        let audioQueue = [];
        let currentIndex = -1;
        let currentPlayingVideoId = ""; 

        let loopMode = 0; 
        let currentSpeed = 1.0; 
        let currentAudioDlTaskId = null;
        
        let isFadingOut = false;
        let fadeInterval = null;
        let isErrorStopped = false; 
        
        let sleepTimer = null;
        let sleepTimeLeft = 0;
        let totalSleepTime = 0;
        
        let deliveryQueue = [];
        let isDelivering = false;

        const audioEngine = document.getElementById('audioEngine');

        function showToast(msg, type='info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`; toast.innerText = msg;
            container.appendChild(toast);
            setTimeout(() => { toast.style.animation = 'slideOut 0.4s forwards'; setTimeout(() => toast.remove(), 400); }, 3000);
        }

        function showLoader() { document.getElementById('global-loader').classList.add('active'); }
        function hideLoader() { document.getElementById('global-loader').classList.remove('active'); }

        let clientId = localStorage.getItem('yt_dl_client_id') || (Math.random().toString(36).substring(2) + Date.now().toString(36));
        localStorage.setItem('yt_dl_client_id', clientId);
        let handledDownloads = JSON.parse(localStorage.getItem('yt_dl_handled') || '[]');
        function markHandled(id) { if (!handledDownloads.includes(id)) { handledDownloads.push(id); localStorage.setItem('yt_dl_handled', JSON.stringify(handledDownloads.slice(-50))); } }

        function saveToHistory(item, mode='audio') {
            let hist = JSON.parse(localStorage.getItem('yt_dl_history') || '[]');
            const date = new Date().toLocaleDateString();
            hist.unshift({ title: item.title, uploader: item.uploader || 'Unknown', duration: item.duration || '--', url: item.url || item.id, date: date, mode: mode, thumbnail: item.thumbnail || 'https://via.placeholder.com/150' });
            if (hist.length > 50) hist = hist.slice(0, 50);
            localStorage.setItem('yt_dl_history', JSON.stringify(hist));
            loadHistory(); 
        }

        function loadHistory() {
            const hist = JSON.parse(localStorage.getItem('yt_dl_history') || '[]');
            const container = document.getElementById('history-list');
            if(hist.length === 0) { container.innerHTML = '<p style="color:#888; text-align:center;">No history yet. Go search something!</p>'; return; }
            
            container.innerHTML = '';
            hist.forEach((h, idx) => {
                container.innerHTML += `
                    <div class="history-card">
                        <div style="flex:1; min-width:0; margin-right:10px;">
                            <strong style="color:white; font-size:0.95rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block;">${h.title}</strong>
                            <p style="font-size:0.75rem; color:#94a3b8; margin-top:5px;">👤 ${h.uploader} • ⏱️ ${h.duration} • 📅 ${h.date}</p>
                        </div>
                        <button class="play-action-btn" style="flex-shrink:0;" onclick="playFromHistory(${idx})">▶ Play</button>
                    </div>`;
            });
            attachRipples();
        }

        function playFromHistory(index) {
            const hist = JSON.parse(localStorage.getItem('yt_dl_history') || '[]');
            const item = hist[index];
            if(!item) return;

            audioEngine.play().catch(e=>{}); 
            document.getElementById('historyModal').style.display = 'none';
            
            if (item.mode === 'video') { startVideo(item.url); } 
            else { 
                audioQueue = [item];
                currentIndex = 0;
                loadQueueItem();
            }
        }

        function loadSettings() {
            let mode = localStorage.getItem('audio_conversion_mode') || 'fast';
            const radios = document.getElementsByName('convMode');
            for(let i=0; i<radios.length; i++) { if(radios[i].value === mode) radios[i].checked = true; }
        }

        function saveSettings() {
            const radios = document.getElementsByName('convMode');
            for(let i=0; i<radios.length; i++) {
                if(radios[i].checked) { localStorage.setItem('audio_conversion_mode', radios[i].value); break; }
            }
            showToast(`Settings Saved!`, "success");
        }

        document.getElementById('volSlider').oninput = (e) => {
            audioEngine.volume = parseInt(e.target.value) / 100;
        };

        window.addEventListener('DOMContentLoaded', () => {
            loadSettings(); 
            loadHistory();
            attachRipples();
            audioEngine.volume = 1.0; 
            
            const params = new URLSearchParams(window.location.search);
            if (params.get('url')) { 
                document.getElementById('searchInput').value = params.get('url'); 
                search(true); 
            }
        });

        window.addEventListener('scroll', () => {
            if(document.getElementById('loadMoreBtn').style.display === 'block') {
                if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
                    if(!isFetchingMore) { isFetchingMore = true; loadMore(); }
                }
            }
        });

        function toggleMenu() {
            const nav = document.getElementById('sideNav');
            nav.classList.toggle('open');
            document.getElementById('navOverlay').style.display = nav.classList.contains('open') ? 'block' : 'none';
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('mode-audio').classList.toggle('active', mode === 'audio');
            document.getElementById('mode-video').classList.toggle('active', mode === 'video');
            document.getElementById('queue-actions').style.display = mode === 'audio' ? 'flex' : 'none';
            document.getElementById('searchInput').placeholder = mode === 'audio' ? "Search for songs..." : "Search for videos...";
            if(currentResults.length > 0) renderResults();
        }

        document.getElementById('searchInput').addEventListener('input', (e) => {
            clearTimeout(typingTimer);
            if(!e.target.value.trim()) return;
            typingTimer = setTimeout(() => { search(true); }, 2000); 
        });

        function loadMore() { currentSearchLimit += 20; search(false); }

        async function search(isNew = true) {
            const query = document.getElementById('searchInput').value.trim();
            if(!query) { isFetchingMore = false; return; }
            
            document.getElementById('status').innerText = 'Searching YouTube...';
            if(isNew) {
                currentSearchLimit = 10;
                document.getElementById('results').innerHTML = '';
                document.getElementById('loadMoreBtn').style.display = 'none';
            }

            showLoader();
            try {
                const res = await fetch('/api/info', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: query, mode: 'search', limit: currentSearchLimit}) });
                const data = await res.json();
                
                if(data.error) { throw new Error(data.error); }
                
                currentResults = data.entries;
                renderResults();
                document.getElementById('status').innerText = `Found ${currentResults.length} results.`;
                document.getElementById('loadMoreBtn').style.display = 'block';
            } catch (err) { showToast(err.message, "error"); document.getElementById('status').innerText = 'Network Error.'; }
            finally { hideLoader(); isFetchingMore = false; attachRipples(); } 
        }

        function renderResults() {
            const container = document.getElementById('results'); container.innerHTML = '';
            currentResults.forEach((item, index) => {
                const uploader = item.uploader || 'Unknown';
                const videoId = item.id || (item.url ? item.url.split('v=')[1] : '');
                const delay = (index % 20) * 0.05;
                
                if(currentMode === 'audio') {
                    container.innerHTML += `
                        <div class="card audio-mode" style="animation-delay: ${delay}s;">
                            <input type="checkbox" class="song-checkbox audio-cb" value="${index}">
                            <img src="${item.thumbnail}" onclick="openFullThumbList('${item.thumbnail}', '${videoId}')" title="View Art">
                            <div class="info">
                                <h4 title="${item.title}">${item.title}</h4>
                                <p>${uploader} • ${item.duration}</p>
                            </div>
                            <div class="action-row-audio">
                                <button class="play-btn" onclick="playSingleAudio(${index})" title="Play">▶</button>
                                <button class="dl-btn" onclick="triggerDownload(${index}, 'mp3')" title="Download MP3">📥</button>
                            </div>
                        </div>`;
                } else {
                    container.innerHTML += `
                        <div class="card video-mode" style="animation-delay: ${delay}s;">
                            <div class="thumb-container">
                                <input type="checkbox" class="song-checkbox video-cb" value="${index}">
                                <img src="${item.thumbnail}" onclick="startVideo('${videoId}')" title="Play Video">
                                <span class="duration-badge">${item.duration}</span>
                            </div>
                            <div class="info-container">
                                <h4 title="${item.title}">${item.title}</h4>
                                <p>${uploader}</p>
                                <div class="action-row-video">
                                    <button class="play-btn-full" onclick="startVideo('${item.url || item.id}')">▶ PLAY VIDEO</button>
                                    <button class="dl-btn-full" onclick="triggerDownload(${index}, 'mp4')">📥 DL</button>
                                </div>
                            </div>
                        </div>`;
                }
            });
            attachRipples();
        }

        function toggleAll() { const c = document.getElementById('selectAll').checked; document.querySelectorAll('.song-checkbox').forEach(cb => cb.checked = c); }

        function openFullThumbList(src, vidId) { 
            document.getElementById('fullThumbImg').src = src; 
            currentPlayingVideoId = vidId; 
            document.getElementById('thumbModal').style.display = 'flex'; 
        }

        function playFromLightbox() {
            document.getElementById('thumbModal').style.display = 'none';
            if(currentPlayingVideoId) { startVideo(currentPlayingVideoId); }
        }

        // DOWNLOADER
        let pendingDlUrl = ""; let pendingDlTitle = ""; let pendingDlType = "";
        
        function triggerDownload(index, type) {
            const item = currentResults[index];
            pendingDlUrl = item.url || item.id; pendingDlTitle = item.title; pendingDlType = type;
            const list = document.getElementById('qualityList'); list.innerHTML = '';
            document.getElementById('modalTitle').innerText = type === 'mp4' ? "Select MP4 Quality" : "Select MP3 Quality";
            
            if(type === 'mp4') {
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('best')"><span>⭐ AUTO BEST</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('1080p')"><span>📽️ 1080p</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('720p')"><span>📽️ 720p</span></div>`;
            } else {
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('320')"><span>⭐ 320 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('256')"><span>🎵 256 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('192')"><span>🎵 192 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('128')"><span>📱 128 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('64')"><span>📉 64 kbps</span></div>`;
            }
            document.getElementById('qualityModal').style.display = 'flex';
        }
        
        function downloadCurrentSong(e) {
            if(e) e.stopPropagation();
            if(currentAudioDlTaskId) return; 
            if(currentIndex >= 0 && currentIndex < audioQueue.length) {
                const item = audioQueue[currentIndex];
                pendingDlUrl = item.url || item.id; pendingDlTitle = item.title; pendingDlType = 'mp3';
                const list = document.getElementById('qualityList'); list.innerHTML = '';
                document.getElementById('modalTitle').innerText = "Select MP3 Quality";
                list.innerHTML += `<div class="quality-item best" onclick="fireBgTask('320', true)"><span>⭐ 320 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('256', true)"><span>🎵 256 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('192', true)"><span>🎵 192 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('128', true)"><span>📱 128 kbps</span></div>`;
                list.innerHTML += `<div class="quality-item" onclick="fireBgTask('64', true)"><span>📉 64 kbps</span></div>`;
                document.getElementById('qualityModal').style.display = 'flex';
            }
        }

        async function fireBgTask(quality, isFromPlayer = false) {
            document.getElementById('qualityModal').style.display = 'none';
            showToast("Download Started!", "info");
            let convMode = localStorage.getItem('audio_conversion_mode') || 'fast';

            try {
                const res = await fetch('/api/download', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ client_id: clientId, url: pendingDlUrl, title: pendingDlTitle, type: pendingDlType, quality: quality, burn_subs: false, conv_mode: convMode }) 
                });
                const data = await res.json();
                if (isFromPlayer && data.task_id) {
                    currentAudioDlTaskId = data.task_id;
                    const btn = document.getElementById('mainPlayerDlBtn');
                    btn.disabled = true; btn.innerText = "⏳ Starting..."; btn.style.background = "#334155";
                }
            } catch(e) { showToast("Download failed to start: " + e.message, "error");}
        }

        function triggerFileDownload(fileUrl, title, ext) {
            const link = document.createElement('a');
            link.href = fileUrl;
            let cleanTitle = title.replace(/[^a-zA-Z0-9 ]/g, "");
            link.download = `${cleanTitle}.${ext}`; 
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function processDeliveryQueue() {
            if(isDelivering || deliveryQueue.length === 0) return;
            isDelivering = true;
            const item = deliveryQueue.shift();
            triggerFileDownload(item.url, item.title, item.ext);
            setTimeout(() => { isDelivering = false; processDeliveryQueue(); }, 1500); 
        }

        setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks?client_id=${clientId}`);
                const tasks = await res.json();
                
                let html = ''; 

                for (const [id, t] of Object.entries(tasks)) {
                    let sCol = t.status==='completed' ? '#1db954' : (t.status==='error' ? '#ff0844' : '#4facfe');
                    
                    let safeTitle = t.title.replace(/'/g, "\\'");
                    let dlUrl = `/api/serve?file=${encodeURIComponent(t.file)}`;
                    let saveBtnHtml = `<button class="action-btn btn-mp4" style="width:100%; padding:10px; margin-top:10px; background:#1db954;" onclick="triggerFileDownload('${dlUrl}', '${safeTitle}', '${t.type}')">💾 SAVE</button>`;

                    html += `<div class="task-item" style="background: rgba(255,255,255,0.05); border-color: ${sCol};"><div class="task-header" style="color: white;"><span>${t.type.toUpperCase()}: ${t.title}</span><span style="color:${sCol}">${t.status.toUpperCase()}</span></div>
                            ${(t.status === 'downloading' || t.status === 'processing') ? `<div class="progress-bar-bg"><div class="progress-fill" style="width: ${t.percent}%"></div></div><div class="progress-stats" style="color:${sCol};"><span>${t.percent}%</span></div>` : ''}
                            ${t.status === 'error' ? `<div style="font-size:0.85rem; color:#ff0844;">${t.error_msg}</div>` : ''}
                            ${t.status === 'completed' ? saveBtnHtml : ''}</div>`;
                            
                    if (t.status === 'completed' && !handledDownloads.includes(id)) {
                        markHandled(id); 
                        showToast(`Download Complete: ${t.title}`, "success");
                        deliveryQueue.push({ url: dlUrl, title: t.title, ext: t.type }); 
                        processDeliveryQueue(); 
                    }
                }
                document.getElementById('tasksWrapper').innerHTML = html || '<p style="text-align:center; color:#94a3b8;">No active downloads.</p>';
                
                if (currentAudioDlTaskId && tasks[currentAudioDlTaskId]) {
                    const t = tasks[currentAudioDlTaskId];
                    const btn = document.getElementById('mainPlayerDlBtn');
                    if (t.status === 'downloading' || t.status === 'processing') {
                        btn.innerText = t.status === 'processing' ? '⏳ Merging...' : `⏳ ${t.percent}%`;
                        btn.style.background = `linear-gradient(90deg, #ff0844 ${t.percent}%, #334155 ${t.percent}%)`;
                    } else if (t.status === 'completed') {
                        btn.innerText = '✅ SAVED'; btn.style.background = '#1db954';
                        currentAudioDlTaskId = null; 
                        setTimeout(() => { btn.innerText = '📥 Download MP3'; btn.style.background = ''; btn.disabled = false; }, 4000);
                    } else if (t.status === 'error') {
                        btn.innerText = '❌ Error'; btn.style.background = '#ff0844';
                        currentAudioDlTaskId = null; 
                        setTimeout(() => { btn.innerText = '📥 Download MP3'; btn.style.background = ''; btn.disabled = false; }, 3000);
                    }
                }
            } catch(e) {}
        }, 1000);

        // VIDEO LOGIC
        async function startVideo(id) {
            stopAudio(); 
            let itemToSave = currentResults.find(i => (i.id === id || i.url.includes(id))) || {title: "Video Stream", uploader: "Unknown", url: id};
            saveToHistory(itemToSave, 'video');

            const modal = document.getElementById('video-modal');
            modal.style.display = 'flex';
            
            const ytLink = document.getElementById('ytFallbackLink');
            ytLink.href = `https://youtube.com/watch?v=${id}`;
            ytLink.style.display = 'block';

            document.getElementById('ytIframe').src = `https://www.youtube.com/embed/${id}?autoplay=1`;
            
            try {
                const container = document.getElementById('videoContainer');
                if (container.requestFullscreen) { await container.requestFullscreen(); }
                if (screen.orientation && screen.orientation.lock) { await screen.orientation.lock("landscape"); }
            } catch(e) {}
        }
        
        async function closeVideo() {
            document.getElementById('video-modal').style.display = 'none';
            document.getElementById('ytIframe').src = "";
            try { 
                if (document.exitFullscreen) { await document.exitFullscreen(); }
                if (screen.orientation && screen.orientation.unlock) { screen.orientation.unlock(); }
            } catch(e) {}
        }

        // V52 STRICT QUEUE AUDIO ENGINE
        function playSingleAudio(index) { 
            audioEngine.play().catch(e=>{}); 
            isErrorStopped = false;
            audioQueue = [currentResults[index]]; 
            currentIndex = 0; 
            loadQueueItem(); 
        }

        function playSelected() {
            audioEngine.play().catch(e=>{}); 
            isErrorStopped = false;
            const checked = document.querySelectorAll('.song-checkbox:checked');
            if(checked.length === 0) return alert("Select songs first!");
            audioQueue = Array.from(checked).map(cb => currentResults[parseInt(cb.value)]);
            currentIndex = 0; 
            loadQueueItem();
        }

        function startFadeIn() {
            clearInterval(fadeInterval);
            isFadingOut = false;
            audioEngine.volume = 0;
            let targetVol = parseInt(document.getElementById('volSlider').value) / 100;
            let step = targetVol / 30; 
            fadeInterval = setInterval(() => {
                if (audioEngine.volume + step < targetVol) { audioEngine.volume += step; } 
                else { audioEngine.volume = targetVol; clearInterval(fadeInterval); }
            }, 100);
        }

        function startFadeOutAndNext() {
            if (isFadingOut) return;
            isFadingOut = true;
            let startVol = audioEngine.volume;
            let step = startVol / 30; 
            fadeInterval = setInterval(() => {
                if (audioEngine.volume > step) { audioEngine.volume -= step; } 
                else { audioEngine.volume = 0; clearInterval(fadeInterval); nextSong(); }
            }, 100);
        }

        async function loadQueueItem() {
            if(currentIndex < 0 || currentIndex >= audioQueue.length) {
                audioEngine.pause();
                document.getElementById('playPauseBtn').innerText = '▶';
                document.getElementById('ap-cover').classList.remove('playing-glow', 'vinyl-mode');
                return;
            }
            const item = audioQueue[currentIndex];
            const titleEl = document.getElementById('ap-title');
            const artistEl = document.getElementById('ap-artist');
            currentPlayingVideoId = item.id || (item.url ? item.url.split('v=')[1] : '');
            
            saveToHistory(item, 'audio'); 

            document.getElementById('audio-player-bar').classList.add('active'); 
            document.getElementById('audio-player-bar').classList.remove('mini');
            document.getElementById('ap-cover').src = item.thumbnail || "https://via.placeholder.com/150";
            document.getElementById('ap-yt-link').href = item.url || `https://youtube.com/watch?v=${item.id}`;
            
            titleEl.innerText = item.title || "Loading stream..."; 
            artistEl.innerText = item.uploader || "Unknown Artist";
            
            titleEl.classList.remove('scroll');
            document.getElementById('seekSlider').value = 0; document.getElementById('seekSlider').style.background = `#334155`;
            
            currentAudioDlTaskId = null;
            document.getElementById('mainPlayerDlBtn').innerText = '📥 Download MP3';
            document.getElementById('mainPlayerDlBtn').style.background = ''; document.getElementById('mainPlayerDlBtn').disabled = false;
            
            showLoader();
            try {
                const res = await fetch('/api/stream_audio', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url: item.url || item.id}) });
                const data = await res.json();
                
                if(data.error) { throw new Error(data.error); }
                
                if(data.stream_url) {
                    audioEngine.src = data.stream_url;
                    audioEngine.playbackRate = currentSpeed;
                    
                    audioEngine.play().then(() => {
                        startFadeIn();
                        if(isVinylMode) document.getElementById('ap-cover').classList.add('vinyl-mode');
                    }).catch(e => {
                        showToast("Autoplay Blocked. Tap Play.", "error");
                        audioEngine.volume = parseInt(document.getElementById('volSlider').value) / 100;
                    });
                    
                    setTimeout(() => {
                        const wrapper = document.querySelector('.marquee-wrapper');
                        if (titleEl.scrollWidth > wrapper.clientWidth + 10) titleEl.classList.add('scroll');
                    }, 100);

                    if ('mediaSession' in navigator) {
                        navigator.mediaSession.metadata = new MediaMetadata({ title: item.title, artist: item.uploader || "Unknown Artist", artwork: [ { src: item.thumbnail, sizes: '512x512', type: 'image/jpeg' } ] });
                        navigator.mediaSession.setActionHandler('play', () => togglePlay()); navigator.mediaSession.setActionHandler('pause', () => togglePlay());
                        navigator.mediaSession.setActionHandler('previoustrack', () => prevSong()); navigator.mediaSession.setActionHandler('nexttrack', () => nextSong());
                    }
                }
            } catch (err) { 
                isErrorStopped = true;
                showToast("Stream Error. Playback stopped.", "error"); 
                stopAudio(); 
            }
            finally { hideLoader(); }
        }

        function toggleMiniPlayer(e) { if(e) e.stopPropagation(); document.getElementById('audio-player-bar').classList.toggle('mini'); }

        function togglePlay(e) { 
            if(e) e.stopPropagation(); 
            if(audioEngine.paused) {
                audioEngine.volume = document.getElementById('volSlider').value / 100;
                audioEngine.play().catch(e => showToast("Playback error.", "error"));
            } else {
                audioEngine.pause(); 
            }
        }
        
        function nextSong(e) { 
            if(e) e.stopPropagation(); 
            if(isErrorStopped) return; 
            clearInterval(fadeInterval); isFadingOut = false; 
            if (loopMode === 2) { audioEngine.currentTime = 0; audioEngine.play(); return; }
            if (currentIndex < audioQueue.length - 1) { currentIndex++; loadQueueItem(); }
            else if (loopMode === 1) { currentIndex = 0; loadQueueItem(); }
            else {
                audioEngine.pause();
                document.getElementById('playPauseBtn').innerText = '▶';
                document.getElementById('ap-cover').classList.remove('playing-glow', 'vinyl-mode');
            }
        }
        
        function prevSong(e) { 
            if(e) e.stopPropagation();
            if(isErrorStopped) return;
            clearInterval(fadeInterval); isFadingOut = false;
            if(audioEngine.currentTime > 3 || loopMode === 2) { audioEngine.currentTime = 0; startFadeIn(); audioEngine.play();} 
            else if (currentIndex > 0) { currentIndex--; loadQueueItem(); } 
            else if (loopMode === 1) { currentIndex = audioQueue.length - 1; loadQueueItem(); }
        }
        
        function stopAudio(e) { 
            if(e) e.stopPropagation();
            clearInterval(fadeInterval); isFadingOut = false;
            audioEngine.pause(); audioEngine.src = ""; document.getElementById('audio-player-bar').classList.remove('active'); 
            document.getElementById('ap-cover').classList.remove('playing-glow', 'vinyl-mode');
        }

        audioEngine.onended = () => { if(!isFadingOut) nextSong(); };
        audioEngine.onplay = () => { document.getElementById('playPauseBtn').innerText = '⏸'; document.getElementById('ap-cover').classList.add('playing-glow'); if(isVinylMode) document.getElementById('ap-cover').classList.add('vinyl-mode');};
        audioEngine.onpause = () => { document.getElementById('playPauseBtn').innerText = '▶'; document.getElementById('ap-cover').classList.remove('playing-glow', 'vinyl-mode'); };

        function formatTimeDetailed(sec) {
            if(isNaN(sec)) return "0:00";
            let h = Math.floor(sec / 3600); let m = Math.floor((sec % 3600) / 60); let s = Math.floor(sec % 60);
            if (h > 0) return `${h}:${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
            return `${m}:${s < 10 ? '0' : ''}${s}`;
        }

        audioEngine.ontimeupdate = () => {
            let val = (audioEngine.currentTime / audioEngine.duration) * 100 || 0;
            document.getElementById('seekSlider').value = val;
            document.getElementById('seekSlider').style.background = `linear-gradient(to right, #ff0844 ${val}%, #334155 ${val}%)`;
            document.getElementById('currTime').innerText = formatTimeDetailed(audioEngine.currentTime);
            document.getElementById('durTime').innerText = formatTimeDetailed(audioEngine.duration);
            
            let timeLeft = audioEngine.duration - audioEngine.currentTime;
            if (timeLeft <= 3.0 && timeLeft > 0 && !isFadingOut && loopMode !== 2 && (currentIndex < audioQueue.length - 1 || loopMode === 1)) {
                startFadeOutAndNext();
            }
        };
        
        document.getElementById('seekSlider').oninput = (e) => { 
            let val = e.target.value; audioEngine.currentTime = (val / 100) * audioEngine.duration; 
            document.getElementById('seekSlider').style.background = `linear-gradient(to right, #ff0844 ${val}%, #334155 ${val}%)`; 
        };

        function toggleSpeed() {
            if(currentSpeed === 1.0) currentSpeed = 1.25; 
            else if(currentSpeed === 1.25) currentSpeed = 1.5; 
            else if(currentSpeed === 1.5) currentSpeed = 2.0; 
            else currentSpeed = 1.0;
            
            audioEngine.playbackRate = currentSpeed; 
            document.getElementById('speedBtn').innerText = currentSpeed + 'x'; 
            document.getElementById('speedBtn').classList.toggle('active', currentSpeed !== 1.0);
            showToast(`Playback Speed: ${currentSpeed}x`, "info");
        }

        function toggleLoop() {
            loopMode = (loopMode + 1) % 3;
            const btn = document.getElementById('loopBtn');
            if (loopMode === 0) { btn.innerText = '🔁'; btn.classList.remove('active'); showToast("Loop Off", "info"); }
            if (loopMode === 1) { btn.innerText = '🔁'; btn.classList.add('active'); showToast("Looping Queue", "info");} 
            if (loopMode === 2) { btn.innerText = '🔂'; btn.classList.add('active'); showToast("Looping Current Song", "info");} 
        }

        function openSleepModal() {
            const btn = document.getElementById('sleepBtn');
            if(sleepTimer) {
                clearInterval(sleepTimer); sleepTimer = null;
                btn.classList.remove('active'); 
                document.getElementById('sleepRing').style.background = 'transparent';
                showToast("Sleep timer cancelled", "info");
                return;
            }
            document.getElementById('sleepModal').style.display = 'flex';
        }

        function setSleepTimer() {
            const mins = parseInt(document.getElementById('sleepInput').value);
            if(isNaN(mins) || mins <= 0) return showToast("Enter a valid time", "error");
            
            document.getElementById('sleepModal').style.display = 'none';
            totalSleepTime = mins * 60; sleepTimeLeft = totalSleepTime;
            document.getElementById('sleepBtn').classList.add('active');
            showToast(`Media will pause in ${mins} minutes`, "success");
            
            sleepTimer = setInterval(() => {
                sleepTimeLeft--;
                let pct = (sleepTimeLeft / totalSleepTime) * 100;
                document.getElementById('sleepRing').style.background = `conic-gradient(#ff0844 ${pct}%, transparent ${pct}%)`;
                
                if(sleepTimeLeft <= 0) {
                    clearInterval(sleepTimer); sleepTimer = null;
                    document.getElementById('sleepBtn').classList.remove('active');
                    document.getElementById('sleepRing').style.background = 'transparent';
                    
                    audioEngine.pause();
                    showToast("Sleep Timer finished. Playback paused.", "info");
                }
            }, 1000);
        }

        function shareSong() {
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
    return jsonify({
        "name": "Music Player and Downloader", 
        "short_name": "Music Player", 
        "start_url": "/", 
        "display": "standalone", 
        "background_color": "#0f172a", 
        "theme_color": "#0f172a", 
        "icons": [{"src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' fill='%230f172a'/%3E%3Ctext y='70' x='25' font-size='60'%3E⚡%3C/text%3E%3C/svg%3E", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"}], 
        "share_target": { "action": "/", "method": "GET", "enctype": "application/x-www-form-urlencoded", "params": { "title": "title", "text": "text", "url": "url" } }
    })

@app.route('/sw.js')
def serve_sw(): 
    return Response("self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });", mimetype='application/javascript')

@app.route('/', strict_slashes=False)
@app.route('/player', strict_slashes=False)
def media_player(): 
    return render_template_string(PLAYER_HTML)

@app.route('/api/stream_audio', methods=['POST'], strict_slashes=False)
def stream_audio():
    url = request.json.get('url')
    # V52: Strip proxies, use decentralized fallback logic
    vid_id = extract_video_id(url)
    
    ydl_opts = { 
        'quiet': True, 
        'format': 'bestaudio/best', 
        'noplaylist': True, 
        'geo_bypass': True, 
        'geo_bypass_country': 'US'
    }
    try:
        # Try direct yt-dlp first
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url') 
            if stream_url: 
                return jsonify({'stream_url': stream_url})
            else: 
                raise Exception("No stream found via direct fetch")
    except Exception as e: 
        logger.warning(f"Direct stream failed ({e}). Engaging Phantom Routing via Piped API...")
        # V52 GHOST FALLBACK
        fallback_url = get_piped_stream(vid_id)
        if fallback_url:
            return jsonify({'stream_url': fallback_url})
        return jsonify({'error': 'All extraction methods failed.'}), 500

@app.route('/api/tasks', methods=['GET'], strict_slashes=False)
def get_tasks():
    client_id = request.args.get('client_id')
    return jsonify({k: v for k, v in active_tasks.items() if v.get('client_id') == client_id})

@app.route('/api/info', methods=['POST'], strict_slashes=False)
def get_info():
    url = request.json.get('url')
    mode = request.json.get('mode')
    limit = request.json.get('limit', 10) 
    if mode != 'search' and 'list=RD' in url: 
        return jsonify({'error': 'Infinite loop detected.'})

    ydl_opts = {
        'quiet': True, 
        'color': 'no_color', 
        'extract_flat': True if mode in ['playlist', 'search'] else False, 
        'noplaylist': mode in ['single', 'search'], 
        'geo_bypass': True, 
        'geo_bypass_country': 'US'
    }
    try:
        fetch_url = f"ytsearch{limit}:{url}" if mode == 'search' else url
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
    except Exception as e: 
        logger.warning(f"Search API Error: {e}")
        # V52 GHOST FALLBACK FOR SEARCHING
        if mode == 'search':
            try:
                res = requests.get(f"https://pipedapi.kavin.rocks/search?q={urllib.parse.quote(url)}&filter=all", timeout=10)
                if res.status_code == 200:
                    items = res.json().get('items', [])
                    entries = []
                    for item in items:
                        if item.get('type') == 'stream':
                            dur = item.get('duration', 0)
                            m, s = divmod(dur, 60); h, m = divmod(m, 60)
                            dur_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
                            entries.append({
                                'id': item['url'].split('v=')[-1],
                                'title': item['title'],
                                'url': 'https://youtube.com/watch?v=' + item['url'].split('v=')[-1],
                                'thumbnail': item['thumbnail'],
                                'uploader': item['uploaderName'],
                                'duration': dur_str
                            })
                    if entries:
                        return jsonify({'entries': entries[:limit]})
            except Exception as pe:
                logger.error(f"Fallback search failed: {pe}")
        return jsonify({'error': "All extraction methods blocked. Try again later."})

def background_downloader(task_id, url, dl_type, quality, burn_subs, conv_mode):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s', 'quiet': True, 'color': 'no_color', 
        'geo_bypass': True, 'geo_bypass_country': 'US', 'nocheckcertificate': True, 'restrictfilenames': True,
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
        if conv_mode == 'full':
            ydl_opts['writethumbnail'] = True 
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}, {'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
        elif conv_mode == 'fast':
            ydl_opts['writethumbnail'] = True 
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            ydl_opts['postprocessors'] = [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}]
        else:
            ydl_opts['writethumbnail'] = False
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [] 

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
            
            if dl_type == 'mp3' and conv_mode == 'rename':
                final_mp3_path = name_without_ext + '.mp3'
                if actual_file != final_mp3_path and os.path.exists(actual_file):
                    os.replace(actual_file, final_mp3_path) 
                    actual_file = final_mp3_path

            active_tasks[task_id]['status'] = 'completed'
            active_tasks[task_id]['file'] = actual_file
            active_tasks[task_id]['completed_at'] = time.time() 
    except Exception as e:
        logger.warning(f"Download failed: {e}. Attempting Ghost Download via Piped...")
        # V52 GHOST DOWNLOAD FALLBACK
        try:
            vid_id = extract_video_id(url)
            stream_url = get_piped_stream(vid_id)
            if stream_url:
                raw_file = os.path.join(DOWNLOAD_DIR, f"{task_id}_raw.m4a")
                r = requests.get(stream_url, stream=True, timeout=10)
                r.raise_for_status()
                with open(raw_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
                
                final_name = active_tasks[task_id]['title'].replace('/', '_').replace('\\', '_')
                final_path = os.path.join(DOWNLOAD_DIR, f"{final_name}.{dl_type}")
                
                # Convert
                if dl_type == 'mp3':
                    os.system(f"ffmpeg -i '{raw_file}' -q:a 0 -map a '{final_path}' -y")
                else:
                    os.replace(raw_file, final_path)
                
                if os.path.exists(raw_file): os.remove(raw_file)
                
                active_tasks[task_id]['status'] = 'completed'
                active_tasks[task_id]['file'] = final_path
                active_tasks[task_id]['completed_at'] = time.time() 
                return
        except Exception as fallback_e:
            logger.error(f"Fallback download failed: {fallback_e}")
            
        active_tasks[task_id]['status'] = 'error'; active_tasks[task_id]['error_msg'] = "All download methods failed (IP Blocked)"

@app.route('/api/download', methods=['POST'], strict_slashes=False)
def trigger_download():
    task_id = str(uuid.uuid4())
    conv_mode = request.json.get('conv_mode', 'fast')
    active_tasks[task_id] = {'client_id': request.json.get('client_id', 'unknown'), 'title': request.json.get('title', 'Unknown Task'), 'type': request.json.get('type'), 'status': 'starting', 'percent': 0, 'speed': '0 MB/s', 'eta': '--:--', 'file': None, 'error_msg': None, 'created_at': time.time()}
    threading.Thread(target=background_downloader, args=(task_id, request.json.get('url'), request.json.get('type'), request.json.get('quality'), request.json.get('burn_subs', False), conv_mode), daemon=True).start()
    return jsonify({'task_id': task_id})

@app.route('/api/serve', methods=['GET'], strict_slashes=False)
def serve_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path): return "File not found", 404
    
    filename = urllib.parse.unquote(os.path.basename(file_path))
    return send_file(os.path.abspath(file_path), as_attachment=True, download_name=filename)

@app.errorhandler(404)
def page_not_found(e):
    return redirect('/')

if __name__ == '__main__':
    print("\n" + "="*50 + "\n 🔥 MUSIC PLAYER AND DOWNLOADER V52 ONLINE 🔥\n" + "="*50 + "\n")
    app.run(host="0.0.0.0", port=5000)
