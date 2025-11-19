import httpx
import asyncio
import json

async def test_quickgo():
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = "https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0006936/ancestors"
        response = await client.get(url)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(json.dumps(data, indent=2))
        
        if "results" in data and data["results"]:
            result = data["results"][0]
            ancestors = result.get("ancestors", [])
            print(f"\nAncestors: {ancestors}")

if __name__ == "__main__":
    asyncio.run(test_quickgo())
