"""
config.py
Configuration and schemas for the cellular template processor.
"""

# API Configuration
API_BASE = "https://openrouter.apify.actor/api/v1"
MODEL_SERVICE_DEFAULT = "google/gemini-2.5-pro"
MODEL_GENERIC_DEFAULT = "google/gemini-2.5-flash"

# Service Mode Schema
SERVICE_SCHEMA = {
    "nr_arfcn": "number",
    "nr_band": "number",
    "nr_pci": "number",
    "nr_bw": "number",
    "nr5g_rsrp": "number",
    "nr5g_rsrq": "number",
    "nr5g_sinr": "number",
    "lte_band": "number",
    "lte_earfcn": "number",
    "lte_pci": "number",
    "lte_bw": "number",
    "lte_rsrp": "number",
    "lte_rsrq": "number",
    "lte_sinr": "number",
}

# Generic Test Schemas
GENERIC_SCHEMAS = {
    "speed_test": {
        "image_type": "speed_test",
        "data": {
            "download_mbps": "number",
            "upload_mbps": "number",
            "ping_ms": "number",
            "jitter_ms": "number",
        },
    },
    "video_test": {
        "image_type": "video_test",
        "data": {
            "max_resolution": "string",
            "load_time_ms": "number",
            "buffering_percentage": "number",
        },
    },
    "voice_call": {
        "image_type": "voice_call",
        "data": {
            "phone_number": "string",
            "call_duration_seconds": "number",
            "call_status": "string",
            "time": "string",
        },
    },
}
