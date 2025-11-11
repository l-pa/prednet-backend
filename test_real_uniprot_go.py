"""Test script to fetch real UniProt data and debug GO term parsing."""

import asyncio
import json
from app.uniprot_client import UniProtClient

async def test_real_protein(protein_id: str = "YAL001C"):
    """Fetch real data from UniProt and test GO parsing."""
    print(f"Testing with real protein: {protein_id}")
    print("=" * 70)
    
    async with UniProtClient() as client:
        result = await client.fetch_protein_features(protein_id)
        
        print(f"\nProtein: {result.protein}")
        print(f"Sequence Length: {result.sequence_length}")
        print(f"Features: {len(result.features)}")
        print(f"Error: {result.error}")
        
        if result.go_terms:
            print("\n✓ GO Terms found!")
            print(f"  Biological Process: {len(result.go_terms.biological_process)}")
            print(f"  Cellular Component: {len(result.go_terms.cellular_component)}")
            print(f"  Molecular Function: {len(result.go_terms.molecular_function)}")
            
            # Show samples
            if result.go_terms.biological_process:
                print("\n  Sample BP terms:")
                for term in result.go_terms.biological_process[:3]:
                    print(f"    - {term.id}: {term.name} [{term.evidence}]")
            
            if result.go_terms.cellular_component:
                print("\n  Sample CC terms:")
                for term in result.go_terms.cellular_component[:3]:
                    print(f"    - {term.id}: {term.name} [{term.evidence}]")
            
            if result.go_terms.molecular_function:
                print("\n  Sample MF terms:")
                for term in result.go_terms.molecular_function[:3]:
                    print(f"    - {term.id}: {term.name} [{term.evidence}]")
        else:
            print("\n✗ No GO terms found!")
            print("\nDebugging: Let's fetch the raw response...")
            
            # Fetch raw response to debug
            url = f"{client.BASE_URL}/search"
            params = {
                "query": f"gene:{protein_id} AND organism_id:559292",
                "format": "json",
                "fields": "length,go,go_p,go_c,go_f",
                "size": "1",
            }
            
            response = await client._client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    entry = results[0]
                    
                    # Check for GO terms in different locations
                    print("\n  Checking entry structure...")
                    print(f"  - Has 'uniProtKBCrossReferences': {'uniProtKBCrossReferences' in entry}")
                    
                    if "uniProtKBCrossReferences" in entry:
                        cross_refs = entry["uniProtKBCrossReferences"]
                        go_refs = [ref for ref in cross_refs if ref.get("database") == "GO"]
                        print(f"  - GO cross-references found: {len(go_refs)}")
                        
                        if go_refs:
                            print("\n  Sample GO reference:")
                            print(f"  {json.dumps(go_refs[0], indent=4)}")
                    
                    # Check for other GO fields
                    if "goAnnotations" in entry:
                        print(f"  - Has 'goAnnotations': {len(entry['goAnnotations'])}")
                    
                    # Save full entry for inspection
                    with open("debug_uniprot_entry.json", "w") as f:
                        json.dump(entry, f, indent=2)
                    print("\n  Full entry saved to: debug_uniprot_entry.json")

if __name__ == "__main__":
    # Test with a few common yeast proteins
    proteins = ["YAL001C", "YAL002W", "ACT1"]
    
    for protein in proteins:
        asyncio.run(test_real_protein(protein))
        print("\n" + "=" * 70 + "\n")
