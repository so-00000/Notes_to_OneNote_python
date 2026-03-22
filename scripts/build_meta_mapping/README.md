# build_meta_mapping

Generate metadata mapping JSON files from view definition CSVs.
This tool does not create or update migration_master.csv.

## Input
- `source_view/<ViewFolder>/*.csv`

## Output
- `../../main/resources/mapping/<ViewFolder>/mapping.json`
- `../../main/resources/mapping/cmn_mapping.json`

## Usage
```powershell
python .\build_meta_mapping_pipeline.py
```

Optional commands:
```powershell
python .\build_meta_mapping_pipeline.py list-views
python .\build_meta_mapping_pipeline.py --view VwHosyu_1
python .\build_meta_mapping_pipeline.py generate-mapping --view VwHosyu_1
```
