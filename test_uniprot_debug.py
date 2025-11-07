"""Debug script to test UniProt API directly."""

import asyncio
import httpx


async def test_uniprot_direct():
    """Test UniProt API directly with httpx."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = "https://rest.uniprot.org/uniprotkb/search"
        
        # Test query 1: gene name
        params1 = {
            "query": "gene:YPL273W AND organism_id:559292",
            "format": "json",
            "fields": "length,ft_domain",
            "size": "1",
        }
        
        print("Testing query 1: gene:YPL273W AND organism_id:559292")
        resp1 = await client.get(url, params=params1)
        print(f"Status: {resp1.status_code}")
        print(f"Response: {resp1.json()}")
        print()
        
        # Test query 2: accession
        params2 = {
            "query": "accession:YPL273W",
            "format": "json",
            "fields": "length,ft_domain",
            "size": "1",
        }
        
        print("Testing query 2: accession:YPL273W")
        resp2 = await client.get(url, params=params2)
        print(f"Status: {resp2.status_code}")
        print(f"Response: {resp2.json()}")
        print()
        
        # Test query 3: plain search
        params3 = {
            "query": "YPL273W AND organism_id:559292",
            "format": "json",
            "fields": "length,ft_domain",
            "size": "1",
        }
        
        print("Testing query 3: YPL273W AND organism_id:559292")
        resp3 = await client.get(url, params=params3)
        print(f"Status: {resp3.status_code}")
        print(f"Response: {resp3.json()}")


if __name__ == "__main__":
    asyncio.run(test_uniprot_direct())
