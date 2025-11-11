"""Manual test script for UniProt client."""

import asyncio

from app.uniprot_client import fetch_multiple_proteins


async def main():
    """Test fetching protein features and GO terms."""
    print("Testing UniProt client with GO terms...")
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
        
        # Display GO terms
        if result.go_terms:
            print(f"  GO Terms:")
            if result.go_terms.biological_process:
                print(f"    Biological Process ({len(result.go_terms.biological_process)}):")
                for go_term in result.go_terms.biological_process[:3]:
                    evidence = f" [{go_term.evidence}]" if go_term.evidence else ""
                    print(f"      - {go_term.id}: {go_term.name}{evidence}")
                if len(result.go_terms.biological_process) > 3:
                    print(f"      ... and {len(result.go_terms.biological_process) - 3} more")
            
            if result.go_terms.cellular_component:
                print(f"    Cellular Component ({len(result.go_terms.cellular_component)}):")
                for go_term in result.go_terms.cellular_component[:3]:
                    evidence = f" [{go_term.evidence}]" if go_term.evidence else ""
                    print(f"      - {go_term.id}: {go_term.name}{evidence}")
                if len(result.go_terms.cellular_component) > 3:
                    print(f"      ... and {len(result.go_terms.cellular_component) - 3} more")
            
            if result.go_terms.molecular_function:
                print(f"    Molecular Function ({len(result.go_terms.molecular_function)}):")
                for go_term in result.go_terms.molecular_function[:3]:
                    evidence = f" [{go_term.evidence}]" if go_term.evidence else ""
                    print(f"      - {go_term.id}: {go_term.name}{evidence}")
                if len(result.go_terms.molecular_function) > 3:
                    print(f"      ... and {len(result.go_terms.molecular_function) - 3} more")
        else:
            print(f"  GO Terms: None")

    print("\n" + "-" * 50)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
