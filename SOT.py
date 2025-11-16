#!/usr/bin/env python3
import time
import json
import subprocess
import psutil
from collections import defaultdict
import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

class AppUsageTracker:
    def __init__(self, interval=1, data_file="~/.app_usage_tracker.json", settings_file="~/.app_usage_tracker_settings.json"):
        self.interval = interval
        self.data_file = os.path.expanduser(data_file)
        self.settings_file = os.path.expanduser(settings_file)
        self.usage_data = defaultdict(lambda: defaultdict(float))
        self.last_app = None
        self.last_time = time.time()
        self.running = False
        self.track_thread = None
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
        self.load_data()
        self.load_settings()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    for date, apps in data.items():
                        if date not in self.usage_data:
                            date_obj = datetime.strptime(date, '%Y-%m-%d')
                            if datetime.now() - date_obj <= timedelta(days=7):
                                self.usage_data[date].update(apps)
            except (json.JSONDecodeError, IOError, ValueError):
                pass

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    self.auto_refresh = tk.BooleanVar(value=settings.get('auto_refresh', True))
                    self.dark_mode = tk.BooleanVar(value=settings.get('dark_mode', True))
            except (json.JSONDecodeError, IOError, ValueError):
                self.auto_refresh = tk.BooleanVar(value=True)
                self.dark_mode = tk.BooleanVar(value=True)
        else:
            self.auto_refresh = tk.BooleanVar(value=True)
            self.dark_mode = tk.BooleanVar(value=True)

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump({
                    'auto_refresh': self.auto_refresh.get(),
                    'dark_mode': self.dark_mode.get()
                }, f, indent=2)
            return True
        except Exception:
            return False

    def get_active_window_process(self):
        try:
            window_id = subprocess.check_output(['xdotool', 'getactivewindow'],
                                                 stderr=subprocess.DEVNULL, timeout=1).decode().strip()
            if not window_id or window_id == '0':
                return "Unknown"

            pid = subprocess.check_output(['xdotool', 'getwindowpid', window_id],
                                          stderr=subprocess.DEVNULL, timeout=1).decode().strip()
            process_name = "Unknown"
            if pid and pid != '0':
                process = psutil.Process(int(pid))
                process_name = process.name().lower()

            window_name = subprocess.check_output(['xdotool', 'getwindowname', window_id],
                                                  stderr=subprocess.DEVNULL, timeout=1).decode().strip()

            app_id = f"{window_name} [{process_name}]"
            return app_id if window_name else process_name
        except Exception:
            return "Unknown"

    def track_usage(self):
        while self.running:
            current_app = self.get_active_window_process()
            current_time = time.time()
            current_date = datetime.now().strftime('%Y-%m-%d')

            if self.last_app is not None:
                time_diff = current_time - self.last_time
                self.usage_data[current_date][self.last_app] += time_diff

            self.last_app = current_app
            self.last_time = current_time
            time.sleep(self.interval)

    def start_tracking(self):
        if not self.running:
            self.running = True
            self.track_thread = threading.Thread(target=self.track_usage, daemon=True)
            self.track_thread.start()

    def stop_tracking(self):
        self.running = False
        if self.track_thread:
            self.track_thread.join()
        self.save_data()

    def save_data(self):
        try:
            if self.last_app:
                current_date = datetime.now().strftime('%Y-%m-%d')
                self.usage_data[current_date][self.last_app] += time.time() - self.last_time
            with open(self.data_file, 'w') as f:
                current_date_obj = datetime.now()
                filtered_data = {
                    date: dict(apps) for date, apps in self.usage_data.items()
                    if (current_date_obj - datetime.strptime(date, '%Y-%m-%d')).days <= 7
                }
                json.dump(filtered_data, f, indent=2)
            return True
        except Exception:
            return False

    def delete_date(self, date):
        if date in self.usage_data:
            del self.usage_data[date]
            self.save_data()
            return True
        return False

    def get_summary(self, date=None):
        if date:
            apps = self.usage_data.get(date, {})
        else:
            current_date = datetime.now().strftime('%Y-%m-%d')
            apps = self.usage_data[current_date]
        total_time = sum(apps.values()) or 1
        sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)
        return sorted_apps, total_time

