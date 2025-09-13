import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import platform
from typing import Optional
from dashboard import Dashboard
from inventory import InventoryManager
from transactions import TransactionManager
from sales_summary import SalesSummary
import sys, traceback
import shutil, datetime
from tkinter import messagebox



try:
    from PIL import Image
    pillow_available = True
except ImportError:
    pillow_available = False
# --- Backup & Crash Handling ---

def backup_database(db_filename="pharmacy.db"):
    """Backup database into ShinanoPOS/backups with timestamp."""
    try:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        db_path = os.path.join(db_dir, db_filename)

        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found at {db_path}")

        # Backups folder
        backup_dir = os.path.join(db_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(
            backup_dir,
            f"{db_filename.replace('.db','')}_backup_{timestamp}.db"
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
        f.write("\n" + "="*80 + "\n")

    print("[Crash] Application crashed. See crash_log.txt")

    # Backup DB on crash
    try:
        backup_database()
    except Exception as e:
        print(f"[Crash Handler Error] Backup failed: {e}")

    # Show error (if tkinter still alive)
    try:
        messagebox.showerror("Crash Detected", "The application crashed.\nRestarting...")
    except:
        pass

    # Restart the app immediately
    python = sys.executable
    os.execl(python, python, *sys.argv)


# Register crash handler globally
sys.excepthook = handle_exception


class LoginApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shinano POS - Login")
        self.root.geometry("300x250")
        self.root.configure(bg="#F5F6F5")
        self.set_window_icon(self.root)
        self.db_path = self.get_writable_db_path()
        self.conn = None
        self.create_database()
        if os.path.exists("crash_log.txt"):
            try:
                # Find the latest backup
                backup_dir = "db_backups"
                if os.path.exists(backup_dir):
                    backups = sorted(
                        [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".db")],
                        key=os.path.getmtime,
                        reverse=True
                    )
                    if backups:
                        latest_backup = backups[0]
                        shutil.copy2(latest_backup, self.db_path)
                        print(f"[Recovery] Restored database from {latest_backup}")
                        messagebox.showwarning(
                            "Recovery",
                            f"The app crashed last time.\nDatabase was restored from backup:\n{os.path.basename(latest_backup)}"
                        )
            except Exception as e:
                print(f"[Recovery Error] {e}")

        # Always load login screen
        self.setup_gui()


    def set_window_icon(self, window: tk.Tk):
        """Set the window and taskbar icon for the given window."""
        try:
            # Determine the path to the icon files
            base_path = os.path.dirname(__file__)
            ico_path = os.path.join(base_path, "shinano.ico")
            png_path = os.path.join(base_path, "shinano.png")

            # Check if ICO file exists for Windows taskbar
            if platform.system() == "Windows":
                if os.path.exists(ico_path):
                    window.iconbitmap(ico_path)
                elif os.path.exists(png_path) and pillow_available:
                    # Convert PNG to ICO if Pillow is available
                    try:
                        img = Image.open(png_path)
                        img.save(ico_path, format="ICO")
                        window.iconbitmap(ico_path)
                    except Exception as e:
                        print(f"Error converting PNG to ICO: {e}")
                        messagebox.showwarning("Warning", "Failed to convert icon for taskbar", parent=window)
                else:
                    # Fallback to iconphoto for PNG
                    try:
                        icon = tk.PhotoImage(file=png_path)
                        window.iconphoto(True, icon)
                    except tk.TclError as e:
                        print(f"Error loading PNG icon: {e}")
                        messagebox.showwarning("Warning", "Failed to load application icon", parent=window)
            else:
                # For non-Windows platforms, use iconphoto with PNG
                if os.path.exists(png_path):
                    icon = tk.PhotoImage(file=png_path)
                    window.iconphoto(True, icon)
                else:
                    print("Icon file (shinano.png) not found")
                    messagebox.showwarning("Warning", "Application icon not found", parent=window)
        except tk.TclError as e:
            print(f"Error setting icon: {e}")
            messagebox.showwarning("Warning", "Failed to set application icon", parent=window)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory {db_dir}: {e}")
            messagebox.showerror("Error", f"Cannot create database directory: {e}", parent=self.root)
            raise
        db_path = os.path.join(db_dir, db_name)
        return db_path

    def create_database(self) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
            backup_database(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT,
                        role TEXT,
                        status TEXT DEFAULT 'Online'
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS inventory (
                        item_id TEXT PRIMARY KEY,
                        name TEXT,
                        type TEXT,
                        retail_price REAL DEFAULT 0.0,
                        unit_price REAL DEFAULT 0.0,
                        quantity INTEGER DEFAULT 0,
                        supplier TEXT
                    )
                ''')
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'retail_price' not in columns and 'price' in columns:
                    cursor.execute("ALTER TABLE inventory RENAME COLUMN price TO retail_price")
                    print("Renamed price to retail_price in inventory table.")
                if 'unit_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN unit_price REAL DEFAULT 0.0")
                    print("Added unit_price column to inventory table.")
                if 'supplier' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN supplier TEXT")
                    print("Added supplier column to inventory table.")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        transaction_id TEXT PRIMARY KEY,
                        items TEXT,
                        total_amount REAL DEFAULT 0.0,
                        cash_paid REAL DEFAULT 0.0,
                        change_amount REAL DEFAULT 0.0,
                        timestamp TEXT,
                        status TEXT,
                        payment_method TEXT,
                        customer_id TEXT
                    )
                ''')
                cursor.execute("PRAGMA table_info(transactions)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'payment_method' not in columns:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT")
                if 'customer_id' not in columns:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN customer_id TEXT")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS funds (
                        fund_id TEXT PRIMARY KEY,
                        type TEXT,
                        amount REAL DEFAULT 0.0,
                        timestamp TEXT,
                        user TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS customers (
                        customer_id TEXT PRIMARY KEY,
                        name TEXT,
                        contact TEXT,
                        address TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS likes (
                        like_id TEXT PRIMARY KEY,
                        transaction_id TEXT,
                        customer_id TEXT,
                        timestamp TEXT,
                        user TEXT,
                        FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
                        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transaction_log (
                        log_id TEXT PRIMARY KEY,
                        action TEXT,
                        details TEXT,
                        timestamp TEXT,
                        user TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_sales (
                        sale_date TEXT PRIMARY KEY,
                        total_sales REAL DEFAULT 0.0,
                        unit_sales INTEGER DEFAULT 0,
                        net_profit REAL DEFAULT 0.0,
                        user TEXT
                    )
                ''')
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("yamato", "ycb-0001", "Drug Lord", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("kongo", "kcb-0001", "User", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                              ("manager", "mcb-0001", "Manager", "Online"))
                self.conn.commit()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to set up database: {e}", parent=self.root)
            self.root.destroy()

    def scale_size(self, size: int, root: tk.Tk) -> int:
        base_resolution = 1920
        current_width = root.winfo_screenwidth()
        scaling_factor = current_width / base_resolution
        return int(size * scaling_factor)
    
    

    def setup_gui(self):
        # Fix window size and center it
        win_w, win_h = 350, 300
        scr_w, scr_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.resizable(False, False)

        # Main card frame
        card = tk.Frame(self.root, bg="white", bd=1, relief="solid")
        card.place(relx=0.5, rely=0.5, anchor="center", width=320, height=260)

        # Title
        tk.Label(card, text="Shinano POS Login",
                font=("Helvetica", 14, "bold"),
                bg="white", fg="#2C3E50").pack(pady=10)

        # Username Entry
        self.username_entry = tk.Entry(card,
                                    font=("Helvetica", 12),
                                    bg="#F8F9FA", relief="solid", bd=1,
                                    justify="center")
        self.username_entry.pack(pady=5, ipady=4, fill="x", padx=30)
        self.add_placeholder(self.username_entry, "Enter Username")

        # Password Entry
        self.password_entry = tk.Entry(card,
                                    font=("Helvetica", 12),
                                    bg="#F8F9FA", relief="solid", bd=1,
                                    justify="center")
        self.password_entry.pack(pady=5, ipady=4, fill="x", padx=30)
        self.add_placeholder(self.password_entry, "Enter Password", is_password=True)

        # Show/Hide password
        self.show_pw = tk.BooleanVar(value=False)
        show_pw_cb = tk.Checkbutton(card, text="Show Password",
                                    variable=self.show_pw,
                                    bg="white", fg="#2C3E50",
                                    font=("Helvetica", 10),
                                    command=lambda: self.password_entry.config(
                                        show="" if self.show_pw.get() else "*"))
        show_pw_cb.pack(pady=2)

        # Login button (Bootstrap-style primary)
        login_btn = tk.Button(card, text="Login", command=self.validate_login,
                            bg="#4DA8DA", fg="white",
                            font=("Helvetica", 12, "bold"),
                            activebackground="#2C3E50", activeforeground="white",
                            relief="flat", cursor="hand2")
        login_btn.pack(pady=15, ipadx=20, ipady=4)

        # Bind Enter key
        self.password_entry.bind("<Return>", lambda e: self.validate_login())



    def validate_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password are required", parent=self.root)
            return

        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username, password, role FROM users WHERE username = ? AND password = ?",
                              (username, password))
                user = cursor.fetchone()
                if user:
                    username, _, role = user
                    self.redirect_to_module(username, role)
                else:
                    messagebox.showerror("Error", "Invalid username or password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Login failed: {e}", parent=self.root)

    def redirect_to_module(self, username: str, role: str):
        self.root.destroy()
        new_root = tk.Tk()
        self.set_window_icon(new_root)
        if role == "Drug Lord":
            self.show_account_management(new_root, username, role)
        elif role == "Manager":
            self.show_manager_dashboard(new_root, username, role)
        elif role == "User":
            Dashboard(new_root, current_user=username, user_role=role) 
        else:
            messagebox.showerror("Error", "Unknown user role", parent=new_root)
            new_root.destroy()
        new_root.mainloop()

    def return_to_login(self, current_root):
        # Backup before closing
        backup_database()  # <— direct function call, not self.backup_database()

        current_root.destroy()
        from login import main
        main()


    def show_account_management(self, root: tk.Tk, username: str, role: str):
        root.title("Admin Dashboard")

        # --- Center the dashboard ---
        win_w, win_h = 900, 600
        scr_w, scr_h = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        root.configure(bg="#ECF0F1")
        root.resizable(True, True)
        self.set_window_icon(root)

        # Larger fonts
        font_header = ("Helvetica", 20, "bold")
        font_btn = ("Helvetica", 18, "bold")

        # Header
        header = tk.Frame(root, bg="#8E44AD", height=60)
        header.pack(fill="x")
        tk.Label(header, text=f"Admin Dashboard - {username}",
                font=font_header, bg="#8E44AD", fg="white").pack(side="left", padx=20, pady=15)

        # Main content
        content = tk.Frame(root, bg="#ECF0F1")
        content.pack(fill="both", expand=True, padx=30, pady=30)

        def create_card(parent, text, command, bg_color="#4DA8DA"):
            card = tk.Frame(parent, bg="white", relief="raised", bd=2)
            card.grid_propagate(True)
            btn = tk.Button(card, text=text, command=command,
                            bg=bg_color, fg="white",
                            font=font_btn, wraplength=200,
                            relief="flat", cursor="hand2", justify="center")
            btn.pack(expand=True, fill="both", padx=20, pady=20)
            return card

        grid = tk.Frame(content, bg="#ECF0F1")
        grid.pack(expand=True, fill="both")

        card1 = create_card(grid, "👥 Manage Users",
                            lambda: self.manage_users(root, username, role), bg_color="#3498DB")
        card2 = create_card(grid, "🚪 Logout",
                            lambda: self.return_to_login(root), bg_color="#E74C3C")

        card1.grid(row=0, column=0, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")
        card2.grid(row=0, column=1, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")

        grid.grid_columnconfigure(0, weight=1, minsize=300)
        grid.grid_columnconfigure(1, weight=1, minsize=300)



    def manage_users(self, root: tk.Tk, username: str, role: str):
        manage_window = tk.Toplevel(root)
        manage_window.title("Manage Users")

        # --- Center the window ---
        win_w, win_h = 800, 500
        scr_w, scr_h = manage_window.winfo_screenwidth(), manage_window.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        manage_window.geometry(f"{win_w}x{win_h}+{x}+{y}")
        manage_window.configure(bg="#F5F6F5")
        self.set_window_icon(manage_window)

        # Bigger font
        tk.Label(manage_window, text="User Management",
                font=("Helvetica", 20, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=20)


        columns = ("Username", "Role", "Status")
        user_table = ttk.Treeview(manage_window, columns=columns, show="headings")
        for col in columns:
            user_table.heading(col, text=col)
            user_table.column(col, width=self.scale_size(150, root))
        user_table.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username, role, status FROM users")
                for user in cursor.fetchall():
                    user_table.insert("", "end", values=user)
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to load users: {e}", parent=manage_window)

        button_frame = tk.Frame(manage_window, bg="#F5F6F5")
        button_frame.pack(pady=5)

        tk.Button(button_frame, text="Add User", command=lambda: self.add_user(manage_window, user_table, root),
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Update User", command=lambda: self.update_user(manage_window, user_table, root),
                  bg="#F1C40F", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Delete User", command=lambda: self.delete_user(manage_window, user_table, username, root),
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Close", command=manage_window.destroy,
                  bg="#95A5A6", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(side=tk.LEFT, padx=5)

    def add_user(self, parent: tk.Tk, user_table: ttk.Treeview, root: tk.Tk):
        add_window = tk.Toplevel(parent)
        add_window.title("Add User")

        # --- Center window ---
        win_w, win_h = 500, 400
        scr_w, scr_h = add_window.winfo_screenwidth(), add_window.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        add_window.geometry(f"{win_w}x{win_h}+{x}+{y}")
        add_window.configure(bg="#F5F6F5")
        self.set_window_icon(add_window)

        # --- Larger fonts ---
        font_label = ("Helvetica", max(self.scale_size(18, root), 18), "bold")
        font_entry = ("Helvetica", max(self.scale_size(18, root), 18))
        font_btn   = ("Helvetica", max(self.scale_size(18, root), 18), "bold")

        # --- Username ---
        tk.Label(add_window, text="Username:", font=font_label,
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10)
        username_entry = tk.Entry(add_window, font=font_entry, width=25,
                                bg="#FFFFFF", fg="#2C3E50", relief="flat",
                                highlightthickness=1, highlightbackground="#BDC3C7")
        username_entry.pack(pady=5, ipady=6)

        # --- Password ---
        tk.Label(add_window, text="Password:", font=font_label,
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10)
        password_entry = tk.Entry(add_window, show="*", font=font_entry, width=25,
                                bg="#FFFFFF", fg="#2C3E50", relief="flat",
                                highlightthickness=1, highlightbackground="#BDC3C7")
        password_entry.pack(pady=5, ipady=6)

        # --- Role ---
        tk.Label(add_window, text="Role:", font=font_label,
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10)
        role_var = tk.StringVar(value="User")
        ttk.Combobox(add_window, textvariable=role_var,
                    values=["User", "Manager", "Drug Lord"],
                    state="readonly", font=font_entry, width=22).pack(pady=5, ipady=4)

        # --- Inner save function ---
        def save_user():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            role = role_var.get()
            if not username or not password:
                messagebox.showerror("Error", "Username and password are required", parent=add_window)
                return
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)",
                        (username, password, role, "Online")
                    )
                    self.conn.commit()
                    user_table.insert("", "end", values=(username, role, "Online"))
                    messagebox.showinfo("Success", "User added successfully", parent=add_window)
                    add_window.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Username already exists", parent=add_window)
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to add user: {e}", parent=add_window)

        # --- Buttons ---
        btn_frame = tk.Frame(add_window, bg="#F5F6F5")
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="Save", command=save_user,
                bg="#4DA8DA", fg="#FFFFFF", font=font_btn,
                activebackground="#2980B9", activeforeground="#FFFFFF",
                relief="flat", padx=20, pady=10).pack(side="left", padx=10)

        tk.Button(btn_frame, text="Cancel", command=add_window.destroy,
                bg="#E74C3C", fg="#FFFFFF", font=font_btn,
                activebackground="#C0392B", activeforeground="#FFFFFF",
                relief="flat", padx=20, pady=10).pack(side="left", padx=10)

        username_entry.focus_set()


    def update_user(self, parent: tk.Tk, user_table: ttk.Treeview, root: tk.Tk):
        selected_item = user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "Please select a user to update", parent=parent)
            return

        username = user_table.item(selected_item)["values"][0]
        update_window = tk.Toplevel(parent)
        update_window.title("Update User")

        # --- Center the window ---
        win_w, win_h = 500, 400
        scr_w, scr_h = update_window.winfo_screenwidth(), update_window.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        update_window.geometry(f"{win_w}x{win_h}+{x}+{y}")
        update_window.configure(bg="#F5F6F5")
        self.set_window_icon(update_window)

        # --- Larger fonts ---
        font_label = ("Helvetica", max(self.scale_size(18, root), 18), "bold")
        font_entry = ("Helvetica", max(self.scale_size(18, root), 18))
        font_btn   = ("Helvetica", max(self.scale_size(18, root), 18), "bold")

        # --- Header ---
        tk.Label(update_window, text=f"Updating User: {username}",
                font=font_label, bg="#F5F6F5", fg="#2C3E50").pack(pady=15)

        # --- New Password ---
        tk.Label(update_window, text="New Password:", font=font_label,
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10)
        password_entry = tk.Entry(update_window, show="*", font=font_entry, width=25,
                                bg="#FFFFFF", fg="#2C3E50", relief="flat",
                                highlightthickness=1, highlightbackground="#BDC3C7")
        password_entry.pack(pady=5, ipady=6)

        # --- Role ---
        tk.Label(update_window, text="Role:", font=font_label,
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10)
        role_var = tk.StringVar(value=user_table.item(selected_item)["values"][1])
        ttk.Combobox(update_window, textvariable=role_var,
                    values=["User", "Manager", "Drug Lord"],
                    state="readonly", font=font_entry, width=22).pack(pady=5, ipady=4)

        # --- Buttons ---
        btn_frame = tk.Frame(update_window, bg="#F5F6F5")
        btn_frame.pack(pady=20)

        def save_update():
            new_password = password_entry.get().strip()
            new_role = role_var.get()
            if not new_password:
                messagebox.showerror("Error", "Password is required", parent=update_window)
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("UPDATE users SET password = ?, role = ? WHERE username = ?",
                                  (new_password, new_role, username))
                    self.conn.commit()
                    user_table.item(selected_item, values=(username, new_role, "Online"))
                    messagebox.showinfo("Success", "User updated successfully", parent=update_window)
                    update_window.destroy()
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to update user: {e}", parent=update_window)

        tk.Button(update_window, text="Save", command=save_update,
                  bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=10)
        tk.Button(update_window, text="Cancel", command=update_window.destroy,
                  bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14, root))).pack(pady=5)

    def delete_user(self, parent: tk.Tk, user_table: ttk.Treeview, current_username: str, root: tk.Tk):
        selected_item = user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "Please select a user to delete", parent=parent)
            return

        username = user_table.item(selected_item)["values"][0]
        if username == current_username:
            messagebox.showerror("Error", "Cannot delete the currently logged-in user", parent=parent)
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete user '{username}'?", parent=parent):
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                    self.conn.commit()
                    user_table.delete(selected_item)
                    messagebox.showinfo("Success", "User deleted successfully", parent=parent)
            except sqlite3.Error as e:
                messagebox.showerror("Database Error", f"Failed to delete user: {e}", parent=parent)

    def show_manager_dashboard(self, root: tk.Tk, username: str, role: str):
        root.title("Manager Dashboard")

        # --- Center and resize ---
        win_w, win_h = 900, 600  # Bigger default size for readability
        scr_w, scr_h = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        root.configure(bg="#ECF0F1")
        root.resizable(True, True)

        self.set_window_icon(root)

        # --- Fonts (minimum size for accessibility) ---
        font_header = ("Helvetica", 20, "bold")
        font_btn = ("Helvetica", 18, "bold")

        # Header
        header = tk.Frame(root, bg="#2C3E50", height=60)
        header.pack(fill="x")
        tk.Label(header, text=f"Manager Dashboard - {username}",
                font=font_header, bg="#2C3E50", fg="white").pack(side="left", padx=20, pady=15)

        # Main content
        content = tk.Frame(root, bg="#ECF0F1")
        content.pack(fill="both", expand=True, padx=30, pady=30)

        # Card creator
        def create_card(parent, text, command, bg_color="#4DA8DA"):
            card = tk.Frame(parent, bg="white", relief="raised", bd=2)
            card.grid_propagate(True)

            btn = tk.Button(card, text=text, command=command,
                            bg=bg_color, fg="white",
                            font=font_btn, wraplength=200,
                            relief="flat", cursor="hand2", justify="center")
            btn.pack(expand=True, fill="both", padx=20, pady=20)
            return card

        # Grid layout (2x2)
        grid = tk.Frame(content, bg="#ECF0F1")
        grid.pack(expand=True, fill="both")

        card1 = create_card(grid, "📦 Inventory Management",
                            lambda: self.open_module(root, InventoryManager, username, role))
        card2 = create_card(grid, "💳 Transaction Management",
                            lambda: self.open_module(root, TransactionManager, username, role))
        card3 = create_card(grid, "📊 Sales Summary",
                            lambda: self.open_module(root, SalesSummary, username, role, db_path=self.db_path))
        card4 = create_card(grid, "🚪 Logout",
                            lambda: self.return_to_login(root), bg_color="#E74C3C")

        # Bigger cards (more padding for touch/readability)
        card1.grid(row=0, column=0, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")
        card2.grid(row=0, column=1, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")
        card3.grid(row=1, column=0, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")
        card4.grid(row=1, column=1, padx=20, pady=20, ipadx=60, ipady=60, sticky="nsew")

        # Allow equal resizing
        for i in range(2):
            grid.grid_columnconfigure(i, weight=1, minsize=250)
            grid.grid_rowconfigure(i, weight=1, minsize=200)



    def open_module(self, current_root: tk.Tk, module_class, username: str, role: str, db_path: Optional[str] = None):
        new_window = tk.Toplevel(current_root)
        self.set_window_icon(new_window)
        if module_class == SalesSummary:
            module_class(new_window, current_user=username, user_role=role, db_path=db_path)
        else:
            module_class(new_window, current_user=username, user_role=role)


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

def main():
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


