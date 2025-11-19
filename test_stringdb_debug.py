"""Debug STRING-DB API calls."""

import asyncio
import httpx


async def test_stringdb_api():
    """Test STRING-DB API directly."""
    print("\nTesting STRING-DB API directly...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test 1: get_string_ids
        print("\n1. Testing get_string_ids endpoint:")
        url = "https://string-db.org/api/json/get_string_ids"
        params = {
            "identifiers": "YAL001C",
            "species": "559292",
            "limit": 1,
        }
        
        try:
            response = await client.post(url, data=params)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Data: {data}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 2: Try with GET instead of POST
        print("\n2. Testing with GET method:")
        try:
            response = await client.get(url, params=params)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Data: {data}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 3: Try resolving endpoint
        print("\n3. Testing resolve endpoint:")
        url = "https://string-db.org/api/json/resolve"
        params = {
            "identifier": "YAL001C",
            "species": "559292",
        }
        
        try:
            response = await client.post(url, data=params)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Data: {data}")
        except Exception as e:
            print(f"   Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_stringdb_api())
