from __future__ import annotations

import ctypes
from pathlib import Path
import queue
import sqlite3
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText

from app_runtime import BundledRuntime, Cancelled
from download_engine import DownloadEngine, VideoList, validate_url
from download_history import DownloadHistory
from history_window import HistoryWindow


def duration_text(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


class DownloadApp:
    def __init__(self, root: tk.Tk, history_path: Path | None = None):
        self.root = root
        root.title("YouTube 다운로드")
        root.geometry("980x780")
        root.minsize(820, 680)
        root.configure(background="#f3f5f9")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.log_visible = False
        self.step = 0
        self.listing: VideoList | None = None
        self.history = DownloadHistory(history_path)
        self.history_window: HistoryWindow | None = None
        self.active_history_id: int | None = None
        self.history_warning = ""
        self.mode = tk.StringVar(value="single")
        self.url = tk.StringVar()
        self.folder = tk.StringVar()
        self.numbered = tk.BooleanVar(value=True)
        self.separate = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="다운로드할 YouTube 링크를 입력해 주세요.")
        self.overall = tk.StringVar(value="")
        self.progress_text = tk.StringVar(value="")
        self.setup_style()
        self.build_ui()
        self.show_step(0)
        root.after(100, self.poll)

    def setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        tkfont.nametofont("TkDefaultFont").configure(family="맑은 고딕", size=10)
        style.configure("TFrame", background="#f3f5f9")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="#f3f5f9", foreground="#192238", font=("맑은 고딕", 10))
        style.configure("Card.TLabel", background="white")
        style.configure("Title.TLabel", font=("맑은 고딕", 22, "bold"))
        style.configure("Heading.TLabel", background="white", font=("맑은 고딕", 15, "bold"))
        style.configure("Muted.TLabel", background="white", foreground="#68748a")
        style.configure("TButton", font=("맑은 고딕", 10), padding=(16, 9))
        style.configure("Accent.TButton", background="#2563eb", foreground="white", borderwidth=0)
        style.map("Accent.TButton", background=[("disabled", "#a6b5d4"), ("active", "#1d4ed8")],
                  foreground=[("disabled", "#edf1f7")])
        style.configure("TRadiobutton", background="white", padding=(0, 8))
        style.configure("TCheckbutton", background="white", padding=(0, 7))
        style.configure("Treeview", rowheight=32, background="white", fieldbackground="white", borderwidth=0)
        style.configure("Treeview.Heading", font=("맑은 고딕", 10, "bold"), padding=(6, 8))
        style.configure("TProgressbar", background="#2563eb", troughcolor="#e6ebf4", borderwidth=0)

    def build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=28)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="YouTube 다운로드", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="링크를 확인하고 원하는 폴더에 저장하세요.", foreground="#68748a").pack(anchor="w", pady=(5, 22))
        steps = ttk.Frame(shell)
        steps.pack(fill="x", pady=(0, 16))
        self.step_labels = []
        for index, title in enumerate(("링크 입력", "목록 확인", "저장 설정", "다운로드")):
            label = ttk.Label(steps, text=f"{index + 1}  {title}", padding=(12, 10), anchor="center")
            label.pack(side="left", fill="x", expand=True, padx=(0, 3))
            self.step_labels.append(label)

        self.body = ttk.Frame(shell, style="Card.TFrame", padding=24)
        self.body.pack(fill="both", expand=True)
        self.body.grid_propagate(False)
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=1)
        self.pages = [ttk.Frame(self.body, style="Card.TFrame") for _ in range(4)]
        self.build_link_page(self.pages[0])
        self.build_review_page(self.pages[1])
        self.build_settings_page(self.pages[2])
        self.build_progress_page(self.pages[3])

        self.loading = ttk.Progressbar(shell, mode="determinate")
        self.loading.pack(fill="x", pady=(14, 6))
        ttk.Label(shell, textvariable=self.status, wraplength=890).pack(fill="x", pady=(2, 12))
        footer = ttk.Frame(shell)
        footer.pack(fill="x")
        self.back_button = ttk.Button(footer, text="이전", command=self.back)
        self.back_button.pack(side="left")
        self.cancel_button = ttk.Button(footer, text="중지", command=self.stop)
        self.cancel_button.pack(side="left", padx=8)
        self.history_button = ttk.Button(footer, text="다운로드 내역", command=self.open_history)
        self.history_button.pack(side="left")
        self.next_button = ttk.Button(footer, text="목록 불러오기", command=self.next, style="Accent.TButton")
        self.next_button.pack(side="right")

    def heading(self, parent: ttk.Frame, title: str, description: str) -> None:
        ttk.Label(parent, text=title, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(parent, text=description, style="Muted.TLabel", wraplength=830).pack(anchor="w", pady=(8, 20))

    def build_link_page(self, parent: ttk.Frame) -> None:
        self.heading(parent, "어떤 영상을 다운로드할까요?", "다운로드 방식을 선택한 다음 영상 또는 재생목록 링크를 붙여 넣으세요.")
        self.radios = []
        for text, value in (("개별 영상", "single"), ("재생목록 전체", "playlist")):
            radio = ttk.Radiobutton(parent, text=text, variable=self.mode, value=value)
            radio.pack(anchor="w")
            self.radios.append(radio)
        ttk.Label(parent, text="YouTube URL", style="Card.TLabel").pack(anchor="w", pady=(25, 8))
        self.url_entry = ttk.Entry(parent, textvariable=self.url, font=("맑은 고딕", 11))
        self.url_entry.pack(fill="x", ipady=8)
        self.url_entry.bind("<Return>", lambda _event: self.next() if not self.busy else None)
        ttk.Label(parent, text="youtube.com/watch, youtu.be, Shorts 및 재생목록 링크를 사용할 수 있습니다.",
                  style="Muted.TLabel", wraplength=800).pack(anchor="w", pady=12)

    def make_table(self, parent: ttk.Frame, progress: bool = False) -> ttk.Treeview:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill="both", expand=True)
        columns = ("index", "title", "state") if progress else ("index", "title", "duration")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=8)
        tree.heading("index", text="순서")
        tree.column("index", width=62, minwidth=55, stretch=False, anchor="center")
        tree.heading("title", text="영상 제목")
        tree.column("title", width=520, minwidth=200)
        last = columns[-1]
        tree.heading(last, text="상태" if progress else "길이")
        tree.column(last, width=105, minwidth=85, stretch=False, anchor="center")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.tag_configure("failed", foreground="#b42318")
        tree.tag_configure("done", foreground="#15803d")
        return tree

    def build_review_page(self, parent: ttk.Frame) -> None:
        self.heading(parent, "다운로드 목록 확인", "목록을 확인한 뒤 저장 위치를 선택하세요.")
        self.list_title = tk.StringVar()
        ttk.Label(parent, textvariable=self.list_title, style="Card.TLabel", wraplength=820).pack(anchor="w", pady=(0, 12))
        self.review_tree = self.make_table(parent)

    def build_settings_page(self, parent: ttk.Frame) -> None:
        self.heading(parent, "어디에 저장할까요?", "최종 영상은 MKV 형식으로 저장됩니다. 재생목록은 제목별 폴더에 정리됩니다.")
        ttk.Label(parent, text="다운로드 폴더", style="Card.TLabel").pack(anchor="w", pady=(8, 8))
        line = ttk.Frame(parent, style="Card.TFrame")
        line.pack(fill="x")
        ttk.Entry(line, textvariable=self.folder).pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 10))
        ttk.Button(line, text="폴더 선택…", command=self.browse_folder).pack(side="right")
        ttk.Label(parent, text="저장 옵션", style="Card.TLabel").pack(anchor="w", pady=(30, 8))
        self.number_check = ttk.Checkbutton(parent, text="파일명 앞에 재생목록 순서 번호 추가 (001, 002…)", variable=self.numbered)
        self.number_check.pack(anchor="w")
        ttk.Checkbutton(parent, text="소리 없는 영상과 WAV 음성 파일도 별도로 저장", variable=self.separate).pack(anchor="w")
        ttk.Label(parent, text="같은 이름의 파일이 있으면 새 이름을 붙여 기존 파일을 보존합니다.",
                  style="Muted.TLabel", wraplength=810).pack(anchor="w", pady=22)

    def build_progress_page(self, parent: ttk.Frame) -> None:
        self.heading(parent, "다운로드 진행 상황", "영상별 결과를 확인할 수 있습니다. 완료된 파일은 중지해도 보존됩니다.")
        controls = ttk.Frame(parent, style="Card.TFrame")
        controls.pack(side="bottom", fill="x")
        ttk.Label(controls, textvariable=self.overall, style="Card.TLabel").pack(anchor="w", pady=(12, 5))
        self.overall_bar = ttk.Progressbar(controls, maximum=100)
        self.overall_bar.pack(fill="x")
        ttk.Label(controls, textvariable=self.progress_text, style="Muted.TLabel").pack(anchor="w", pady=(10, 5))
        self.file_bar = ttk.Progressbar(controls, maximum=100)
        self.file_bar.pack(fill="x")
        self.log_button = ttk.Button(controls, text="상세 로그 보기", command=self.toggle_log)
        self.log_button.pack(anchor="w", pady=(10, 0))
        self.log_text = ScrolledText(controls, height=5, wrap="word", font=("맑은 고딕", 9),
                                     relief="flat", background="#f4f6fa", state="disabled")
        self.progress_tree = self.make_table(parent, True)

    def show_step(self, step: int) -> None:
        self.step = step
        for page in self.pages:
            page.grid_remove()
        self.pages[step].grid(row=0, column=0, sticky="nsew")
        for index, label in enumerate(self.step_labels):
            label.configure(background="#dce8ff" if index == step else "#e9edf4",
                            foreground="#1d4ed8" if index == step else "#68748a")
        if step == 0:
            self.url_entry.focus_set()
        if step == 2:
            self.number_check.configure(state="normal" if self.listing and self.listing.playlist else "disabled")
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        self.back_button.configure(state="normal" if 0 < self.step < 3 and not self.busy else "disabled")
        self.cancel_button.configure(state="normal" if self.busy and not self.cancel.is_set() else "disabled")
        self.next_button.configure(text=("목록 불러오기", "저장 설정", "다운로드 시작", "새 다운로드")[self.step],
                                   state="disabled" if self.busy else "normal")
        self.url_entry.configure(state="disabled" if self.busy else "normal")
        for radio in self.radios:
            radio.configure(state="disabled" if self.busy else "normal")

    def back(self) -> None:
        if not self.busy and self.step in (1, 2):
            self.show_step(self.step - 1)

    def next(self) -> None:
        if self.busy:
            return
        if self.step == 0:
            try:
                playlist = self.mode.get() == "playlist"
                url = validate_url(self.url.get(), playlist)
            except ValueError as error:
                messagebox.showerror("링크 확인", str(error), parent=self.root)
                return
            self.start_task("inspect", url=url, playlist=playlist)
        elif self.step == 1:
            self.show_step(2)
        elif self.step == 2:
            try:
                if not self.folder.get().strip():
                    raise ValueError("다운로드 폴더를 선택해 주세요.")
                destination = Path(self.folder.get().strip()).expanduser()
                if not destination.is_absolute():
                    raise ValueError("전체 폴더 경로를 입력하거나 ‘폴더 선택’을 사용해 주세요.")
                destination.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=destination):
                    pass
            except (ValueError, OSError) as error:
                messagebox.showerror("저장 위치 확인", str(error), parent=self.root)
                return
            self.clear_table(self.progress_tree)
            for row, video in enumerate(self.listing.videos):
                self.progress_tree.insert("", "end", iid=str(row), values=(video.index, video.title, "대기"))
            self.overall.set(f"전체 0 / {len(self.listing.videos)}개 처리")
            self.overall_bar["value"] = 0
            self.file_bar["value"] = 0
            self.progress_text.set("다운로드 준비 중…")
            self.show_step(3)
            self.start_task("download", listing=self.listing, destination=destination,
                            numbered=self.numbered.get(), separate=self.separate.get())
        else:
            self.show_step(0)
            self.status.set("다음에 다운로드할 링크를 입력해 주세요.")

    def browse_folder(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="다운로드 폴더 선택",
                                           initialdir=self.folder.get() or str(Path.home() / "Downloads"))
        if selected:
            self.folder.set(selected)

    def start_task(self, operation: str, **arguments) -> None:
        self.cancel.clear()
        self.busy = True
        self.history_warning = ""
        self.status.set("다운로드 준비 중…")
        self.loading.configure(mode="indeterminate")
        self.loading.start(12)
        self.refresh_buttons()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        def worker() -> None:
            history_id = None
            history_failed = False

            def record(action, *args):
                nonlocal history_failed
                try:
                    return action(*args)
                except (OSError, sqlite3.Error) as error:
                    if not history_failed:
                        history_failed = True
                        self.emit("history_warning", {"message": str(error)})

            def download_event(kind, data):
                if history_id is not None:
                    record(self.history.record_event, history_id, kind, data)
                self.emit(kind, data)

            try:
                if operation == "download":
                    history_id = record(self.history.start, arguments["listing"], arguments["destination"])
                    self.emit("history_started", {"id": history_id})
                with BundledRuntime(self.cancel) as runtime:
                    engine = DownloadEngine(runtime, self.cancel, download_event)
                    if operation == "inspect":
                        self.emit("status", {"message": "영상 목록을 불러오는 중…"})
                        self.emit("listing", {"listing": engine.inspect(**arguments)})
                    else:
                        result = engine.download(**arguments)
                        if history_id is not None:
                            record(self.history.finish, history_id, "complete")
                        self.emit("complete", result)
            except Cancelled:
                if history_id is not None:
                    record(self.history.finish, history_id, "cancelled")
                self.emit("cancelled", {})
            except Exception as error:
                if history_id is not None:
                    record(self.history.finish, history_id, "error", str(error))
                self.emit("error", {"message": str(error) or type(error).__name__})
            finally:
                self.emit("idle", {})

        threading.Thread(target=worker, name="download-worker", daemon=False).start()

    def emit(self, kind: str, data: dict) -> None:
        self.events.put((kind, data))

    @staticmethod
    def clear_table(tree: ttk.Treeview) -> None:
        children = tree.get_children()
        if children:
            tree.delete(*children)

    def append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 800:
            self.log_text.delete("1.0", f"{lines - 800}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def mark_unfinished(self) -> None:
        for row in self.progress_tree.get_children():
            state = self.progress_tree.set(row, "state")
            if state in {"다운로드 중", "재시도 중"}:
                self.progress_tree.set(row, "state", "중지됨")
            elif state in {"대기", "재시도 대기"}:
                self.progress_tree.set(row, "state", "미실행")

    def poll(self) -> None:
        for _ in range(150):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                if not self.cancel.is_set():
                    self.status.set(data["message"])
            elif kind == "log":
                self.append_log(data["message"])
            elif kind == "listing":
                self.listing = data["listing"]
                self.clear_table(self.review_tree)
                for video in self.listing.videos:
                    self.review_tree.insert("", "end", values=(video.index, video.title, duration_text(video.duration)))
                self.list_title.set(f"{self.listing.title}  ·  {len(self.listing.videos)}개 영상")
                self.status.set("목록을 확인했습니다. 저장 위치를 선택해 주세요.")
                self.show_step(1)
            elif kind == "item":
                row = str(data["row"])
                self.progress_tree.set(row, "state", data["state"])
                self.progress_tree.item(row, tags=("failed" if data["state"] == "실패" else "done" if data["state"] == "완료" else "",))
                self.progress_tree.see(row)
                if data.get("reason"):
                    self.append_log(f"[{int(row) + 1}] {data['reason']}")
            elif kind == "overall":
                self.overall.set(f"전체 {data['done']} / {data['total']}개 처리")
                self.overall_bar["value"] = 100 * data["done"] / data["total"]
            elif kind == "progress":
                self.file_bar["value"] = data["percent"]
                size = data.get("bytes", 0) / (1024 * 1024)
                detail = f"현재 스트림 {data['percent']:.1f}%  ·  {size:.1f} MB"
                if data.get("speed"):
                    detail += f"  ·  {data['speed'] / (1024 * 1024):.1f} MB/s"
                if data.get("eta") is not None:
                    detail += f"  ·  남은 시간 {duration_text(data['eta'])}"
                self.progress_text.set(detail)
            elif kind == "history_started":
                self.active_history_id = data["id"]
                self.refresh_history()
            elif kind == "history_warning":
                self.history_warning = data["message"]
                self.append_log("다운로드 내역 저장 실패: " + self.history_warning)
            elif kind == "complete":
                self.status.set(f"다운로드 완료 — 성공 {data['success']}개 / 실패 {len(data['failed'])}개")
                self.progress_text.set("모든 영상의 처리가 끝났습니다.")
                self.file_bar["value"] = 100 if data["success"] else 0
                if data["failed"] and not self.log_visible:
                    self.toggle_log()
            elif kind == "cancelled":
                self.status.set("작업을 중지했습니다. 완료된 파일은 저장 폴더에 남아 있습니다.")
                self.mark_unfinished()
            elif kind == "error":
                self.status.set("작업을 완료하지 못했습니다.")
                self.append_log(data["message"])
                self.mark_unfinished()
                if not self.closing:
                    messagebox.showerror("작업 실패", data["message"], parent=self.root)
            elif kind == "idle":
                self.busy = False
                self.active_history_id = None
                self.loading.stop()
                self.loading.configure(mode="determinate")
                self.loading["value"] = 0
                self.refresh_buttons()
                self.refresh_history()
                if self.history_warning and not self.closing:
                    messagebox.showwarning("다운로드 내역 저장 실패",
                                           "다운로드 결과와 별개로 내역을 저장하지 못했습니다.\n" + self.history_warning,
                                           parent=self.root)
        if self.closing and not self.busy:
            self.root.destroy()
        else:
            self.root.after(100, self.poll)

    def stop(self) -> None:
        if self.busy:
            self.cancel.set()
            self.status.set("중지 요청됨 — 현재 네트워크 또는 병합 작업을 정리하는 중…")
            self.refresh_buttons()

    def close(self) -> None:
        if self.busy:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()

    def open_history(self) -> None:
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.refresh()
            self.history_window.deiconify()
            self.history_window.lift()
        else:
            self.history_window = HistoryWindow(self.root, self.history, lambda: self.active_history_id)

    def refresh_history(self) -> None:
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.refresh()

    def toggle_log(self) -> None:
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_button.configure(text="상세 로그 보기")
        else:
            self.log_text.pack(fill="x", pady=(8, 0))
            self.log_button.configure(text="상세 로그 숨기기")
        self.log_visible = not self.log_visible


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    DownloadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
