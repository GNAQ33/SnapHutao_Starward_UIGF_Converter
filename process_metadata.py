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
    
    def add_from_record(self, rec: StarwardRecord):
        # 如果没有 item_id 就跳过
        if not rec.item_id:
            return
        iid = str(rec.item_id)
        # 若不存在则创建新条目
        if iid not in self.by_id:
            self.by_id[iid] = StarwardMetaItem(
                name=rec.name or "",
                item_type=rec.item_type,
                rank_type=rec.rank_type,
                item_id=iid,
            )
        else:
            # 已存在：用记录中非空字段补全已有条目
            meta = self.by_id[iid]
            if (not meta.name or meta.name == "") and rec.name:
                meta.name = rec.name
            if (not meta.item_type) and rec.item_type:
                meta.item_type = rec.item_type
            if (not meta.rank_type) and rec.rank_type:
                meta.rank_type = rec.rank_type

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

def UIGF_id_name_mapping(filename):
    # 读取 mapping 文件，支持 { name: [ids...] } 或 { name: id } 两种格式
    # url: https://api.uigf.org/dict/genshin/chs.json
    with open(filename, "r", encoding="utf-8") as f:
        name_to_id = json.load(f)
    id_to_name: Dict[str, str] = {}
    for name, ids in name_to_id.items():
        if isinstance(ids, (list, tuple, set)):
            for iid in ids:
                id_to_name[str(iid)] = name
        else:
            id_to_name[str(ids)] = name
    return id_to_name, name_to_id

def build_meta_db_from_mapping(mapping_file: str) -> StarwardMetaDB:
    id_to_name, _ = UIGF_id_name_mapping(mapping_file)
    db = StarwardMetaDB()
    for iid, name in id_to_name.items():
        db.by_id[str(iid)] = StarwardMetaItem(name=name, item_id=str(iid))
    return db

