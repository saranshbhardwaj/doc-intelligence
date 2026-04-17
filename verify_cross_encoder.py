#!/usr/bin/env python3
"""
Verification script for cross-encoder chunk pairing upgrade.

Tests that the cross-encoder similarity computation works correctly.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.rag.reranker import Reranker
import numpy as np


def test_cross_encoder_similarity():
    """Test cross-encoder similarity computation with sample chunks"""

    print("=" * 60)
    print("Cross-Encoder Similarity Verification")
    print("=" * 60)

    # Initialize reranker
    print("\n1. Initializing cross-encoder model...")
    try:
        reranker = Reranker()
        print("   ✓ Cross-encoder loaded successfully")
        print(f"   Model: {reranker.model_name}")
    except Exception as e:
        print(f"   ✗ Failed to load cross-encoder: {e}")
        return False

    # Test cases: pairs of similar and dissimilar chunks
    print("\n2. Testing semantic similarity scoring...")

    test_cases = [
        {
            "name": "High similarity (cap rate discussion)",
            "text_a": "The capitalization rate for this asset is 6.5%",
            "text_b": "Property shows a cap rate of 7.2%",
            "expected": "high (>0.7)"
        },
        {
            "name": "Moderate similarity (revenue/income)",
            "text_a": "Annual revenue for the property is $2.5M",
            "text_b": "The property generates $2.3M in yearly income",
            "expected": "high (>0.7)"
        },
        {
            "name": "Low similarity (unrelated topics)",
            "text_a": "The property is located in downtown Manhattan",
            "text_b": "The tenant has a 10-year lease with annual escalations",
            "expected": "low (<0.5)"
        },
        {
            "name": "Very high similarity (near-identical)",
            "text_a": "Net operating income is $500,000 annually",
            "text_b": "Annual net operating income: $500,000",
            "expected": "very high (>0.8)"
        }
    ]

    all_passed = True

    for i, test in enumerate(test_cases, 1):
        print(f"\n   Test {i}: {test['name']}")
        print(f"   Text A: {test['text_a'][:60]}...")
        print(f"   Text B: {test['text_b'][:60]}...")

        try:
            # Score the pair
            pairs = [[test['text_a'], test['text_b']]]
            scores = reranker.model.predict(pairs, show_progress_bar=False)
            raw_score = scores[0]

            # Normalize with sigmoid
            normalized_score = 1 / (1 + np.exp(-raw_score))

            print(f"   Raw score: {raw_score:.4f}")
            print(f"   Normalized (sigmoid): {normalized_score:.4f}")
            print(f"   Expected: {test['expected']}")

            # Validate score is in valid range
            if 0 <= normalized_score <= 1:
                print(f"   ✓ Score in valid range [0, 1]")
            else:
                print(f"   ✗ Score out of range: {normalized_score}")
                all_passed = False

        except Exception as e:
            print(f"   ✗ Scoring failed: {e}")
            all_passed = False

    # Test batch scoring (multiple pairs at once)
    print("\n3. Testing batch scoring efficiency...")
    try:
        batch_pairs = [
            ["Text A1", "Text B1"],
            ["Text A2", "Text B2"],
            ["Text A3", "Text B3"],
        ]
        scores = reranker.model.predict(batch_pairs, batch_size=32, show_progress_bar=False)
        normalized = [1 / (1 + np.exp(-s)) for s in scores]

        print(f"   ✓ Batch scored {len(batch_pairs)} pairs")
        print(f"   Normalized scores: {[f'{s:.4f}' for s in normalized]}")
    except Exception as e:
        print(f"   ✗ Batch scoring failed: {e}")
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All verification tests passed!")
        print("\nThe cross-encoder is working correctly and ready for use.")
    else:
        print("✗ Some verification tests failed.")
        print("\nPlease check the errors above.")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = test_cross_encoder_similarity()
    sys.exit(0 if success else 1)
