import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import platform
import sys
import traceback
import shutil
import datetime

# Optional: Pillow for icon handling
try:
    from PIL import Image
    pillow_available = True
except ImportError:
    pillow_available = False


# ------------------- BACKUP & CRASH HANDLING -------------------
def get_appdata_path() -> str:
    """Return the application data path for ShinanoPOS."""
    return os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ShinanoPOS")


def backup_database(db_filename="pharmacy.db"):
    """Backup database into ShinanoPOS/backups with timestamp."""
    try:
        db_dir = get_appdata_path()
        db_path = os.path.join(db_dir, db_filename)

        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found at {db_path}")

        backup_dir = os.path.join(db_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(
            backup_dir, f"{db_filename.replace('.db','')}_backup_{timestamp}.db"
        )

        shutil.copy2(db_path, backup_file)
        print(f"[Backup] Database saved: {backup_file}")
        return backup_file

    except Exception as e:
        print(f"[Backup Error] {e}")
        return None


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception hook for crash handling, backup, and auto-restart."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Save crash details
    with open("crash_log.txt", "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        f.write("\n" + "=" * 80 + "\n")

    print("[Crash] Application crashed. See crash_log.txt")

    # Backup database before restarting
    try:
        backup_database()
    except Exception as e:
        print(f"[Crash Handler Error] Backup failed: {e}")

    try:
        messagebox.showerror("Crash Detected", "The application crashed.\nRestarting...")
    except Exception:
        pass

    # Restart the app
    python = sys.executable
    os.execl(python, python, *sys.argv)


sys.excepthook = handle_exception


# ------------------- MAIN LOGIN APPLICATION -------------------
class LoginApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shinano POS - Login")
        self.root.configure(bg="#F5F6F5")
        self.db_path = self.get_writable_db_path()
        self.conn = None

        self.set_window_icon(self.root)
        self.create_database()
        self.check_previous_crash()
        self.setup_gui()

    # ------------------- ICON -------------------
    def set_window_icon(self, window: tk.Tk):
        """Set the window/taskbar icon."""
        try:
            base_path = os.path.dirname(__file__)
            ico_path = os.path.join(base_path, "shinano.ico")
            png_path = os.path.join(base_path, "shinano.png")

            if platform.system() == "Windows" and os.path.exists(ico_path):
                window.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                try:
                    if pillow_available and not os.path.exists(ico_path):
                        Image.open(png_path).save(ico_path, format="ICO")
                        window.iconbitmap(ico_path)
                    else:
                        icon = tk.PhotoImage(file=png_path)
                        window.iconphoto(True, icon)
                except Exception as e:
                    print(f"[Icon Error] {e}")
            else:
                print("No icon file found (shinano.ico/png).")
        except Exception as e:
            print(f"[Icon Setup Error] {e}")

    # ------------------- DATABASE SETUP -------------------
    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        db_dir = get_appdata_path()
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, db_name)

    def create_database(self) -> None:
        """Create and initialize all required tables."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()

            tables = [
                """CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    role TEXT,
                    status TEXT DEFAULT 'Online'
                )""",
                """CREATE TABLE IF NOT EXISTS inventory (
                    item_id TEXT PRIMARY KEY,
                    name TEXT,
                    type TEXT,
                    retail_price REAL DEFAULT 0.0,
                    unit_price REAL DEFAULT 0.0,
                    quantity INTEGER DEFAULT 0,
                    supplier TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    items TEXT,
                    total_amount REAL DEFAULT 0.0,
                    cash_paid REAL DEFAULT 0.0,
                    change_amount REAL DEFAULT 0.0,
                    timestamp TEXT,
                    status TEXT,
                    payment_method TEXT,
                    customer_id TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS funds (
                    fund_id TEXT PRIMARY KEY,
                    type TEXT,
                    amount REAL DEFAULT 0.0,
                    timestamp TEXT,
                    user TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    name TEXT,
                    contact TEXT,
                    address TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS likes (
                    like_id TEXT PRIMARY KEY,
                    transaction_id TEXT,
                    customer_id TEXT,
                    timestamp TEXT,
                    user TEXT,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                )""",
                """CREATE TABLE IF NOT EXISTS transaction_log (
                    log_id TEXT PRIMARY KEY,
                    action TEXT,
                    details TEXT,
                    timestamp TEXT,
                    user TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS daily_sales (
                    sale_date TEXT PRIMARY KEY,
                    total_sales REAL DEFAULT 0.0,
                    unit_sales INTEGER DEFAULT 0,
                    net_profit REAL DEFAULT 0.0,
                    user TEXT
                )""",
            ]
            for sql in tables:
                cursor.execute(sql)

            # Default users
            cursor.executemany(
                "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
                [
                    ("yamato", "ycb-0001", "Drug Lord", "Online"),
                    ("kongo", "kcb-0001", "User", "Online"),
                    ("manager", "mcb-0001", "Manager", "Online"),
                ],
            )

            self.conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Database setup failed:\n{e}")
            self.root.destroy()

    # ------------------- CRASH RECOVERY -------------------
    def check_previous_crash(self):
        """Attempt to recover database from latest backup."""
        crash_log = os.path.join(os.getcwd(), "crash_log.txt")
        backup_dir = os.path.join(get_appdata_path(), "backups")

        if not (os.path.exists(crash_log) and os.path.exists(backup_dir)):
            return

        try:
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith("pharmacy_backup_") and f.endswith(".db"):
                    backups.append(os.path.join(backup_dir, f))

            if not backups:
                return

            backups.sort(key=os.path.getmtime, reverse=True)
            latest_backup = backups[0]

            if os.path.basename(latest_backup) == "pharmacy.db":
                print("[Recovery] Skipping live DB file.")
                return

            shutil.copy2(latest_backup, self.db_path)
            print(f"[Recovery] Restored database from {latest_backup}")
            messagebox.showwarning(
                "Recovery",
                f"The app crashed previously.\nDatabase restored from:\n{os.path.basename(latest_backup)}",
            )
        except Exception as e:
            print(f"[Recovery Error] {e}")

    # ------------------- AUTO BACKUP ON LOGIN -------------------
    def auto_backup_database(self):
        """Automatically back up database upon successful login and delete old backups."""
        try:
            db_dir = get_appdata_path()
            db_path = os.path.join(db_dir, "pharmacy.db")
            backup_dir = os.path.join(db_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)

            # Create new backup
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"pharmacy_backup_{timestamp}.db"
            backup_file = os.path.join(backup_dir, backup_filename)
            shutil.copy2(db_path, backup_file)
            print(f"[Auto Backup] Created {backup_filename}")

            # Auto-delete old backups (>7 days)
            now = datetime.datetime.now()
            retention_days = 7
            deleted = 0
            for f in os.listdir(backup_dir):
                if f.startswith("pharmacy_backup_") and f.endswith(".db"):
                    f_path = os.path.join(backup_dir, f)
                    try:
                        ts = f.replace("pharmacy_backup_", "").replace(".db", "")
                        f_time = datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S")
                        if (now - f_time).days > retention_days:
                            os.remove(f_path)
                            deleted += 1
                    except Exception as err:
                        print(f"[Cleanup Warning] Skipped {f}: {err}")
            if deleted:
                print(f"[Cleanup] Deleted {deleted} old backup(s).")
        except Exception as e:
            print(f"[Auto Backup Error] {e}")

    # ------------------- LOGIN GUI -------------------
    def setup_gui(self):
        win_w, win_h = 350, 300
        scr_w, scr_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.resizable(False, False)

        card = tk.Frame(self.root, bg="white", bd=1, relief="solid")
        card.place(relx=0.5, rely=0.5, anchor="center", width=320, height=260)

        tk.Label(card, text="Shinano POS Login",
                 font=("Helvetica", 14, "bold"), bg="white", fg="#2C3E50").pack(pady=10)

        self.username_entry = tk.Entry(card, font=("Helvetica", 12),
                                       bg="#F8F9FA", relief="solid", bd=1,
                                       justify="center")
        self.username_entry.pack(pady=5, ipady=4, fill="x", padx=30)
        self.add_placeholder(self.username_entry, "Enter Username")

        self.password_entry = tk.Entry(card, font=("Helvetica", 12),
                                       bg="#F8F9FA", relief="solid", bd=1,
                                       justify="center")
        self.password_entry.pack(pady=5, ipady=4, fill="x", padx=30)
        self.add_placeholder(self.password_entry, "Enter Password", is_password=True)

        self.show_pw = tk.BooleanVar(value=False)
        show_pw_cb = tk.Checkbutton(
            card, text="Show Password", variable=self.show_pw,
            bg="white", fg="#2C3E50", font=("Helvetica", 10),
            command=lambda: self.password_entry.config(
                show="" if self.show_pw.get() else "*")
        )
        show_pw_cb.pack(pady=2)

        tk.Button(card, text="Login", command=self.validate_login,
                  bg="#4DA8DA", fg="white", font=("Helvetica", 12, "bold"),
                  relief="flat", cursor="hand2").pack(pady=15, ipadx=20, ipady=4)

        self.password_entry.bind("<Return>", lambda e: self.validate_login())

    # ------------------- AUTH -------------------
    def validate_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password are required", parent=self.root)
            return

        try:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute("SELECT username, password, role FROM users WHERE username=? AND password=?",
                            (username, password))
                user = cur.fetchone()
                if user:
                    username, _, role = user

                    # Auto backup upon successful login
                    self.auto_backup_database()

                    self.redirect_to_module(username, role)
                else:
                    messagebox.showerror("Error", "Invalid username or password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Login failed:\n{e}", parent=self.root)

    def redirect_to_module(self, username: str, role: str):
        self.root.destroy()
        new_root = tk.Tk()

        if role == "Drug Lord":
            from account import AccountDashboard
            AccountDashboard(new_root, username, role, self.db_path)
        elif role == "Manager":
            from manager import ManagerDashboard
            ManagerDashboard(new_root, username, role, self.db_path)
        elif role == "User":
            from dashboard import Dashboard
            Dashboard(new_root, current_user=username, user_role=role)
        else:
            messagebox.showerror("Error", "Unknown role detected", parent=new_root)
            new_root.destroy()

        new_root.mainloop()

    # ------------------- UTILITIES -------------------
    def add_placeholder(self, entry, placeholder, is_password=False):
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                if is_password:
                    entry.config(show="*")

        def on_focus_out(event):
            if not entry.get():
                entry.insert(0, placeholder)
                if is_password:
                    entry.config(show="")

        entry.insert(0, placeholder)
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def __del__(self):
        if self.conn:
            self.conn.close()


# ------------------- MAIN -------------------
def main():
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
