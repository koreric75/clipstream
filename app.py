#!/usr/bin/env python3
"""
ClipStream - Streamlit Web Interface
Modern web UI for video intro automation
"""

import os
import sys
import json
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from yt_automation.auth import get_service
from yt_automation.editor import stitch_intro, stitch_intro_auto, is_vertical_video
from yt_automation.youtube_ops import (
    list_videos, upload_video, set_thumbnail,
    get_video_details, get_video_playlists, add_video_to_playlist
)
from yt_automation.storage import (
    get_folder_size, format_size, check_storage_warning,
    cleanup_folder, storage_status, STORAGE_WARNING_THRESHOLD
)

# Load environment variables
load_dotenv()

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly',
          'https://www.googleapis.com/auth/youtube']
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE', 'client_secrets.json')

# Intro files - horizontal (16:9) for regular videos
INTRO_VIDEO = os.getenv('INTRO_VIDEO', 'intro.mp4')
INTRO_THUMBNAIL = os.getenv('INTRO_THUMBNAIL', 'intro.jpg')

# Intro files - vertical (9:16) for Shorts
INTRO_VIDEO_SHORT = os.getenv('INTRO_VIDEO_SHORT', 'intro_short.mp4')
INTRO_THUMBNAIL_SHORT = os.getenv('INTRO_THUMBNAIL_SHORT', 'intro_short.jpg')

OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', 'output'))
DOWNLOAD_DIR = Path('downloads')

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# History file
HISTORY_FILE = Path('clipstream_history.json')

# ─── History / Analytics System ───────────────────────────────────────────────

