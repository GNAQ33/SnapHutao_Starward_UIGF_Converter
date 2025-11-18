import json
import sys
import pandas as pd
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog

# Starward 单条抽卡记录（文件中 hk4e[].list 的项）
class StarwardRecord(BaseModel):
    uigf_gacha_type: Optional[str] = None
    uid: Optional[str] = None
    id: Optional[str] = None
    gacha_type: Optional[str] = None
    name: Optional[str] = None
    item_type: Optional[str] = None
    rank_type: Optional[str] = None
    time: Optional[str] = None
    item_id: Optional[str] = None
    count: Optional[str] = None
    lang: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

# Starward 用户级别容器（hk4e 列表项）
class StarwardUserBundle(BaseModel):
    uid: str
    timezone: Optional[int] = None
    lang: Optional[str] = None
    list: List[StarwardRecord] = Field(default_factory=list)

# Starward UIGF 顶层结构
class StarwardUIGF(BaseModel):
    info: Dict[str, Any]
    hk4e: List[StarwardUserBundle] = Field(default_factory=list)
    hkrpg: Optional[List[Any]] = None
    nap: Optional[List[Any]] = None

# Snap Hutao 单条记录（其 hk4e[].list 的项，字段通常较少）
class SnapHutaoRecord(BaseModel):
    uigf_gacha_type: Optional[str] = None
    gacha_type: Optional[str] = None
    item_id: Optional[str] = None
    time: Optional[str] = None
    id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    class Config:
        extra = "allow"

# Snap Hutao 用户级别容器与顶层
class SnapHutaoUserBundle(BaseModel):
    uid: str
    timezone: Optional[int] = None
    list: List[SnapHutaoRecord] = Field(default_factory=list)

class SnapHutaoUIGF(BaseModel):
    info: Dict[str, Any]
    hk4e: List[SnapHutaoUserBundle] = Field(default_factory=list)

# Starward 元数据数据库项（用于 output_starward_db 的结构）
class StarwardMetaItem(BaseModel):
    name: str
    item_type: Optional[str] = None
    rank_type: Optional[str] = None
    item_id: str

# Starward 元数据数据库容器（通过 item_id 映射到元数据）
class StarwardMetaDB(BaseModel):
    by_id: Dict[str, StarwardMetaItem] = Field(default_factory=dict)

    def get(self, item_id: str) -> Optional[StarwardMetaItem]:
        return self.by_id.get(item_id)

def output_starward_db(sw_metas: StarwardMetaDB, outfile: str):
    # 使用 model_dump 输出结构化 JSON
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(sw_metas.model_dump(), f, ensure_ascii=False, indent=2)

def read_starward_meta_db(filename: str) -> StarwardMetaDB:
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    db = StarwardMetaDB()
    by_id = data.get("by_id", {})
    for iid, meta in by_id.items():
        db.by_id[str(iid)] = StarwardMetaItem(**meta)
    return db

def read_starward_uigf4(filename: str) -> StarwardUIGF:
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        # 使用 model_validate 接受 dict
        uigf = StarwardUIGF.model_validate(data)
    except Exception as e:
        raise RuntimeError(f"Starward UIGF 验证失败: {e}") from e
    return uigf

def read_snap_hutao_uigf4(filename: str) -> SnapHutaoUIGF:
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        uigf = SnapHutaoUIGF.model_validate(data)
    except Exception as e:
        raise RuntimeError(f"Snap Hutao UIGF 验证失败: {e}") from e
    return uigf

def convert_snap_hutao_to_starward(snap_uigf: SnapHutaoUIGF, sw_meta_db: StarwardMetaDB) -> StarwardUIGF:
    export_info = snap_uigf.info.copy()
    export_info["export_app"] = "Converted from Snap Hutao"
    out = StarwardUIGF(info=export_info, hk4e=[], hkrpg=[], nap=[])
    for user in snap_uigf.hk4e:
        # 默认用户层 lang 为 zh-cn
        bundle = StarwardUserBundle(uid=user.uid, timezone=user.timezone, lang="zh-cn", list=[])
        for srec in user.list:
            iid = str(srec.item_id) if srec.item_id is not None else None
            meta = sw_meta_db.get(iid) if iid is not None else None
            if meta is None or meta.item_type is None or meta.rank_type is None:
                raise RuntimeError(f"无法在元数据数据库中找到 item_id={iid} 的条目，转换失败。请先补全元数据后重试。")
            # 默认 count=1/lang=zh-cn；仅当 extra 非空时才加入
            rec_kwargs = dict(
                uigf_gacha_type=srec.uigf_gacha_type,
                gacha_type=srec.gacha_type,
                item_id=srec.item_id,
                time=srec.time,
                id=srec.id,
                uid=user.uid,
                name=meta.name,
                item_type=meta.item_type,
                rank_type=meta.rank_type,
                count="1",
                lang="zh-cn",
            )
            if getattr(srec, "extra", None):
                if isinstance(srec.extra, dict) and len(srec.extra) > 0:
                    rec_kwargs["extra"] = srec.extra
            rec = StarwardRecord(**rec_kwargs)
            bundle.list.append(rec)
        out.hk4e.append(bundle)
    return out

def convert_snap_file_with_meta(meta_db_file: str, snap_file: str, out_starward_file: str):
    db = read_starward_meta_db(meta_db_file)
    snap = read_snap_hutao_uigf4(snap_file)
    starward_uigf = convert_snap_hutao_to_starward(snap, db)
    with open(out_starward_file, "w", encoding="utf-8") as f:
        # exclude_defaults=True 可省略默认 {} 的 extra；exclude_none=True 省略 None 字段
        json.dump(starward_uigf.model_dump(exclude_none=True, exclude_defaults=True), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    try:
        meta_db_file = filedialog.askopenfilename(
            title="选择 Starward Meta DB JSON（输入）",
            filetypes=[("JSON 文件", "*.json")]
        )
        if not meta_db_file:
            messagebox.showinfo("已取消", "未选择 Meta DB 文件。")
            sys.exit(0)

        snap_file = filedialog.askopenfilename(
            title="选择 Snap Hutao UIGF JSON（输入）",
            filetypes=[("JSON 文件", "*.json")]
        )
        if not snap_file:
            messagebox.showinfo("已取消", "未选择 Snap Hutao 文件。")
            sys.exit(0)
        
        out_dir = filedialog.askdirectory(
            title="选择 Starward UIGF 输出文件夹"
        )
        if not out_dir:
            messagebox.showinfo("已取消", "未选择输出文件夹。")
            sys.exit(0)

        import os
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_starward_file = os.path.join(out_dir, f"Starward_UIGF_{ts}.json")

        convert_snap_file_with_meta(meta_db_file, snap_file, out_starward_file)
        messagebox.showinfo("完成", f"已生成 Starward 数据：\n{out_starward_file}")
    finally:
        try:
            root.destroy()
        except Exception:
            pass

