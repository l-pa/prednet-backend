"""Test the UniProt client directly."""

import asyncio
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

from app.uniprot_client import fetch_multiple_proteins


async def main():
    """Test fetching proteins."""
    proteins = ["YPL273W", "YBR160W"]
    print(f"Fetching proteins: {proteins}")
    results = await fetch_multiple_proteins(proteins)
    
    for result in results:
        print(f"\nProtein: {result.protein}")
        print(f"  Length: {result.sequence_length}")
        print(f"  Features: {len(result.features)}")
        print(f"  Error: {result.error}")
        if result.features:
            for feat in result.features[:3]:  # Show first 3 features
                print(f"    - {feat.type}: {feat.description} ({feat.start}-{feat.end})")


if __name__ == "__main__":
    asyncio.run(main())