def _load_history() -> list:
    """Load processing history from disk."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def _save_history(history: list):
    """Persist history to disk."""
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def add_history_event(event_type: str, title: str, details: dict | None = None):
    """Append an event to the history log."""
    history = _load_history()
    history.insert(0, {
        'timestamp': datetime.now().isoformat(),
        'type': event_type,          # 'process', 'upload', 'download', 'cleanup'
        'title': title,
        'details': details or {},
    })
    # Keep last 200 events
    _save_history(history[:200])


def get_history_stats() -> dict:
    """Derive aggregate statistics from history."""
    history = _load_history()
    now = datetime.now()
    today = now.date()
    week_ago = now - timedelta(days=7)

    stats = {
        'total_processed': 0,
        'total_uploaded': 0,
        'total_shorts': 0,
        'today_processed': 0,
        'week_processed': 0,
        'recent': history[:8],
    }
    for e in history:
        ts = datetime.fromisoformat(e['timestamp'])
        if e['type'] == 'process':
            stats['total_processed'] += 1
            if ts.date() == today:
                stats['today_processed'] += 1
            if ts >= week_ago:
                stats['week_processed'] += 1
            if e.get('details', {}).get('is_short'):
                stats['total_shorts'] += 1
        elif e['type'] == 'upload':
            stats['total_uploaded'] += 1
    return stats

# Page configuration
st.set_page_config(
    page_title="ClipStream",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Inject all CSS + brand styling ──────────────────────────────────────────┐
st.markdown("""
<style>
    /* ──── Google Fonts ──── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* ──── Brand tokens (logo: dark charcoal + orange/purple/cyan gradient) ──── */
    :root {
        --cs-bg-dark:       #1F2023;
        --cs-bg-card:       #27282D;
        --cs-accent-gold:   #FFE566;
        --cs-accent-cream:  #FFF5CA;
        --cs-accent-orange: #FF8A50;
        --cs-accent-purple: #9B59B6;
        --cs-accent-cyan:   #3EC6E0;
        --cs-action:        #FF6B6B;
        --cs-action-hover:  #FF5252;
        --cs-success:       #4CAF50;
        --cs-warning:       #FFB74D;
        --cs-text:          #F5F5F5;
        --cs-text-muted:    #9E9E9E;
        --cs-border:        #3A3B40;
        --cs-glow-gold:     rgba(255,229,102,0.25);
        --cs-glow-action:   rgba(255,107,107,0.35);
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ──── Keyframe Animations ──── */
    @keyframes fadeSlideUp {
        from { opacity:0; transform:translateY(18px); }
        to   { opacity:1; transform:translateY(0); }
    }
    @keyframes pulseGlow {
        0%,100% { box-shadow: 0 0 8px var(--cs-glow-gold); }
        50%     { box-shadow: 0 0 22px var(--cs-glow-gold); }
    }
    @keyframes shimmer {
        0%   { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }
    @keyframes gradientShift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    @keyframes countUp {
        from { opacity:0; transform: scale(0.8); }
        to   { opacity:1; transform: scale(1); }
    }

    /* ──── Header ──── */
    .main-header {
        font-size: 2.8rem; font-weight: 800;
        background: linear-gradient(135deg, var(--cs-accent-gold), var(--cs-accent-cream), var(--cs-accent-gold));
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        text-align: center; padding: 1.5rem 0; letter-spacing: -0.5px;
    }
    .tagline {
        text-align:center; color:var(--cs-text-muted); font-size:1.05rem;
        margin-top:-0.4rem; margin-bottom:1.2rem;
    }

    /* ──── Dashboard stat card ──── */
    .stat-card {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border: 1px solid var(--cs-border);
        border-radius: 16px;
        padding: 1.4rem 1.2rem;
        text-align: center;
        animation: fadeSlideUp 0.5s ease-out both;
        transition: transform 0.22s, box-shadow 0.22s;
        position: relative;
        overflow: hidden;
    }
    .stat-card::before {
        content: '';
        position: absolute; inset: 0;
        background: linear-gradient(135deg, transparent 40%, rgba(255,255,255,0.03) 100%);
        pointer-events: none;
    }
    .stat-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 28px rgba(0,0,0,0.4);
    }
    .stat-card .stat-icon { font-size: 2rem; margin-bottom: 0.3rem; }
    .stat-card .stat-value {
        font-size: 2.2rem; font-weight: 800;
        background: linear-gradient(135deg, var(--cs-accent-gold), var(--cs-accent-orange));
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        animation: countUp 0.6s ease-out both;
    }
    .stat-card .stat-label {
        font-size: 0.82rem; color: var(--cs-text-muted);
        text-transform: uppercase; letter-spacing: 1px; margin-top: 0.2rem;
    }

    /* ──── Accent-coloured stat cards ──── */
    .stat-card.accent-coral  { border-bottom: 3px solid var(--cs-action); }
    .stat-card.accent-gold   { border-bottom: 3px solid var(--cs-accent-gold); }
    .stat-card.accent-purple { border-bottom: 3px solid var(--cs-accent-purple); }
    .stat-card.accent-cyan   { border-bottom: 3px solid var(--cs-accent-cyan); }

    /* ──── Quick Action Card ──── */
    .quick-action {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border: 1px solid var(--cs-border);
        border-radius: 14px;
        padding: 1.5rem 1rem;
        text-align: center;
        transition: all 0.25s;
        cursor: default;
    }
    .quick-action:hover {
        border-color: var(--cs-accent-gold);
        box-shadow: 0 6px 24px var(--cs-glow-gold);
        transform: translateY(-3px);
    }
    .quick-action .qa-icon { font-size: 2.4rem; margin-bottom: 0.5rem; }
    .quick-action .qa-title { font-weight: 700; font-size: 1rem; color: var(--cs-text); }
    .quick-action .qa-desc  { font-size: 0.82rem; color: var(--cs-text-muted); margin-top: 0.3rem; }

    /* ──── Activity Feed ──── */
    .activity-item {
        display: flex; align-items: flex-start; gap: 12px;
        padding: 0.7rem 0; border-bottom: 1px solid #2E2F34;
        animation: fadeSlideUp 0.4s ease-out both;
    }
    .activity-dot {
        width: 10px; height: 10px; border-radius: 50%;
        margin-top: 6px; flex-shrink: 0;
    }
    .activity-dot.type-process { background: var(--cs-accent-gold); }
    .activity-dot.type-upload  { background: var(--cs-action); }
    .activity-dot.type-cleanup { background: var(--cs-accent-cyan); }
    .activity-dot.type-download{ background: var(--cs-accent-purple); }
    .activity-text { flex: 1; }
    .activity-text .at-title { font-size: 0.88rem; color: var(--cs-text); }
    .activity-text .at-time  { font-size: 0.75rem; color: var(--cs-text-muted); }

    /* ──── Pipeline Steps ──── */
    .pipeline {
        display: flex; align-items: center; justify-content: center;
        gap: 0; padding: 1.2rem 0; flex-wrap: wrap;
    }
    .pipe-step {
        display: flex; flex-direction: column; align-items: center;
        padding: 0.8rem 1.2rem; border-radius: 12px;
        background: var(--cs-bg-card); border: 1px solid var(--cs-border);
        min-width: 100px; transition: all 0.3s;
    }
    .pipe-step.active {
        border-color: var(--cs-accent-gold);
        box-shadow: 0 0 18px var(--cs-glow-gold);
        animation: pulseGlow 1.8s infinite;
    }
    .pipe-step.done {
        border-color: var(--cs-success);
        background: linear-gradient(145deg, #1B3D1F, #153318);
    }
    .pipe-icon  { font-size: 1.6rem; margin-bottom: 0.3rem; }
    .pipe-label { font-size: 0.78rem; color: var(--cs-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .pipe-arrow { font-size: 1.4rem; color: var(--cs-border); padding: 0 0.3rem; align-self: center; }

    /* ──── Empty-state illustration ──── */
    .empty-state {
        text-align: center; padding: 3rem 1rem;
        animation: fadeSlideUp 0.6s ease-out both;
    }
    .empty-state .es-icon { font-size: 4rem; opacity: 0.5; margin-bottom: 0.5rem; }
    .empty-state .es-title { font-size: 1.2rem; font-weight: 600; color: var(--cs-text); }
    .empty-state .es-desc  { font-size: 0.9rem; color: var(--cs-text-muted); max-width: 380px; margin: 0.5rem auto 0; }

    /* ──── Status card ──── */
    .status-card {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border: 1px solid var(--cs-border); border-radius: 12px;
        padding: 1.25rem; margin: 0.5rem 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .success-box {
        background: linear-gradient(145deg, #1B3D1F, #153318);
        border-left: 4px solid var(--cs-success);
        border-radius: 8px; padding: 1rem 1.25rem; color: #A5D6A7;
    }
    .warning-box {
        background: linear-gradient(145deg, #3D2E0F, #332508);
        border-left: 4px solid var(--cs-warning);
        border-radius: 8px; padding: 1rem 1.25rem; color: #FFE082;
    }

    /* ──── Buttons ──── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--cs-action), #FF8A65) !important;
        border: none !important; border-radius: 10px !important;
        font-weight: 600 !important; letter-spacing: 0.3px;
        box-shadow: 0 4px 14px var(--cs-glow-action) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, var(--cs-action-hover), #FF7043) !important;
        box-shadow: 0 6px 20px var(--cs-glow-action) !important;
        transform: translateY(-2px) !important;
    }
    .stButton > button:not([kind="primary"]) {
        background: var(--cs-bg-card) !important;
        border: 1px solid var(--cs-border) !important;
        border-radius: 10px !important; color: var(--cs-text) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        background: #3A3B40 !important; border-color: var(--cs-accent-gold) !important;
    }

    /* ──── Progress bar ──── */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, var(--cs-action), var(--cs-accent-gold)) !important;
    }

    /* ──── Sticky process panel ──── */
    .sticky-container {
        position: sticky; top: 0; z-index: 999;
        background: linear-gradient(180deg, var(--cs-bg-dark) 0%, rgba(31,32,35,0.97) 100%);
        padding: 1rem 0; border-bottom: 2px solid var(--cs-accent-gold);
        margin-bottom: 1rem; backdrop-filter: blur(12px);
    }

    /* ──── Tabs ──── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px; background: var(--cs-bg-card); border-radius: 12px; padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px; padding: 10px 20px; font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, var(--cs-accent-orange), var(--cs-accent-purple)) !important;
        color: white !important;
    }
    .stTabs [aria-selected="true"] p,
    .stTabs [aria-selected="true"] span { color: white !important; }

    /* ──── Inputs ──── */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        background: var(--cs-bg-card) !important;
        border: 1px solid var(--cs-border) !important; border-radius: 10px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: var(--cs-accent-gold) !important;
        box-shadow: 0 0 0 2px var(--cs-glow-gold) !important;
    }

    /* ──── Sidebar ──── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--cs-bg-dark), #15161A);
        border-right: 1px solid var(--cs-border);
    }

    /* ──── Metrics ──── */
    [data-testid="metric-container"] {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border: 1px solid var(--cs-border); border-radius: 14px; padding: 1rem;
    }
    [data-testid="stMetricValue"] { color: var(--cs-accent-gold) !important; }

    /* ──── Video card (list page) ──── */
    .video-card {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border: 1px solid var(--cs-border); border-radius: 14px;
        padding: 1rem; margin-bottom: 0.6rem;
        transition: all 0.22s;
    }
    .video-card:hover {
        border-color: var(--cs-accent-gold);
        box-shadow: 0 4px 20px var(--cs-glow-gold);
    }

    /* ──── Badges ──── */
    .badge {
        display: inline-block; padding: 3px 10px; border-radius: 6px;
        font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    .badge-short  { background: linear-gradient(135deg, var(--cs-action), #FF8A65); color: white; }
    .badge-regular{ background: linear-gradient(135deg, var(--cs-accent-gold), var(--cs-accent-cream)); color: var(--cs-bg-dark); }

    /* ──── Divider / Alerts ──── */
    hr { border-color: var(--cs-border) !important; opacity: 0.4; }
    .stAlert { border-radius: 10px !important; }

    /* ──── File uploader ──── */
    [data-testid="stFileUploader"] {
        background: var(--cs-bg-card); border: 2px dashed var(--cs-border);
        border-radius: 14px; padding: 1rem;
        transition: border-color 0.25s;
    }
    [data-testid="stFileUploader"]:hover { border-color: var(--cs-accent-gold); }

    /* ──── Misc ──── */
    .stCheckbox > label > div[data-testid="stCheckbox"] { background: var(--cs-bg-card); }
    .streamlit-expanderHeader { background: var(--cs-bg-card) !important; border-radius: 10px !important; }
    .logo-container { text-align:center; padding:1rem 0; }
    .logo-container img { max-width:80px; filter: drop-shadow(0 4px 12px var(--cs-glow-gold)); }

    /* ──── Section titles ──── */
    .section-title {
        font-size: 1.15rem; font-weight: 700; color: var(--cs-text);
        padding-bottom: 0.4rem; margin-bottom: 0.8rem;
        border-bottom: 2px solid var(--cs-accent-gold);
        display: inline-block;
    }

    /* ──── Tip box ──── */
    .tip-box {
        background: linear-gradient(145deg, #2A2B30, var(--cs-bg-card));
        border-left: 4px solid var(--cs-accent-cyan);
        border-radius: 8px; padding: 0.8rem 1.1rem; margin: 0.5rem 0;
        font-size: 0.88rem; color: var(--cs-text-muted);
    }
    .tip-box strong { color: var(--cs-accent-cyan); }
</style>
""", unsafe_allow_html=True)
# └──────────────────────────────────────────────────────────────────────────────┘


def get_youtube_service():
    """Get authenticated YouTube service, caching in session state."""
    if 'youtube_service' not in st.session_state:
        try:
            st.session_state.youtube_service = get_service(CLIENT_SECRETS_FILE, SCOPES)
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            return None
    return st.session_state.youtube_service


def render_header():
    """Render the main header with wide logo."""
    # Wide logo for header (contains text)
    logo_wide_path = "assets/logo-wide.png"
    if os.path.exists(logo_wide_path):
        col1, col2, col3 = st.columns([1, 3, 1])
        with col2:
            st.image(logo_wide_path, width="stretch")
    else:
        # Fallback to text header if wide logo not found
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<p class="main-header">ClipStream</p>', unsafe_allow_html=True)
            st.markdown('<p class="tagline">Intro Stitcher & YouTube Uploader</p>', unsafe_allow_html=True)
    st.divider()


def render_sidebar():
    """Render the sidebar with status info."""
    with st.sidebar:
        # Brand logo in sidebar
        if os.path.exists("assets/logo.png"):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image("assets/logo.png", width=60)
        
        st.markdown("### 📊 Status")
        
        # Horizontal (16:9) intro status
        st.markdown("**📺 16:9 Intro** *(Regular)*")
        if os.path.exists(INTRO_VIDEO):
            st.markdown(f'<span style="color: #4CAF50;">✓ {INTRO_VIDEO}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color: #FFB74D;">⚠ No intro video</span>', unsafe_allow_html=True)
        
        if os.path.exists(INTRO_THUMBNAIL):
            st.markdown(f'<span style="color: #4CAF50;">✓ {INTRO_THUMBNAIL}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color: #9E9E9E;">ℹ No thumbnail</span>', unsafe_allow_html=True)
        
        # Vertical (9:16) intro status for Shorts
        st.markdown("")
        st.markdown("**📱 9:16 Intro** *(Shorts)*")
        if os.path.exists(INTRO_VIDEO_SHORT):
            st.markdown(f'<span style="color: #4CAF50;">✓ {INTRO_VIDEO_SHORT}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color: #FFB74D;">⚠ No Shorts intro</span>', unsafe_allow_html=True)
        
        if os.path.exists(INTRO_THUMBNAIL_SHORT):
            st.markdown(f'<span style="color: #4CAF50;">✓ {INTRO_THUMBNAIL_SHORT}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color: #9E9E9E;">ℹ No Shorts thumbnail</span>', unsafe_allow_html=True)
        
        # Client secrets
        st.divider()
        st.markdown("**🔑 API Status**")
        if os.path.exists(CLIENT_SECRETS_FILE):
            st.markdown('<span style="color: #4CAF50;">✓ Credentials found</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color: #FF6B6B;">✗ No API credentials</span>', unsafe_allow_html=True)
        
        st.divider()
        
        # Storage status
        st.markdown("### 💾 Storage")
        output_size = get_folder_size(OUTPUT_DIR)
        download_size = get_folder_size(DOWNLOAD_DIR)
        total_size = output_size + download_size
        
        # Progress bar for storage
        usage_percent = min(total_size / STORAGE_WARNING_THRESHOLD, 1.0)
        
        # Custom progress display
        progress_color = "#4CAF50" if usage_percent < 0.8 else "#FFB74D" if usage_percent < 1.0 else "#FF6B6B"
        st.markdown(f'''
        <div style="background: #3A3B40; border-radius: 8px; height: 12px; overflow: hidden; margin: 0.5rem 0;">
            <div style="background: linear-gradient(90deg, {progress_color}, #FFE566); width: {min(usage_percent * 100, 100)}%; height: 100%; border-radius: 8px; transition: width 0.3s;"></div>
        </div>
        <p style="text-align: center; color: #9E9E9E; font-size: 0.85rem;">{format_size(total_size)} / {format_size(STORAGE_WARNING_THRESHOLD)}</p>
        ''', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Output", format_size(output_size))
        with col2:
            st.metric("Downloads", format_size(download_size))
        
        if usage_percent >= 0.8:
            st.warning("⚠ Storage running low!")


def process_video_page():
    """Render the video processing page."""
    st.markdown('<span class="section-title">🎬 Process Video</span>', unsafe_allow_html=True)
    st.markdown("")
    st.markdown('''
    <div class="tip-box">
        <strong>ℹ️ How it works:</strong> Upload a video file and ClipStream will auto-detect its orientation, 
        select the matching intro (16:9 or 9:16), apply a smooth fade transition, and output the final video.
    </div>''', unsafe_allow_html=True)
    st.markdown("")
    
    # Check for intro
    if not os.path.exists(INTRO_VIDEO):
        st.error(f"❌ Intro video not found at '{INTRO_VIDEO}'. Please add an intro video first.")
        return
    
    # Show available intros
    col1, col2 = st.columns(2)
    with col1:
        if os.path.exists(INTRO_VIDEO):
            st.markdown('''
            <div class="stat-card" style="padding:0.8rem 1rem;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:1.6rem;">📺</span>
                    <div>
                        <div style="font-weight:600;color:var(--cs-text);">16:9 Intro Ready</div>
                        <div style="font-size:0.78rem;color:var(--cs-text-muted);">For regular landscape videos</div>
                    </div>
                </div>
            </div>''', unsafe_allow_html=True)
    with col2:
        if os.path.exists(INTRO_VIDEO_SHORT):
            st.markdown('''
            <div class="stat-card" style="padding:0.8rem 1rem;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:1.6rem;">📱</span>
                    <div>
                        <div style="font-weight:600;color:var(--cs-text);">9:16 Intro Ready</div>
                        <div style="font-size:0.78rem;color:var(--cs-text-muted);">For YouTube Shorts</div>
                    </div>
                </div>
            </div>''', unsafe_allow_html=True)
        else:
            st.warning(f"⚠ No 9:16 intro – run `create_vertical_intro.py`")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Upload your video",
        type=['mp4', 'mov', 'avi', 'mkv'],
        help="Supported formats: MP4, MOV, AVI, MKV"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        output_name = st.text_input(
            "Output filename (optional)",
            placeholder="Leave blank for auto-generated name"
        )
    with col2:
        fade_duration = st.slider("Fade duration (seconds)", 0.0, 2.0, 0.5, 0.1)
    
    if uploaded_file is not None:
        st.video(uploaded_file)
        
        if st.button("🚀 Process Video", type="primary", width="stretch"):
            # Animated pipeline
            pipeline_ph = st.empty()
            def _render_pipe(active):
                steps = ['Input','Detect','Stitch','Fade','Output']
                icons = ['📥','🔍','🎬','✨','✅']
                h = '<div class="pipeline">'
                for i,(s,ic) in enumerate(zip(steps,icons)):
                    c = 'done' if i<active else ('active' if i==active else '')
                    h += f'<div class="pipe-step {c}"><div class="pipe-icon">{ic}</div><div class="pipe-label">{s}</div></div>'
                    if i<len(steps)-1: h += '<div class="pipe-arrow">→</div>'
                h += '</div>'
                pipeline_ph.markdown(h, unsafe_allow_html=True)
            
            _render_pipe(0)
            with st.spinner("Processing video..."):
                # Save uploaded file temporarily
                temp_dir = tempfile.mkdtemp()
                temp_path = Path(temp_dir) / uploaded_file.name
                
                with open(temp_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                _render_pipe(1)
                # Detect video orientation and select appropriate intro
                video_is_vertical = is_vertical_video(str(temp_path))
                if video_is_vertical and os.path.exists(INTRO_VIDEO_SHORT):
                    intro_to_use = INTRO_VIDEO_SHORT
                    st.info("📱 Using 9:16 (Shorts) intro for vertical video")
                else:
                    intro_to_use = INTRO_VIDEO
                    if video_is_vertical:
                        st.warning("📱 Vertical video detected but no 9:16 intro available")
                    else:
                        st.info("📺 Using 16:9 intro for horizontal video")
                
                # Determine output path
                if output_name:
                    output_filename = output_name if output_name.endswith('.mp4') else f"{output_name}.mp4"
                else:
                    output_filename = f"{Path(uploaded_file.name).stem}_with_intro.mp4"
                
                output_path = OUTPUT_DIR / output_filename
                
                try:
                    _render_pipe(2)
                    # Process video
                    progress_bar = st.progress(0, text="Stitching intro...")
                    stitch_intro(str(intro_to_use), str(temp_path), str(output_path), fade_duration)
                    _render_pipe(3)
                    progress_bar.progress(80, text="Applying fade...")
                    time.sleep(0.3)
                    _render_pipe(4)
                    progress_bar.progress(100, text="Complete!")
                    
                    st.success(f"✓ Video processed successfully!")
                    st.info(f"📁 Output: {output_path}")
                    
                    # Log to history
                    add_history_event('process', uploaded_file.name, {
                        'output': str(output_path),
                        'is_short': video_is_vertical,
                        'fade': fade_duration,
                    })
                    
                    # Offer download
                    with open(output_path, 'rb') as f:
                        st.download_button(
                            "⬇️ Download Processed Video",
                            f,
                            file_name=output_filename,
                            mime="video/mp4",
                            width="stretch"
                        )
                    
                except Exception as e:
                    st.error(f"❌ Processing failed: {e}")
                finally:
                    # Cleanup temp file
                    if temp_path.exists():
                        temp_path.unlink()


def upload_video_page():
    """Render the upload video page."""
    st.markdown('<span class="section-title">⬆️ Process & Upload</span>', unsafe_allow_html=True)
    st.markdown("")
    st.markdown('''
    <div class="tip-box">
        <strong>🚀 One-click workflow:</strong> Upload a video, add your branded intro, and publish directly to YouTube – all in one step.
    </div>''', unsafe_allow_html=True)
    st.markdown("")
    
    # Check requirements
    if not os.path.exists(INTRO_VIDEO):
        st.error(f"❌ Intro video not found at '{INTRO_VIDEO}'")
        return
    
    if not os.path.exists(CLIENT_SECRETS_FILE):
        st.error(f"❌ Client secrets not found. Please add '{CLIENT_SECRETS_FILE}'")
        return
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Upload your video",
        type=['mp4', 'mov', 'avi', 'mkv'],
        key="upload_video"
    )
    
    # Video metadata
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("Video Title", placeholder="Enter video title")
        privacy = st.selectbox("Privacy", ["private", "unlisted", "public"], index=0)
    with col2:
        description = st.text_area("Description", placeholder="Enter video description", height=100)
    
    if uploaded_file is not None:
        st.video(uploaded_file)
        
        if st.button("🚀 Process & Upload", type="primary", width="stretch", disabled=not title):
            if not title:
                st.warning("Please enter a video title")
                return
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # Save uploaded file
                status_text.text("Saving video...")
                progress_bar.progress(10)
                
                temp_dir = tempfile.mkdtemp()
                temp_path = Path(temp_dir) / uploaded_file.name
                with open(temp_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                # Process video
                status_text.text("Adding intro...")
                progress_bar.progress(30)
                
                output_filename = f"{Path(uploaded_file.name).stem}_with_intro.mp4"
                output_path = OUTPUT_DIR / output_filename
                stitch_intro(str(INTRO_VIDEO), str(temp_path), str(output_path))
                
                # Authenticate
                status_text.text("Authenticating with YouTube...")
                progress_bar.progress(50)
                youtube = get_youtube_service()
                
                if youtube is None:
                    st.error("Failed to authenticate with YouTube")
                    return
                
                # Upload
                status_text.text("Uploading to YouTube...")
                progress_bar.progress(70)
                
                response = upload_video(
                    youtube,
                    str(output_path),
                    title,
                    description or "",
                    privacy_status=privacy
                )
                
                video_id = response['id']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                # Set thumbnail
                if os.path.exists(INTRO_THUMBNAIL):
                    status_text.text("Setting thumbnail...")
                    progress_bar.progress(90)
                    try:
                        set_thumbnail(youtube, video_id, INTRO_THUMBNAIL)
                    except Exception as e:
                        st.warning(f"Could not set thumbnail: {e}")
                
                progress_bar.progress(100)
                status_text.text("Complete!")
                
                st.success("✓ Video uploaded successfully!")
                st.markdown(f"**Video URL:** [{video_url}]({video_url})")
                st.balloons()
                
                # Log to history
                add_history_event('upload', title, {
                    'video_id': video_id,
                    'new_url': video_url,
                    'privacy': privacy,
                })
                
            except Exception as e:
                st.error(f"❌ Upload failed: {e}")
            finally:
                if 'temp_path' in locals() and temp_path.exists():
                    temp_path.unlink()


def download_video(video_id, output_path):
    """Download a video from YouTube using yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-f', 'best[height<=1080]',
        '-o', str(output_path),
        '--no-playlist',
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def list_videos_page():
    """Render the list videos page with selection and processing."""
    st.markdown('<span class="section-title">📺 My YouTube Videos</span>', unsafe_allow_html=True)
    st.markdown("")
    
    if not os.path.exists(CLIENT_SECRETS_FILE):
        st.error(f"❌ Client secrets not found. Please add '{CLIENT_SECRETS_FILE}'")
        return
    
    # Initialize session state for videos
    if 'channel_videos' not in st.session_state:
        st.session_state.channel_videos = []
    if 'selected_videos' not in st.session_state:
        st.session_state.selected_videos = []
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 Fetch My Videos", type="primary", width="stretch"):
            with st.spinner("Authenticating and fetching videos..."):
                youtube = get_youtube_service()
                
                if youtube is None:
                    st.error("Failed to authenticate")
                    return
                
                videos = list_videos(youtube, max_results=50)
                
                if not videos:
                    st.markdown('''
                    <div class="empty-state">
                        <div class="es-icon">📺</div>
                        <div class="es-title">No videos found</div>
                        <div class="es-desc">Your YouTube channel doesn't have any videos yet, or the API credentials don't have access.</div>
                    </div>''', unsafe_allow_html=True)
                    return
                
                # Enrich videos with details (is_short, playlists)
                enriched_videos = []
                progress_text = st.empty()
                for i, video in enumerate(videos):
                    video_id = video['snippet']['resourceId']['videoId']
                    progress_text.text(f"Getting details for video {i+1}/{len(videos)}...")
                    
                    # Get video details to determine if it's a Short
                    try:
                        details = get_video_details(youtube, video_id)
                        if details:
                            video['is_short'] = details.get('is_short', False)
                            video['duration_seconds'] = details.get('duration_seconds', 0)
                        else:
                            video['is_short'] = False
                            video['duration_seconds'] = 0
                    except Exception:
                        video['is_short'] = False
                        video['duration_seconds'] = 0
                    
                    # Get playlists this video belongs to
                    try:
                        playlists = get_video_playlists(youtube, video_id)
                        video['playlists'] = playlists
                    except Exception:
                        video['playlists'] = []
                    
                    enriched_videos.append(video)
                
                progress_text.empty()
                st.session_state.channel_videos = enriched_videos
                st.session_state.selected_videos = []
                st.success(f"Found {len(enriched_videos)} videos")
    
    with col2:
        num_selected = len(st.session_state.selected_videos)
        st.metric("Selected", num_selected)
    
    # Check for intro
    intro_available = os.path.exists(INTRO_VIDEO)
    if not intro_available:
        st.warning("⚠️ Intro video not found. Processing will be disabled.")
    
    # Initialize pin state
    if 'pin_process_panel' not in st.session_state:
        st.session_state.pin_process_panel = True
    
    # Process panel at the top (always visible when pinned)
    if st.session_state.channel_videos:
        pin_col1, pin_col2 = st.columns([4, 1])
        with pin_col2:
            st.session_state.pin_process_panel = st.toggle("📌 Pin", value=st.session_state.pin_process_panel, help="Keep process panel visible while scrolling")
        
        # Sticky container when pinned
        if st.session_state.pin_process_panel:
            st.markdown('<div class="sticky-container">', unsafe_allow_html=True)
        
        # Process selected videos panel
        num_selected = len(st.session_state.selected_videos)
        
        st.subheader(f"🚀 Process Selected Videos ({num_selected} selected)")
        
        if num_selected > 0 and intro_available:
            col1, col2, col3 = st.columns([2, 2, 2])
            with col1:
                new_privacy = st.selectbox(
                    "Privacy",
                    ["private", "unlisted", "public"],
                    index=0,
                    key="privacy_select"
                )
            with col2:
                reupload = st.checkbox("Re-upload to YouTube", value=True, key="reupload_check")
            with col3:
                if st.button(f"🎬 Process {num_selected} Videos", type="primary", width="stretch", key="process_btn"):
                    process_selected_videos(st.session_state.selected_videos, new_privacy, reupload)
        elif num_selected == 0:
            st.info("👇 Select videos below to process them")
        else:
            st.warning("No intro video available")
        
        if st.session_state.pin_process_panel:
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
    
    # Display videos with checkboxes
    if st.session_state.channel_videos:
        
        # Select all / deselect all
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("Select All"):
                st.session_state.selected_videos = [
                    item['snippet']['resourceId']['videoId'] 
                    for item in st.session_state.channel_videos
                ]
                st.rerun()
        with col2:
            if st.button("Deselect All"):
                st.session_state.selected_videos = []
                st.rerun()
        
        st.divider()
        
        # Video list with checkboxes
        for item in st.session_state.channel_videos:
            title = item['snippet']['title']
            video_id = item['snippet']['resourceId']['videoId']
            thumbnail_url = item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', '')
            
            col1, col2, col3 = st.columns([0.5, 1.5, 4])
            
            with col1:
                is_selected = video_id in st.session_state.selected_videos
                if st.checkbox("", value=is_selected, key=f"select_{video_id}", label_visibility="collapsed"):
                    if video_id not in st.session_state.selected_videos:
                        st.session_state.selected_videos.append(video_id)
                else:
                    if video_id in st.session_state.selected_videos:
                        st.session_state.selected_videos.remove(video_id)
            
            with col2:
                if thumbnail_url:
                    st.image(thumbnail_url, width=120)
            
            with col3:
                # Show Short badge if applicable
                is_short = item.get('is_short', False)
                playlists = item.get('playlists', [])
                dur = item.get('duration_seconds', 0)
                
                if is_short:
                    st.markdown(f'**{title}** <span class="badge badge-short">Short</span>', unsafe_allow_html=True)
                else:
                    st.markdown(f'**{title}** <span class="badge badge-regular">Video</span>', unsafe_allow_html=True)
                
                # Duration and playlists row
                info_parts = []
                if dur > 0:
                    mins, secs = divmod(int(dur), 60)
                    info_parts.append(f"⏱ {mins}:{secs:02d}")
                if playlists:
                    playlist_names = ", ".join([p['title'] for p in playlists[:3]])
                    if len(playlists) > 3:
                        playlist_names += f" +{len(playlists)-3} more"
                    info_parts.append(f"📂 {playlist_names}")
                info_parts.append(f"[Watch ↗](https://www.youtube.com/watch?v={video_id})")
                
                st.caption(" | ".join(info_parts))
            
            st.divider()


def process_selected_videos(video_ids, privacy_status, reupload):
    """Process selected videos: download, add intro, optionally re-upload."""
    
    # Get video info from session state
    video_info = {}
    for item in st.session_state.channel_videos:
        vid = item['snippet']['resourceId']['videoId']
        if vid in video_ids:
            video_info[vid] = {
                'title': item['snippet']['title'],
                'description': item['snippet'].get('description', ''),
                'is_short': item.get('is_short', False),
                'playlists': item.get('playlists', [])
            }
    
    total = len(video_ids)
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    
    results = []
    youtube = None
    
    # Pre-authenticate if we're going to reupload
    if reupload:
        youtube = get_youtube_service()
        if not youtube:
            st.error("Failed to authenticate with YouTube")
            return
    
    for idx, video_id in enumerate(video_ids):
        info = video_info.get(video_id, {'title': video_id, 'description': '', 'is_short': False, 'playlists': []})
        title = info['title']
        description = info['description']
        is_short = info['is_short']
        original_playlists = info['playlists']
        
        status_text.text(f"Processing {idx + 1}/{total}: {title[:40]}...")
        progress_bar.progress((idx) / total)
        
        try:
            # Download
            download_path = DOWNLOAD_DIR / f"{video_id}.mp4"
            
            if not download_path.exists():
                status_text.text(f"Downloading: {title[:40]}...")
                if not download_video(video_id, download_path):
                    results.append({'id': video_id, 'title': title, 'status': 'download_failed'})
                    continue
            
            # Detect if downloaded video is vertical (for Shorts)
            video_is_vertical = is_vertical_video(str(download_path))
            
            # Select appropriate intro based on video orientation
            if video_is_vertical and os.path.exists(INTRO_VIDEO_SHORT):
                intro_to_use = INTRO_VIDEO_SHORT
                thumbnail_to_use = INTRO_THUMBNAIL_SHORT if os.path.exists(INTRO_THUMBNAIL_SHORT) else INTRO_THUMBNAIL
            else:
                intro_to_use = INTRO_VIDEO
                thumbnail_to_use = INTRO_THUMBNAIL
            
            # Add intro
            status_text.text(f"Adding intro: {title[:40]}...")
            output_path = OUTPUT_DIR / f"{video_id}_with_intro.mp4"
            stitch_intro(str(intro_to_use), str(download_path), str(output_path))
            
            result = {
                'id': video_id, 
                'title': title, 
                'status': 'processed', 
                'output': str(output_path),
                'is_short': is_short or video_is_vertical,
                'used_vertical_intro': video_is_vertical and os.path.exists(INTRO_VIDEO_SHORT)
            }
            
            # Re-upload if requested
            if reupload and youtube:
                status_text.text(f"Uploading: {title[:40]}...")
                
                # For Shorts, ensure #Shorts tag is in title if not already
                upload_title = title
                if (is_short or video_is_vertical) and '#shorts' not in title.lower():
                    upload_title = f"{title} #Shorts"
                
                response = upload_video(
                    youtube,
                    str(output_path),
                    upload_title,
                    description or f"Re-uploaded with intro. Original: https://youtu.be/{video_id}",
                    privacy_status=privacy_status
                )
                
                new_video_id = response['id']
                result['new_id'] = new_video_id
                result['new_url'] = f"https://www.youtube.com/watch?v={new_video_id}"
                result['status'] = 'uploaded'
                
                # Set thumbnail (use vertical thumbnail for Shorts if available)
                if os.path.exists(thumbnail_to_use):
                    try:
                        set_thumbnail(youtube, new_video_id, thumbnail_to_use)
                        result['thumbnail'] = True
                    except:
                        result['thumbnail'] = False
                
                # Add to same playlists as original
                if original_playlists:
                    status_text.text(f"Adding to playlists: {title[:40]}...")
                    added_playlists = []
                    for playlist in original_playlists:
                        try:
                            add_video_to_playlist(youtube, new_video_id, playlist['id'])
                            added_playlists.append(playlist['title'])
                        except Exception as e:
                            pass  # Silently skip if can't add to playlist
                    result['playlists_added'] = added_playlists
            
            results.append(result)
            
            # Log to history
            event_type = 'upload' if result.get('status') == 'uploaded' else 'process'
            add_history_event(event_type, title, {
                'is_short': result.get('is_short', False),
                'new_url': result.get('new_url'),
                'new_id': result.get('new_id'),
            })
            
        except Exception as e:
            results.append({'id': video_id, 'title': title, 'status': 'error', 'error': str(e)})
    
    progress_bar.progress(1.0)
    status_text.text("Complete!")
    
    # Display results
    with results_container:
        st.divider()
        st.subheader("📊 Results")
        
        successful = [r for r in results if r['status'] in ['processed', 'uploaded']]
        failed = [r for r in results if r['status'] not in ['processed', 'uploaded']]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("✓ Successful", len(successful))
        with col2:
            st.metric("✗ Failed", len(failed))
        
        if successful:
            st.success("Successfully processed:")
            for r in successful:
                short_badge = " 📱" if r.get('is_short') else ""
                playlists_info = ""
                if r.get('playlists_added'):
                    playlists_info = f" (Added to: {', '.join(r['playlists_added'])})"
                
                if 'new_url' in r:
                    st.markdown(f"- **{r['title'][:50]}**{short_badge} → [New Video]({r['new_url']}){playlists_info}")
                else:
                    st.markdown(f"- **{r['title'][:50]}**{short_badge} → Saved to {r.get('output', 'output/')}")
        
        if failed:
            st.error("Failed:")
            for r in failed:
                st.markdown(f"- **{r['title'][:50]}** - {r['status']}: {r.get('error', '')}")
    
    # Clear selection
    st.session_state.selected_videos = []


def storage_page():
    """Render the storage management page."""
    st.markdown('<span class="section-title">💾 Storage Management</span>', unsafe_allow_html=True)
    st.markdown("")
    
    # Storage overview
    output_size = get_folder_size(OUTPUT_DIR)
    download_size = get_folder_size(DOWNLOAD_DIR)
    total_size = output_size + download_size
    
    col1, col2, col3 = st.columns(3)
    with col1:
        out_size_str = format_size(output_size)
        st.markdown(f'''
        <div class="stat-card accent-gold">
            <div class="stat-icon">&#128193;</div>
            <div class="stat-value">{out_size_str}</div>
            <div class="stat-label">Output Folder</div>
        </div>''', unsafe_allow_html=True)
    with col2:
        dl_size_str = format_size(download_size)
        st.markdown(f'''
        <div class="stat-card accent-purple">
            <div class="stat-icon">&#128229;</div>
            <div class="stat-value">{dl_size_str}</div>
            <div class="stat-label">Downloads</div>
        </div>''', unsafe_allow_html=True)
    with col3:
        total_size_str = format_size(total_size)
        st.markdown(f'''
        <div class="stat-card accent-coral">
            <div class="stat-icon">&#128190;</div>
            <div class="stat-value">{total_size_str}</div>
            <div class="stat-label">Total Used</div>
        </div>''', unsafe_allow_html=True)
    
    st.markdown("")
    
    # Progress bar
    usage_percent = total_size / STORAGE_WARNING_THRESHOLD
    st.progress(min(usage_percent, 1.0), text=f"Storage: {usage_percent*100:.1f}% of {format_size(STORAGE_WARNING_THRESHOLD)} limit")
    
    if usage_percent >= 1.0:
        st.error("⚠️ Storage limit exceeded! Please clean up files.")
    elif usage_percent >= 0.8:
        st.warning("⚠️ Storage approaching limit. Consider cleaning up.")
    
    st.divider()
    
    # File lists
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📁 Output Folder")
        output_files = list(OUTPUT_DIR.glob('*'))
        if output_files:
            for f in output_files:
                if f.is_file():
                    size = f.stat().st_size
                    st.text(f"📄 {f.name} ({format_size(size)})")
        else:
            st.info("No files in output folder")
        
        if output_files and st.button("🗑️ Clear Output", type="secondary", key="clear_output"):
            count = sum(1 for f in output_files if f.is_file())
            for f in output_files:
                if f.is_file():
                    f.unlink()
            add_history_event('cleanup', f'Cleared {count} output files')
            st.success("Output folder cleared!")
            st.rerun()
    
    with col2:
        st.subheader("📁 Downloads Folder")
        download_files = list(DOWNLOAD_DIR.glob('*'))
        if download_files:
            for f in download_files:
                if f.is_file():
                    size = f.stat().st_size
                    st.text(f"📄 {f.name} ({format_size(size)})")
        else:
            st.info("No files in downloads folder")
        
        if download_files and st.button("🗑️ Clear Downloads", type="secondary", key="clear_downloads"):
            count = sum(1 for f in download_files if f.is_file())
            for f in download_files:
                if f.is_file():
                    f.unlink()
            add_history_event('cleanup', f'Cleared {count} download files')
            st.success("Downloads folder cleared!")
            st.rerun()
    
    st.divider()
    
    if (output_files or download_files) and st.button("🗑️ Clear All Storage", type="primary", width="stretch"):
        count = sum(1 for f in output_files + download_files if f.is_file())
        for f in output_files + download_files:
            if f.is_file():
                f.unlink()
        add_history_event('cleanup', f'Cleared all storage ({count} files)')
        st.success("All storage cleared!")
        st.rerun()


def settings_page():
    """Render the settings page with config upload and editing."""
    st.markdown('<span class="section-title">⚙️ Settings</span>', unsafe_allow_html=True)
    st.markdown("")
    
    # Initialize settings in session state if not present
    if 'app_settings' not in st.session_state:
        st.session_state.app_settings = {
            'intro_video': INTRO_VIDEO,
            'intro_video_short': INTRO_VIDEO_SHORT,
            'intro_thumbnail': INTRO_THUMBNAIL,
            'intro_thumbnail_short': INTRO_THUMBNAIL_SHORT,
            'output_dir': str(OUTPUT_DIR),
            'download_dir': str(DOWNLOAD_DIR),
            'client_secrets': CLIENT_SECRETS_FILE,
            'default_privacy': 'private',
            'auto_cleanup': False,
            'fade_duration': 0.5
        }
    
    # Tabs for different settings sections
    settings_tab1, settings_tab2, settings_tab3 = st.tabs(["📁 File Paths", "🎬 Processing", "📤 Import/Export"])
    
    with settings_tab1:
        st.subheader("File Paths")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**16:9 Intro (Regular Videos)**")
            new_intro = st.text_input(
                "Intro Video",
                value=st.session_state.app_settings['intro_video'],
                key="settings_intro_video"
            )
            if os.path.exists(new_intro):
                st.success("✓ File exists")
            else:
                st.error("✗ File not found")
            
            new_thumb = st.text_input(
                "Intro Thumbnail",
                value=st.session_state.app_settings['intro_thumbnail'],
                key="settings_intro_thumb"
            )
            if os.path.exists(new_thumb):
                st.success("✓ File exists")
            else:
                st.warning("✗ File not found (optional)")
        
        with col2:
            st.markdown("**9:16 Intro (Shorts)**")
            new_intro_short = st.text_input(
                "Shorts Intro Video",
                value=st.session_state.app_settings['intro_video_short'],
                key="settings_intro_video_short"
            )
            if os.path.exists(new_intro_short):
                st.success("✓ File exists")
            else:
                st.warning("✗ File not found (optional)")
            
            new_thumb_short = st.text_input(
                "Shorts Thumbnail",
                value=st.session_state.app_settings['intro_thumbnail_short'],
                key="settings_intro_thumb_short"
            )
            if os.path.exists(new_thumb_short):
                st.success("✓ File exists")
            else:
                st.warning("✗ File not found (optional)")
        
        st.divider()
        
        st.markdown("**Directories**")
        col1, col2 = st.columns(2)
        with col1:
            new_output = st.text_input(
                "Output Directory",
                value=st.session_state.app_settings['output_dir'],
                key="settings_output_dir"
            )
        with col2:
            new_download = st.text_input(
                "Downloads Directory",
                value=st.session_state.app_settings['download_dir'],
                key="settings_download_dir"
            )
        
        st.divider()
        
        st.markdown("**API Credentials**")
        new_secrets = st.text_input(
            "Client Secrets File",
            value=st.session_state.app_settings['client_secrets'],
            key="settings_client_secrets"
        )
        if os.path.exists(new_secrets):
            st.success("✓ File exists")
        else:
            st.error("✗ File not found - YouTube features won't work")
    
    with settings_tab2:
        st.subheader("Processing Options")
        
        col1, col2 = st.columns(2)
        with col1:
            default_privacy = st.selectbox(
                "Default Privacy",
                ["private", "unlisted", "public"],
                index=["private", "unlisted", "public"].index(st.session_state.app_settings['default_privacy']),
                key="settings_default_privacy"
            )
            
            fade_duration = st.slider(
                "Default Fade Duration (seconds)",
                0.0, 2.0,
                st.session_state.app_settings['fade_duration'],
                0.1,
                key="settings_fade_duration"
            )
        
        with col2:
            auto_cleanup = st.checkbox(
                "Auto-cleanup after upload",
                value=st.session_state.app_settings['auto_cleanup'],
                help="Automatically delete processed files after successful upload",
                key="settings_auto_cleanup"
            )
    
    with settings_tab3:
        st.subheader("Import/Export Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Export Current Settings**")
            
            # Prepare config for export
            export_config = {
                'intro_video': st.session_state.app_settings['intro_video'],
                'intro_video_short': st.session_state.app_settings['intro_video_short'],
                'intro_thumbnail': st.session_state.app_settings['intro_thumbnail'],
                'intro_thumbnail_short': st.session_state.app_settings['intro_thumbnail_short'],
                'output_dir': st.session_state.app_settings['output_dir'],
                'download_dir': st.session_state.app_settings['download_dir'],
                'client_secrets': st.session_state.app_settings['client_secrets'],
                'default_privacy': st.session_state.app_settings['default_privacy'],
                'auto_cleanup': st.session_state.app_settings['auto_cleanup'],
                'fade_duration': st.session_state.app_settings['fade_duration']
            }
            
            import json
            config_json = json.dumps(export_config, indent=2)
            
            st.download_button(
                "⬇️ Export Config (JSON)",
                config_json,
                file_name="clipstream_config.json",
                mime="application/json",
                width="stretch"
            )
            
            # Also show as .env format
            env_content = f"""# ClipStream Configuration
CLIENT_SECRETS_FILE={export_config['client_secrets']}
INTRO_VIDEO={export_config['intro_video']}
INTRO_VIDEO_SHORT={export_config['intro_video_short']}
INTRO_THUMBNAIL={export_config['intro_thumbnail']}
INTRO_THUMBNAIL_SHORT={export_config['intro_thumbnail_short']}
OUTPUT_DIR={export_config['output_dir']}
DOWNLOAD_DIR={export_config['download_dir']}
DEFAULT_PRIVACY={export_config['default_privacy']}
AUTO_CLEANUP={str(export_config['auto_cleanup']).lower()}
FADE_DURATION={export_config['fade_duration']}
"""
            
            st.download_button(
                "⬇️ Export as .env",
                env_content,
                file_name=".env",
                mime="text/plain",
                width="stretch"
            )
        
        with col2:
            st.markdown("**Import Settings**")
            
            uploaded_config = st.file_uploader(
                "Upload config file",
                type=['json', 'env'],
                help="Upload a JSON config or .env file"
            )
            
            if uploaded_config is not None:
                try:
                    content = uploaded_config.read().decode('utf-8')
                    
                    if uploaded_config.name.endswith('.json'):
                        # Parse JSON config
                        import json
                        imported = json.loads(content)
                        st.session_state.app_settings.update(imported)
                        st.success("✓ Config imported successfully!")
                        st.rerun()
                    else:
                        # Parse .env file
                        for line in content.split('\n'):
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                key = key.strip().lower()
                                value = value.strip()
                                
                                # Map env keys to settings keys
                                key_map = {
                                    'client_secrets_file': 'client_secrets',
                                    'intro_video': 'intro_video',
                                    'intro_video_short': 'intro_video_short',
                                    'intro_thumbnail': 'intro_thumbnail',
                                    'intro_thumbnail_short': 'intro_thumbnail_short',
                                    'output_dir': 'output_dir',
                                    'download_dir': 'download_dir',
                                    'default_privacy': 'default_privacy',
                                    'auto_cleanup': 'auto_cleanup',
                                    'fade_duration': 'fade_duration'
                                }
                                
                                if key in key_map:
                                    settings_key = key_map[key]
                                    # Convert types
                                    if settings_key == 'auto_cleanup':
                                        value = value.lower() == 'true'
                                    elif settings_key == 'fade_duration':
                                        value = float(value)
                                    st.session_state.app_settings[settings_key] = value
                        
                        st.success("✓ .env file imported successfully!")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Failed to import config: {e}")
    
    st.divider()
    
    # Save button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("💾 Save Settings", type="primary", width="stretch"):
            # Update session state with current values
            st.session_state.app_settings.update({
                'intro_video': st.session_state.get('settings_intro_video', INTRO_VIDEO),
                'intro_video_short': st.session_state.get('settings_intro_video_short', INTRO_VIDEO_SHORT),
                'intro_thumbnail': st.session_state.get('settings_intro_thumb', INTRO_THUMBNAIL),
                'intro_thumbnail_short': st.session_state.get('settings_intro_thumb_short', INTRO_THUMBNAIL_SHORT),
                'output_dir': st.session_state.get('settings_output_dir', str(OUTPUT_DIR)),
                'download_dir': st.session_state.get('settings_download_dir', str(DOWNLOAD_DIR)),
                'client_secrets': st.session_state.get('settings_client_secrets', CLIENT_SECRETS_FILE),
                'default_privacy': st.session_state.get('settings_default_privacy', 'private'),
                'auto_cleanup': st.session_state.get('settings_auto_cleanup', False),
                'fade_duration': st.session_state.get('settings_fade_duration', 0.5)
            })
            st.success("✓ Settings saved for this session!")
            st.info("💡 To make settings permanent, export and save as .env file in the project folder.")


# ─── Helper: Relative time ──────────────────────────────────────────────────
def _relative_time(iso_ts: str) -> str:
    """Return a human-friendly relative timestamp."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        diff = datetime.now() - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            m = secs // 60
            return f"{m}m ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h}h ago"
        d = secs // 86400
        return f"{d}d ago"
    except Exception:
        return ""


# ─── Dashboard Page ──────────────────────────────────────────────────────────
def dashboard_page():
    """Rich dashboard with stats, quick actions, and activity feed."""

    stats = get_history_stats()

    # ── Row 1: Stat Cards ────
    st.markdown("")
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "🎬", stats['total_processed'], "Videos Processed", "accent-gold"),
        (c2, "☁️", stats['total_uploaded'],  "Uploaded",          "accent-coral"),
        (c3, "📱", stats['total_shorts'],    "Shorts",            "accent-purple"),
        (c4, "📅", stats['today_processed'], "Today",             "accent-cyan"),
    ]
    for col, icon, value, label, accent in cards:
        with col:
            st.markdown(f'''
            <div class="stat-card {accent}" style="animation-delay:{cards.index((col,icon,value,label,accent))*0.08}s">
                <div class="stat-icon">{icon}</div>
                <div class="stat-value">{value}</div>
                <div class="stat-label">{label}</div>
            </div>''', unsafe_allow_html=True)

    st.markdown("")

    # ── Row 2: Quick Actions + Activity ────
    left, right = st.columns([3, 2])

    with left:
        st.markdown('<span class="section-title">⚡ Quick Actions</span>', unsafe_allow_html=True)
        st.markdown("")
        qa1, qa2, qa3 = st.columns(3)
        with qa1:
            st.markdown('''
            <div class="quick-action">
                <div class="qa-icon">📂</div>
                <div class="qa-title">Process File</div>
                <div class="qa-desc">Add intro to a local video</div>
            </div>''', unsafe_allow_html=True)
            if st.button("Go →", key="qa_process", width="stretch"):
                st.info("Switch to the **Process Video** tab above")
        with qa2:
            st.markdown('''
            <div class="quick-action">
                <div class="qa-icon">📺</div>
                <div class="qa-title">Batch from YT</div>
                <div class="qa-desc">Pull & process channel vids</div>
            </div>''', unsafe_allow_html=True)
            if st.button("Go →", key="qa_batch", width="stretch"):
                st.info("Switch to the **My Videos** tab above")
        with qa3:
            st.markdown('''
            <div class="quick-action">
                <div class="qa-icon">🚀</div>
                <div class="qa-title">Upload</div>
                <div class="qa-desc">Process & upload in one step</div>
            </div>''', unsafe_allow_html=True)
            if st.button("Go →", key="qa_upload", width="stretch"):
                st.info("Switch to the **Upload** tab above")

        st.markdown("")

        # ── System overview ────
        st.markdown('<span class="section-title">🖥️ System</span>', unsafe_allow_html=True)
        st.markdown("")
        s1, s2, s3, s4 = st.columns(4)

        output_size = get_folder_size(OUTPUT_DIR)
        download_size = get_folder_size(DOWNLOAD_DIR)
        total_size = output_size + download_size
        usage_pct = min(total_size / STORAGE_WARNING_THRESHOLD * 100, 100)

        intro_ok = os.path.exists(INTRO_VIDEO)
        short_ok = os.path.exists(INTRO_VIDEO_SHORT)
        api_ok = os.path.exists(CLIENT_SECRETS_FILE)

        with s1:
            colour = "#4CAF50" if usage_pct < 80 else "#FFB74D" if usage_pct < 100 else "#FF6B6B"
            st.markdown(f'''
            <div class="stat-card" style="padding:1rem 0.8rem;">
                <div style="font-size:0.78rem;color:var(--cs-text-muted);text-transform:uppercase;letter-spacing:0.5px;">Storage</div>
                <div style="font-size:1.4rem;font-weight:700;color:{colour};">{usage_pct:.0f}%</div>
                <div style="font-size:0.75rem;color:var(--cs-text-muted);">{format_size(total_size)}</div>
            </div>''', unsafe_allow_html=True)
        with s2:
            badge = "✓" if intro_ok else "✗"
            clr = "#4CAF50" if intro_ok else "#FF6B6B"
            st.markdown(f'''
            <div class="stat-card" style="padding:1rem 0.8rem;">
                <div style="font-size:0.78rem;color:var(--cs-text-muted);text-transform:uppercase;letter-spacing:0.5px;">16:9 Intro</div>
                <div style="font-size:1.4rem;font-weight:700;color:{clr};">{badge}</div>
                <div style="font-size:0.75rem;color:var(--cs-text-muted);">{"Ready" if intro_ok else "Missing"}</div>
            </div>''', unsafe_allow_html=True)
        with s3:
            badge = "✓" if short_ok else "—"
            clr = "#4CAF50" if short_ok else "#9E9E9E"
            st.markdown(f'''
            <div class="stat-card" style="padding:1rem 0.8rem;">
                <div style="font-size:0.78rem;color:var(--cs-text-muted);text-transform:uppercase;letter-spacing:0.5px;">9:16 Intro</div>
                <div style="font-size:1.4rem;font-weight:700;color:{clr};">{badge}</div>
                <div style="font-size:0.75rem;color:var(--cs-text-muted);">{"Ready" if short_ok else "Optional"}</div>
            </div>''', unsafe_allow_html=True)
        with s4:
            badge = "✓" if api_ok else "✗"
            clr = "#4CAF50" if api_ok else "#FF6B6B"
            st.markdown(f'''
            <div class="stat-card" style="padding:1rem 0.8rem;">
                <div style="font-size:0.78rem;color:var(--cs-text-muted);text-transform:uppercase;letter-spacing:0.5px;">YT API</div>
                <div style="font-size:1.4rem;font-weight:700;color:{clr};">{badge}</div>
                <div style="font-size:0.75rem;color:var(--cs-text-muted);">{"Connected" if api_ok else "Setup needed"}</div>
            </div>''', unsafe_allow_html=True)

        # ── Visual Pipeline ────
        st.markdown("")
        st.markdown('<span class="section-title">🔄 Processing Pipeline</span>', unsafe_allow_html=True)
        st.markdown('''
        <div class="pipeline">
            <div class="pipe-step"><div class="pipe-icon">📥</div><div class="pipe-label">Input</div></div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-step"><div class="pipe-icon">🔍</div><div class="pipe-label">Detect</div></div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-step"><div class="pipe-icon">🎬</div><div class="pipe-label">Stitch</div></div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-step"><div class="pipe-icon">✨</div><div class="pipe-label">Fade</div></div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-step"><div class="pipe-icon">🖼️</div><div class="pipe-label">Thumb</div></div>
            <div class="pipe-arrow">→</div>
            <div class="pipe-step"><div class="pipe-icon">☁️</div><div class="pipe-label">Upload</div></div>
        </div>''', unsafe_allow_html=True)

        st.markdown('''
        <div class="tip-box">
            <strong>💡 Tip:</strong> ClipStream auto-detects whether your video is 16:9 or 9:16 and selects the matching intro, thumbnail, and upload format automatically.
        </div>''', unsafe_allow_html=True)

    with right:
        st.markdown('<span class="section-title">📋 Recent Activity</span>', unsafe_allow_html=True)
        st.markdown("")

        recent = stats['recent']
        if recent:
            for ev in recent:
                ev_type = ev.get('type', 'process')
                title_text = ev.get('title', '')[:55]
                ts_text = _relative_time(ev['timestamp'])
                details = ev.get('details', {})
                extra = ""
                if details.get('is_short'):
                    extra = ' <span class="badge badge-short">Short</span>'
                if details.get('new_url'):
                    extra += f' <a href="{details["new_url"]}" target="_blank" style="color:var(--cs-accent-cyan);font-size:0.8rem;">↗ view</a>'

                st.markdown(f'''
                <div class="activity-item">
                    <div class="activity-dot type-{ev_type}"></div>
                    <div class="activity-text">
                        <div class="at-title">{title_text}{extra}</div>
                        <div class="at-time">{ts_text}</div>
                    </div>
                </div>''', unsafe_allow_html=True)
        else:
            st.markdown('''
            <div class="empty-state">
                <div class="es-icon">🎥</div>
                <div class="es-title">No activity yet</div>
                <div class="es-desc">Process your first video to see your activity feed here.</div>
            </div>''', unsafe_allow_html=True)

        st.markdown("")

        # ── Week summary ────
        if stats['week_processed'] > 0:
            st.markdown(f'''
            <div class="tip-box">
                <strong>📊 This week:</strong> {stats['week_processed']} video{"s" if stats["week_processed"]!=1 else ""} processed
            </div>''', unsafe_allow_html=True)


def main():
    """Main application entry point."""
    render_header()
    render_sidebar()
    
    # Navigation
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🏠 Dashboard",
        "🎬 Process",
        "⬆️ Upload",
        "📺 My Videos",
        "💾 Storage",
        "⚙️ Settings"
    ])
    
    with tab1:
        dashboard_page()
    
    with tab2:
        process_video_page()
    
    with tab3:
        upload_video_page()
    
    with tab4:
        list_videos_page()
    
    with tab5:
        storage_page()
    
    with tab6:
        settings_page()


if __name__ == "__main__":
    main()
