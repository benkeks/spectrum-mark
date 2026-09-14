#!/usr/bin/env python3
"""
CSV to AUT format converter for Labeled Transition Systems.

This script converts CSV files containing LTS data into AUT format files.
Each CSV file contains two types of triples:
- Transition: src_state_id, tar_state_id, transition_action_name
- Meta: state_id, state_name, state_meta (where state_meta is "implicit-main")

The AUT format is documented at:
https://mcrl2.org/web/user_manual/tools/lts.html#language-aut-lts

Each output AUT file represents the full LTS with one named state as the initial state.
AUT files are written to an 'aut' subdirectory relative to the input CSV file.
"""

import csv
import os
import sys
from pathlib import Path


def parse_csv(filepath):
    """
    Parse a CSV file into transitions and meta entries.
    
    Args:
        filepath: Path to the CSV file
        
    Returns:
        tuple: (transitions, meta)
            - transitions: list of dicts with keys 'src', 'tar', 'action'
            - meta: list of dicts with keys 'state_id', 'state_name', 'state_meta'
    """
    transitions = []
    meta = []
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            # Skip empty rows
            if not row or all(cell.strip() == '' for cell in row):
                continue
            
            # Each row should have exactly 3 fields
            if len(row) != 3:
                print(f"Warning: Row has {len(row)} fields (expected 3): {row}", file=sys.stderr)
                continue
            
            field0, field1, field2 = [cell.strip() for cell in row]
            
            # Check if this is a meta entry (state_meta == "implicit-main")
            if field2 == "implicit-main":
                try:
                    state_id = int(field0)
                except ValueError:
                    print(f"Warning: Invalid state_id '{field0}' in meta entry: {row}", file=sys.stderr)
                    continue
                meta.append({
                    'state_id': state_id,
                    'state_name': field1,
                    'state_meta': field2
                })
            else:
                # This is a transition
                try:
                    src = int(field0)
                    tar = int(field1)
                except ValueError:
                    print(f"Warning: Invalid state id in transition: {row}", file=sys.stderr)
                    continue
                transitions.append({
                    'src': src,
                    'tar': tar,
                    'action': field2
                })
    
    return transitions, meta


def generate_aut(transitions, meta_entry, basename):
    """
    Generate AUT format content for a given meta entry.
    
    Args:
        transitions: List of transition dicts
        meta_entry: Dict with 'state_id', 'state_name', 'state_meta'
        basename: Base filename without extension
        
    Returns:
        str: AUT format content
    """
    initial_state = meta_entry['state_id']
    state_name = meta_entry['state_name']
    
    # Collect all unique states from transitions
    all_states = set()
    for t in transitions:
        all_states.add(t['src'])
        all_states.add(t['tar'])
    
    # Also include the initial state (in case it has no transitions)
    all_states.add(initial_state)
    
    num_states = len(all_states)
    num_transitions = len(transitions)
    
    # Build the AUT file content
    lines = []
    
    # Header line
    header = f"des ({initial_state},{num_transitions},{num_states})"
    lines.append(header)
    
    # Transition lines
    for t in transitions:
        line = f"({t['src']},\"{t['action']}\",{t['tar']})"
        lines.append(line)
    
    return "\n".join(lines) + "\n"


def convert_csv_to_aut(csv_path):
    """
    Convert a CSV file to multiple AUT files.
    
    Creates one AUT file per meta entry, with the state_name as part of the filename.
    AUT files are written to an 'aut' subdirectory relative to the CSV file.
    
    Args:
        csv_path: Path to the input CSV file
    """
    # Parse the CSV
    transitions, meta = parse_csv(csv_path)
    
    if not meta:
        print(f"Warning: No meta entries found in {csv_path}", file=sys.stderr)
        return
    
    # Get the base filename
    basename = Path(csv_path).stem
    
    # Get all unique states for validation
    all_states = set()
    for t in transitions:
        all_states.add(t['src'])
        all_states.add(t['tar'])
    
    # Create output directory: {csv_dir}/aut
    output_dir = Path(csv_path).parent / "aut"
    output_dir.mkdir(exist_ok=True)
    
    # Generate AUT files for each meta entry
    for entry in meta:
        state_name = entry['state_name']
        # Create output filename: {basename}_{state_name}.aut
        output_filename = f"{basename}_{state_name}.aut"
        output_path = output_dir / output_filename
        
        # Generate AUT content
        aut_content = generate_aut(transitions, entry, basename)
        
        # Write the file
        with open(output_path, 'w') as f:
            f.write(aut_content)
        
        print(f"Created: {output_path}")


def main():
    """
    Main function: convert CSV files to AUT format.
    
    Usage:
        python csv_to_aut.py          # Convert all CSV files in examples/
        python csv_to_aut.py file.csv # Convert specific CSV file
    """
    # Check if a specific file was provided as argument
    if len(sys.argv) > 1:
        csv_files = [Path(arg) for arg in sys.argv[1:]]
    else:
        # Default: process all CSV files in the examples directory
        examples_dir = Path(__file__).parent / "examples"
        
        if not examples_dir.exists():
            print(f"Error: Examples directory not found: {examples_dir}", file=sys.stderr)
            sys.exit(1)
        
        # Find all CSV files
        csv_files = list(examples_dir.glob("*.csv"))
        
        if not csv_files:
            print(f"No CSV files found in {examples_dir}", file=sys.stderr)
            sys.exit(1)
    
    # Filter to only existing files with .csv extension
    csv_files = [f for f in csv_files if f.exists() and f.suffix.lower() == '.csv']
    
    if not csv_files:
        print("No valid CSV files to process", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(csv_files)} CSV file(s) to process")
    
    for csv_file in csv_files:
        print(f"\nProcessing: {csv_file}")
        transitions, meta = parse_csv(csv_file)
        print(f"  Transitions: {len(transitions)}")
        print(f"  Meta entries: {len(meta)}")
        
        # Generate AUT files
        convert_csv_to_aut(csv_file)
    
    print("\nConversion complete!")


if __name__ == "__main__":
    main()
