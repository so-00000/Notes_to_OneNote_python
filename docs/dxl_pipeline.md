# DXL入力以降の処理パイプライン

## スコープ

このドキュメントは、Notes 側で DXL を出力した後の処理を対象とする。

- スコープ外: Notes から `ドキュメントデータ（dxl）` / `フォームデータ（dxl）` を出力する処理
- スコープ内: DXL を受け取り、テンプレート資材を生成し、文書 DXL を OneNote 投入用データへ変換する処理

## 全体像

```text
フォームデータ（dxl）
  -> フォームHTMLテンプレート生成
  -> fields.json 生成
  -> resources/templates, resources/forms に配置

ドキュメントデータ（dxl）
  -> fields.json を参照して必要フィールドを抽出
  -> フォームHTMLテンプレートへ値を埋め込み
  -> RichText を HTML / 添付セグメントへ変換
  -> PagePayload を生成
  -> 後段で OneNote 作成処理へ渡す
```

## 1. フォームデータ（dxl）をテンプレート資材へ変換

フォーム DXL は、文書 DXL を描画するための「型」を作る入力として使う。

### 入力

- `フォームデータ（dxl）`
- 必要に応じて参照される `subform` DXL

### 主処理

`scripts/generate_template_from_dxl_form.py`

このスクリプトはフォーム DXL の `body/richtext` を解析し、画面レイアウトに近い HTML テンプレートを生成する。
同時に、フォーム上で可視なフィールド一覧も JSON 化する。

### スクリプト内の処理

1. フォーム DXL を XML として読み込む
2. `FormToHtml` で `richtext` を走査する
3. `field` / `sharedfieldref` を `{{field_name}}` プレースホルダへ変換する
4. `table` / `section` / `subformref` などのレイアウト要素を HTML に変換する
5. `hide` / `hidewhen` を見て、非表示要素はテンプレート出力対象から外す
6. 可視フィールドを `visible_fields` として収集する
7. HTML テンプレートと `fields.json` を出力する

### 生成物

- `main/resources/templates/.../*.html`
  - フォームの見た目を表す HTML テンプレート
  - 文書 DXL の値を埋め込むための `{{field_name}}` を含む
- `main/resources/forms/.../*.fields.json`
  - 可視フィールド一覧
  - 各フィールドの `name`, `type`, `kind`, `allow_multivalues`, `shared` などを保持

### この生成物の役割

- HTML テンプレート: 文書 DXL の値をどこへ埋めるかを定義する
- `fields.json`: 文書 DXL からどのフィールドを拾うかを定義する

## 2. 対象データ種別ごとの設定を決定

データ種別ごとに、入力 DXL 配置先とテンプレート資材の参照先を切り替える。

### 主処理

`main/data_type_config.py`

ここでデータ種別ごとに以下を定義している。

- 文書 DXL の配置先
- HTML テンプレートの配置先
- `fields.json` の配置先
- ページタイトルに使うフィールド名
- 対応するビュー名

つまり、以降の処理は「どの DXL を読むか」と「どのフォーム資材を使うか」をこの設定で決める。

## 3. 文書データ（dxl）のバッチ入力

### 主処理

`main/main.py`

### 入力単位

- `main/data_type_config.py` で決まった `dxl_dir`
- 配下のセクションディレクトリごとの `*.dxl`

### 処理

1. 対象 DXL ディレクトリ配下を走査する
2. セクション単位で DXL ファイル一覧を作る
3. 1件ずつ `build_page_payload()` に渡す

この時点では、文書 DXL を「OneNote へ送る前の中間データ」に変換するのが目的になる。

## 4. 文書データ（dxl）1件から PagePayload を組み立てる

### 主処理

`main/services/page_payload_builder.py`

`build_page_payload(dxl_path, row_no=...)`

### 処理の流れ

1. 文書 DXL を XML として読み込む
2. DXL の `replicaid` と `noteinfo/unid` を取得する
3. 対応する `fields.json` を読む
4. `fields.json` から
   - 可視フィールド名一覧
   - RichText フィールド名一覧
   を取得する
5. 文書 DXL から通常フィールド値を抽出する
6. タイトル用フィールドからページタイトルを決定する
7. RichText と添付を含む本文を HTML 化する
8. 結果を `PagePayload` にまとめる

## 5. 文書 DXL から通常フィールド値を抽出

### 主処理

`main/services/dxl_to_ui_field_map.py`

### 役割

フォーム資材側の `fields.json` を基準に、「文書 DXL からどの item を読むか」を決める。

### 処理

- `visible_field_names` に含まれる項目だけを対象にする
- ただし RichText フィールドは別処理なのでここでは除外する
- `text`, `number`, `datetime` などを文字列へ正規化する
- 結果を `field_name -> value` の辞書にする

