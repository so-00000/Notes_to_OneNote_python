from __future__ import annotations

from main import config
from main.enums import DataType
from main.models import DataTypeSettings


_SETTINGS: dict[DataType, DataTypeSettings] = {

    DataType.SYOGAI: DataTypeSettings(
        label="障害DB",
        view_name="VwSyogai_11ALL",
        dxl_dir="1_target_dxl/Fm_Document_2/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_2/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_2/",
        title_field="Fd_Text_1",
    ),

    DataType.DATA_PATCH: DataTypeSettings(
        label="データ強制変更DB",
        view_name="VwData_Patch_1_3ALL",
        dxl_dir="1_target_dxl/Fm_Document_3/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_3/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_3/",
        title_field="Fd_Text_1",
    ),

    DataType.HOSYU: DataTypeSettings(
        label="保守DB",
        view_name="VwHosyu_1",
        dxl_dir="1_target_dxl/Fm_Document_5/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_5/",
        fields_json_path="resources/forms/synhbe29.nsf/Fm_Document_5/",
        title_field="Fd_Text_1",
    ),
    


    # UserCallは同じView・項目・テンプレートを使用
    
    DataType.CALL2024: DataTypeSettings(
        label="UserCall2024",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/UserCall2024/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),

    DataType.CALL2023: DataTypeSettings(
        label="UserCall2023",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/UserCall2023/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),

    DataType.CALL2022: DataTypeSettings(
        label="UserCall2022",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/UserCall2022/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),
    
    DataType.CALL2021: DataTypeSettings(
        label="UserCall2021",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/UserCall2021/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),

        DataType.CALL2020: DataTypeSettings(
        label="UserCall2020",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/UserCall2020/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),
}

def get_data_type_settings() -> DataTypeSettings:
    key = config.DATA_TYPE
    return _SETTINGS[key]
