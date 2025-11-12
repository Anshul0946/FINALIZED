"""
data_processor.py
Core business logic: data validation, processing pipeline, expression resolution.
"""

import re
from pathlib import Path
from typing import Optional, List
from config import SERVICE_SCHEMA, GENERIC_SCHEMAS


# Global data stores (reinitialized per run)
alpha_service = {}
beta_service = {}
gamma_service = {}
alpha_speedtest = {}
beta_speedtest = {}
gamma_speedtest = {}
alpha_video = {}
beta_video = {}
gamma_video = {}
voice_test = {}
extract_text = []
avearge = {}

# FIXED: Proper regex pattern with escaped brackets
key_pattern = re.compile(r"$$['\"]([^'\"]+)['\"]$$")


def _normalize_name(s: str) -> str:
    """Normalize variable names for case-insensitive matching"""
    return re.sub(r"[^0-9a-zA-Z]", "", s).lower()


def resolve_expression_with_vars(expr: str, allowed_vars: dict):
    """Resolve expression like 'alpha_service["nr_band"]' using allowed variables"""
    expr = expr.strip()
    m = re.match(r"^([A-Za-z_]\w*)(.*)$", expr)
    if not m:
        return None
    
    base_raw = m.group(1)
    rest = m.group(2) or ""
    
    norm_map = {_normalize_name(k): k for k in allowed_vars.keys()}
    base_key = norm_map.get(_normalize_name(base_raw))
    
    if not base_key:
        for k in allowed_vars.keys():
            if k.lower() == base_raw.lower():
                base_key = k
                break
    
    if not base_key:
        return None
    
    obj = allowed_vars[base_key]
    if rest.strip() == "":
        return obj
    
    keys = key_pattern.findall(rest)
    if not keys:
        return None
    
    try:
        for k in keys:
            if not isinstance(obj, dict):
                return None
            if k in obj:
                obj = obj[k]
                continue
            
            found = None
            for real_k in obj.keys():
                if real_k.lower() == k.lower() or _normalize_name(real_k) == _normalize_name(k):
                    found = real_k
                    break
            
            if found:
                obj = obj[found]
            else:
                return None
        return obj
    except Exception:
        return None


def set_nested_value_case_insensitive(target: dict, keys: list, value):
    """Set nested dictionary value with case-insensitive key matching"""
    cur = target
    for idx, k in enumerate(keys):
        last = idx == (len(keys) - 1)
        
        if last:
            if isinstance(cur, dict):
                found = None
                for real_k in list(cur.keys()):
                    if real_k.lower() == k.lower() or _normalize_name(real_k) == _normalize_name(k):
                        found = real_k
                        break
                
                if found:
                    cur[found] = value
                else:
                    cur[k] = value
                return True
        else:
            found = None
            if isinstance(cur, dict):
                for real_k in list(cur.keys()):
                    if real_k.lower() == k.lower() or _normalize_name(real_k) == _normalize_name(k):
                        found = real_k
                        break
            
            if found:
                if not isinstance(cur[found], dict):
                    cur[found] = {}
                cur = cur[found]
            else:
                cur[k] = {}
                cur = cur[k]
    return True


def contains_nulls(d):
    """Check if dictionary contains any null values"""
    if not isinstance(d, dict):
        return False
    for v in d.values():
        if v is None:
            return True
        if isinstance(v, dict) and contains_nulls(v):
            return True
    return False


def missing_service_fields(svc_obj):
    """Check which service schema fields are missing or null"""
    missing = []
    for k in SERVICE_SCHEMA.keys():
        if k not in svc_obj or svc_obj.get(k) is None:
            missing.append(k)
    return missing


def compute_averages(alpha_speedtest, beta_speedtest, gamma_speedtest):
    """Compute average speed test metrics across all tests"""
    
    def _to_number(v):
        try:
            if v is None:
                return None
            if isinstance(v, bool):
                return None
            return float(v)
        except Exception:
            return None
    
    def _compute_speed_averages(speed_map):
        metrics = {"download_mbps": [], "upload_mbps": [], "ping_ms": []}
        for entry in speed_map.values():
            if not isinstance(entry, dict):
                continue
            for m in metrics.keys():
                val = _to_number(entry.get(m))
                if val is not None:
                    metrics[m].append(val)
        
        result = {}
        for m, vals in metrics.items():
            if vals:
                result[m] = sum(vals) / len(vals)
            else:
                result[m] = None
        return result
    
    return {
        "avearge_alpha_speedtest": _compute_speed_averages(alpha_speedtest),
        "avearge_beta_speedtest": _compute_speed_averages(beta_speedtest),
        "avearge_gamma_speedtest": _compute_speed_averages(gamma_speedtest),
    }


def group_images_by_sector(image_paths: List[str]) -> dict:
    """Group extracted images by sector (alpha/beta/gamma/voicetest)"""
    images_by_sector = {"alpha": [], "beta": [], "gamma": [], "voicetest": [], "unknown": []}
    for p in image_paths:
        sector = Path(p).stem.split("_")
        if sector in images_by_sector:
            images_by_sector[sector].append(p)
        else:
            images_by_sector["unknown"].append(p)
    return images_by_sector


def get_global_data_stores():
    """Return all global data stores as dictionary"""
    return {
        "alpha_service": alpha_service,
        "beta_service": beta_service,
        "gamma_service": gamma_service,
        "alpha_speedtest": alpha_speedtest,
        "beta_speedtest": beta_speedtest,
        "gamma_speedtest": gamma_speedtest,
        "alpha_video": alpha_video,
        "beta_video": beta_video,
        "gamma_video": gamma_video,
        "voice_test": voice_test,
        "extract_text": extract_text,
        "avearge": avearge,
    }


def reset_global_data_stores():
    """Reset all global data stores to empty"""
    global alpha_service, beta_service, gamma_service
    global alpha_speedtest, beta_speedtest, gamma_speedtest
    global alpha_video, beta_video, gamma_video
    global voice_test, extract_text, avearge
    
    alpha_service = {}
    beta_service = {}
    gamma_service = {}
    alpha_speedtest = {}
    beta_speedtest = {}
    gamma_speedtest = {}
    alpha_video = {}
    beta_video = {}
    gamma_video = {}
    voice_test = {}
    extract_text = []
    avearge = {}