この辞書が、後でテンプレートへ埋め込まれる通常フィールド値になる。

## 6. RichText と添付を HTML / セグメントへ変換

### 主処理

`main/services/render_body_html_and_segments.py`

`render_body_html_and_segments(...)`

### 目的

文書 DXL の RichText を、テンプレートに埋め込める HTML と、本文外バイナリのセグメント情報に分解する。

### 前処理

- `_extract_attachments()` で `$FILE` 配下の添付ファイルを抽出する
- 添付ファイルは `filename -> binary` の辞書にする

### RichText フィールドごとの処理

各 RichText フィールドに対して `richtext_item_to_html_and_segment()` を実行する。

この関数では `item/richtext` を走査し、以下のように変換する。

- 通常段落 `par`
  - テキストを HTML に変換
  - `doclink` はプレースホルダ付きリンク HTML に変換
  - `urllink` は通常リンク HTML に変換
- `attachmentref`
  - 本文中にはアンカー `seg-xxx` を埋め込む
  - 実体は `Segment(kind="attachment")` として保持する
- `picture`
  - 本文中にはアンカー `seg-xxx` を埋め込む
  - 実体は `Segment(kind="image")` として保持する
- `table`
  - HTML の table に変換する

### 出力

- RichText フィールドごとの HTML
- 添付 / 画像の `Segment` 一覧
- Notes 文書リンク差し替え用の `DocLinkPlaceholder` 一覧

## 7. テンプレートへ値を埋め込んで本文 HTML を完成

### 主処理

`main/services/fill_template.py`

### 入力

- フォーム DXL 由来の HTML テンプレート
- 通常フィールド値の辞書
- RichText を HTML 化した辞書

### 処理

1. 通常フィールド値と RichText HTML をマージする
2. テンプレート中の `{{field_name}}` を対応値へ置換する
3. 通常フィールドは HTML エスケープして埋め込む
4. RichText フィールドは生 HTML のまま埋め込む
5. RichText 用プレースホルダが `span` に包まれている場合は、妥当な HTML になるよう `div` へ置き換える

### 結果

フォームレイアウトを保った本文 HTML が完成する。

## 8. oversized 添付の退避

### 主処理

`main/services/page_payload_builder.py`

`_export_oversize_segments(...)`

### 役割

Graph multipart 上限を超える添付は、そのままでは後段送信できないためローカルへ退避する。

### 処理

- サイズ上限を超える `Segment` を検出する
- ファイルを `result/oversize_attachments/...` へ書き出す
- 本文中の該当アンカーを「外部退避した」旨の案内 HTML に差し替える
- 上限超過セグメントは送信対象から外す

## 9. PagePayload を生成

### 主処理

`main/models/models.py`

### 生成されるデータ

`PagePayload` には主に以下が入る。

- `page_title`
- `body_html`
- `segment_list`
- `doc_replicaid`
- `doc_unid`
- `extracted_fields`
- `migration_master_map`
- `doclink_placeholders`

この `PagePayload` が、後段の OneNote 作成処理へ渡される最終的な入力データになる。

## 10. パイプラインをひとことで表すと

### フォーム DXL 側

フォーム DXL は、文書 DXL をどう見せるかを決める「テンプレート定義」と「抽出対象フィールド定義」に変換される。

### 文書 DXL 側

文書 DXL は、そのテンプレート定義に従って

- 通常項目は文字列値へ変換され
- RichText は HTML / 添付セグメントへ分解され
- 最終的に `PagePayload` にまとめられる

## 補足: 実コード上の責務分担

- `scripts/generate_template_from_dxl_form.py`
  - フォーム DXL からテンプレート資材を作る
- `main/data_type_config.py`
  - データ種別ごとの入力先 / 資材参照先を切り替える
- `main/main.py`
  - 文書 DXL のバッチ実行を制御する
- `main/services/page_payload_builder.py`
  - 文書 DXL 1件を `PagePayload` にまとめる
- `main/services/dxl_to_ui_field_map.py`
  - 通常フィールド値を抽出する
- `main/services/render_body_html_and_segments.py`
  - RichText, 画像, 添付, doclink を HTML / セグメントへ変換する
- `main/services/fill_template.py`
  - テンプレートへ値を埋め込む
- `main/services/extract_attachments.py`
  - `$FILE` から添付実体を取り出す

## 参考フロー図

```text
フォームデータ（dxl）
  -> generate_template_from_dxl_form.py
  -> form_template.html
  -> form_template.fields.json

文書データ（dxl）
  -> build_page_payload()
    -> fields.json 読み込み
    -> dxl_to_ui_field_map()
    -> render_body_html_and_segments()
      -> _extract_attachments()
      -> richtext_item_to_html_and_segment()
    -> fill_template()
    -> _export_oversize_segments()
  -> PagePayload
  -> 後段の OneNote 作成処理
```
