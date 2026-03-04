# create_view_mapper_and_csv

Viewフォルダ単位で以下を生成するCLIです。

1. `mapping.json`（Viewごとの抽出仕様）
2. `migration_master.csv`（成果CSV/正本）
3. `migration_master.xlsx`（Excel出力）

## ディレクトリ構成

- 入力: `source_view/<Viewフォルダ>/*.csv`
- 出力（View別）: `../../main/resources/mapping/<Viewフォルダ>/mapping.json`
- 出力（View別）: `../../main/resources/mapping/<Viewフォルダ>/migration_master.csv`
- 出力（View別）: `../../main/resources/mapping/<Viewフォルダ>/migration_master.xlsx`
- 共通出力: `../../main/resources/mapping/cmn_mapping.json`

## 実行

```powershell
python .\build_view_mapping_pipeline.py build
```

`--view` 未指定時は、`source_view` 配下のフォルダ一覧が表示され、番号選択できます。

## Viewを直接指定して実行

```powershell
python .\build_view_mapping_pipeline.py build --view VwHosyu_1
```

## 個別実行

```powershell
python .\build_view_mapping_pipeline.py generate-mapping --view VwHosyu_1
python .\build_view_mapping_pipeline.py sync-master-csv --view VwHosyu_1
python .\build_view_mapping_pipeline.py export-excel --view VwHosyu_1
```

## View一覧表示

```powershell
python .\build_view_mapping_pipeline.py list-views
```

## 備考

- `common_columns` は要件の共通項目（`source_id`, `replica_id`, `unid`, ...）を固定で出力します。
- View定義CSVの列追加・順序変更は、`generate-mapping` 再実行で追従できます。
- Excel出力には `openpyxl` が必要です。未導入の場合は `pip install openpyxl` を実行してください。
