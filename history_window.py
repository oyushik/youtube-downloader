from __future__ import annotations

from datetime import datetime
import sqlite3
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from download_history import DownloadHistory


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, history: DownloadHistory, active_download):
        super().__init__(parent)
        self.history = history
        self.active_download = active_download
        self.records = {}
        self.videos = {}
        self.title("다운로드 내역")
        self.geometry("1020x740")
        self.minsize(820, 640)
        self.configure(background="#f3f5f9")
        self.transient(parent)
        self.message = tk.StringVar()
        self.folder = tk.StringVar()
        self.url = tk.StringVar()
        self.summary = tk.StringVar(value="내역을 선택하면 영상별 결과를 확인할 수 있습니다.")
        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        body.rowconfigure(7, weight=1)
        ttk.Label(body, text="다운로드 내역", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, textvariable=self.message, foreground="#68748a", wraplength=950).grid(row=1, column=0, sticky="w", pady=(6, 12))
        self.jobs = self.table(body, 2, (
            ("date", "시작 일시", 155), ("kind", "종류", 80), ("title", "제목", 310),
            ("state", "결과", 80), ("count", "성공 / 전체", 100),
        ))
        self.jobs.bind("<<TreeviewSelect>>", self.select_download)
        ttk.Label(body, textvariable=self.summary, wraplength=950).grid(row=3, column=0, sticky="w", pady=(12, 8))
        self.readonly_line(body, 4, "저장 위치", self.folder)
        self.readonly_line(body, 5, "원본 링크", self.url)
        ttk.Label(body, text="영상별 결과", font=("맑은 고딕", 11, "bold")).grid(row=6, column=0, sticky="w", pady=(12, 6))
        self.items = self.table(body, 7, (("index", "순서", 60), ("title", "영상 제목", 610), ("state", "결과", 110)))
        self.items.bind("<<TreeviewSelect>>", self.select_video)
        self.detail = ScrolledText(body, height=3, wrap="word", font=("맑은 고딕", 9),
                                   background="white", relief="flat", state="disabled")
        self.detail.grid(row=8, column=0, sticky="ew", pady=(8, 10))
        footer = ttk.Frame(body)
        footer.grid(row=9, column=0, sticky="ew")
        ttk.Button(footer, text="새로고침", command=self.refresh).pack(side="left")
        ttk.Button(footer, text="닫기", command=self.destroy).pack(side="right")
        self.refresh()

    @staticmethod
    def table(parent, row, columns):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="nsew")
        tree = ttk.Treeview(frame, columns=[key for key, _, _ in columns], show="headings", selectmode="browse", height=5)
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=55, stretch=key == "title", anchor="w" if key == "title" else "center")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    @staticmethod
    def readonly_line(parent, row, label, variable):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=3)
        ttk.Label(frame, text=label, width=10).pack(side="left")
        ttk.Entry(frame, textvariable=variable, state="readonly").pack(fill="x", expand=True)

    def set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def refresh(self):
        selected = self.jobs.selection()
        try:
            records = self.history.list_downloads()
        except (OSError, sqlite3.Error) as error:
            self.message.set(f"다운로드 내역을 읽지 못했습니다: {error}")
            return
        self.records = {str(record["id"]): record for record in records}
        for child in self.jobs.get_children():
            self.jobs.delete(child)
        for record in records:
            date = datetime.fromisoformat(record["started_at"]).astimezone().strftime("%Y-%m-%d %H:%M")
            state = "진행 중" if record["id"] == self.active_download() else record["state"]
            self.jobs.insert("", "end", iid=str(record["id"]), values=(date, record["kind"], record["title"], state,
                                                                       f"{record['success']} / {record['total']}"))
        self.message.set(f"총 {len(records)}건 · 최신순 · 미완료는 종료 결과가 확인되지 않은 작업입니다." if records else
                         "다운로드 내역이 없습니다. 이 버전에서 시작한 다운로드부터 기록됩니다.")
        if records:
            key = selected[0] if selected and selected[0] in self.records else str(records[0]["id"])
            self.jobs.selection_set(key)
            self.jobs.see(key)
            self.select_download()

    def select_download(self, _event=None):
        selected = self.jobs.selection()
        if not selected or selected[0] not in self.records:
            return
        record = self.records[selected[0]]
        self.folder.set(record["folder"])
        self.url.set(record["url"])
        self.summary.set(f"{record['title']} · 성공 {record['success']}개 / 실패 {record['failed']}개 / 전체 {record['total']}개")
        self.videos = {}
        for child in self.items.get_children():
            self.items.delete(child)
        try:
            videos = self.history.list_videos(record["id"])
        except (OSError, sqlite3.Error) as error:
            self.set_detail(f"영상별 내역을 읽지 못했습니다: {error}")
            return
        self.videos = {str(video["position"]): video for video in videos}
        for video in videos:
            self.items.insert("", "end", iid=str(video["position"]), values=(video["playlist_index"], video["title"], video["state"]))
        self.set_detail(record["error"] or "영상을 선택하면 링크, 저장 파일, 실패 이유를 확인할 수 있습니다.")

    def select_video(self, _event=None):
        selected = self.items.selection()
        if selected and selected[0] in self.videos:
            video = self.videos[selected[0]]
            self.set_detail(f"{video['title']}\n링크: {video['url']}\n저장 파일: {video['path'] or '없음'}"
                            + (f"\n실패 이유: {video['reason']}" if video["reason"] else ""))

    def destroy(self):
        super().destroy()
        # Release Tcl variables on the UI thread even when a worker later collects this window.
        self.message = self.folder = self.url = self.summary = None