def prompt_missing_meta_fields(sw_meta_db: StarwardMetaDB):
    # Windows 10 优先使用稳定的单窗口向导；仅当 tkinter 不可用时回退 CLI
    ITEM_TYPES = ["武器", "角色"]
    RANK_CHOICES = ["1", "2", "3", "4", "5"]

    # 收集待处理条目（存在 name 与 item_id，且缺少 item_type 或 rank_type）
    pending = []
    try:
        def _key(kv):
            k = kv[0]
            return (0, int(k)) if str(k).isdigit() else (1, str(k))
        items = sorted(sw_meta_db.by_id.items(), key=_key)
    except Exception:
        items = list(sw_meta_db.by_id.items())

    for iid, meta in items:
        if not meta or not getattr(meta, "item_id", None) or not getattr(meta, "name", None):
            continue
        if (not meta.item_type) or (not meta.rank_type):
            pending.append((iid, meta))

    if not pending:
        return

    # 开启 Windows DPI 感知，减少缩放导致的遮挡
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        pass


    if tk is not None:
        class MetaFillWizard(tk.Tk):
            def __init__(self, items):
                super().__init__()
                self.title("补全 Starward 元数据")
                # 允许拉伸，设置最小尺寸
                self.resizable(True, True)
                self.minsize(520, 260)

                try:
                    self.attributes("-topmost", True)
                    self.after(300, lambda: self.attributes("-topmost", False))
                except Exception:
                    pass

                self.items = items
                self.index = 0

                # 顶层网格使容器可伸缩
                self.rowconfigure(0, weight=1)
                self.columnconfigure(0, weight=1)

                # 容器：自适应布局
                container = ttk.Frame(self, padding=12)
                container.grid(row=0, column=0, sticky="nsew")
                container.columnconfigure(0, weight=0)  # 标签列
                container.columnconfigure(1, weight=1)  # 内容列可伸缩

                # 顶部信息
                self.lbl_title = ttk.Label(container, text="", font=("Segoe UI", 10, "bold"))
                self.lbl_title.grid(row=0, column=0, columnspan=2, padx=0, pady=(0, 8), sticky="w")

                # name/id 行
                self.var_name = tk.StringVar(value="")
                self.var_id = tk.StringVar(value="")
                ttk.Label(container, text="名称:").grid(row=1, column=0, padx=(0, 8), pady=4, sticky="e")
                self.ent_name = ttk.Entry(container, textvariable=self.var_name, state="readonly")
                self.ent_name.grid(row=1, column=1, padx=0, pady=4, sticky="ew")
                ttk.Label(container, text="ID:").grid(row=2, column=0, padx=(0, 8), pady=4, sticky="e")
                self.ent_id = ttk.Entry(container, textvariable=self.var_id, state="readonly")
                self.ent_id.grid(row=2, column=1, padx=0, pady=4, sticky="ew")

                # item_type 下拉
                self.var_type = tk.StringVar(value=ITEM_TYPES[0])
                ttk.Label(container, text="物品类型:").grid(row=3, column=0, padx=(0, 8), pady=4, sticky="e")
                self.cmb_type = ttk.Combobox(container, textvariable=self.var_type, values=ITEM_TYPES, state="readonly")
                self.cmb_type.grid(row=3, column=1, padx=0, pady=4, sticky="ew")

                # rank_type 下拉
                self.var_rank = tk.StringVar(value=RANK_CHOICES[-1])
                ttk.Label(container, text="稀有度(rank_type):").grid(row=4, column=0, padx=(0, 8), pady=4, sticky="e")
                self.cmb_rank = ttk.Combobox(container, textvariable=self.var_rank, values=RANK_CHOICES, state="readonly")
                self.cmb_rank.grid(row=4, column=1, padx=0, pady=4, sticky="ew")

                # 占位让内容列更平衡（可选）
                container.rowconfigure(4, weight=1)

                # 按钮行
                btns = ttk.Frame(container)
                btns.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="ew")
                btns.columnconfigure(0, weight=1)  # 按钮区右对齐
                btn_bar = ttk.Frame(btns)
                btn_bar.grid(row=0, column=1, sticky="e")

                self.btn_prev = ttk.Button(btn_bar, text="上一个", command=self.on_prev)
                self.btn_prev.grid(row=0, column=0, padx=4)
                self.btn_skip = ttk.Button(btn_bar, text="跳过", command=self.on_skip)
                self.btn_skip.grid(row=0, column=1, padx=4)
                self.btn_save_next = ttk.Button(btn_bar, text="保存并下一个", command=self.on_save_next)
                self.btn_save_next.grid(row=0, column=2, padx=4)
                self.btn_finish = ttk.Button(btn_bar, text="完成", command=self.on_finish)
                self.btn_finish.grid(row=0, column=3, padx=4)
                self.btn_cancel = ttk.Button(btn_bar, text="取消", command=self.on_cancel)
                self.btn_cancel.grid(row=0, column=4, padx=4)

                self.protocol("WM_DELETE_WINDOW", self.on_cancel)
                self.bind("<Escape>", lambda e: self.on_cancel())
                self.after(0, self.load_current)

                self.center()

            def center(self):
                # 根据请求尺寸计算居中，不强制固定大小
                self.update_idletasks()
                req_w = max(self.winfo_reqwidth(), 520)
                req_h = max(self.winfo_reqheight(), 260)
                try:
                    sw = self.winfo_screenwidth()
                    sh = self.winfo_screenheight()
                    x = int((sw - req_w) / 2)
                    y = int((sh - req_h) / 3)
                except Exception:
                    x, y = 200, 150
                self.geometry(f"{req_w}x{req_h}+{x}+{y}")

            def load_current(self):
                iid, meta = self.items[self.index]
                self.lbl_title.config(text=f"待处理 {self.index+1}/{len(self.items)}")
                self.var_name.set(meta.name or "")
                self.var_id.set(str(iid))

                # 已有值用已有，否则默认
                self.var_type.set(meta.item_type if meta.item_type in ITEM_TYPES else ITEM_TYPES[0])
                self.var_rank.set(meta.rank_type if meta.rank_type in RANK_CHOICES else RANK_CHOICES[-1])

                # 导航按钮可用性
                self.btn_prev.configure(state=("normal" if self.index > 0 else "disabled"))

            def save_current(self):
                iid, meta = self.items[self.index]
                if not meta.item_type:
                    meta.item_type = self.var_type.get()
                if not meta.rank_type:
                    meta.rank_type = self.var_rank.get()

            def on_prev(self):
                if self.index > 0:
                    self.index -= 1
                    self.load_current()

            def on_skip(self):
                if self.index < len(self.items) - 1:
                    self.index += 1
                    self.load_current()
                else:
                    messagebox.showinfo("提示", "已到最后一项。")

            def on_save_next(self):
                self.save_current()
                if self.index < len(self.items) - 1:
                    self.index += 1
                    self.load_current()
                else:
                    self.on_finish()

            def on_finish(self):
                self.destroy()

            def on_cancel(self):
                if messagebox.askyesno("确认取消", "确定要取消并关闭吗？已填写内容将保留，未填写的保持缺省。"):
                    self.destroy()

        app = MetaFillWizard(pending)
        app.mainloop()
        return

    # CLI 回退（tkinter 不可用时）
    print("\nGUI 不可用，进入命令行模式：")
    for iid, meta in pending:
        print(f"\nitem_id={iid}  name={meta.name}")
        if not meta.item_type:
            while True:
                print("请选择物品类型： 1. 武器  2. 角色")
                v = input("输入编号(回车跳过)：").strip()
                if v == "":
                    break
                if v == "1":
                    meta.item_type = "武器"; break
                if v == "2":
                    meta.item_type = "角色"; break
                print("无效输入，请重试。")
        if not meta.rank_type:
            while True:
                print("请选择稀有度(rank_type)： 1/2/3/4/5")
                v = input("输入数值(回车跳过)：").strip()
                if v == "":
                    break
                if v in RANK_CHOICES:
                    meta.rank_type = v; break
                print("无效输入，请重试。")


