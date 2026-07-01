import json
import re
import uuid
from typing import Dict, Any, List, Optional

# ==========================================
# 1. CANONICAL DATA STRUCTURE & NORMALIZERS
# ==========================================

class Normalizer:
    @staticmethod
    def phone(raw_phone: Any) -> List[str]:
        if not raw_phone:
            return []
        # Basic E.164 extraction (digits only, prefixed with + if originally present)
        digits = re.sub(r'\D', '', str(raw_phone))
        if not digits:
            return []
        return [f"+{digits}" if str(raw_phone).strip().startswith('+') else f"+1{digits}" if len(digits) == 10 else f"+{digits}"]

    @staticmethod
    def email(raw_email: Any) -> List[str]:
        if not raw_email:
            return []
        email_str = str(raw_email).strip().lower()
        return [email_str] if re.match(r"[^@]+@[^@]+\.[^@]+", email_str) else []

    @staticmethod
    def date_ym(raw_date: Any) -> Optional[str]:
        if not raw_date:
            return None
        # Handle formats like YYYY-MM-DD, YYYY/MM, or text months
        date_str = str(raw_date).strip()
        match = re.search(r'(\d{4})[-/](\d{2})', date_str)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        match_year = re.search(r'\b(\d{4})\b', date_str)
        if match_year:
            return f"{match_year.group(1)}-01"
        return None

# ==========================================
# 2. INGESTION & PIPELINE ENGINE
# ==========================================

class CandidateTransformerEngine:
    def __init__(self):
        # Higher score means higher confidence/priority
        self.source_weights = {
            "ats_json": 0.9,
            "recruiter_csv": 0.8,
            "linkedin_profile": 0.85,
            "recruiter_notes": 0.5
        }

    def create_empty_canonical(self) -> Dict[str, Any]:
        return {
            "candidate_id": str(uuid.uuid4()),
            "full_name": None,
            "emails": [],
            "phones": [],
            "location": {"city": None, "region": None, "country": None},
            "links": {},
            "headline": None,
            "years_experience": None,
            "skills": [],
            "experience": [],
            "education": [],
            "provenance": [],
            "overall_confidence": 0.0
        }

    def process_sources(self, raw_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        canonical = self.create_empty_canonical()
        confidence_accum = []

        for src in raw_sources:
            src_type = src.get("source_type")
            data = src.get("data", {})
            weight = self.source_weights.get(src_type, 0.5)
            confidence_accum.append(weight)

            # --- Full Name Extraction ---
            if "name" in data or "full_name" in data:
                name_val = data.get("full_name") or data.get("name")
                if not canonical["full_name"] or weight > 0.6:  
                    canonical["full_name"] = name_val
                    canonical["provenance"].append({
                        "field": "full_name", "source": src_type, "method": "direct_override"
                    })

            # --- Emails Ingestion ---
            raw_emails = data.get("emails") or ([data.get("email")] if "email" in data else [])
            for em in raw_emails:
                norm_emails = Normalizer.email(em)
                for ne in norm_emails:
                    if ne not in canonical["emails"]:
                        canonical["emails"].append(ne)
                        canonical["provenance"].append({
                            "field": "emails", "source": src_type, "method": "regex_extraction"
                        })

            # --- Phones Ingestion ---
            raw_phones = data.get("phones") or ([data.get("phone")] if "phone" in data else [])
            for ph in raw_phones:
                norm_ph = Normalizer.phone(ph)
                for np in norm_ph:
                    if np not in canonical["phones"]:
                        canonical["phones"].append(np)
                        canonical["provenance"].append({
                            "field": "phones", "source": src_type, "method": "e164_normalization"
                        })

            # --- Skills Parser ---
            if "skills" in data:
                skills_input = data.get("skills", [])
                # Handle list of strings or list of dicts
                for sk in skills_input:
                    skill_name = sk if isinstance(sk, str) else sk.get("name")
                    if skill_name:
                        # Simple case canonicalization
                        canonical_skill = skill_name.strip().upper()
                        # Check if skill exists
                        existing = next((s for s in canonical["skills"] if s["name"] == canonical_skill), None)
                        if not existing:
                            canonical["skills"].append({
                                "name": canonical_skill,
                                "confidence": weight,
                                "sources": [src_type]
                            })
                        else:
                            if src_type not in existing["sources"]:
                                existing["sources"].append(src_type)
                                existing["confidence"] = max(existing["confidence"], weight)

        if confidence_accum:
            canonical["overall_confidence"] = round(sum(confidence_accum) / len(confidence_accum), 2)
        
        return canonical

# ==========================================
# 3. RUNTIME CONFIG & PROJECTION LAYER
# ==========================================

class ProjectionLayer:
    @staticmethod
    def project(canonical: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        output = {}
        fields_config = config.get("fields", [])
        include_confidence = config.get("include_confidence", True)
        on_missing = config.get("on_missing", "null")

        # Core mapping evaluation
        for field_cfg in fields_config:
            target_path = field_cfg.get("path")
            source_key = field_cfg.get("from", target_path)
            is_required = field_cfg.get("required", False)

            # Basic parsing support for array indexing patterns like emails[0] or phones[0]
            array_match = re.match(r"(\w+)\[(\d+)\]", source_key)
            
            val = None
            if array_match:
                base_key = array_match.group(1)
                idx = int(array_match.group(2))
                base_list = canonical.get(base_key, [])
                if isinstance(base_list, list) and idx < len(base_list):
                    val = base_list[idx]
            else:
                val = canonical.get(source_key)

            # Handle Missing Policies
            if val is None or val == [] or val == {}:
                if is_required and on_missing == "error":
                    raise ValueError(f"Required field missing: {target_path}")
                if on_missing == "omit":
                    continue
                else:
                    val = None

            output[target_path] = val

        if include_confidence:
            output["overall_confidence"] = canonical.get("overall_confidence", 0.0)
            output["provenance"] = canonical.get("provenance", [])

        return output