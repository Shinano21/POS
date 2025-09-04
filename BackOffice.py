import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import json
from datetime import datetime
import os
import shutil
import threading
import psutil
import subprocess
import time
import logging

# Configure logging to console and file for persistent crash records
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("back_office.log"),
        logging.StreamHandler()
    ]
)

def get_db_path(db_name="pharmacy.db"):
    """Get or create the database path, copying from app directory if needed."""
    app_data = os.getenv('APPDATA') or os.path.expanduser("~")
    db_dir = os.path.join(app_data, "ShinanoPOS")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, db_name)
    app_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir_db = os.path.join(app_dir, db_name)

    if os.path.exists(app_dir_db) and not os.path.exists(db_path):
        try:
            shutil.copy(app_dir_db, db_path)
            logging.info(f"Copied database from {app_dir_db} to {db_path}")
        except Exception as e:
            logging.error(f"Failed to copy database: {str(e)}")
            messagebox.showerror("Error", f"Failed to copy database: {str(e)}")
    elif not os.path.exists(app_dir_db):
        logging.warning(f"Database file {app_dir_db} not found, creating new database at {db_path}")

    return db_path

class BackOfficeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pharmacy Back Office")
        self.root.geometry("800x600")
        self.root.configure(bg="#E8ECEF")
        self.db_path = get_db_path()
        try:
            self.conn = sqlite3.connect(self.db_path)
        except Exception as e:
            logging.error(f"Database connection failed: {str(e)}")
            messagebox.showerror("Error", f"Failed to connect to database: {str(e)}")
            return
        self.main_app_pid = None
        self.is_monitoring = False
        self.crash_count = 0  # Track repeated crashes
        self.last_crash_time = None  # Timestamp of last crash
        self.main_app_name = "Gems_POS.exe" if os.path.exists(os.path.join(os.path.dirname(__file__), "Gems_POS.exe")) else "Gems_POS.py"

        self.init_db()
        self.setup_gui()
        self.start_monitoring()

    def init_db(self):
        """Initialize database tables."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recovery_cart (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cart_data TEXT,
                    user TEXT,
                    timestamp DATETIME
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    item_id TEXT PRIMARY KEY,
                    name TEXT,
                    quantity INTEGER,
                    retail_price REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_sales (
                    sale_date TEXT PRIMARY KEY,
                    total_sales REAL,
                    unit_sales INTEGER,
                    net_profit REAL,
                    user TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transaction_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    details TEXT,
                    timestamp DATETIME,
                    user TEXT
                )
            """)
            self.conn.commit()
            logging.info("Database tables initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize database: {str(e)}")
            messagebox.showerror("Error", f"Failed to initialize database: {str(e)}")

    def setup_gui(self):
        """Set up the main GUI with tabs."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        header = tk.Label(
            main_frame,
            text="Pharmacy Back Office System",
            font=("Helvetica", 20, "bold"),
            bg="#4DA8DA",
            fg="white",
            pady=10
        )
        header.pack(fill="x")

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=10)

        recovery_tab = ttk.Frame(notebook)
        notebook.add(recovery_tab, text="Crash Recovery")
        self.setup_recovery_tab(recovery_tab)

        inventory_tab = ttk.Frame(notebook)
        notebook.add(inventory_tab, text="Inventory")
        self.setup_inventory_tab(inventory_tab)

        reports_tab = ttk.Frame(notebook)
        notebook.add(reports_tab, text="Reports")
        self.setup_reports_tab(reports_tab)

        logs_tab = ttk.Frame(notebook)
        notebook.add(logs_tab, text="Logs")
        self.setup_logs_tab(logs_tab)

        self.status_var = tk.StringVar(value="Monitoring Gems_POS...")
        status_bar = tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg="#E8ECEF",
            fg="#333",
            font=("Helvetica", 10),
            anchor="w",
            padx=10
        )
        status_bar.pack(fill="x", side="bottom")

    def setup_recovery_tab(self, frame):
        """Set up the Crash Recovery tab."""
        frame.configure(padding=20)
        tk.Button(
            frame,
            text="Recover Last Cart",
            command=self.recover_cart,
            bg="#4DA8DA",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)
        tk.Button(
            frame,
            text="Restart Gems_POS",
            command=self.restart_main_app,
            bg="#E74C3C",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)

    def recover_cart(self):
        """Recover the last saved cart from the database."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT cart_data, user, timestamp FROM recovery_cart ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                cart_data, user, ts = row
                cart = json.loads(cart_data)
                messagebox.showinfo(
                    "Recovery",
                    f"Recovered cart for {user} at {ts}\n\nItems:\n{json.dumps(cart, indent=2)}"
                )
            else:
                messagebox.showwarning("No Data", "No recovery data found.")
        except Exception as e:
            logging.error(f"Failed to recover cart: {str(e)}")
            messagebox.showerror("Error", f"Failed to recover cart: {str(e)}")

    def restart_main_app(self):
        """Restart the Gems_POS application."""
        try:
            main_app_path = os.path.join(os.path.dirname(__file__), self.main_app_name)
            if not os.path.exists(main_app_path):
                logging.error(f"Gems_POS not found at {main_app_path}")
                messagebox.showerror("Error", f"Gems_POS not found at {main_app_path}.")
                self.status_var.set("Error: Gems_POS not found")
                return
            if self.main_app_pid:
                try:
                    proc = psutil.Process(self.main_app_pid)
                    proc.terminate()
                    proc.wait(timeout=3)
                except psutil.NoSuchProcess:
                    pass  # Process already gone
            self.status_var.set("Launching Gems_POS...")
            cmd = [main_app_path] if self.main_app_name.endswith(".exe") else ["python", main_app_path]
            process = subprocess.Popen(cmd)
            self.main_app_pid = process.pid
            self.crash_count += 1
            current_time = time.time()
            if self.last_crash_time and (current_time - self.last_crash_time) < 300:  # 5 minutes
                if self.crash_count > 3:
                    messagebox.showwarning("Warning", "Gems_POS has crashed multiple times. Please check the application.")
            self.last_crash_time = current_time
            self.status_var.set(f"Started Gems_POS (PID: {self.main_app_pid})")
            logging.info(f"Started Gems_POS (PID: {self.main_app_pid})")
            messagebox.showinfo("Success", "Gems_POS application restarted.")
        except Exception as e:
            logging.error(f"Failed to restart Gems_POS: {str(e)}")
            messagebox.showerror("Error", f"Failed to restart Gems_POS: {str(e)}")
            self.status_var.set(f"Error restarting Gems_POS: {str(e)}")

    def monitor_main_app(self):
        """Monitor Gems_POS process and restart if crashed."""
        while self.is_monitoring:
            try:
                if self.main_app_pid:
                    proc = psutil.Process(self.main_app_pid)
                    if proc.name() not in [self.main_app_name, "python.exe", "pythonw.exe"]:
                        self.status_var.set("Gems_POS crashed! Attempting restart...")
                        logging.warning("Gems_POS process crashed (wrong process name), restarting...")
                        self.restart_main_app()
                    elif not psutil.pid_exists(self.main_app_pid):
                        self.status_var.set("Gems_POS crashed! Attempting restart...")
                        logging.warning("Gems_POS process crashed (PID missing), restarting...")
                        self.restart_main_app()
            except psutil.NoSuchProcess:
                self.status_var.set("Gems_POS crashed! Attempting restart...")
                logging.warning("Gems_POS process crashed (no such process), restarting...")
                self.restart_main_app()
            except Exception as e:
                logging.error(f"Monitoring error: {str(e)}")
                self.status_var.set(f"Monitoring error: {str(e)}")
            time.sleep(2)  # Reduced from 5 to 2 seconds for faster detection

    def start_monitoring(self):
        """Start monitoring Gems_POS."""
        self.is_monitoring = True
        main_app_path = os.path.join(os.path.dirname(__file__), self.main_app_name)
        if os.path.exists(main_app_path):
            try:
                cmd = [main_app_path] if self.main_app_name.endswith(".exe") else ["python", main_app_path]
                process = subprocess.Popen(cmd)
                self.main_app_pid = process.pid
                self.status_var.set(f"Started monitoring Gems_POS (PID: {self.main_app_pid})")
                logging.info(f"Started monitoring Gems_POS (PID: {self.main_app_pid})")
            except Exception as e:
                logging.error(f"Failed to start Gems_POS: {str(e)}")
                self.status_var.set(f"Error starting Gems_POS: {str(e)}")
        else:
            logging.error(f"Gems_POS not found at {main_app_path}")
            self.status_var.set("Error: Gems_POS not found")
        monitor_thread = threading.Thread(target=self.monitor_main_app, daemon=True)
        monitor_thread.start()

    def setup_inventory_tab(self, frame):
        """Set up the Inventory tab."""
        frame.configure(padding=20)
        tk.Button(
            frame,
            text="View Inventory",
            command=self.show_inventory,
            bg="#2ECC71",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)
        tk.Button(
            frame,
            text="Update Inventory",
            command=self.update_inventory,
            bg="#3498DB",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)

    def show_inventory(self):
        """Display inventory in a new window."""
        try:
            win = tk.Toplevel(self.root)
            win.title("Inventory List")
            win.geometry("600x400")
            tree = ttk.Treeview(win, columns=("ID", "Name", "Qty", "Price"), show="headings")
            for col in ("ID", "Name", "Qty", "Price"):
                tree.heading(col, text=col)
                tree.column(col, width=150, anchor="center")
            tree.pack(fill="both", expand=True)

            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id, name, quantity, retail_price FROM inventory")
            for row in cursor.fetchall():
                tree.insert("", "end", values=row)
        except Exception as e:
            logging.error(f"Failed to load inventory: {str(e)}")
            messagebox.showerror("Error", f"Failed to load inventory: {str(e)}")

    def update_inventory(self):
        """Open window to update inventory quantity."""
        win = tk.Toplevel(self.root)
        win.title("Update Inventory")
        win.geometry("400x300")
        tk.Label(win, text="Item ID:", font=("Helvetica", 10)).pack(pady=5)
        item_id_entry = tk.Entry(win)
        item_id_entry.pack(pady=5)
        tk.Label(win, text="New Quantity:", font=("Helvetica", 10)).pack(pady=5)
        qty_entry = tk.Entry(win)
        qty_entry.pack(pady=5)
        tk.Button(
            win,
            text="Update",
            command=lambda: self.submit_inventory_update(item_id_entry.get(), qty_entry.get(), win),
            bg="#2ECC71",
            fg="white",
            font=("Helvetica", 10)
        ).pack(pady=10)

    def submit_inventory_update(self, item_id, qty, window):
        """Update inventory quantity in the database."""
        try:
            qty = int(qty)
            cursor = self.conn.cursor()
            cursor.execute("UPDATE inventory SET quantity = ? WHERE item_id = ?", (qty, item_id))
            if cursor.rowcount > 0:
                self.conn.commit()
                messagebox.showinfo("Success", f"Updated item {item_id} to quantity {qty}")
                logging.info(f"Updated inventory: item_id={item_id}, quantity={qty}")
                window.destroy()
            else:
                messagebox.showwarning("Not Found", f"Item ID {item_id} not found")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number")
        except Exception as e:
            logging.error(f"Failed to update inventory: {str(e)}")
            messagebox.showerror("Error", f"Failed to update inventory: {str(e)}")

    def setup_reports_tab(self, frame):
        """Set up the Reports tab."""
        frame.configure(padding=20)
        tk.Button(
            frame,
            text="Daily Sales Report",
            command=self.daily_report,
            bg="#E67E22",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)

    def daily_report(self):
        """Generate and display daily sales report."""
        try:
            cursor = self.conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("SELECT * FROM daily_sales WHERE sale_date=?", (today,))
            row = cursor.fetchone()
            if row:
                sale_date, total_sales, unit_sales, net_profit, user = row
                messagebox.showinfo(
                    "Daily Report",
                    f"Date: {sale_date}\n"
                    f"Total Sales: ₱{total_sales:.2f}\n"
                    f"Units: {unit_sales}\n"
                    f"Net Profit: ₱{net_profit:.2f}\n"
                    f"User: {user}"
                )
            else:
                messagebox.showwarning("No Data", "No sales record found for today.")
        except Exception as e:
            logging.error(f"Failed to generate report: {str(e)}")
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")

    def setup_logs_tab(self, frame):
        """Set up the Logs tab."""
        frame.configure(padding=20)
        tk.Button(
            frame,
            text="View Transaction Logs",
            command=self.show_logs,
            bg="#8E44AD",
            fg="white",
            font=("Helvetica", 12),
            width=20
        ).pack(pady=10)

    def show_logs(self):
        """Display transaction logs in a new window."""
        try:
            win = tk.Toplevel(self.root)
            win.title("Transaction Logs")
            win.geometry("800x400")
            tree = ttk.Treeview(win, columns=("ID", "Action", "Details", "Timestamp", "User"), show="headings")
            for col in ("ID", "Action", "Details", "Timestamp", "User"):
                tree.heading(col, text=col)
                tree.column(col, width=150, anchor="center")
            tree.pack(fill="both", expand=True)

            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transaction_log ORDER BY timestamp DESC LIMIT 50")
            for row in cursor.fetchall():
                tree.insert("", "end", values=row)
        except Exception as e:
            logging.error(f"Failed to load logs: {str(e)}")
            messagebox.showerror("Error", f"Failed to load logs: {str(e)}")

    def __del__(self):
        """Clean up resources on exit."""
        self.is_monitoring = False
        try:
            self.conn.close()
            logging.info("Database connection closed")
        except Exception as e:
            logging.error(f"Failed to close database: {str(e)}")

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BackOfficeApp(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"Back Office failed to start: {str(e)}")
        messagebox.showerror("Error", f"Back Office failed to start: {str(e)}")