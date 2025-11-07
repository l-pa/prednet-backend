# UniProt API Client and Protein Features Endpoint Implementation

## Overview

This implementation adds a UniProt API client and a new REST endpoint to fetch protein sequence features for the protein sequence comparison feature.

## Files Created

### 1. `backend/app/uniprot_client.py`

A complete async HTTP client for the UniProt REST API with the following features:

#### Key Components:

- **Pydantic Models**:
  - `ProteinFeature`: Represents a single sequence feature (domain, region, motif, etc.)
  - `ProteinFeatureData`: Contains protein data with sequence length, features, and error handling
  - `ProteinFeaturesResponse`: Response wrapper for multiple proteins

- **UniProtCache**: In-memory cache with 24-hour TTL
  - Stores fetched protein data to minimize API calls
  - Automatic expiration of stale data
  - Thread-safe implementation

- **UniProtClient**: Async HTTP client for UniProt API
  - Fetches protein sequence length and feature annotations
  - Implements retry logic with exponential backoff
  - Handles rate limiting (HTTP 429)
  - Tries multiple query strategies (gene name, accession, general search)
  - Timeout protection (10 seconds per request)
  - Comprehensive error handling

- **fetch_multiple_proteins()**: Parallel fetching function
  - Fetches multiple proteins concurrently using asyncio.gather()
  - Handles partial failures gracefully
  - Returns results for all proteins (with errors for failed ones)

#### Features Extracted:
- Sequence length
- Domains (ft_domain)
- Regions (ft_region)
- Motifs (ft_motif)
- Repeats (ft_repeat)
- Sites (ft_site)

### 2. `backend/app/api/routes/proteins.py` (Modified)

Added new endpoint: `GET /api/v1/proteins/{network_name}/features`

#### Endpoint Details:

**Path**: `/api/v1/proteins/{network_name}/features`

**Method**: GET

**Query Parameters**:
- `proteins` (required): Comma-separated list of protein identifiers
- `name_mode` (optional): "systematic" or "gene" (default: "systematic")
- `organism_id` (optional): NCBI taxonomy ID (default: "559292" for S. cerevisiae)

**Response Format**:
```json
{
  "proteins": [
    {
      "protein": "YAL001C",
      "sequence_length": 284,
      "features": [
        {
          "type": "Domain",
          "description": "Tropomyosin",
          "start": 1,
          "end": 284
        }
      ],
      "error": null
    }
  ]
}
```

**Error Handling**:
- Returns 400 for empty protein list
- Returns 400 for more than 50 proteins per request
- Returns 500 for unexpected errors
- Handles partial failures (returns data for successful proteins, errors for failed ones)
- Network validation is optional (endpoint works even if network doesn't exist)

### 3. Test Files

#### `backend/tests/test_uniprot_client.py`
Unit tests for the UniProt client:
- Cache functionality tests
- Protein fetching tests
- Parallel fetching tests
- Error handling tests

#### `backend/tests/api/routes/test_proteins_features.py`
Integration tests for the API endpoint:
- Invalid network handling
- Empty protein list validation
- Too many proteins validation
- Single protein fetching
- Multiple protein fetching
- Name mode parameter testing

#### `backend/test_uniprot_manual.py`
Manual test script for quick verification:
- Tests fetching real protein data
- Displays results in readable format
- Can be run with: `uv run python test_uniprot_manual.py`

## Implementation Details

### Rate Limiting Strategy
- Implements exponential backoff on rate limit errors (HTTP 429)
- Waits 2^attempt seconds before retry
- Maximum 2 retries per query strategy
- Tries 3 different query strategies per protein

### Caching Strategy
- In-memory cache with 24-hour TTL
- Cache key: protein identifier
- Reduces load on UniProt API
- Improves response time for repeated requests
- Production deployment should consider Redis for distributed caching

### Error Handling
- Graceful degradation: partial failures don't block successful results
- Detailed error messages for debugging
- Timeout protection prevents hanging requests
- Handles UniProt API unavailability
- Handles malformed responses

### Performance Optimizations
- Parallel fetching using asyncio.gather()
- Connection pooling via httpx.AsyncClient
- Request timeout: 10 seconds
- Maximum 50 proteins per request to prevent abuse

## Usage Examples

### Fetch features for single protein:
```bash
GET /api/v1/proteins/BioGRIDCC24Y/features?proteins=YAL001C
```

### Fetch features for multiple proteins:
```bash
GET /api/v1/proteins/BioGRIDCC24Y/features?proteins=YAL001C,YAL002W,TPM1
```

### Use gene names instead of systematic names:
```bash
GET /api/v1/proteins/BioGRIDCC24Y/features?proteins=TPM1,MYO1&name_mode=gene
```

### Specify different organism:
```bash
GET /api/v1/proteins/BioGRIDCC24Y/features?proteins=P12345&organism_id=9606
```

## Dependencies

All required dependencies are already in `pyproject.toml`:
- `httpx`: Async HTTP client
- `pydantic`: Data validation and serialization
- `fastapi`: Web framework

No additional dependencies needed!

## Testing

Run the tests:
```bash
# Unit tests
uv run pytest tests/test_uniprot_client.py -v

# Integration tests
uv run pytest tests/api/routes/test_proteins_features.py -v

# All tests
uv run pytest -v

# Manual test
uv run python test_uniprot_manual.py
```

## Next Steps

This backend implementation is complete and ready for frontend integration. The next task is to:

1. Regenerate the frontend API client to include the new endpoint
2. Create the frontend components for the protein comparison modal
3. Implement the visualization components

## Notes

- The endpoint works independently of network validation (can fetch UniProt data even if network doesn't exist)
- Cache is in-memory and will reset on server restart
- For production, consider using Redis for distributed caching
- UniProt API has no official rate limit, but we implement conservative rate limiting
- The implementation follows FastAPI best practices and matches the existing codebase style
