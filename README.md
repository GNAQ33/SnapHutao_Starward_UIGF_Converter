# SnapHutao_Starward_UIGF_Converter
转换 Snap Hutao 1.14+ 版本的 UIGF4.1 抽卡记录到 Starward Layla 及更新版本的严格 UIGF4 记录 / Convert Gasha JSON from Snap Hutao 1.12+ to Starward Layla+ rich-metadata JSON log.

----

使用方法：

- 从 release 中下载发行包，并解压至同一目录
- 运行脚本 `sh_to_starward.py`，首先选择下载的仓库的元数据标注 JSON `GIGacha_Metadata_xxxxxxxx.json`，然后选择 Snap Hutao 导出 JSON 和转换后的保存目录。
- 得到转换后的 Starward 导入 JSON

或者 

- 安装 Python 依赖库 `pydantic`, `tkinter`
- 下载仓库的元数据标注 JSON，运行脚本 `sh_to_starward.py`
- 同理选择对应的文件。
  
