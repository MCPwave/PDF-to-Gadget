#!/usr/bin/env python3
"""
Simple test runner for connector_parser tests.
Runs tests manually without pytest dependency.
"""

import sys
from pathlib import Path

# Add the agents directory to path
sys.path.insert(0, str(Path(__file__).parent))

from test_connector_parser import *

def run_test_class(test_class):
    """Run all test methods in a test class."""
    instance = test_class()
    methods = [m for m in dir(instance) if m.startswith('test_')]
    passed = 0
    failed = 0
    
    for method_name in methods:
        try:
            method = getattr(instance, method_name)
            method()
            print(f"✓ {test_class.__name__}.{method_name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_class.__name__}.{method_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_class.__name__}.{method_name}: ERROR: {e}")
            failed += 1
    
    return passed, failed


def main():
    """Run all tests."""
    test_classes = [
        TestPinExtraction,
        TestBusTypeInference,
        TestConnectorTypeExtraction,
        TestVoltageExtraction,
        TestFullParsing,
        TestRealWorldExamples,
        TestEdgeCases,
    ]
    
    total_passed = 0
    total_failed = 0
    
    print("=" * 70)
    print("Running Connector Parser Tests")
    print("=" * 70)
    
    for test_class in test_classes:
        passed, failed = run_test_class(test_class)
        total_passed += passed
        total_failed += failed
        print()
    
    print("=" * 70)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print("=" * 70)
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