def build_meta_db_from_uigf(uigf: StarwardUIGF) -> StarwardMetaDB:
    db = StarwardMetaDB()
    for user in uigf.hk4e:
        for rec in user.list:
            db.add_from_record(rec)
    return db

def merge_meta_db(into: "StarwardMetaDB", src: "StarwardMetaDB"):
    # 仅在 into 缺失时，用 src 的非空值进行补全
    for iid, s in src.by_id.items():
        if iid not in into.by_id:
            into.by_id[iid] = StarwardMetaItem(
                name=s.name or "",
                item_type=s.item_type,
                rank_type=s.rank_type,
                item_id=str(iid),
            )
            continue
        t = into.by_id[iid]
        if (not t.name or t.name == "") and s.name:
            t.name = s.name
        if (not t.item_type) and s.item_type:
            t.item_type = s.item_type
        if (not t.rank_type) and s.rank_type:
            t.rank_type = s.rank_type

def merge_mapping_and_starward(mapping_file: str, starward_file: str, meta_file: str):
    # 0) 读取已有 meta（允许不完整/不存在）
    try:
        base_db = read_starward_meta_db(meta_file)
    except Exception:
        base_db = StarwardMetaDB()

    # 1) 用 mapping 补齐所有 name/item_id（不覆盖已有有效值）
    mapping_db = build_meta_db_from_mapping(mapping_file)
    merge_meta_db(base_db, mapping_db)

    # 2) 用 starward 记录补全（add_from_record 仅补缺）
    uigf = read_starward_uigf4(starward_file)
    for user in uigf.hk4e:
        for rec in user.list:
            base_db.add_from_record(rec)

    # 3) 交互补表
    print("以下字段仍然缺失，请手动填写：")
    prompt_missing_meta_fields(base_db)
    print("元数据补全完成。")
    
    # 4) 覆盖保存到 meta_file（源文件）
    output_starward_db(base_db, meta_file)
    return base_db

if __name__ == "__main__":
    merge_mapping_and_starward(
        sys.argv[1],  # mapping_file
        sys.argv[2],  # starward_file
        sys.argv[3],  # meta_file
    )