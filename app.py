import io
import math
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False


APP_TITLE = "ClearCut AI"

MODELS = {
    "Preciso · isnet-general-use": "isnet-general-use",
    "Máxima calidad · birefnet": "birefnet-general",
    "Clásico · u2net": "u2net",
    "Rápido · u2netp": "u2netp",
    "Anime · isnet-anime": "isnet-anime",
}

# ── Paleta ────────────────────────────────────────────────────────────────
BG = "#0a0e1a"
PANEL = "#0f1424"
CARD = "#151b30"
BORDER = "#232b47"
TEXT = "#e8ecf8"
MUTED = "#7c87a6"
ACC = "#7c5cff"
ACC_H = "#6a49f0"
CYAN = "#22d3ee"
TEAL = "#0891b2"
TEAL_H = "#0e7490"
OK = "#22c55e"
OK_D = "#16a34a"
OK_H = "#15803d"
ERR = "#f43f5e"

FONT = "Segoe UI"
FPS_MS = 25

ctk.set_appearance_mode("dark")


# ── Utilidades ────────────────────────────────────────────────────────────
def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    ra, rb = hex2rgb(a), hex2rgb(b)
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(int(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))


def ease_out(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def rrect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def make_checker(w, h, tile=14, c1=(228, 232, 240), c2=(202, 208, 220)):
    img = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(img)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2:
                d.rectangle([x, y, x + tile - 1, y + tile - 1], fill=c2)
    return img


def make_logo(size=46):
    s = 4
    big = size * s
    grad = Image.new("RGB", (big, big))
    a, b = hex2rgb(ACC), hex2rgb(CYAN)
    px = grad.load()
    for y in range(big):
        for x in range(big):
            t = (x + y) / (2 * big)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=14 * s, fill=255)
    grad.putalpha(mask)
    d = ImageDraw.Draw(grad)
    cx = cy = big / 2
    R, r = big * 0.26, big * 0.07
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=(255, 255, 255, 255))
    return grad.resize((size, size), Image.Resampling.LANCZOS)


