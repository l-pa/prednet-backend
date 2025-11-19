"""Test script to verify both UniProt and STRING-DB data sources work."""

import asyncio
import sys
from app.uniprot_client import fetch_multiple_proteins as fetch_uniprot
from app.stringdb_client import fetch_multiple_proteins as fetch_stringdb


async def test_uniprot():
    """Test UniProt data source."""
    print("\n" + "="*60)
    print("Testing UniProt Data Source")
    print("="*60)
    
    proteins = ["YAL001C", "YAL002W"]
    organism = "559292"  # S. cerevisiae
    
    print(f"\nFetching proteins: {proteins}")
    print(f"Organism: {organism}")
    
    try:
        results = await fetch_uniprot(proteins, organism)
        
        print(f"\n✓ Successfully fetched {len(results)} proteins")
        
        for result in results:
            print(f"\n  Protein: {result.protein}")
            print(f"  Sequence Length: {result.sequence_length}")
            print(f"  Features: {len(result.features)}")
            print(f"  Error: {result.error}")
            
            if result.go_terms:
                bp_count = len(result.go_terms.biological_process)
                cc_count = len(result.go_terms.cellular_component)
                mf_count = len(result.go_terms.molecular_function)
                print(f"  GO Terms: BP={bp_count}, CC={cc_count}, MF={mf_count}")
                
                # Show first GO term from each category
                if result.go_terms.biological_process:
                    term = result.go_terms.biological_process[0]
                    print(f"    Sample BP: {term.id} - {term.name}")
                if result.go_terms.cellular_component:
                    term = result.go_terms.cellular_component[0]
                    print(f"    Sample CC: {term.id} - {term.name}")
                if result.go_terms.molecular_function:
                    term = result.go_terms.molecular_function[0]
                    print(f"    Sample MF: {term.id} - {term.name}")
        
        return True
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stringdb():
    """Test STRING-DB data source."""
    print("\n" + "="*60)
    print("Testing STRING-DB Data Source")
    print("="*60)
    
    proteins = ["YAL001C", "YAL002W"]
    organism = "559292"  # S. cerevisiae
    
    print(f"\nFetching proteins: {proteins}")
    print(f"Organism: {organism}")
    
    try:
        results = await fetch_stringdb(proteins, organism)
        
        print(f"\n✓ Successfully fetched {len(results)} proteins")
        
        for result in results:
            print(f"\n  Protein: {result.protein}")
            print(f"  Sequence Length: {result.sequence_length}")
            print(f"  Features: {len(result.features)}")
            print(f"  Error: {result.error}")
            
            if result.go_terms:
                bp_count = len(result.go_terms.biological_process)
                cc_count = len(result.go_terms.cellular_component)
                mf_count = len(result.go_terms.molecular_function)
                print(f"  GO Terms: BP={bp_count}, CC={cc_count}, MF={mf_count}")
                
                # Show first GO term from each category
                if result.go_terms.biological_process:
                    term = result.go_terms.biological_process[0]
                    print(f"    Sample BP: {term.id} - {term.name}")
                if result.go_terms.cellular_component:
                    term = result.go_terms.cellular_component[0]
                    print(f"    Sample CC: {term.id} - {term.name}")
                if result.go_terms.molecular_function:
                    term = result.go_terms.molecular_function[0]
                    print(f"    Sample MF: {term.id} - {term.name}")
        
        return True
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Data Source Integration Tests")
    print("="*60)
    
    uniprot_ok = await test_uniprot()
    stringdb_ok = await test_stringdb()
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"UniProt:    {'✓ PASS' if uniprot_ok else '✗ FAIL'}")
    print(f"STRING-DB:  {'✓ PASS' if stringdb_ok else '✗ FAIL'}")
    print("="*60 + "\n")
    
    if uniprot_ok and stringdb_ok:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
