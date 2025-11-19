"""Test the API endpoint directly to verify serialization."""

import asyncio
import sys
from app.api.routes.proteins import get_protein_features
from fastapi import Query


async def test_api_endpoint():
    """Test the API endpoint with both data sources."""
    
    print("\n" + "="*60)
    print("Testing API Endpoint Serialization")
    print("="*60)
    
    # Test UniProt
    print("\n1. Testing UniProt source:")
    try:
        result = await get_protein_features(
            network_name="Yeast/BioGRID",
            proteins="YAL001C,YAL002W",
            name_mode="systematic",
            organism_id="559292",
            source="uniprot"
        )
        
        print(f"   ✓ Response type: {type(result)}")
        print(f"   ✓ Proteins count: {len(result.proteins)}")
        
        # Try to serialize to dict (this is what FastAPI does)
        result_dict = result.model_dump()
        print(f"   ✓ Serialization successful")
        print(f"   ✓ First protein: {result_dict['proteins'][0]['protein']}")
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test STRING-DB
    print("\n2. Testing STRING-DB source:")
    try:
        result = await get_protein_features(
            network_name="Yeast/BioGRID",
            proteins="YAL001C,YAL002W",
            name_mode="systematic",
            organism_id="559292",
            source="stringdb"
        )
        
        print(f"   ✓ Response type: {type(result)}")
        print(f"   ✓ Proteins count: {len(result.proteins)}")
        
        # Try to serialize to dict (this is what FastAPI does)
        result_dict = result.model_dump()
        print(f"   ✓ Serialization successful")
        print(f"   ✓ First protein: {result_dict['proteins'][0]['protein']}")
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*60)
    print("✓ All API endpoint tests passed!")
    print("="*60 + "\n")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_api_endpoint())
    sys.exit(0 if success else 1)
