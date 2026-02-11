"""
One-time utility to fix edge handles in existing saved scenarios.
This ensures jumpbox connections use the right handle.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fs_manager
import helpers

def fix_scenario_edges(scenario_name):
    """Fix edge handles for a single scenario"""
    print(f"\nProcessing scenario: {scenario_name}")
    
    scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
    if "ERROR" in scenario:
        print(f"  ❌ Error loading scenario: {scenario}")
        return False
    
    topology = scenario.get("topology", {})
    if not topology:
        print(f"  ⚠️  No topology found")
        return False
    
    nodes = topology.get("nodes", [])
    edges = topology.get("edges", [])
    
    if not edges:
        print(f"  ⚠️  No edges found")
        return False
    
    node_map = {node["id"]: node for node in nodes}
    
    # Fix edges
    fixed_count = 0
    for i, edge in enumerate(edges):
        # Ensure edge has an ID
        if not edge.get("id"):
            edge["id"] = f"edge-{i + 1}"
            fixed_count += 1
        
        # Find source and target nodes
        source_node = node_map.get(edge.get("source"))
        target_node = node_map.get(edge.get("target"))
        
        if not source_node or not target_node:
            continue
        
        is_jumpbox_connection = target_node.get("type") == "jumpbox"
        
        if is_jumpbox_connection:
            if edge.get("sourceHandle") != "right":
                edge["sourceHandle"] = "right"
                fixed_count += 1
                print(f"  ✓ Fixed jumpbox connection: {source_node.get('data', {}).get('workstationName') or source_node.get('data', {}).get('domainControllerName') or edge.get('source')} -> Jumpbox")
    
    if fixed_count > 0:
        fs_manager.save_file(scenario, helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        print(f"  ✅ Fixed {fixed_count} edges")
        return True
    else:
        print(f"  ℹ️  No changes needed")
        return False

def main():
    print("=" * 60)
    print("Fixing Edge Handles in Saved Scenarios")
    print("=" * 60)
    
    scenario_dir = helpers.SCENARIO_DIRECTORY
    if not os.path.exists(scenario_dir):
        print(f"❌ Scenario directory not found: {scenario_dir}")
        return
    
    scenario_files = [f for f in os.listdir(scenario_dir) if f.endswith('.json')]
    
    if not scenario_files:
        print("No scenario files found")
        return
    
    print(f"\nFound {len(scenario_files)} scenario files")
    
    fixed_count = 0
    for scenario_file in scenario_files:
        scenario_name = scenario_file.replace('.json', '')
        if fix_scenario_edges(scenario_name):
            fixed_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Complete! Fixed {fixed_count} scenarios")
    print("=" * 60)
    print("\nRefresh your browser to see the changes!")

if __name__ == "__main__":
    main()
