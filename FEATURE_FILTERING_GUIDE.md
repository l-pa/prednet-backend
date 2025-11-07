# Protein Feature Filtering Guide

## Overview

The protein comparison feature now filters UniProt features to show only the most meaningful and relevant feature types. This reduces visual clutter and focuses on the most important structural and functional information.

## Included Feature Types

### 1. Domain ✅ (PRIMARY - Most Important)
- **What it is**: Functional protein domains (e.g., kinase domain, DNA-binding domain)
- **Why included**: Domains are the most important functional units of proteins
- **Example**: "Protein kinase domain", "Zinc finger C2H2-type"
- **Color**: Blue (#4299e1)

### 2. Repeat ✅
- **What it is**: Repeated sequence patterns within the protein
- **Why included**: Repeats often have structural or functional significance
- **Example**: "ANK repeat", "WD repeat", "Leucine-rich repeat"
- **Color**: Orange (#ed8936)

### 3. Region ✅ (Meaningful Ones Only)
- **What it is**: Regions of interest with specific functions or properties
- **Why included**: Provides context about functional areas
- **Example**: "Disordered region", "Interaction region", "Catalytic region"
- **Color**: Green (#48bb78)

### 4. Transit peptide ✅
- **What it is**: Targeting sequences that direct proteins to specific cellular locations
- **Why included**: Important for understanding protein localization
- **Example**: "Mitochondrial transit peptide", "Chloroplast transit peptide"
- **Color**: Dark green (#2f855a)

### 5. Chain ✅ (Optional)
- **What it is**: The mature protein chain after processing
- **Why included**: Shows the processed, functional form of the protein
- **Example**: "Mature protein chain"
- **Color**: Darkest green (#22543d)

## Excluded Feature Types

The following feature types are **NOT** shown to reduce clutter:

### Excluded - Too Detailed
- **Motif**: Short sequence patterns (often too numerous)
- **Site**: Individual amino acid sites (too granular)
- **Active site**: Specific catalytic residues (too specific)
- **Binding site**: Individual binding positions (too numerous)
- **Modified residue**: Post-translational modifications (too many)

### Excluded - Structural Details
- **Helix**: Alpha helices (too detailed for overview)
- **Beta strand**: Beta sheets (too detailed)
- **Turn**: Structural turns (too detailed)
- **Transmembrane**: Membrane-spanning regions (specialized use case)

### Excluded - Variations
- **Sequence variant**: Natural variations (not structural)
- **Mutagenesis**: Experimental mutations (not natural)
- **Sequence conflict**: Database conflicts (not relevant)

### Excluded - Processing Details
- **Signal peptide**: Already removed in mature protein
- **Propeptide**: Removed during processing
- **Peptide**: Small peptide fragments

## Implementation

### Backend Filtering
Location: `backend/app/uniprot_client.py`

```python
ALLOWED_FEATURE_TYPES = {
    "Domain",
    "Repeat",
    "Region",
    "Transit peptide",
    "Chain",
}
```

The filtering happens in the `_parse_uniprot_response` method:
1. UniProt returns all available features
2. Backend filters to only allowed types
3. Frontend receives only the filtered features
4. Legend automatically shows only present feature types

### Frontend Display
Location: `frontend/src/components/Networks/Cytoscape/FeatureLegend.tsx`

The legend dynamically shows only the feature types present in the current comparison:
- If no proteins have "Chain" features, it won't appear in the legend
- Colors are consistent across all visualizations
- Feature types are sorted alphabetically

## Benefits of Filtering

1. **Reduced Visual Clutter**: Fewer overlapping features make the visualization clearer
2. **Focus on Function**: Shows the most functionally relevant information
3. **Better Performance**: Less data to render and process
4. **Easier Interpretation**: Users can quickly identify key structural elements
5. **Consistent Experience**: Same feature types across all proteins

## Customization

To modify which features are shown, edit the `ALLOWED_FEATURE_TYPES` set in `backend/app/uniprot_client.py`:

```python
# Add a new feature type
ALLOWED_FEATURE_TYPES = {
    "Domain",
    "Repeat",
    "Region",
    "Transit peptide",
    "Chain",
    "Motif",  # Add this to include motifs
}

# Remove a feature type
ALLOWED_FEATURE_TYPES = {
    "Domain",
    "Repeat",
    "Region",
    # "Transit peptide",  # Comment out to exclude
    "Chain",
}
```

After modifying, restart the backend server for changes to take effect.

## Feature Type Reference

### UniProt Feature Type Names (Exact Match Required)
The filtering uses exact string matching with UniProt's feature type names:

- ✅ `"Domain"` - Correct
- ❌ `"domain"` - Wrong (case-sensitive)
- ❌ `"Domains"` - Wrong (plural)

Common UniProt feature types:
- `"Domain"`
- `"Repeat"`
- `"Region"`
- `"Transit peptide"` (note the space)
- `"Chain"`
- `"Signal peptide"`
- `"Motif"`
- `"Binding site"`
- `"Active site"`
- `"Transmembrane"`
- `"Helix"`
- `"Beta strand"`
- `"Modified residue"`

## Testing

To verify the filtering is working:

1. **Check backend logs**: Look for feature counts in the logs
2. **Test with known proteins**: 
   - YPL273W should show Domain features
   - YBR160W should show Domain features
3. **Verify legend**: Only filtered types should appear in the legend
4. **Compare with UniProt**: Check the UniProt website to see all features vs. filtered ones

## Cache Behavior

- Filtered features are cached for 24 hours
- If you change the filter, you need to:
  1. Restart the backend server
  2. Wait for cache to expire (24 hours) OR
  3. Clear the cache by restarting the server

## Performance Impact

Filtering features has minimal performance impact:
- **Backend**: Negligible (simple set membership check)
- **Frontend**: Improved (fewer features to render)
- **Network**: Reduced (smaller JSON payloads)
- **Cache**: More efficient (smaller cached objects)

## Future Enhancements

Possible improvements:
1. Make feature filtering configurable via API parameter
2. Add user preferences for feature types
3. Implement feature type grouping (e.g., "Structural", "Functional")
4. Add tooltips explaining each feature type
5. Allow toggling feature types in the UI
