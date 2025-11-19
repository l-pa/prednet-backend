"""Test if STRING-DB returns p-values."""

import asyncio
from app.stringdb_client import fetch_multiple_proteins


async def test_pvalues():
    """Check if STRING-DB returns p-values in GO terms."""
    
    print("\nTesting STRING-DB P-Values...")
    print("="*60)
    
    proteins = ["YAL001C", "YAL002W"]
    organism = "559292"
    
    results = await fetch_multiple_proteins(proteins, organism)
    
    for result in results:
        print(f"\nProtein: {result.protein}")
        print(f"Error: {result.error}")
        
        if result.go_terms:
            # Check biological process
            if result.go_terms.biological_process:
                print(f"\nBiological Process ({len(result.go_terms.biological_process)} terms):")
                for i, term in enumerate(result.go_terms.biological_process[:3]):
                    print(f"  {i+1}. {term.id} - {term.name}")
                    print(f"     P-value: {term.p_value}")
            
            # Check cellular component
            if result.go_terms.cellular_component:
                print(f"\nCellular Component ({len(result.go_terms.cellular_component)} terms):")
                for i, term in enumerate(result.go_terms.cellular_component[:3]):
                    print(f"  {i+1}. {term.id} - {term.name}")
                    print(f"     P-value: {term.p_value}")
            
            # Check molecular function
            if result.go_terms.molecular_function:
                print(f"\nMolecular Function ({len(result.go_terms.molecular_function)} terms):")
                for i, term in enumerate(result.go_terms.molecular_function[:3]):
                    print(f"  {i+1}. {term.id} - {term.name}")
                    print(f"     P-value: {term.p_value}")
            
            # Count terms with p-values
            all_terms = (
                result.go_terms.biological_process +
                result.go_terms.cellular_component +
                result.go_terms.molecular_function
            )
            terms_with_pvalue = sum(1 for t in all_terms if t.p_value is not None)
            print(f"\nTotal terms: {len(all_terms)}")
            print(f"Terms with p-value: {terms_with_pvalue}")
        else:
            print("No GO terms")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(test_pvalues())