class AppUsageGUI:
    def __init__(self, root):
        self.root = root
        self.tracker = AppUsageTracker()
        self.update_interval = 1000
        self.current_view = "Applications"
        self.sort_column = None
        self.sort_reverse = False
        self.indicator = None

        self.setup_ui()
        self.tracker.start_tracking()
        self.setup_tray()
        self.update_display()

    def setup_ui(self):
        self.root.title("App Usage Tracker")
        self.root.geometry("800x600")
        self.root.configure(bg='#2c2f33')

        self.sidebar = tk.Frame(self.root, bg="#23272a", width=150)
        self.sidebar.pack(side="left", fill="y")

        tk.Label(self.sidebar, text="Tracker", font=("Helvetica", 18, "bold"), fg="white", bg="#23272a").pack(pady=20)
        tk.Button(self.sidebar, text="Applications", command=self.show_applications, bg="#7289da", fg="white",
                  relief="flat", font=("Helvetica", 14)).pack(fill="x", pady=5)
        tk.Button(self.sidebar, text="History", command=self.show_history, bg="#23272a", fg="white",
                  relief="flat", font=("Helvetica", 14)).pack(fill="x", pady=5)
        tk.Button(self.sidebar, text="Settings", command=self.show_settings, bg="#23272a", fg="white",
                  relief="flat", font=("Helvetica", 14)).pack(fill="x", pady=5)

        self.content = tk.Frame(self.root, bg="#2c2f33")
        self.content.pack(side="left", fill="both", expand=True)

        self.settings_panel = tk.Frame(self.content, bg="#2c2f33")
        tk.Checkbutton(self.settings_panel, text="Auto Refresh", variable=self.tracker.auto_refresh, bg="#2c2f33",
                       fg="white", selectcolor="#2c2f33", font=("Helvetica", 14)).pack(anchor='w', pady=10)
        tk.Checkbutton(self.settings_panel, text="Dark Mode", variable=self.tracker.dark_mode, bg="#2c2f33",
                       fg="white", selectcolor="#2c2f33", font=("Helvetica", 14), command=self.toggle_theme).pack(anchor='w', pady=10)

        # --- HISTORY PANEL SETUP (MODIFIED) ---
        self.history_panel = tk.Frame(self.content, bg="#2c2f33")
        tk.Label(self.history_panel, text="Select Date:", bg="#2c2f33", fg="white", font=("Helvetica", 14)).pack(pady=5)
        
        # Get unique dates from data, sorted newest first
        dates = sorted(list(self.tracker.usage_data.keys()), reverse=True)
        
        self.selected_date = tk.StringVar()

        if not dates:
            # If there's no data at all, just use today's date
            today = datetime.now().strftime('%Y-%m-%d')
            dates.append(today)
            self.selected_date.set(today)
        else:
            # If there is data, select the most recent date
            self.selected_date.set(dates[0])
        
        # Create the OptionMenu. The *dates unpacks the list into arguments.
        # The initial value is taken from the StringVar, preventing duplicates.
        self.date_menu = tk.OptionMenu(self.history_panel, self.selected_date, *dates, command=self.update_history)
        self.date_menu.config(bg="#40444b", fg="white", font=("Helvetica", 12))
        self.date_menu.pack(pady=5)
        tk.Entry(self.history_panel, textvariable=self.selected_date).pack(pady=5)
        tk.Button(self.history_panel, text="Delete Date", command=self.delete_date).pack(pady=5)
        # --- END OF MODIFICATION ---

        self.tree = ttk.Treeview(self.content, columns=('time', 'percentage'), selectmode='browse')
        self.tree.heading('#0', text='Application', command=lambda: self.sort_tree('#0'))
        self.tree.heading('time', text='Time Spent', command=lambda: self.sort_tree('time'))
        self.tree.heading('percentage', text='Percentage', command=lambda: self.sort_tree('percentage'))
        self.tree.column('#0', width=400)
        self.tree.column('time', width=150, anchor='e')
        self.tree.column('percentage', width=100, anchor='e')
        self.tree.pack(fill="both", expand=True)

        self.date_label = tk.Label(self.content, text=f"Date: {datetime.now().strftime('%Y-%m-%d')}, Day: {datetime.now().strftime('%A')}",
                                   bg="#2c2f33", fg="white", font=("Helvetica", 12))
        self.date_label.pack(anchor='w', pady=5, padx=10)

        self.total_label = tk.Label(self.content, text="Total tracked time: 0 hours", bg="#2c2f33", fg="white", font=("Helvetica", 14))
        self.total_label.pack(anchor='w', pady=10, padx=10)

        self.show_applications()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_tray(self):
        self.indicator = AppIndicator3.Indicator.new(
            "App Usage Tracker",
            "application-default-icon",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.create_tray_menu())

    def create_tray_menu(self):
        menu = Gtk.Menu()
        item_open = Gtk.MenuItem(label="Show")
        item_open.connect("activate", self.restore_window)
        menu.append(item_open)

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.quit_app)
        menu.append(item_quit)

        menu.show_all()
        return menu

    def restore_window(self, source):
        def _restore():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        self.root.after(0, _restore)

    def quit_app(self, source):
        self.tracker.stop_tracking()
        self.tracker.save_settings()
        self.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
        self.root.destroy()
        Gtk.main_quit()

    # --- DELETE DATE METHOD (MODIFIED) ---
    def delete_date(self):
        date_to_delete = self.selected_date.get()
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete all data for {date_to_delete}?"):
            if self.tracker.delete_date(date_to_delete):
                # Re-fetch the list of dates from the tracker data
                dates = sorted(list(self.tracker.usage_data.keys()), reverse=True)
                
                # Clear the old menu
                menu = self.date_menu['menu']
                menu.delete(0, 'end')

                if not dates:
                    # If all dates were deleted, add today's date as a placeholder
                    today = datetime.now().strftime('%Y-%m-%d')
                    menu.add_command(label=today, command=lambda d=today: self.selected_date.set(d))
                    self.selected_date.set(today)
                    self.update_history(today) # Update view to show empty state
                else:
                    # Repopulate the menu with the new list of dates
                    for date in dates:
                        menu.add_command(label=date, command=lambda d=date: self.selected_date.set(d))
                    # Set the selection to the newest available date
                    new_selection = dates[0]
                    self.selected_date.set(new_selection)
                    # self.update_history will be called automatically by the set() command,
                    # but calling it explicitly ensures the view updates if the new selection is the same as the old.
                    self.update_history(new_selection)
    # --- END OF MODIFICATION ---

    def sort_tree(self, column):
        if column == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        if column == '#0':
            items = [(self.tree.item(child, 'text'), child) for child in self.tree.get_children('')]
        else:
            items = [(self.tree.set(child, column), child) for child in self.tree.get_children('')]

        if column == '#0':
            items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)
        elif column == 'time':
            items.sort(key=lambda x: self.parse_time(x[0]), reverse=not self.sort_reverse)
        elif column == 'percentage':
            items.sort(key=lambda x: float(x[0].rstrip('%')), reverse=not self.sort_reverse)

        for index, (val, child) in enumerate(items):
            self.tree.move(child, '', index)

    def parse_time(self, time_str):
        hours = 0
        minutes = 0
        seconds = 0

        parts = time_str.split()
        for part in parts:
            if 'h' in part:
                hours = int(part.replace('h', ''))
            elif 'm' in part:
                minutes = int(part.replace('m', ''))
            elif 's' in part:
                seconds = int(part.replace('s', ''))

        return hours * 3600 + minutes * 60 + seconds

    def toggle_theme(self):
        if self.tracker.dark_mode.get():
            bg = "#2c2f33"
            fg = "#ffffff"
            sidebar_bg = "#23272a"
            button_active = "#7289da"
        else:
            bg = "#ffffff"
            fg = "#000000"
            sidebar_bg = "#e0e0e0"
            button_active = "#c0c0c0"

        self.root.configure(bg=bg)
        self.sidebar.configure(bg=sidebar_bg)
        for child in self.sidebar.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=sidebar_bg, fg=fg)
            else:
                child.configure(bg=button_active, fg=fg, font=("Helvetica", 14))
        self.content.configure(bg=bg)
        self.settings_panel.configure(bg=bg)
        for child in self.settings_panel.winfo_children():
            child.configure(bg=bg, fg=fg)
        self.history_panel.configure(bg=bg)
        for child in self.history_panel.winfo_children():
            child.configure(bg=bg, fg=fg)
        self.date_label.configure(bg=bg, fg=fg)
        self.total_label.configure(bg=bg, fg=fg)

    def show_applications(self):
        self.clear_content()
        self.current_view = "Applications"
        self.date_label.pack(anchor='w', pady=5, padx=10)
        self.tree.pack(fill="both", expand=True)
        self.total_label.pack(anchor='w', pady=10, padx=10)
        self.update_display()

    def show_history(self):
        self.clear_content()
        self.current_view = "History"
        self.history_panel.pack(fill='both', expand=True)
        self.tree.pack(fill="both", expand=True)
        self.total_label.pack(anchor='w', pady=10, padx=10)
        self.update_history(self.selected_date.get())

    def show_settings(self):
        self.clear_content()
        self.current_view = "Settings"
        self.settings_panel.pack(fill='both', expand=True)

    def clear_content(self):
        for widget in self.content.winfo_children():
            widget.pack_forget()

    def update_history(self, date):
        sorted_apps, total_time = self.tracker.get_summary(date)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for app, seconds in sorted_apps:
            hours, rem = divmod(seconds, 3600)
            minutes, secs = divmod(rem, 60)
            time_str = f"{int(hours)}h {int(minutes):02d}m {int(secs):02d}s"
            pct = (seconds / total_time) * 100
            self.tree.insert('', 'end', text=app, values=(time_str, f"{pct:.1f}%"))
        self.total_label.config(text=f"Total tracked time: {total_time / 3600:.2f} hours")

    def update_display(self):
        if self.tracker.running and self.tracker.auto_refresh.get():
            if self.current_view == "Applications":
                current_date = datetime.now().strftime('%Y-%m-%d')
                self.date_label.config(text=f"Date: {current_date}, Day: {datetime.now().strftime('%A')}")
                sorted_apps, total_time = self.tracker.get_summary(current_date)
                for item in self.tree.get_children():
                    self.tree.delete(item)
                total_seconds = sum(s for _, s in sorted_apps) or 1
                for app, seconds in sorted_apps:
                    hours, rem = divmod(seconds, 3600)
                    minutes, secs = divmod(rem, 60)
                    time_str = f"{int(hours)}h {int(minutes):02d}m {int(secs):02d}s"
                    pct = (seconds / total_seconds) * 100
                    self.tree.insert('', 'end', text=app, values=(time_str, f"{pct:.1f}%"))
                self.total_label.config(text=f"Total tracked time: {total_seconds / 3600:.2f} hours")
        self.root.after(self.update_interval, self.update_display)

    def on_close(self):
        self.root.withdraw()
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

def check_dependencies():
    try:
        subprocess.run(['xdotool', '--version'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def main():
    if not check_dependencies():
        print("Error: xdotool is not installed. Please install it with:")
        print("sudo apt install xdotool")
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()

    try:
        app = AppUsageGUI(root)
        app.restore_window(None)

        def process_tk_events():
            try:
                if not root.winfo_exists():
                    return False # GLib.SOURCE_REMOVE

                root.update()

            except tk.TclError:
                return False # Stop if window is destroyed
            return True # GLib.SOURCE_CONTINUE

        GLib.timeout_add(50, process_tk_events)

        Gtk.main()
    except Exception as e:
        print(f"Error: {str(e)}")
        Gtk.main_quit()
        sys.exit(1)

if __name__ == "__main__":
    main()

