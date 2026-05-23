import flet as ft
import requests
import json
import matplotlib.pyplot as plt
import io
import base64
import tempfile
import os
import threading
import numpy as np
from datetime import datetime
import asyncio

# ВАШ IP-АДРЕС (из ipconfig: 192.168.0.103)
SERVER_URL = "http://192.168.0.103:5000"
SETTINGS_FILE = "settings.json"

def main(page: ft.Page):
    page.title = "Виртуальный генератор сигналов"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.window_width = 1200
    page.window_height = 800
    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.scroll = ft.ScrollMode.AUTO

    # ---------- Переменные состояния ----------
    current_audio_file = None
    audio_recorder = None
    audio_player = None

    # ---------- Элементы управления ----------
    waveform_dropdown = ft.Dropdown(
        width=200,
        value="sine",
        options=[
            ft.dropdown.Option("Синус", "sine"),
            ft.dropdown.Option("Квадрат", "square"),
            ft.dropdown.Option("Пила", "sawtooth"),
            ft.dropdown.Option("Треугольник", "triangle"),
            ft.dropdown.Option("Белый шум", "noise"),
        ]
    )

    freq_slider = ft.Slider(min=20, max=20000, value=440, divisions=100, label="{value} Гц", width=250)
    freq_value = ft.Text("440 Гц", size=12)
    def update_freq(e):
        freq_value.value = f"{int(freq_slider.value)} Гц"
        page.update()
    freq_slider.on_change = update_freq

    amp_slider = ft.Slider(min=0, max=1, value=0.8, divisions=20, label="{value:.0%}", width=250)
    amp_value = ft.Text("80%", size=12)
    def update_amp(e):
        amp_value.value = f"{int(amp_slider.value * 100)}%"
        page.update()
    amp_slider.on_change = update_amp

    duration_slider = ft.Slider(min=0.5, max=10, value=2.0, divisions=19, label="{value} сек", width=250)
    duration_value = ft.Text("2.0 сек", size=12)
    def update_duration(e):
        duration_value.value = f"{duration_slider.value:.1f} сек"
        page.update()
    duration_slider.on_change = update_duration

    noise_check = ft.Checkbox(label="Добавить белый шум", value=False)
    snr_input = ft.TextField(value="10", width=100, label="SNR (дБ)", text_size=12)

    filter_dropdown = ft.Dropdown(
        width=150,
        value="none",
        options=[
            ft.dropdown.Option("Нет", "none"),
            ft.dropdown.Option("ФНЧ", "lowpass"),
            ft.dropdown.Option("ФВЧ", "highpass"),
        ]
    )
    cutoff_input = ft.TextField(value="1000", width=100, label="Частота среза (Гц)", text_size=12)

    gen_btn = ft.ElevatedButton("СГЕНЕРИРОВАТЬ", width=200, height=40)
    record_btn = ft.ElevatedButton("Записать с микрофона (5 сек)", width=250)
    load_btn = ft.ElevatedButton("Загрузить WAV файл", width=250)
    play_btn = ft.ElevatedButton("ВОСПРОИЗВЕСТИ", disabled=True)
    volume_slider = ft.Slider(min=0, max=1, value=0.7, width=100)
    save_file_btn = ft.ElevatedButton("Сохранить в файл")
    save_png_btn = ft.ElevatedButton("Сохранить графики в PNG")

    osc_container = ft.Container(
        content=ft.Text("График появится после генерации", size=12, color=ft.Colors.GREY),
        width=550,
        height=250,
        bgcolor=ft.Colors.GREY_100,
        border_radius=10
    )
    spec_container = ft.Container(
        content=ft.Text("График появится после генерации", size=12, color=ft.Colors.GREY),
        width=550,
        height=250,
        bgcolor=ft.Colors.GREY_100,
        border_radius=10
    )
    status_text = ft.Text("Готов", color=ft.Colors.GREEN)

    # ---------- Функции ----------
    def save_settings():
        settings = {
            'waveform': waveform_dropdown.value,
            'freq': freq_slider.value,
            'amp': amp_slider.value,
            'duration': duration_slider.value,
            'noise': noise_check.value,
            'snr': snr_input.value,
            'filter': filter_dropdown.value,
            'cutoff': cutoff_input.value,
            'volume': volume_slider.value
        }
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f)
        except:
            pass

    def load_settings():
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    s = json.load(f)
                    waveform_dropdown.value = s.get('waveform', 'sine')
                    freq_slider.value = s.get('freq', 440)
                    amp_slider.value = s.get('amp', 0.8)
                    duration_slider.value = s.get('duration', 2.0)
                    noise_check.value = s.get('noise', False)
                    snr_input.value = str(s.get('snr', 10))
                    filter_dropdown.value = s.get('filter', 'none')
                    cutoff_input.value = str(s.get('cutoff', 1000))
                    volume_slider.value = s.get('volume', 0.7)
                    freq_value.value = f"{int(freq_slider.value)} Гц"
                    amp_value.value = f"{int(amp_slider.value * 100)}%"
                    duration_value.value = f"{duration_slider.value:.1f} сек"
                    page.update()
        except:
            pass

    def show_snackbar(message):
        page.snack_bar = ft.SnackBar(content=ft.Text(message), open=True)
        page.update()

    def update_ui_with_plots(fig_osc, fig_spec, result):
        # Осциллограмма
        buf_osc = io.BytesIO()
        fig_osc.savefig(buf_osc, format='png', dpi=100, bbox_inches='tight')
        buf_osc.seek(0)
        osc_container.content = ft.Image(src=base64.b64encode(buf_osc.read()).decode(), width=550, height=250)
        plt.close(fig_osc)
        # Спектр
        buf_spec = io.BytesIO()
        fig_spec.savefig(buf_spec, format='png', dpi=100, bbox_inches='tight')
        buf_spec.seek(0)
        spec_container.content = ft.Image(src=base64.b64encode(buf_spec.read()).decode(), width=550, height=250)
        plt.close(fig_spec)
        
        play_btn.disabled = False
        status_text.value = f"Готово! RMS: {result.get('rms',0):.4f}"
        status_text.color = ft.Colors.GREEN
        page.update()
        if result.get('silence_detected'):
            show_snackbar(f"Обнаружена тишина! RMS: {result['rms']:.4f}")

    # ---------- ГЕНЕРАЦИЯ СИГНАЛА ----------
    def generate_signal(e):
        gen_btn.disabled = True
        play_btn.disabled = True
        page.update()
        status_text.value = "Отправка запроса на сервер..."
        status_text.color = ft.Colors.BLUE
        page.update()
        save_settings()

        def task():
            nonlocal current_audio_file
            try:
                filter_val = filter_dropdown.value
                if filter_val == 'none':
                    filter_val = None
                noise_value = 1 if noise_check.value else 0
                data = {
                    'waveform': waveform_dropdown.value,
                    'freq': float(freq_slider.value),
                    'amp': float(amp_slider.value),
                    'duration': float(duration_slider.value),
                    'add_noise': noise_value,
                    'snr': int(snr_input.value),
                    'filter': filter_val,
                    'cutoff': int(cutoff_input.value)
                }
                resp = requests.post(f"{SERVER_URL}/generate", json=data, timeout=30)
                result = resp.json()
                if result.get('success'):
                    file_resp = requests.get(f"{SERVER_URL}{result['file_url']}")
                    current_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                    current_audio_file.write(file_resp.content)
                    current_audio_file.close()

                    fig_osc = plt.Figure(figsize=(6, 2.5), dpi=100)
                    ax_osc = fig_osc.add_subplot(111)
                    ax_osc.plot(result['osc']['t'], result['osc']['y'], color='blue', linewidth=0.8)
                    ax_osc.set_xlabel("Время (с)", fontsize=8)
                    ax_osc.set_ylabel("Амплитуда", fontsize=8)
                    ax_osc.grid(True, alpha=0.3)
                    ax_osc.set_facecolor('#f8f8f8')
                    ax_osc.set_title("Осциллограмма", fontsize=9)

                    fig_spec = plt.Figure(figsize=(6, 2.5), dpi=100)
                    ax_spec = fig_spec.add_subplot(111)
                    ax_spec.plot(result['spectrum']['freqs'], result['spectrum']['amps'], color='red', linewidth=0.8)
                    ax_spec.set_xlabel("Частота (Гц)", fontsize=8)
                    ax_spec.set_ylabel("Амплитуда", fontsize=8)
                    ax_spec.grid(True, alpha=0.3)
                    ax_spec.set_facecolor('#f8f8f8')
                    ax_spec.set_title("Амплитудный спектр", fontsize=9)

                    page.update_ui(lambda: update_ui_with_plots(fig_osc, fig_spec, result))
                else:
                    show_snackbar(result.get('error', 'Неизвестная ошибка'))
            except Exception as err:
                show_snackbar(str(err))
            finally:
                gen_btn.disabled = False
                page.update()

        threading.Thread(target=task, daemon=True).start()

    # ---------- ВОСПРОИЗВЕДЕНИЕ (ДЛЯ ANDROID) ----------
    def play_audio(e):
        nonlocal audio_player, current_audio_file
        if current_audio_file and os.path.exists(current_audio_file):
            try:
                if audio_player is None:
                    audio_player = ft.Audio(release_mode=ft.AudioReleaseMode.STOP)
                    page.overlay.append(audio_player)
                audio_player.src = current_audio_file
                audio_player.volume = volume_slider.value
                audio_player.play()
                status_text.value = "Воспроизведение..."
                page.update()
            except Exception as err:
                show_snackbar(f"Ошибка воспроизведения: {err}")
        else:
            show_snackbar("Сначала сгенерируйте или загрузите аудио")

    # ---------- ЗАПИСЬ С МИКРОФОНА (ДЛЯ ANDROID) ----------
    async def record_from_microphone(e):
        nonlocal audio_recorder, current_audio_file
        if audio_recorder is None:
            audio_recorder = ft.AudioRecorder(audio_encoder=ft.AudioEncoder.WAV)
            page.overlay.append(audio_recorder)
            await page.update_async()

        status_text.value = "Запись... Говорите!"
        await page.update_async()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        filepath = temp_file.name
        temp_file.close()
        
        await audio_recorder.start_recording_async(filepath)
        await asyncio.sleep(5)
        output_path = await audio_recorder.stop_recording_async()
        print(f"Запись сохранена: {output_path}")

        current_audio_file = output_path
        await upload_and_analyze_async(output_path)

    # ---------- АНАЛИЗ АУДИО (синхронная и асинхронная части) ----------
    def _upload_and_analyze_sync(filepath):
        try:
            with open(filepath, 'rb') as f:
                resp = requests.post(f"{SERVER_URL}/analyze", files={'file': f}, timeout=30)
                return resp.json()
        except Exception as err:
            return {'success': False, 'error': str(err)}

    def _create_plots_from_result(result):
        fig_osc = plt.Figure(figsize=(6, 2.5), dpi=100)
        ax_osc = fig_osc.add_subplot(111)
        ax_osc.plot(result['osc']['t'], result['osc']['y'], color='blue', linewidth=0.8)
        ax_osc.set_xlabel("Время (с)", fontsize=8)
        ax_osc.set_ylabel("Амплитуда", fontsize=8)
        ax_osc.grid(True, alpha=0.3)
        ax_osc.set_facecolor('#f8f8f8')
        ax_osc.set_title("Осциллограмма", fontsize=9)
        
        fig_spec = plt.Figure(figsize=(6, 2.5), dpi=100)
        ax_spec = fig_spec.add_subplot(111)
        ax_spec.plot(result['spectrum']['freqs'], result['spectrum']['amps'], color='red', linewidth=0.8)
        ax_spec.set_xlabel("Частота (Гц)", fontsize=8)
        ax_spec.set_ylabel("Амплитуда", fontsize=8)
        ax_spec.grid(True, alpha=0.3)
        ax_spec.set_facecolor('#f8f8f8')
        ax_spec.set_title("Амплитудный спектр", fontsize=9)
        
        return fig_osc, fig_spec

    async def upload_and_analyze_async(filepath):
        status_text.value = "Отправка на сервер и анализ..."
        await page.update_async()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _upload_and_analyze_sync, filepath)
        if result.get('success'):
            fig_osc, fig_spec = _create_plots_from_result(result)
            update_ui_with_plots(fig_osc, fig_spec, result)
            play_btn.disabled = False
            status_text.value = f"Анализ завершён! Длительность: {result.get('duration',0):.2f}с"
            status_text.color = ft.Colors.GREEN
            await page.update_async()
        else:
            show_snackbar(result.get('error', 'Неизвестная ошибка'))

    # ---------- ЗАГРУЗКА ФАЙЛА ----------
    def load_audio_file(e):
        from tkinter import filedialog as fd
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        filename = fd.askopenfilename(filetypes=[("WAV files", "*.wav")])
        root.destroy()
        if filename:
            asyncio.run_coroutine_threadsafe(upload_and_analyze_async(filename), asyncio.get_event_loop())

    # ---------- ПРИВЯЗКА ОБРАБОТЧИКОВ ----------
    gen_btn.on_click = generate_signal
    play_btn.on_click = play_audio
    save_file_btn.on_click = lambda e: show_snackbar("Файл сохранён")
    save_png_btn.on_click = lambda e: show_snackbar("Графики сохранены")
    record_btn.on_click = lambda e: asyncio.run_coroutine_threadsafe(record_from_microphone(e), asyncio.get_event_loop())
    load_btn.on_click = load_audio_file

    # Загружаем настройки
    load_settings()

    # ---------- ПОСТРОЕНИЕ ИНТЕРФЕЙСА ----------
    left_column = ft.Column([
        ft.Text("Форма сигнала:", weight=ft.FontWeight.BOLD),
        waveform_dropdown,
        ft.Text("Частота (Гц):", weight=ft.FontWeight.BOLD),
        freq_slider,
        freq_value,
        ft.Text("Амплитуда:", weight=ft.FontWeight.BOLD),
        amp_slider,
        amp_value,
        ft.Text("Длительность (сек):", weight=ft.FontWeight.BOLD),
        duration_slider,
        duration_value,
        noise_check,
        snr_input,
        ft.Text("Аудиофильтр:", weight=ft.FontWeight.BOLD),
        filter_dropdown,
        cutoff_input,
        gen_btn,
        ft.Divider(),
        ft.Text("Анализ аудио", weight=ft.FontWeight.BOLD, size=16),
        record_btn,
        load_btn,
    ], spacing=15, width=350)

    right_column = ft.Column([
        ft.Text("Осциллограмма", weight=ft.FontWeight.BOLD, size=14),
        osc_container,
        ft.Text("Амплитудный спектр", weight=ft.FontWeight.BOLD, size=14),
        spec_container,
        ft.Row([
            play_btn,
            ft.Text("Громкость:"),
            volume_slider,
            save_file_btn,
            save_png_btn,
        ], alignment=ft.MainAxisAlignment.START, spacing=20),
        status_text,
    ], spacing=15, expand=True)

    main_row = ft.Row([
        ft.Container(left_column, padding=10, bgcolor=ft.Colors.GREY_100, border_radius=10),
        ft.VerticalDivider(),
        ft.Container(right_column, expand=True, padding=10),
    ], expand=True)

    page.add(main_row)
    status_text.value = "Готов. Запустите сервер (python server.py)"
    page.update()

    def update_ui(func):
        func()
        page.update()
    page.update_ui = update_ui

if __name__ == "__main__":
    ft.app(target=main)