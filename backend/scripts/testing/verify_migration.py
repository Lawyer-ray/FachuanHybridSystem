#!/usr/bin/env python
"""
Migration Verification Script

This script runs a comprehensive verification of the backend structure optimization migration.
It checks:
1. Structure validation tests
2. Sample unit tests
3. Sample integration tests
4. Sample property-based tests
5. Test coverage summary

Usage:
    python scripts/testing/verify_migration.py
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"\n{'='*80}")
    print(f"Running: {description}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"⚠️  Command timed out: {description}")
        return False
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False


def main():
    """Run all verification checks."""
    print("Backend Structure Optimization - Migration Verification")
    print("="*80)
    
    results = {}
    
    # 1. Structure validation tests
    results['structure'] = run_command(
        "venv311/bin/python -m pytest tests/structure/ -v --no-cov --tb=no -q",
        "Structure Validation Tests"
    )
    
    # 2. Core unit tests
    results['unit_core'] = run_command(
        "venv311/bin/python -m pytest tests/unit/core/ -v --no-cov --tb=no -q",
        "Core Unit Tests"
    )
    
    # 3. Cases integration tests
    results['integration_cases'] = run_command(
        "venv311/bin/python -m pytest tests/integration/cases/ -v --no-cov --tb=no -q",
        "Cases Integration Tests"
    )
    
    # 4. Cases property tests
    results['property_cases'] = run_command(
        "venv311/bin/python -m pytest tests/property/cases/ -v --no-cov --tb=no -q",
        "Cases Property-Based Tests"
    )
    
    # 5. Test collection summary
    print(f"\n{'='*80}")
    print("Test Collection Summary")
    print(f"{'='*80}")
    
    for test_type in ['unit', 'integration', 'property', 'structure']:
        result = subprocess.run(
            f"venv311/bin/python -m pytest tests/{test_type}/ --collect-only -q 2>&1 | tail -1",
            shell=True,
            capture_output=True,
            text=True
        )
        print(f"{test_type.capitalize()}: {result.stdout.strip()}")
    
    # Print summary
    print(f"\n{'='*80}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*80}")
    
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name:30s}: {status}")
    
    all_passed = all(results.values())
    
    print(f"\n{'='*80}")
    if all_passed:
        print("✅ ALL VERIFICATION CHECKS PASSED")
        print("Migration is verified and approved!")
    else:
        print("⚠️  SOME VERIFICATION CHECKS FAILED")
        print("Please review the failures above.")
    print(f"{'='*80}\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
