#!/usr/bin/env python3

"""
Scans the CVMFS directory structure for CMSSW releases and reports the
XRootD version for each architecture.

Writes a JSON object to 'cmssw_releasex.json' with the structure:
{
  "CMSSW_RELEASE_NAME": {
    "ARCHITECTURE_NAME": {
      "xrootd_version": "X.Y.Z",
      "isTokenReady": true|false
    },
    ...
  },
  ...
}
"""

import sys
import json
import pathlib
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
from typing import Union  # Import Union for backward compatibility

# Note: Changed 'bool | None' to 'Union[bool, None]' for older Python
def is_version_greater(version_str: str, target_str: str) -> Union[bool, None]:
    """
    Compares two version strings (e.g., "5.28.00d", "5.6.0").
    Returns True if version_str > target_str, False otherwise.
    Returns None if parsing fails.
    
    Args:
        version_str (str): The version to check.
        target_str (str): The version to compare against.
        
    Returns:
        Union[bool, None]: True if version_str > target_str, False otherwise.
                           None if a version part cannot be parsed.
    """
    try:
        # Clean the version string parts by removing any non-digit characters.
        # This turns "5.28.00d" into [5, 28, 0]
        v_parts = [int(re.sub(r'[^\d]', '', p)) for p in version_str.split('.')]
        t_parts = [int(p) for p in target_str.split('.')]
        
        # Pad the shorter list with zeros for comparison
        max_len = max(len(v_parts), len(t_parts))
        v_parts.extend([0] * (max_len - len(v_parts)))
        t_parts.extend([0] * (max_len - len(t_parts)))
        
        for v, t in zip(v_parts, t_parts):
            if v > t:
                return True
            if v < t:
                return False
        
        # If all parts are equal, it's not greater
        return False
    except (ValueError, TypeError) as e:
        # Catch errors from int() if a part is empty or invalid
        # after cleaning, (e.g., "5..1" would fail)
        return None
    except Exception as e:
        # Catch any other unexpected error
        print(f"Warning: Unexpected error comparing '{version_str}' and '{target_str}': {e}", file=sys.stderr)
        return None

def find_xrootd_versions(base_dir="/cvmfs/cms.cern.ch", token_ready_version="5.6.0"):
    """
    Scans the CVMFS directory structure to find XRootD versions
    for all CMSSW releases across all architectures.
    
    Args:
        base_dir (str): The base CVMFS path to scan.
        token_ready_version (str): The XRootD version threshold for "isTokenReady".
    
    Returns:
        dict: A nested dictionary mapping:
              {release: {arch: {"xrootd_version": "...", "isTokenReady": bool}}}
    """
    base_path = pathlib.Path(base_dir)
    if not base_path.is_dir():
        print(f"Error: Base path {base_path} not found or is not a directory.", file=sys.stderr)
        return {}

    # This will store: {release: {arch: {details...}}}
    release_data = defaultdict(dict)
    
    # Regex to check if a version string is "clean" (only digits and dots)
    clean_version_regex = re.compile(r"^[\d\.]+$")

    # Find all architecture directories, e.g., slc7_amd64_gcc11, el9_amd64_gcc11
    arch_dirs = sorted(base_path.glob("*gcc*"))

    if not arch_dirs:
        print(f"Warning: No architecture directories matching '*gcc*' found in {base_path}", file=sys.stderr)

    for arch_dir in arch_dirs:
        if not arch_dir.is_dir():
            continue
        
        arch = arch_dir.name
        cmssw_base_path = arch_dir / "cms" / "cmssw"

        if not cmssw_base_path.is_dir():
            continue

        # Find all CMSSW release directories, e.g., CMSSW_13_0_3
        for rel_dir in sorted(cmssw_base_path.glob("CMSSW_*")):
            if not rel_dir.is_dir():
                continue
            
            rel = rel_dir.name
            
            # Construct the specific path to the xrootd.xml file
            xml_file = rel_dir / "config" / "toolbox" / arch / "tools" / "selected" / "xrootd.xml"

            if xml_file.is_file():
                try:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()
                    
                    if root.tag == "tool" and root.get("name") == "xrootd":
                        version_full = root.get("version")
                        
                        if version_full:
                            # Get only the part before the dash
                            version = version_full.split("-")[0]
                            
                            # --- NEW WARNING BLOCK ---
                            # Check if the version string is "unclean"
                            if not clean_version_regex.match(version):
                                # Re-create the logic from is_version_greater to show the user
                                cleaned_version = ".".join([re.sub(r'[^\d]', '', p) for p in version.split('.')])
                                print(f"Warning: Non-standard XRootD version string '{version}' detected.\n"
                                      f"         Will be parsed as '{cleaned_version}'.\n"
                                      f"         Context: CMSSW={rel}, ARCH={arch}.",
                                      file=sys.stderr)
                            # --- END NEW WARNING BLOCK ---

                            # Check if the version is greater than the target
                            is_token_ready = is_version_greater(version, token_ready_version)
                            
                            if is_token_ready is None:
                                # Parsing failed, print the context-aware warning
                                print(f"Error: Could not parse XRootD version string '{version}' (from '{version_full}').\n"
                                      f"       Context: CMSSW={rel}, ARCH={arch}.\n"
                                      f"       Defaulting to isTokenReady=False.",
                                      file=sys.stderr)
                                is_token_ready = False # Set a safe default
                            
                            release_data[rel][arch] = {
                                "xrootd_version": version,
                                "isTokenReady": is_token_ready
                            }
                        else:
                            print(f"Warning: 'version' attribute not found in {xml_file}", file=sys.stderr)
                    else:
                        print(f"Warning: Unexpected XML content in {xml_file}", file=sys.stderr)
                        
                except ET.ParseError:
                    print(f"Error: Could not parse XML file {xml_file}", file=sys.stderr)
                except Exception as e:
                    print(f"Error: An unexpected error occurred with {xml_file}: {e}", file=sys.stderr)

    return release_data

if __name__ == "__main__":
    output_filename = "cmssw_releasex.json"
    
    # Run the main function
    all_release_data = find_xrootd_versions(base_dir="/cvmfs/cms.cern.ch")
    
    # Write the results to the specified JSON file
    try:
        with open(output_filename, "w") as json_file:
            # Use json.dump() to write to the file handle
            # sort_keys=True ensures a consistent output order
            json.dump(all_release_data, json_file, indent=2, sort_keys=True)
        
        print(f"Successfully wrote JSON output to {output_filename}")
        
    except IOError as e:
        print(f"Error: Could not write file {output_filename}. {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred while writing JSON file: {e}", file=sys.stderr)
