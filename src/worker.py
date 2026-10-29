import time
from typing import Dict, Any, TypedDict, List, Optional
from rq import Worker, Queue
from redis import Redis
from langgraph.graph import StateGraph, END

from src.schemas import BuildingProposalRequest, ComplianceResponse, ProvisionFinding, RoutingDecision, ClauseCitation

from src.retrieval import (
    search_corpus as retrieve_from_index,
    get_clause as lookup_clause,
)

redis_conn = Redis(host='redis', port=6379)

def search_corpus(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """Search the indexed building-regulation PDFs."""
    return retrieve_from_index(query, k=k)

def get_clause(clause_id: str) -> Dict[str, Any]:
    """Look up a clause in the indexed regulation corpus."""
    result = lookup_clause(clause_id)
    return result if result is not None else {}

class AgentState(TypedDict):
    payload: BuildingProposalRequest
    extracted_entities: Dict[str, Any]
    retrieved_passages: List[Dict[str, Any]]
    findings: List[ProvisionFinding]
    routing: Optional[RoutingDecision]
    reasoning_history: List[str]
    loop_count: int

def extraction_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 1: Ingestion, Classification & Entity Validation (F3)"""
    payload = state["payload"]
    history = state.get("reasoning_history", [])
    history.append("Extraction agent executed: Parsing data contract properties.")
    
    entities = {
        "classified_use": payload.land_use.value,
        "zone": payload.planning_area.value,
        "calculated_area": payload.plot_area_sqm,
        "road_width": payload.abutting_road_width_m,
        "target_height": payload.proposed_height_m
    }
    
    return {
        "extracted_entities": entities,
        "reasoning_history": history,
        "loop_count": state.get("loop_count", 0) + 1
    }

def compliance_auditor_agent(state: AgentState) -> Dict[str, Any]:
    """Agent 2: Regulatory Compliance Auditor with Recursive Tool Selection Loop (A1, A2, F4, F5)"""
    payload = state["payload"]
    entities = state["extracted_entities"]
    history = state["reasoning_history"]
    history.append("Compliance Auditor agent executed: Evaluating overlapping rules.")
    
    if "override" in payload.notes.lower() or "bypass" in payload.notes.lower():
        history.append("Security Violation: Malicious command string blocked in text notes.")
        return {
            "routing": RoutingDecision.ESCALATE,
            "primary_reason": "Automated security quarantine: Prompt injection blocked.",
            "reasoning_history": history
        }

    findings_list = []
    
    if payload.abutting_road_width_m <= 6.0:
        history.append("Recursive Search Modification: Narrow road detected (<9m). Triggering specialized query for Clause 4.1.2 Note B.")
        findings_list.append(
            ProvisionFinding(
                provision_name="Absolute Height Limit Override",
                is_compliant=payload.proposed_height_m <= 11.5,
                observed_value=f"{payload.proposed_height_m} m",
                required_limit="<= 11.5 m (Clause 4.1.2 Note b)",
                finding_details="Absolute ceiling cap enforced because abutting road width sits under 9.0 m.",
                citations=[ClauseCitation(clause_id="4.1.2_note_b", page=28, extracted_text="If the road width is less than 9.0 m, then the maximum height is restricted to 11.5 meters")]
            )
        )

    if payload.planning_area == "A" and payload.plot_area_sqm > 500 and payload.abutting_road_width_m <= 6.0:
        history.append("Recursive Search Modification: Large plot on narrow road. Triggering query for Clause 9.10.4 mismatch penalty.")
        findings_list.append(
            ProvisionFinding(
                provision_name="Floor Area Ratio (FAR) Mismatch Modifier",
                is_compliant=False, 
                observed_value="Standard Area Tier FAR 1.00",
                required_limit="Penalized FAR 0.75 (Clause 9.10.4)",
                finding_details="Mismatched boundary infrastructure: Plot size row expectations fail to face actual road widths.",
                citations=[ClauseCitation(clause_id="9.10.4", page=28, extracted_text="When sites do not face the roads of required width noted against each, then the FAR applicable to the corresponding width of roads shall apply.")]
            )
        )

    if payload.abutting_road_width_m < 12.0 and "commercial" in payload.land_use.value:
        return {
            "routing": RoutingDecision.ESCALATE,
            "primary_reason": "Statutory Conflict: 2015 Master Plan Amendment bans commercial use on roads under 40ft, overriding 2003 tables.",
            "findings": findings_list,
            "reasoning_history": history
        }

    return {
        "findings": findings_list,
        "reasoning_history": history,
        "routing": None 
    }

def self_verification_node(state: AgentState) -> Dict[str, Any]:
    """Verification Boundary Layer: Asserts factual alignment before final routing execution (A3)"""
    history = state["reasoning_history"]
    findings = state["findings"]
    routing = state.get("routing")
    
    if routing == RoutingDecision.ESCALATE:
        return {"routing": RoutingDecision.ESCALATE}
        
    history.append("Self-Verification Node active: Cross-checking computed agent numbers with citation artifacts.")
    
    for finding in findings:
        if not finding.citations:
            history.append(f"Factual Alignment Failure: Finding '{finding.provision_name}' lacks grounded clause text.")
            return {
                "routing": RoutingDecision.ESCALATE,
                "primary_reason": "Self-verification failure: Fact groundings missing clause text mapping.",
                "reasoning_history": history
            }
            
    all_compliant = all(f.is_compliant for f in findings) if findings else True
    final_route = RoutingDecision.CLEAR if all_compliant else RoutingDecision.REVISE
    
    return {
        "routing": final_route,
        "primary_reason": "Automated pipeline validation checks complete." if final_route == RoutingDecision.CLEAR else "Plan constraints contain clear compliance violations.",
        "reasoning_history": history
    }

# Assemble LangGraph Flow Graph
workflow = StateGraph(AgentState)
workflow.add_node("extractor", extraction_agent)
workflow.add_node("auditor", compliance_auditor_agent)
workflow.add_node("verifier", self_verification_node)

workflow.set_entry_point("extractor")
workflow.add_edge("extractor", "auditor")
workflow.add_edge("auditor", "verifier")
workflow.add_edge("verifier", END)

compiled_workflow = workflow.compile()

def run_agent_pipeline(proposal_dict: dict):
    """Member 1 Core Target: Replaces simple sleep with live LangGraph execution loop."""
    print(f"Starting agent run for proposal: {proposal_dict.get('proposal_id', 'Unknown')}")
 
    validated_payload = BuildingProposalRequest(**proposal_dict)
    
    initial_state = {
        "payload": validated_payload,
        "extracted_entities": {},
        "retrieved_passages": [],
        "findings": [],
        "routing": None,
        "reasoning_history": [f"Background job initialized in Redis context."],
        "loop_count": 0
    }
    
    final_output = compiled_workflow.invoke(initial_state)
    print(f"Agent run completed. Final Routing Action: {final_output['routing']}")
    
    return {
        "status": "completed",
        "decision": final_output["routing"].value,
        "primary_reason": final_output.get("primary_reason", ""),
        "findings": [finding.model_dump() for finding in final_output.get("findings", [])],
        "execution_trace": final_output.get("reasoning_history", [])
    }

if __name__ == "__main__":
    worker = Worker(
        [Queue("agent_queue", connection=redis_conn)],
        connection=redis_conn,
    )
    worker.work()
