from __future__ import annotations

from main import config
from main.enums import DataType
from main.models import DataTypeSettings


_SETTINGS: dict[DataType, DataTypeSettings] = {

    DataType.SYOGAI: DataTypeSettings(
        label="障害DB",
        section_name="障害DB",
        view_name="VwSyogai_11ALL",
        dxl_dir="1_target_dxl/Fm_Document_2/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_2/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_2/",
        title_field="Fd_Text_1",
    ),

    DataType.DATA_PATCH: DataTypeSettings(
        label="データ強制変更DB",
        section_name="データ強制変更DB",
        view_name="VwData_Patch_1_3ALL",
        dxl_dir="1_target_dxl/Fm_Document_3/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_3/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_3/",
        title_field="Fd_Text_1",
    ),

    DataType.HOSYU: DataTypeSettings(
        label="保守DB",
        section_name="保守DB",
        view_name="VwHosyu_1",
        dxl_dir="1_target_dxl/Fm_Document_5/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_5/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_5/",
        title_field="Fd_Text_1",
    ),
    
    DataType.CALL2024: DataTypeSettings(
        label="CallDB2024",
        section_name="CallDB2024",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/Call2024/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),
}

def get_data_type_settings() -> DataTypeSettings:
    key = config.DATA_TYPE
    return _SETTINGS[key]
