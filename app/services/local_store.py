# app/services/local_store.py
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

FAILED_SAVES_FILE = "failed_saves.json"
ANALYTICS_FILE = "analytics.json"

logger = logging.getLogger(__name__)

# --- FAILED SAVES (Plan Item 2) ---

def save_failed_entry(data: Dict[str, Any], error: str):
    """Save a failed row to a local JSON file for manual review."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "error": str(error),
        "data": data
    }
    
    entries = []
    if os.path.exists(FAILED_SAVES_FILE):
        try:
            with open(FAILED_SAVES_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except json.JSONDecodeError:
            entries = []
            
    entries.append(entry)
    
    with open(FAILED_SAVES_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved failed entry locally. Total failed: {len(entries)}")

# --- ANALYTICS (Plan Item 3) ---

def track_event(event_type: str, details: str = None):
    """
    Track events like 'validation_error', 'save_success', 'save_failure'.
    Structure: { "validation_error": { "count": 10, "details": ["error 1", "error 2"] } }
    """
    stats = {}
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
        except json.JSONDecodeError:
            stats = {}
            
    if event_type not in stats:
        stats[event_type] = {"count": 0, "last_occurrence": None}
        
    stats[event_type]["count"] += 1
    stats[event_type]["last_occurrence"] = datetime.now().isoformat()
    
    # Optional: Log specific validation error details (kept limited to avoid file bloat)
    if details:
        if "examples" not in stats[event_type]:
            stats[event_type]["examples"] = []
        # Keep last 10 examples
        stats[event_type]["examples"] = ([details] + stats[event_type].get("examples", []))[:10]

    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)