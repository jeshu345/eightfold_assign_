import sys
import json

def run_pipeline():
    # Simulated input source files matching problem domain instructions
    mock_input_sources = [
        {
            "source_type": "recruiter_csv",
            "data": {
                "name": "Jane Doe",
                "email": "JANE.DOE@GMAIL.COM",
                "phone": "555-0199"
            }
        },
        {
            "source_type": "ats_json",
            "data": {
                "full_name": "Jane Doe",
                "skills": ["Python", "Data Extraction"]
            }
        }
    ]

    # Matching the exact syntax request in the prompt images
    runtime_config = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
            {"path": "skills", "type": "array"}
        ],
        "include_confidence": True,
        "on_missing": "null"
    }

    engine = CandidateTransformerEngine()
    
    # 1. Transform raw variant sources into Unified Canonical Record
    canonical_profile = engine.process_sources(mock_input_sources)
    
    # 2. Reshape according to runtime configuration schema requirements
    final_projection = ProjectionLayer.project(canonical_profile, runtime_config)

    print(json.dumps(final_projection, indent=2))

if __name__ == "__main__":
    run_pipeline()