# ── Base con soporte opcional de arrastrar y soltar ───────────────────────
if HAS_DND:
    class Base(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    Base = ctk.CTk


class BackgroundRemoverApp(Base):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(fg_color=BG)
        w, h = 1200, 780
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        self.minsize(1020, 720)

        # estado
        self.mode = "empty"          # empty | loaded | processing | done
        self.path = None
        self.orig = None
        self.orig_small = None
        self.result = None
        self.result_small = None
        self.sessions = {}
        self.q = queue.Queue()
        self.split = 1.0
        self.bg_mode = "Cuadros"
        self.bg_color = "#ffffff"
        self.dirty = True
        self.t0 = time.time()
        self.reveal_start = None
        self.enter_start = None
        self.hover_drop = False
        self.dragging = False
        self.proc_msg = "Analizando imagen"
        self.layout = None
        self.photo = None
        self.disp_orig = None
        self.disp_dim = None
        self.disp_res = None
        self.toast_w = None
        self._resize_job = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._bind_events()
        self._set_step(0)
        self._refresh_buttons()

        self.attributes("-alpha", 0.0) if self._alpha_ok() else None
        self._fade_in(0.0)
        self.after(FPS_MS, self._tick)

    # ── Ventana ───────────────────────────────────────────────────────────
    def _alpha_ok(self):
        try:
            self.attributes("-alpha")
            return True
        except tk.TclError:
            return False

    def _fade_in(self, a):
        if not self._alpha_ok():
            return
        self.attributes("-alpha", a)
        if a < 1:
            self.after(15, lambda: self._fade_in(min(1.0, a + 0.07)))

    # ── Interfaz ──────────────────────────────────────────────────────────
    def _section(self, parent, text):
        ctk.CTkLabel(
            parent, text=text.upper(), text_color=MUTED,
            font=ctk.CTkFont(FONT, 10, "bold"), anchor="w"
        ).pack(fill="x", padx=26, pady=(20, 8))

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, width=320)
        sb.grid(row=0, column=0, sticky="ns")
        sb.pack_propagate(False)
        self.sidebar = sb

        # logo
        top = tk.Frame(sb, bg=PANEL)
        top.pack(fill="x", padx=24, pady=(26, 0))
        self.logo_img = ImageTk.PhotoImage(make_logo(46))
        tk.Label(top, image=self.logo_img, bg=PANEL, bd=0).pack(side="left")
        tt = tk.Frame(top, bg=PANEL)
        tt.pack(side="left", padx=12)
        tk.Label(tt, text="Removedor de Fondos", bg=PANEL, fg=TEXT,
                 font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(tt, text="IA local · PNG transparente", bg=PANEL, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w")

        # pasos
        self._section(sb, "Progreso")
        self.step_items = []
        for i, txt in enumerate(["Elegir imagen", "Quitar fondo", "Guardar PNG"]):
            row = tk.Frame(sb, bg=PANEL)
            row.pack(fill="x", padx=26, pady=3)
            cv = tk.Canvas(row, width=28, height=28, bg=PANEL, highlightthickness=0)
            cv.pack(side="left")
            lb = tk.Label(row, text=txt, bg=PANEL, fg=MUTED, font=(FONT, 11))
            lb.pack(side="left", padx=10)
            self.step_items.append((cv, lb))
        self.steps_done = 0

        # botones
        self._section(sb, "Acciones")
        bf = ctk.CTkFont(FONT, 13, "bold")
        self.btn_open = ctk.CTkButton(
            sb, text="Abrir imagen", command=self.select_image, height=44,
            corner_radius=12, font=bf, text_color_disabled=MUTED)
        self.btn_open.pack(fill="x", padx=24, pady=(0, 8))
        self.btn_remove = ctk.CTkButton(
            sb, text="Quitar fondo", command=self.start_removal, height=44,
            corner_radius=12, font=bf, text_color_disabled=MUTED)
        self.btn_remove.pack(fill="x", padx=24, pady=(0, 8))
        self.btn_save = ctk.CTkButton(
            sb, text="Guardar PNG", command=self.save_image, height=44,
            corner_radius=12, font=bf, text_color_disabled=MUTED)
        self.btn_save.pack(fill="x", padx=24, pady=(0, 4))

        # ajustes
        self._section(sb, "Modelo de IA")
        self.model_var = ctk.StringVar(value=list(MODELS)[0])
        ctk.CTkOptionMenu(
            sb, values=list(MODELS), variable=self.model_var, height=36,
            corner_radius=10, fg_color=CARD, button_color=BORDER,
            button_hover_color=ACC, dropdown_fg_color=CARD,
            dropdown_hover_color=ACC, text_color=TEXT,
            font=ctk.CTkFont(FONT, 12), dropdown_font=ctk.CTkFont(FONT, 12)
        ).pack(fill="x", padx=24)
        self.matting_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            sb, text="Bordes suaves (más lento)", variable=self.matting_var,
            progress_color=ACC, button_color=TEXT, button_hover_color="#ffffff",
            fg_color=BORDER, text_color=MUTED, font=ctk.CTkFont(FONT, 12)
        ).pack(anchor="w", padx=26, pady=(14, 0))

        self._section(sb, "Fondo de vista previa")
        self.seg = ctk.CTkSegmentedButton(
            sb, values=["Cuadros", "Blanco", "Negro", "Color"],
            command=self._on_bg, height=34, corner_radius=10,
            fg_color=CARD, selected_color=ACC, selected_hover_color=ACC_H,
            unselected_color=CARD, unselected_hover_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(FONT, 11, "bold"))
        self.seg.set("Cuadros")
        self.seg.pack(fill="x", padx=24)

        tk.Label(sb, text="Ctrl+O abrir  ·  Ctrl+S guardar  ·  Enter procesar",
                 bg=PANEL, fg=MUTED, font=(FONT, 8)).pack(side="bottom", pady=14)

    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        head = tk.Frame(self.main, bg=BG)
        head.grid(row=0, column=0, sticky="ew", padx=32, pady=(24, 0))
        self.lbl_name = tk.Label(head, text="Sin imagen", bg=BG, fg=TEXT,
                                 font=(FONT, 15, "bold"))
        self.lbl_name.pack(side="left")
        self.lbl_meta = tk.Label(head, text="", bg=BG, fg=MUTED, font=(FONT, 10))
        self.lbl_meta.pack(side="right")

        self.canvas = tk.Canvas(self.main, bg=BG, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=(8, 20))

    def _bind_events(self):
        c = self.canvas
        c.bind("<Configure>", self._on_resize)
        c.bind("<Button-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", lambda e: setattr(self, "dragging", False))
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda e: setattr(self, "hover_drop", False))
        self.bind("<Control-o>", lambda e: self.select_image())
        self.bind("<Control-s>", lambda e: self.save_image())
        self.bind("<Return>", lambda e: self.start_removal())
        if HAS_DND:
            try:
                c.drop_target_register(DND_FILES)
                c.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    # ── Estado visual ─────────────────────────────────────────────────────
    def _refresh_buttons(self):
        busy = self.mode == "processing"

        def style(btn, on, color, hover):
            btn.configure(
                state="normal" if on else "disabled",
                fg_color=color if on else CARD,
                hover_color=hover if on else CARD)

        style(self.btn_open, not busy, ACC, ACC_H)
        style(self.btn_remove, self.orig is not None and not busy, TEAL, TEAL_H)
        style(self.btn_save, self.result is not None and not busy, OK_D, OK_H)
        self.btn_remove.configure(text="Procesando…" if busy else "Quitar fondo")

    def _set_step(self, n):
        self.steps_done = n

    def _draw_steps(self):
        t = time.time() - self.t0
        for i, (cv, lb) in enumerate(self.step_items):
            cv.delete("all")
            done = i < self.steps_done
            active = i == self.steps_done
            if done:
                cv.create_oval(4, 4, 24, 24, fill=OK, outline="")
                cv.create_line(9, 14, 13, 18, 19, 10, fill="white", width=2,
                               capstyle="round", joinstyle="round")
                lb.configure(fg=TEXT)
            elif active:
                pulse = (math.sin(t * 4) + 1) / 2
                r = 12 + pulse * 2
                cv.create_oval(14 - r, 14 - r, 14 + r, 14 + r,
                               fill=mix(PANEL, ACC, 0.35 + 0.3 * pulse), outline="")
                cv.create_oval(5, 5, 23, 23, fill=ACC, outline="")
                cv.create_text(14, 14, text=str(i + 1), fill="white",
                               font=(FONT, 9, "bold"))
                lb.configure(fg=TEXT)
            else:
                cv.create_oval(5, 5, 23, 23, fill=PANEL, outline=BORDER, width=2)
                cv.create_text(14, 14, text=str(i + 1), fill=MUTED, font=(FONT, 9, "bold"))
                lb.configure(fg=MUTED)

    # ── Toast ─────────────────────────────────────────────────────────────
    def toast(self, msg, kind="info"):
        col = {"info": ACC, "ok": OK, "error": ERR}[kind]
        if self.toast_w is not None:
            try:
                self.toast_w.destroy()
            except Exception:
                pass
        f = ctk.CTkFrame(self.main, fg_color=CARD, border_color=col,
                         border_width=2, corner_radius=14)
        ctk.CTkLabel(f, text=msg, text_color=TEXT,
                     font=ctk.CTkFont(FONT, 13, "bold")).pack(padx=22, pady=11)
        self.toast_w = f
        self._toast_anim(f, 0)

    def _toast_anim(self, f, step):
        try:
            if not f.winfo_exists():
                return
        except Exception:
            return
        total, slide = 90, 14
        if step <= slide:
            y = -60 + (16 + 60) * ease_out(step / slide)
        elif step >= total - slide:
            y = 16 - (16 + 70) * ease_out((step - (total - slide)) / slide)
        else:
            y = 16
        f.place(relx=0.5, y=int(y), anchor="n")
        f.lift()
        if step >= total:
            f.destroy()
            if self.toast_w is f:
                self.toast_w = None
            return
        self.after(FPS_MS, lambda: self._toast_anim(f, step + 1))

    # ── Eventos de ratón ──────────────────────────────────────────────────
    def _on_resize(self, e):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._rebuild_display)

    def _on_motion(self, e):
        if self.mode == "empty":
            self.hover_drop = True
            self.canvas.configure(cursor="hand2")
        elif self.mode == "done":
            self.canvas.configure(cursor="sb_h_double_arrow")
        else:
            self.canvas.configure(cursor="")

    def _on_press(self, e):
        if self.mode == "empty":
            self.select_image()
        elif self.mode == "done":
            self.dragging = True
            self._set_split(e.x)

    def _on_drag(self, e):
        if self.dragging and self.mode == "done":
            self._set_split(e.x)

    def _set_split(self, x):
        if not self.layout:
            return
        ox, oy, dw, dh = self.layout
        self.split = min(1.0, max(0.0, (x - ox) / dw))
        self.reveal_start = None
        self.dirty = True

    def _on_drop(self, event):
        try:
            files = self.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if files:
            self.load_image(files[0])

    def _on_bg(self, value):
        if value == "Color":
            res = colorchooser.askcolor(color=self.bg_color, title="Color de fondo")
            if res and res[1]:
                self.bg_color = res[1]
        self.bg_mode = value
        self._rebuild_display()

    # ── Carga y guardado ──────────────────────────────────────────────────
    def select_image(self):
        if self.mode == "processing":
            return
        path = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                       ("Todos los archivos", "*.*")])
        if path:
            self.load_image(path)

    def load_image(self, path):
        if self.mode == "processing":
            return
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGBA")
                self.orig = im.copy()
        except Exception as exc:
            self.toast("No se pudo abrir la imagen", "error")
            messagebox.showerror("No se pudo abrir la imagen", str(exc))
            return
        self.path = path
        self.result = None
        self.result_small = None
        self.orig_small = self._small(self.orig)
        self.mode = "loaded"
        self.split = 1.0
        self.reveal_start = None
        self.enter_start = time.time()
        self.lbl_name.configure(text=Path(path).name)
        self.lbl_meta.configure(text=f"{self.orig.width} × {self.orig.height} px")
        self._set_step(1)
        self._refresh_buttons()
        self._rebuild_display()
        self.toast("Imagen cargada", "info")

    @staticmethod
    def _small(img, limit=1800):
        s = img.copy()
        s.thumbnail((limit, limit), Image.Resampling.LANCZOS)
        return s

    def save_image(self):
        if self.result is None or self.mode == "processing":
            return
        path = filedialog.asksaveasfilename(
            title="Guardar imagen sin fondo", defaultextension=".png",
            initialfile=f"{Path(self.path).stem}_sin_fondo.png",
            filetypes=[("Imagen PNG", "*.png")])
        if not path:
            return
        try:
            self.result.save(path, format="PNG", optimize=False)
            self._set_step(3)
            self.toast("PNG guardado correctamente", "ok")
        except Exception as exc:
            self.toast("Error al guardar", "error")
            messagebox.showerror("Error al guardar", str(exc))

    # ── Procesamiento ─────────────────────────────────────────────────────
    def start_removal(self):
        if self.orig is None or self.mode == "processing":
            return
        self.mode = "processing"
        self.result = None
        self.result_small = None
        self.disp_res = None
        self.proc_msg = "Analizando imagen"
        self._refresh_buttons()
        model = MODELS[self.model_var.get()]
        matting = bool(self.matting_var.get())
        threading.Thread(target=self._worker, args=(model, matting), daemon=True).start()

    def _worker(self, model, matting):
        try:
            from rembg import new_session, remove
            if model not in self.sessions:
                self.q.put(("msg", "Cargando modelo (1ª vez descarga)"))
                self.sessions[model] = new_session(model)
            self.q.put(("msg", "Eliminando fondo"))
            buf = io.BytesIO()
            self.orig.save(buf, format="PNG")
            out = remove(buf.getvalue(), session=self.sessions[model],
                         alpha_matting=matting)
            res = Image.open(io.BytesIO(out)).convert("RGBA")
            self.q.put(("ok", res))
        except ModuleNotFoundError as exc:
            self.q.put(("err", f"Falta el módulo '{exc.name}'.\n\n"
                        "Cierra la app y ejecuta INICIAR.bat.\n"
                        "Si persiste, borra la carpeta .venv y vuelve a ejecutarlo.\n"
                        "Requiere Python 3.11 o 3.12."))
        except Exception as exc:
            self.q.put(("err", str(exc)))

    def _poll_queue(self):
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                return
            if kind == "msg":
                self.proc_msg = payload
            elif kind == "ok":
                self._on_success(payload)
            elif kind == "err":
                self._on_error(payload)

    def _on_success(self, res):
        self.result = res
        self.result_small = self._small(res)
        self.mode = "done"
        self.split = 1.0
        self.reveal_start = time.time()
        self._set_step(2)
        self._refresh_buttons()
        self._rebuild_display()
        self.toast("Fondo eliminado", "ok")

    def _on_error(self, err):
        self.mode = "loaded"
        self._refresh_buttons()
        self._rebuild_display()
        self.toast("No se pudo procesar la imagen", "error")
        messagebox.showerror(
            "Error al eliminar el fondo",
            f"{err}\n\nComprueba tu conexión a internet la primera vez y vuelve a intentarlo.")

    # ── Preparación de imágenes para mostrar ──────────────────────────────
    def _rebuild_display(self):
        self._resize_job = None
        self.dirty = True
        if self.orig_small is None:
            self.layout = None
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 100 or ch < 100:
            return
        pad = 28
        ow, oh = self.orig.size
        s = min((cw - 2 * pad) / ow, (ch - 2 * pad) / oh, 1.6)
        dw, dh = max(1, int(ow * s)), max(1, int(oh * s))
        self.layout = ((cw - dw) // 2, (ch - dh) // 2, dw, dh)

        checker = make_checker(dw, dh).convert("RGBA")
        base = checker.copy()
        base.alpha_composite(self.orig_small.resize((dw, dh), Image.Resampling.LANCZOS))
        self.disp_orig = base.convert("RGB")
        self.disp_dim = ImageEnhance.Brightness(self.disp_orig).enhance(0.32)

        if self.result_small is not None:
            if self.bg_mode == "Cuadros":
                bg = checker.copy()
            elif self.bg_mode == "Blanco":
                bg = Image.new("RGBA", (dw, dh), "#ffffff")
            elif self.bg_mode == "Negro":
                bg = Image.new("RGBA", (dw, dh), "#000000")
            else:
                bg = Image.new("RGBA", (dw, dh), self.bg_color)
            bg.alpha_composite(self.result_small.resize((dw, dh), Image.Resampling.LANCZOS))
            self.disp_res = bg.convert("RGB")
        else:
            self.disp_res = None

    # ── Bucle de animación ────────────────────────────────────────────────
    def _tick(self):
        try:
            self._poll_queue()
            self._draw_steps()

            if self.reveal_start is not None:
                p = (time.time() - self.reveal_start) / 1.2
                self.split = 1.0 - 0.5 * ease_out(p)
                self.dirty = True
                if p >= 1:
                    self.reveal_start = None

            if self.mode == "empty":
                self._draw_empty()
            elif self.mode == "processing" and self.layout:
                self._draw_scan()
            elif self.layout and (self.dirty or self.enter_start):
                self._draw_compare()
                self.dirty = False
        finally:
            self.after(FPS_MS, self._tick)

    # ── Dibujo: estado vacío ──────────────────────────────────────────────
    def _draw_empty(self):
        c = self.canvas
        c.delete("all")
        cw, ch = c.winfo_width(), c.winfo_height()
        t = time.time() - self.t0
        m = 22
        hov = self.hover_drop
        border = mix(BORDER, ACC, 0.95 if hov else 0.4 + 0.15 * math.sin(t * 2))
        rrect(c, m, m, cw - m, ch - m, 30,
              fill=mix(BG, CARD, 1.0 if hov else 0.55), outline=border, width=2,
              dash=(9, 9), dashoffset=int(t * 24) % 18)

        cx, cy = cw / 2, ch / 2 - 60
        for i in range(3):
            ph = (t * 0.55 + i / 3) % 1
            r = 42 + ph * 80
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=mix(ACC, BG, ph ** 0.7), width=2)
        bob = math.sin(t * 2.2) * 4
        c.create_oval(cx - 42, cy - 42, cx + 42, cy + 42,
                      fill=ACC_H if hov else ACC, outline="")
        y = cy + bob
        c.create_line(cx, y + 15, cx, y - 15, fill="white", width=4, capstyle="round")
        c.create_line(cx - 13, y - 3, cx, y - 16, cx + 13, y - 3, fill="white",
                      width=4, capstyle="round", joinstyle="round")
        c.create_line(cx - 16, y + 20, cx + 16, y + 20, fill="white", width=4,
                      capstyle="round")

        c.create_text(cx, cy + 134, text="Arrastra una imagen aquí" if HAS_DND
                      else "Selecciona una imagen", fill=TEXT, font=(FONT, 20, "bold"))
        c.create_text(cx, cy + 168, text="o haz clic para elegirla desde tu equipo",
                      fill=MUTED, font=(FONT, 12))
        c.create_text(cx, cy + 200, text="PNG  ·  JPG  ·  WEBP  ·  BMP  ·  TIFF",
                      fill=mix(MUTED, BG, 0.35), font=(FONT, 10, "bold"))

    # ── Dibujo: comparación / vista previa ────────────────────────────────
    def _glow(self, ox, oy, dw, dh, color):
        c = self.canvas
        for i in range(7, 0, -1):
            rrect(c, ox - i * 2, oy - i * 2, ox + dw + i * 2, oy + dh + i * 2,
                  6 + i, fill="", outline=mix(BG, color, 0.045 * (8 - i)), width=2)

    def _draw_compare(self):
        c = self.canvas
        c.delete("all")
        ox, oy, dw, dh = self.layout
        x = int(dw * self.split)
        done = self.disp_res is not None

        self._glow(ox, oy, dw, dh, ACC if not done else CYAN)

        frame = self.disp_orig.copy()
        if done and x < dw:
            frame.paste(self.disp_res.crop((x, 0, dw, dh)), (x, 0))

        if self.enter_start:
            p = (time.time() - self.enter_start) / 0.55
            if p >= 1:
                self.enter_start = None
            else:
                bg = Image.new("RGB", frame.size, hex2rgb(BG))
                frame = Image.blend(bg, frame, ease_out(p))
        self.photo = ImageTk.PhotoImage(frame)
        c.create_image(ox, oy, anchor="nw", image=self.photo)

        if not done:
            return

        lx = ox + x
        c.create_line(lx, oy, lx, oy + dh, fill="white", width=2)
        cy = oy + dh / 2
        c.create_oval(lx - 22, cy - 22, lx + 22, cy + 22, fill=ACC, outline="white", width=2)
        c.create_polygon(lx - 12, cy, lx - 5, cy - 6, lx - 5, cy + 6, fill="white", outline="")
        c.create_polygon(lx + 12, cy, lx + 5, cy - 6, lx + 5, cy + 6, fill="white", outline="")

        if x > 90:
            rrect(c, ox + 12, oy + 12, ox + 86, oy + 38, 8, fill="#0b0f1a", outline=BORDER)
            c.create_text(ox + 49, oy + 25, text="ANTES", fill=TEXT, font=(FONT, 9, "bold"))
        if dw - x > 110:
            rrect(c, ox + dw - 100, oy + 12, ox + dw - 12, oy + 38, 8, fill="#0b0f1a", outline=CYAN)
            c.create_text(ox + dw - 56, oy + 25, text="DESPUÉS", fill=CYAN, font=(FONT, 9, "bold"))

    # ── Dibujo: escáner mientras procesa ──────────────────────────────────
    def _draw_scan(self):
        c = self.canvas
        c.delete("all")
        ox, oy, dw, dh = self.layout
        t = time.time() - self.t0
        p = (t * 0.8) % 2
        yy = int((p if p <= 1 else 2 - p) * dh)
        band = max(20, int(dh * 0.14))
        y0, y1 = max(0, yy - band), min(dh, yy + band)

        self._glow(ox, oy, dw, dh, CYAN)
        frame = self.disp_dim.copy()
        if y1 > y0:
            frame.paste(self.disp_orig.crop((0, y0, dw, y1)), (0, y0))
        self.photo = ImageTk.PhotoImage(frame)
        c.create_image(ox, oy, anchor="nw", image=self.photo)

        c.create_rectangle(ox, oy + yy - 7, ox + dw, oy + yy + 7,
                           fill=CYAN, stipple="gray25", outline="")
        c.create_line(ox, oy + yy, ox + dw, oy + yy, fill=CYAN, width=2)

        L = 26
        for (px, py, sx, sy) in ((ox, oy, 1, 1), (ox + dw, oy, -1, 1),
                                 (ox, oy + dh, 1, -1), (ox + dw, oy + dh, -1, -1)):
            c.create_line(px, py + sy * L, px, py, px + sx * L, py,
                          fill=CYAN, width=3, capstyle="round", joinstyle="round")

        dots = "." * (int(t * 3) % 4)
        cx, by = ox + dw / 2, oy + dh - 34
        rrect(c, cx - 150, by - 18, cx + 150, by + 18, 14, fill="#0b0f1a", outline=CYAN)
        c.create_text(cx, by, text=f"{self.proc_msg}{dots}", fill=TEXT,
                      font=(FONT, 11, "bold"))


def main():
    app = BackgroundRemoverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
