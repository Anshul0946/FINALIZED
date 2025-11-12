"""
app.py
Streamlit UI and workflow orchestration.
Main entry point for the application.
"""

import os
import tempfile
import shutil
import time
from pathlib import Path
import streamlit as st

from config import MODEL_SERVICE_DEFAULT, MODEL_GENERIC_DEFAULT, SERVICE_SCHEMA, GENERIC_SCHEMAS
from api_client import APIClient
from excel_handler import extract_images_from_excel, scan_bold_red_expressions, map_values_to_template
from data_processor import (
    group_images_by_sector, resolve_expression_with_vars, set_nested_value_case_insensitive,
    contains_nulls, missing_service_fields, compute_averages, key_pattern,
    reset_global_data_stores, get_global_data_stores
)


def log_append(log_placeholder, logs_list: list, msg: str):
    """Append timestamped log and update display"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    logs_list.append(line)
    display = "\n".join(logs_list[-2000:])
    try:
        log_placeholder.text_area("Logs", value=display, height=360)
    except Exception:
        print(line)


def process_file_streamlit(user_file_path: str,
                          token: str,
                          temp_dir: str,
                          logs: list,
                          text_area_placeholder,
                          model_service: str = MODEL_SERVICE_DEFAULT,
                          model_generic: str = MODEL_GENERIC_DEFAULT):
    """Main processing pipeline"""
    
    # Reset global data stores
    reset_global_data_stores()
    stores = get_global_data_stores()
    
    # Initialize API client with logging
    api = APIClient(token, log_callback=lambda msg: log_append(text_area_placeholder, logs, msg))
    
    os.makedirs(temp_dir, exist_ok=True)
    images_temp = os.path.join(temp_dir, "images")
    os.makedirs(images_temp, exist_ok=True)
    
    local_template = user_file_path
    if not os.path.exists(local_template):
        log_append(text_area_placeholder, logs, f"[ERROR] Template not found: {local_template}")
        return None
    
    if Path(local_template).suffix.lower() != ".xlsx":
        log_append(text_area_placeholder, logs, "[ERROR] Unsupported file type (only .xlsx supported).")
        return None
    
    # Extract images from Excel
    image_paths = extract_images_from_excel(
        local_template, 
        images_temp, 
        lambda msg: log_append(text_area_placeholder, logs, msg)
    )
    
    if not image_paths:
        log_append(text_area_placeholder, logs, "[ERROR] No images to process.")
        return None
    
    # Group images by sector
    images_by_sector = group_images_by_sector(image_paths)
    
    log_append(text_area_placeholder, logs, "[PROCESS] Starting main processing loop...")
    
    # Process service images for each sector
    for sector in ["alpha", "beta", "gamma"]:
        log_append(text_area_placeholder, logs, f"--- Processing sector: {sector.upper()} ---")
        sector_images = images_by_sector[sector]
        
        img1 = next((p for p in sector_images if Path(p).stem.endswith("_image_1")), None)
        img2 = next((p for p in sector_images if Path(p).stem.endswith("_image_2")), None)
        
        if img1 and img2:
            svc = api.process_service_images(img1, img2, model_service, sector)
            if svc:
                stores[f"{sector}_service"].update(svc)
        else:
            log_append(text_area_placeholder, logs, f"[WARN] Missing service images for {sector}")
        
        # Process other images (speed test, video test)
        other_images = [
            p for p in sector_images
            if not (Path(p).stem.endswith("_image_1") or Path(p).stem.endswith("_image_2"))
        ]
        
        for img in other_images:
            res = api.analyze_generic_image(img, model_generic, Path(img).name)
            if res and "image_type" in res:
                image_name = Path(img).stem
                if res["image_type"] == "speed_test":
                    stores[f"{sector}_speedtest"][image_name] = res.get("data", {})
                elif res["image_type"] == "video_test":
                    stores[f"{sector}_video"][image_name] = res.get("data", {})
                elif res["image_type"] == "voice_call":
                    stores["voice_test"][image_name] = res.get("data", {})
    
    # Process voicetest sector
    if images_by_sector["voicetest"]:
        log_append(text_area_placeholder, logs, "--- Processing sector: VOICETEST ---")
        for img in images_by_sector["voicetest"]:
            res = api.analyze_voice_image(img, model_generic, Path(img).name)
            if res and res.get("image_type") == "voice_call":
                stores["voice_test"][Path(img).stem] = res.get("data", {})
    
    # Evaluation pass
    log_append(text_area_placeholder, logs, "\n[PROCESS] Starting evaluation pass...")
    
    retried_service_sectors = set()
    retried_images = set()
    
    # Re-evaluate service dicts with missing/null fields
    for sector in ["alpha", "beta", "gamma"]:
        svc_var = stores[f"{sector}_service"]
        
        if not svc_var or contains_nulls(svc_var):
            img1 = next((p for p in images_by_sector[sector] if Path(p).stem.endswith("_image_1")), None)
            img2 = next((p for p in images_by_sector[sector] if Path(p).stem.endswith("_image_2")), None)
            
            if img1 and img2 and sector not in retried_service_sectors:
                log_append(text_area_placeholder, logs, f"[EVAL] Re-evaluating service for {sector}")
                eval_res = api.evaluate_service_images(img1, img2, model_service, sector)
                retried_service_sectors.add(sector)
                
                if eval_res:
                    for k, v in eval_res.items():
                        if svc_var.get(k) is None and v is not None:
                            svc_var[k] = v
    
    # Helper: retry single images
def _retry_image_and_merge(image_name: str, sector_var_map: dict) -> bool:
    image_path = os.path.join(images_temp, f"{image_name}.png")
    if not os.path.exists(image_path):
        found = None
        for s_list in images_by_sector.values():
            for p in s_list:
                if Path(p).stem == image_name:
                    found = p
                    break
            if found:
                break
        
        if found:
            image_path = found
        else:
            log_append(text_area_placeholder, logs, f"[EVAL WARN] Image {image_name} not found.")
            return False
    
    # Ensure image_path is string (fix for unhashable type error)
    image_path = str(image_path) if not isinstance(image_path, list) else str(image_path[0])
    
    if str(image_path) in retried_images:
        return False
    
    is_voice = image_name.startswith("voicetest")
    
    log_append(text_area_placeholder, logs, f"[EVAL] Retrying analysis for {image_name}")
    if is_voice:
        normal_res = api.analyze_voice_image(image_path, model_generic, image_name)
    else:
        normal_res = api.analyze_generic_image(image_path, model_generic, image_name)
    
    retried_images.add(image_path)
    
    if normal_res and "image_type" in normal_res:
        sector_var_map.setdefault(image_name, {})
        data = normal_res.get("data", {})
        for k, v in data.items():
            if sector_var_map[image_name].get(k) is None and v is not None:
                sector_var_map[image_name][k] = v
        return True
    
    # Try careful evaluation
    if is_voice:
        eval_res = api.evaluate_voice_image(image_path, model_generic, image_name)
    else:
        eval_res = api.evaluate_generic_image(image_path, model_generic, image_name)
    
    if eval_res and "image_type" in eval_res:
        sector_var_map.setdefault(image_name, {})
        for k, v in eval_res.get("data", {}).items():
            if sector_var_map[image_name].get(k) is None and v is not None:
                sector_var_map[image_name][k] = v
        return True
    
    return False

    # Rule 2: Verify expected images and completeness
    sector_maps = [
        ("alpha", stores["alpha_speedtest"], stores["alpha_video"]),
        ("beta", stores["beta_speedtest"], stores["beta_video"]),
        ("gamma", stores["gamma_speedtest"], stores["gamma_video"]),
    ]
    
    for sector, speed_map, video_map in sector_maps:
        log_append(text_area_placeholder, logs, f"[RULE2] Verifying {sector} completeness...")
        
        svc_var = stores[f"{sector}_service"]
        svc_missing = missing_service_fields(svc_var) if svc_var else list(SERVICE_SCHEMA.keys())
        
        if svc_missing and sector not in retried_service_sectors:
            img1 = next((p for p in images_by_sector[sector] if Path(p).stem.endswith("_image_1")), None)
            img2 = next((p for p in images_by_sector[sector] if Path(p).stem.endswith("_image_2")), None)
            
            if img1 and img2:
                log_append(text_area_placeholder, logs, f"[RULE2] Re-processing service for {sector}")
                normal_svc = api.process_service_images(img1, img2, model_service, sector)
                retried_service_sectors.add(sector)
                
                if normal_svc:
                    for k, v in normal_svc.items():
                        if svc_var.get(k) is None and v is not None:
                            svc_var[k] = v
                    
                    if missing_service_fields(svc_var):
                        eval_svc = api.evaluate_service_images(img1, img2, model_service, sector)
                        if eval_svc:
                            for k, v in eval_svc.items():
                                if svc_var.get(k) is None and v is not None:
                                    svc_var[k] = v
        
        # Check speed test images
        for img_path in images_by_sector[sector]:
            name = Path(img_path).stem
            if "image_" in name and not name.endswith("_1") and not name.endswith("_2"):
                if name not in speed_map and name not in video_map:
                    log_append(text_area_placeholder, logs, f"[RULE2] Processing missing image {name}")
                    _retry_image_and_merge(name, speed_map)
                else:
                    # Check for missing fields
                    if name in speed_map:
                        missing = []
                        for k in GENERIC_SCHEMAS["speed_test"]["data"].keys():
                            if k not in speed_map[name] or speed_map[name].get(k) is None:
                                missing.append(k)
                        if missing:
                            log_append(text_area_placeholder, logs, f"[RULE2] {name} missing {missing}")
                            _retry_image_and_merge(name, speed_map)
                    
                    if name in video_map:
                        missing = []
                        for k in GENERIC_SCHEMAS["video_test"]["data"].keys():
                            if k not in video_map[name] or video_map[name].get(k) is None:
                                missing.append(k)
                        if missing:
                            log_append(text_area_placeholder, logs, f"[RULE2] {name} missing {missing}")
                            _retry_image_and_merge(name, video_map)
    
    # Voicetest completeness check
    log_append(text_area_placeholder, logs, "[RULE2] Verifying voicetest completeness...")
    for img_path in images_by_sector["voicetest"]:
        name = Path(img_path).stem
        if name not in stores["voice_test"]:
            log_append(text_area_placeholder, logs, f"[RULE2] Processing missing voice {name}")
            _retry_image_and_merge(name, stores["voice_test"])
        else:
            missing = []
            for k in GENERIC_SCHEMAS["voice_call"]["data"].keys():
                if k not in stores["voice_test"][name] or stores["voice_test"][name].get(k) is None:
                    missing.append(k)
            if missing:
                log_append(text_area_placeholder, logs, f"[RULE2] {name} missing {missing}")
                _retry_image_and_merge(name, stores["voice_test"])
    
    log_append(text_area_placeholder, logs, "[PROCESS] Rule 2 verification complete.")
    
    # Compute averages
    stores["avearge"] = compute_averages(
        stores["alpha_speedtest"],
        stores["beta_speedtest"],
        stores["gamma_speedtest"]
    )
    
    # Scan template for bold+red expressions
    cells_to_process = scan_bold_red_expressions(
        local_template,
        lambda msg: log_append(text_area_placeholder, logs, msg)
    )
    
    # Extract expressions for reference
    for _, expr in cells_to_process:
        stores["extract_text"].append(expr)
    
    # Map values to template
    allowed_vars = {
        "alpha_service": stores["alpha_service"],
        "beta_service": stores["beta_service"],
        "gamma_service": stores["gamma_service"],
        "alpha_speedtest": stores["alpha_speedtest"],
        "beta_speedtest": stores["beta_speedtest"],
        "gamma_speedtest": stores["gamma_speedtest"],
        "alpha_video": stores["alpha_video"],
        "beta_video": stores["beta_video"],
        "gamma_video": stores["gamma_video"],
        "voice_test": stores["voice_test"],
        "avearge": stores["avearge"],
    }
    
    result_path = map_values_to_template(
        local_template,
        cells_to_process,
        allowed_vars,
        resolve_expression_with_vars,
        lambda msg: log_append(text_area_placeholder, logs, msg)
    )
    
    # Show API statistics
    stats = api.get_stats()
    log_append(text_area_placeholder, logs, f"\n[API STATS] {stats}")
    log_append(text_area_placeholder, logs, "[SUCCESS] Processing complete!")
    
    return result_path


def main():
    st.set_page_config(page_title="Advanced Cellular Template Processor", page_icon="📡", layout="wide")
    st.title("📡 Advanced Cellular Template Processor")
    
    st.markdown("""
    **Upload your Excel template** containing embedded images (service screenshots, speed tests, video tests, voice calls).
    The tool will extract data from images using AI vision and populate bold+red expressions in the template.
    """)
    
    if "api_token" not in st.session_state:
        st.session_state["api_token"] = ""
    
    api_token = st.text_input("Enter your Apify API Key:", type="password", value=st.session_state.get("api_token", ""))
    
    if api_token and api_token != st.session_state.get("api_token", ""):
        if api_token.startswith("apify_api_"):
            st.session_state["api_token"] = api_token
            st.success("[UI] API token stored (format validated).")
        else:
            st.error("[UI] Invalid API token format (must start with 'apify_api_').")
    
    uploaded_file = st.file_uploader("Upload Excel Template (.xlsx)", type=["xlsx"])
    
    if uploaded_file and st.session_state.get("api_token"):
        if st.button("Process Template"):
            st.session_state["logs"] = []
            st.session_state["logs"].append("[UI] Starting processing...")
            
            temp_dir = tempfile.mkdtemp(prefix="streamlit_")
            
            user_file_path = os.path.join(temp_dir, uploaded_file.name)
            with open(user_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            log_placeholder = st.empty()
            
            try:
                result_path = process_file_streamlit(
                    user_file_path=user_file_path,
                    token=st.session_state["api_token"],
                    temp_dir=temp_dir,
                    logs=st.session_state["logs"],
                    text_area_placeholder=log_placeholder,
                )
                
                if result_path and os.path.exists(result_path):
                    st.success("✅ Processing complete! Download your filled template below:")
                    
                    with open(result_path, "rb") as f:
                        st.download_button(
                            label="⬇️ Download Filled Template",
                            data=f.read(),
                            file_name=f"filled_{uploaded_file.name}",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("❌ Processing failed. Check logs above for details.")
            
            except Exception as e:
                st.error(f"❌ Fatal error: {type(e).__name__} - {str(e)}")
                log_append(log_placeholder, st.session_state["logs"], f"[FATAL ERROR] {e}")
            
            finally:
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
