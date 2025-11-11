"""Test GO term parsing logic with mock data."""

from app.uniprot_client import UniProtClient

# Mock UniProt response with GO terms
mock_entry = {
    "sequence": {"length": 284},
    "features": [],
    "uniProtKBCrossReferences": [
        {
            "database": "GO",
            "id": "GO:0006936",
            "properties": [
                {"key": "GoTerm", "value": "P:muscle contraction"},
                {"key": "GoEvidenceType", "value": "IDA:SGD"}
            ]
        },
        {
            "database": "GO",
            "id": "GO:0005737",
            "properties": [
                {"key": "GoTerm", "value": "C:cytoplasm"},
                {"key": "GoEvidenceType", "value": "IDA:SGD"}
            ]
        },
        {
            "database": "GO",
            "id": "GO:0003779",
            "properties": [
                {"key": "GoTerm", "value": "F:actin binding"},
                {"key": "GoEvidenceType", "value": "IPI:SGD"}
            ]
        },
        {
            "database": "GO",
            "id": "GO:0003012",
            "properties": [
                {"key": "GoTerm", "value": "P:muscle system process"},
                {"key": "GoEvidenceType", "value": "IEA"}
            ]
        },
        {
            "database": "InterPro",
            "id": "IPR001715",
            "properties": []
        }
    ]
}

def test_go_parsing():
    """Test that GO terms are parsed correctly."""
    client = UniProtClient()
    result = client._parse_uniprot_response("TEST_PROTEIN", mock_entry)
    
    print("Testing GO term parsing...")
    print("-" * 50)
    print(f"Protein: {result.protein}")
    print(f"Sequence Length: {result.sequence_length}")
    print(f"Error: {result.error}")
    
    if result.go_terms:
        print("\nGO Terms parsed successfully!")
        print(f"\nBiological Process ({len(result.go_terms.biological_process)}):")
        for term in result.go_terms.biological_process:
            print(f"  - {term.id}: {term.name} [{term.evidence}]")
        
        print(f"\nCellular Component ({len(result.go_terms.cellular_component)}):")
        for term in result.go_terms.cellular_component:
            print(f"  - {term.id}: {term.name} [{term.evidence}]")
        
        print(f"\nMolecular Function ({len(result.go_terms.molecular_function)}):")
        for term in result.go_terms.molecular_function:
            print(f"  - {term.id}: {term.name} [{term.evidence}]")
        
        # Verify counts
        assert len(result.go_terms.biological_process) == 2, "Expected 2 BP terms"
        assert len(result.go_terms.cellular_component) == 1, "Expected 1 CC term"
        assert len(result.go_terms.molecular_function) == 1, "Expected 1 MF term"
        
        # Verify specific terms
        bp_ids = {t.id for t in result.go_terms.biological_process}
        assert "GO:0006936" in bp_ids, "Expected GO:0006936 in BP"
        assert "GO:0003012" in bp_ids, "Expected GO:0003012 in BP"
        
        cc_ids = {t.id for t in result.go_terms.cellular_component}
        assert "GO:0005737" in cc_ids, "Expected GO:0005737 in CC"
        
        mf_ids = {t.id for t in result.go_terms.molecular_function}
        assert "GO:0003779" in mf_ids, "Expected GO:0003779 in MF"
        
        # Verify evidence codes
        bp_term = next(t for t in result.go_terms.biological_process if t.id == "GO:0006936")
        assert bp_term.evidence == "IDA", "Expected IDA evidence"
        assert bp_term.name == "muscle contraction", "Expected correct term name"
        
        print("\n" + "-" * 50)
        print("✓ All assertions passed!")
    else:
        print("\n✗ ERROR: No GO terms parsed!")
        return False
    
    return True

# Test with empty GO terms
def test_no_go_terms():
    """Test that proteins without GO terms are handled gracefully."""
    mock_entry_no_go = {
        "sequence": {"length": 100},
        "features": [],
        "uniProtKBCrossReferences": []
    }
    
    client = UniProtClient()
    result = client._parse_uniprot_response("NO_GO_PROTEIN", mock_entry_no_go)
    
    print("\nTesting protein without GO terms...")
    print("-" * 50)
    print(f"Protein: {result.protein}")
    print(f"GO Terms: {result.go_terms}")
    
    assert result.go_terms is None, "Expected None for proteins without GO terms"
    print("✓ Correctly returns None for proteins without GO terms")
    
    return True

if __name__ == "__main__":
    success = test_go_parsing()
    success = test_no_go_terms() and success
    
    if success:
        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("✗ Some tests failed!")
        print("=" * 50)
        exit(1)
