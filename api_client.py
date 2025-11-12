"""
api_client.py
Handles all API communication with OpenRouter/Gemini.
If API behavior changes, update ONLY this file.
"""

import re
import json
import time
import base64
import requests
from typing import Optional
from config import API_BASE, SERVICE_SCHEMA, GENERIC_SCHEMAS


class APIClient:
    """Manages all API calls and response parsing"""
    
    def __init__(self, token: str, log_callback=None):
        self.token = token
        self.log = log_callback or print
        self.call_count = 0
        self.error_count = 0
    
    def _clean_json_response(self, content: str) -> str:
        """
        Remove markdown code blocks from JSON responses.
        UPDATE THIS METHOD if API changes response format.
        """
        if not content:
            return content
        
        content = content.strip()
        
        # Remove markdown code block wrappers (avoiding problematic backtick strings)
        content = re.sub(r"^```")
        content = re.sub(r"^```\s*\n?", "", content)
        content = re.sub(r"\n?```
        
        return content.strip()
    
    def _apify_headers(self) -> dict:
        """Generate headers for API requests"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Advanced Cellular Template Processor",
        }
    
    def _post_chat_completion(self, payload: dict, timeout: int = 60):
        """Core API call method"""
        headers = self._apify_headers()
        return requests.post(
            url=f"{API_BASE}/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout
        )
    
    def process_service_images(self, image1_path: str, image2_path: str, 
                               model_name: str, sector: str) -> Optional[dict]:
        """Analyze service mode screenshots"""
        self.call_count += 1
        self.log(f"[API] Call #{self.call_count} - Processing service images for '{sector}'")
        
        try:
            with open(image1_path, "rb") as f:
                b1 = base64.b64encode(f.read()).decode("utf-8")
            with open(image2_path, "rb") as f:
                b2 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Could not read/encode service images: {e}")
            return None
        
        prompt = (
            "You are a hyper-specialized AI for cellular network engineering data analysis. "
            "Analyze both provided service-mode screenshots carefully and return exactly one JSON object "
            "matching the schema. Use null where value is not found.\n\n"
            f"SCHEMA:\n{json.dumps(SERVICE_SCHEMA, indent=2)}"
        )
        
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b1}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b2}"}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }
        
        try:
            resp = self._post_chat_completion(payload, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"]["message"]["content"]
            content = self._clean_json_response(content)
            result = json.loads(content)
            self.log(f"[API] Success - Service data for '{sector}'")
            return result
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            self.log(f"[API ERROR] Network error: {e}")
            return None
        except (KeyError, IndexError) as e:
            self.error_count += 1
            self.log(f"[API ERROR] API response format changed! Missing key: {e}")
            if "resp" in locals():
                self.log(f"[API ERROR] Raw response: {getattr(resp, 'text', '')[:500]}")
            return None
        except json.JSONDecodeError as e:
            self.error_count += 1
            self.log(f"[API ERROR] JSON parsing failed - API format may have changed!")
            self.log(f"[API ERROR] Content: {content[:200] if 'content' in locals() else 'N/A'}")
            return None
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Unexpected error: {type(e).__name__} - {e}")
            return None
        finally:
            time.sleep(2)
    
    def analyze_generic_image(self, image_path: str, model_name: str, 
                             image_name: str) -> Optional[dict]:
        """Analyze speed test, video test, or voice call screenshot"""
        self.call_count += 1
        self.log(f"[API] Call #{self.call_count} - Analyzing '{image_name}'")
        
        try:
            with open(image_path, "rb") as f:
                b = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Could not read image '{image_name}': {e}")
            return None
        
        prompt = (
            "You are an expert AI assistant for analyzing cellular network test data. "
            "Classify the image as 'speed_test', 'video_test', or 'voice_call' and return a single JSON object "
            "matching the corresponding schema. Use null for missing fields.\n\n"
            f"SCHEMAS:\n{json.dumps(GENERIC_SCHEMAS, indent=2)}"
        )
        
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }
        
        try:
            resp = self._post_chat_completion(payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"]["message"]["content"]
            content = self._clean_json_response(content)
            result = json.loads(content)
            self.log(f"[API] Success - '{image_name}' classified as '{result.get('image_type', 'unknown')}'")
            return result
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            self.log(f"[API ERROR] Network error: {e}")
            return None
        except (KeyError, IndexError) as e:
            self.error_count += 1
            self.log(f"[API ERROR] API response format changed! Missing key: {e}")
            if "resp" in locals():
                self.log(f"[API ERROR] Raw response: {getattr(resp, 'text', '')[:500]}")
            return None
        except json.JSONDecodeError as e:
            self.error_count += 1
            self.log(f"[API ERROR] JSON parsing failed - API format may have changed!")
            self.log(f"[API ERROR] Content: {content[:200] if 'content' in locals() else 'N/A'}")
            return None
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Unexpected error: {type(e).__name__} - {e}")
            return None
        finally:
            time.sleep(2)
    
    def analyze_voice_image(self, image_path: str, model_name: str, 
                           image_name: str) -> Optional[dict]:
        """Analyze voice call screenshot"""
        self.call_count += 1
        self.log(f"[API] Call #{self.call_count} - Voice analysis for '{image_name}'")
        
        try:
            with open(image_path, "rb") as f:
                b = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Could not read voice image: {e}")
            return None
        
        prompt = (
            "You are an expert in telecom voice-call screenshot extraction. Extract ONLY the fields in the voice_call schema "
            "and emphasize 'time' (return exactly as seen). Return one JSON object.\n\n"
            f"SCHEMA:\n{json.dumps(GENERIC_SCHEMAS['voice_call'], indent=2)}"
        )
        
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }
        
        try:
            resp = self._post_chat_completion(payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"]["message"]["content"]
            content = self._clean_json_response(content)
            res = json.loads(content)
            self.log(f"[API] Success - Voice image '{image_name}' processed")
            return res
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            self.log(f"[API ERROR] Network error: {e}")
            return None
        except (KeyError, IndexError) as e:
            self.error_count += 1
            self.log(f"[API ERROR] API response format changed! Missing key: {e}")
            if "resp" in locals():
                self.log(f"[API ERROR] Raw response: {getattr(resp, 'text', '')[:500]}")
            return None
        except json.JSONDecodeError as e:
            self.error_count += 1
            self.log(f"[API ERROR] JSON parsing failed - API format may have changed!")
            self.log(f"[API ERROR] Content: {content[:200] if 'content' in locals() else 'N/A'}")
            return None
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Unexpected error: {type(e).__name__} - {e}")
            return None
        finally:
            time.sleep(2)
    
    def evaluate_service_images(self, image1_path: str, image2_path: str, 
                               model_name: str, sector: str) -> Optional[dict]:
        """Careful re-evaluation of service images"""
        self.log(f"[API] EVAL - Re-evaluating service for '{sector}' (careful mode)")
        return self.process_service_images(image1_path, image2_path, model_name, sector)
    
    def evaluate_generic_image(self, image_path: str, model_name: str, 
                              image_name: str) -> Optional[dict]:
        """Careful re-evaluation of generic image"""
        self.log(f"[API] EVAL - Re-evaluating '{image_name}' (careful mode)")
        return self.analyze_generic_image(image_path, model_name, image_name)
    
    def evaluate_voice_image(self, image_path: str, model_name: str, 
                            image_name: str) -> Optional[dict]:
        """Careful re-evaluation of voice image"""
        self.log(f"[API] EVAL - Re-evaluating voice '{image_name}' (careful mode)")
        return self.analyze_voice_image(image_path, model_name, image_name)
    
    def ask_model_for_expression_value(self, var_name: str, var_obj, 
                                      expression: str, model_name: str):
        """Ask model to evaluate expression using provided JSON variable"""
        self.call_count += 1
        
        try:
            var_json = json.dumps(var_obj, indent=2)
        except Exception:
            var_json = json.dumps(str(var_obj))
        
        prompt = (
            f"You are an exact assistant. You are given a JSON variable named '{var_name}':\n\n"
            f"{var_json}\n\nGiven the expression:\n{expression}\n\n"
            "Using ONLY the provided JSON variable, return exactly one JSON object:\n{ \"value\": <result> }\n"
            "Where <result> is the exact value or null. Return ONLY the JSON object and nothing else."
        )
        
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "response_format": {"type": "json_object"},
        }
        
        try:
            resp = self._post_chat_completion(payload, timeout=30)
            resp.raise_for_status()
            content = resp.json()["choices"]["message"]["content"]
            content = self._clean_json_response(content)
            parsed = json.loads(content)
            return parsed.get("value", None)
        except Exception as e:
            self.error_count += 1
            self.log(f"[API ERROR] Expression evaluation failed: {e}")
            return None
    
    def get_stats(self) -> dict:
        """Get API usage statistics"""
        success_rate = 0 if self.call_count == 0 else \
                      ((self.call_count - self.error_count) / self.call_count) * 100
        return {
            "total_calls": self.call_count,
            "errors": self.error_count,
            "success_rate": f"{success_rate:.1f}%"
        }
