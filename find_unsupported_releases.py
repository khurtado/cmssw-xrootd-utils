#!/usr/bin/env python3

"""
Analyzes the 'cmssw_releasex.json' file to find the minimal CMSSW version
per major release series (e.g., CMSSW_10_X, CMSSW_11_X) that is
"token ready".

A release is only considered "token ready" if ALL of its architectures
are marked as "isTokenReady": true.

The "inflection point" is the first version in a series (e.g., CMSSW_10_6_0)
such that it AND all subsequent versions in that series are token ready.

The script also lists all "unsupported" (not token-ready) releases
between the CMSSW_10_X and CMSSW_13_X series.
"""

import sys
import json
import re
from collections import defaultdict
from typing import Tuple, List, Dict, Any # Added for clarity

def get_sort_key(release_name: str) -> tuple:
    """
    Creates a sort key from a CMSSW release string for natural sorting.
    
    Handles versions like 'CMSSW_10_1_1' and 'CMSSW_10_1_1_pre1'.
    
    Returns:
        A tuple e.g., ((10, 1, 1), ('pre', 1))
    """
    # Remove prefix
    parts = release_name.split('_')[1:]
    
    num_parts = []
    pre_parts = ('zz', 0) # 'zz' sorts after 'pre', 'rc', etc.
    
    for part in parts:
        if part.isdigit():
            num_parts.append(int(part))
        else:
            # Found a non-numeric part, treat as pre-release
            # e.g., 'pre1', 'patch2', 'rc3'
            match = re.match(r'([a-zA-Z]+)(\d+)?', part)
            if match:
                pre_name = match.group(1).lower()
                pre_num = int(match.group(2) or 0)
                pre_parts = (pre_name, pre_num)
            
            # Stop parsing numbers after the first pre-release tag
            break
            
    # Pad with zeros for robust comparison
    num_parts.extend([0] * (4 - len(num_parts)))
    return (tuple(num_parts), pre_parts)

def analyze_releases(json_file: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Loads the JSON file and performs the inflection point analysis.
    
    Args:
        json_file (str): Path to the input JSON file.
        
    Returns:
        A tuple containing:
        - (dict): A dictionary mapping series_name to an analysis string.
        - (list): A list of unsupported release names (CMSSW 10-13).
    """
    
    try:
        with open(json_file, 'r') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{json_file}' not found.", file=sys.stderr)
        return {}, []
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON from '{json_file}'.", file=sys.stderr)
        return {}, []

    flattened_releases = []

    # 1. Flatten the data from (release -> arch -> status)
    #    to (release -> aggregated_status)
    for release_name, arch_data in json_data.items():
        if not arch_data:
            # Skip empty entries
            continue
            
        # A release is "ready" ONLY IF all its listed architectures are ready
        is_release_ready = all(v.get("isTokenReady", False) for v in arch_data.values())
        
        # Get its sort key
        sort_key = get_sort_key(release_name)
        
        flattened_releases.append((release_name, is_release_ready, sort_key))

    # 2. Sort all releases chronologically
    flattened_releases.sort(key=lambda x: x[2])

    # 3. Group by major series (e.g., CMSSW_10_X)
    major_series_map = defaultdict(list)
    unsupported_releases_10_to_13 = []
    
    for release_name, is_ready, sort_key in flattened_releases:
        num_parts = sort_key[0]
        if not num_parts:
            # Skip unparseable names
            continue
            
        major_version = num_parts[0]
        
        # Group by the first version number
        major_series_name = f"CMSSW_{major_version}_X Series"
        major_series_map[major_series_name].append((release_name, is_ready))
        
        # --- NEW: Check for unsupported releases in the target range ---
        if not is_ready and 10 <= major_version <= 13:
            unsupported_releases_10_to_13.append(release_name)
        # --- END NEW ---

    # 4. Find the inflection point for each series
    analysis_results = {}
    for series_name, releases in major_series_map.items():
        if not releases:
            analysis_results[series_name] = "No data found."
            continue
            
        # Find the index of the *last* False release
        last_false_index = -1
        all_true = True
        all_false = True
        
        for i, (release_name, is_ready) in enumerate(releases):
            if is_ready:
                all_false = False
            if not is_ready:
                all_true = False
                last_false_index = i
        
        # Report based on the findings
        if all_true:
            # All releases in the series are True
            inflection_point = releases[0][0]
            analysis_results[series_name] = f"Token ready starting from {inflection_point} (all releases in series are ready)"
        elif all_false:
            # All releases in the series are False
            analysis_results[series_name] = "No releases are token ready."
        elif last_false_index == len(releases) - 1:
            # The series ends with a False, so no stable point
            analysis_results[series_name] = "No stable 'Token ready' status (series ends with a non-ready release)."
        else:
            # The inflection point is the release *after* the last False one
            inflection_point = releases[last_false_index + 1][0]
            analysis_results[series_name] = f"Token ready starting from {inflection_point}"
            
    return analysis_results, unsupported_releases_10_to_13

if __name__ == "__main__":
    input_file = "cmssw_releasex.json"
    analysis, unsupported = analyze_releases(input_file)
    
    if analysis:
        print("--- CMSSW Token-Ready Inflection Point Analysis ---")
        # Sort the series names for a clean report
        # (e.g., "CMSSW_10_X", "CMSSW_11_X", ...)
        sorted_series_keys = sorted(analysis.keys(), key=lambda s: int(s.split('_')[1]))
        
        for series in sorted_series_keys:
            print(f"{series:<20}: {analysis[series]}")
    else:
        print("Analysis failed. No results to show.", file=sys.stderr)

    # --- NEW: Print the unsupported list ---
    if unsupported:
        print("\n--- Unsupported Releases (Not Token Ready, CMSSW 10-13) ---")
        for release in unsupported:
            print(f"  - {release}")
    elif analysis: # Only print this if analysis ran but found no unsupported
        print("\n--- No unsupported releases found in CMSSW 10-13 ---")
    # --- END NEW ---
