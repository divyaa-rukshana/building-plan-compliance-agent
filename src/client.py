import streamlit as st
import requests
import time

st.set_page_config(layout="wide", page_title="Building Plan Compliance Pre-Check")

st.title("Building Plan Compliance Pre-Check Portal")
st.subheader("Agent Submission & Citation Interface")

API_URL = "http://localhost:8000/v1/compliance/check"

with st.sidebar:
    st.header("Proposal Data Contract")
    proposal_id = st.text_input("Proposal ID/Correlation ID", value="PROP-2026-001")
    occupancy = st.selectbox("Occupancy Group", ["residential_main", "residential_mixed", "commercial_central", "commercial_business"])
    zoning = st.selectbox("Zoning Category", ["A", "B", "C"])
    width = st.number_input("Plot Width (meters)", min_value=0.1, value=9.0, step=0.1)
    depth = st.number_input("Plot Depth (meters)", min_value=0.1, value=12.0, step=0.1)
    road_width = st.number_input("Abutting Road Width (meters)", min_value=0.1, value=6.0, step=0.1)
    height = st.number_input("Proposed Height (meters)", min_value=0.1, value=8.5, step=0.1)
    
st.header("Free-Text Notes & Architectural Specifications")
notes = st.text_area(
    "Enter additional building notes (e.g., parking layout, structural exemptions):",
    placeholder="Proposed single-family residence with stilt parking structure..."
)

if st.button("Submit Proposal for Agent Review"):
    payload = {
        "proposal_id": proposal_id,
        "occupancy_group": occupancy,
        "zoning_category": zoning,
        "plot_width_m": width,
        "plot_depth_m": depth,
        "abutting_road_width_m": road_width,
        "proposed_height_m": height,
        "notes": notes
    }
    
    with st.spinner("Transmitting proposal to boundary API ingestion queue..."):
        try:
            res = requests.post(API_URL, json=payload, timeout=5)
            if res.status_code == 202:
                data = res.json()
                run_id = data["run_id"]
                poll_url = f"http://localhost:8000/v1/compliance/status/{run_id}"
                st.success(f"Proposal Accepted! Assigned Correlation Run ID: {run_id}")
                
                progress_bar = st.progress(0)
                status_box = st.empty()
                
                for attempt in range(1, 30):
                    status_res = requests.get(poll_url).json()
                    current_status = status_res.get("status")
                    status_box.info(f"Pipeline Operations Status: {current_status.upper()} (Attempt {attempt}/30)")
                    
                    if current_status == "completed":
                        progress_bar.progress(100)
                        status_box.empty()
                        
                        result = status_res["result"]
                        routing = result["routing"]
                        
                        if routing == "clear-for-submission":
                            st.balloons()
                            st.success(f"**FINAL ROUTING DECISION: {routing.upper()}**")
                        elif routing == "revise-and-recheck":
                            st.warning(f"**FINAL ROUTING DECISION: {routing.upper()}**")
                        else:
                            st.error(f"**FINAL ROUTING DECISION: {routing.upper()}**")
                            
                        st.markdown(f"**Primary Reason:** {result['primary_reason']}")
                        
                        st.header("Clause Finding Verification Logs")
                        for finding in result["findings"]:
                            with st.expander(f"Provision: {finding['provision_name']} (Compliant: {finding['is_compliant']})"):
                                st.markdown(f"**Observed Value:** {finding['observed_value']}")
                                st.markdown(f"**Required Constraint Limit:** {finding['required_limit']}")
                                st.markdown(f"**Details:** {finding['finding_details']}")
                                
                                if finding["citations"]:
                                    st.markdown("#### Grounded Factual Citations")
                                    for cite in finding["citations"]:
                                        st.info(f"**Clause ID:** {cite['clause_id']} | **Printed Page:** {cite['page']}\n\n*Verbatim Source Content:* \"{cite['extracted_text']}\"")
                        break
                    elif current_status == "failed":
                        progress_bar.progress(100)
                        st.error(f"Pipeline Execution Failure: {status_res.get('error')}")
                        break
                        
                    time.sleep(1)
                    progress_bar.progress(min(attempt * 4, 95))
            else:
                st.error(f"Ingestion Boundary Rejection (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            st.error(f"Unable to establish connectivity with API service: {str(e)}")
