"""Manual test script for UniProt client."""

import asyncio

from app.uniprot_client import fetch_multiple_proteins


async def main():
    """Test fetching protein features."""
    print("Testing UniProt client...")
    print("-" * 50)

    # Test with a few S. cerevisiae proteins
    proteins = ["YAL001C", "YAL002W", "TPM1"]

    print(f"Fetching features for: {', '.join(proteins)}")
    results = await fetch_multiple_proteins(proteins)

    for result in results:
        print(f"\nProtein: {result.protein}")
        print(f"  Sequence Length: {result.sequence_length}")
        print(f"  Features: {len(result.features)}")
        if result.error:
            print(f"  Error: {result.error}")
        else:
            for feature in result.features[:3]:  # Show first 3 features
                print(
                    f"    - {feature.type}: {feature.description} "
                    f"({feature.start}-{feature.end})"
                )
            if len(result.features) > 3:
                print(f"    ... and {len(result.features) - 3} more features")

    print("\n" + "-" * 50)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
