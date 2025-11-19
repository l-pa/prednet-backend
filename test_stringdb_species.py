"""Test STRING-DB species format."""

import asyncio
import httpx


async def test_species_formats():
    """Test different species format options."""
    print("\nTesting STRING-DB species formats...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test different species identifiers for S. cerevisiae
        species_options = [
            "4932",  # NCBI taxonomy ID (different from 559292 which is a strain)
            "559292",  # Strain-specific
            "Saccharomyces cerevisiae",
            "saccharomyces_cerevisiae",
        ]
        
        for species in species_options:
            print(f"\nTrying species: {species}")
            url = "https://string-db.org/api/json/resolve"
            params = {
                "identifier": "YAL001C",
                "species": species,
            }
            
            try:
                response = await client.post(url, data=params)
                print(f"  Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"  ✓ SUCCESS!")
                    print(f"  Data: {data}")
                    return species
                else:
                    print(f"  ✗ Failed: {response.text[:200]}")
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        return None


if __name__ == "__main__":
    result = asyncio.run(test_species_formats())
    if result:
        print(f"\n✓ Working species identifier: {result}")
    else:
        print("\n✗ No working species identifier found")
