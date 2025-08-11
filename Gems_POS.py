import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import uuid
from PIL import Image, ImageTk
from typing import Optional, List, Dict, Callable
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
from pathlib import Path
import webbrowser
from datetime import datetime, date
from tkcalendar import DateEntry

class PharmacyPOS:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shinano POS")
        self.scaling_factor = self.get_scaling_factor()
        base_width = 1280
        base_height = 720
        scaled_width = int(base_width * self.scaling_factor)
        scaled_height = int(base_height * self.scaling_factor)
        self.root.geometry(f"{scaled_width}x{scaled_height}")
        self.root.configure(bg="#F5F5DC")

        try:
            icon_image = Image.open("images/shinano.png")
            icon_size = (int(32 * self.scaling_factor), int(32 * self.scaling_factor))
            icon_image = icon_image.resize(icon_size, Image.Resampling.LANCZOS)
            self.icon_image = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, self.icon_image)
        except Exception as e:
            print(f"Error loading icon: {e}")

        self.db_path = self.get_writable_db_path()
        self.conn = None
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.OperationalError as e:
            print(f"Failed to connect to database at {self.db_path}: {e}")
            messagebox.showerror("Database Error", f"Cannot access database: {e}", parent=self.root)
            self.root.quit()
            return

        self.current_user: Optional[str] = None
        self.cart: List[Dict] = []
        self.selected_item_index: Optional[int] = None
        self.discount_authenticated: bool = False
        self.discount_var = tk.BooleanVar()
        self.sidebar_visible: bool = True
        self.suggestion_window: Optional[tk.Toplevel] = None
        self.suggestion_listbox: Optional[tk.Listbox] = None
        self.customer_table: Optional[ttk.Treeview] = None

        self.style_config()
        self.create_database()
        self.initialize_inventory_with_receipt()
        self.setup_gui()
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", lambda e: self.root.attributes('-fullscreen', False))
        self.root.bind("<F1>", self.edit_quantity_window)
        self.root.bind("<F2>", self.void_selected_items)
        self.root.bind("<F3>", self.void_order)
        self.root.bind("<F4>", self.hold_transaction)
        self.root.bind("<F5>", self.view_unpaid_transactions)
        self.root.bind("<F6>", self.mode_of_payment)
        self.root.bind("<F7>", self.handle_discount_toggle_event)
        self.root.bind("<F9>", self.select_customer)
        self.root.bind("<Shift_R>", self.focus_cash_paid)


    def get_scaling_factor(self) -> float:
    
        default_dpi = 96  # Standard DPI for 100% scaling
        current_dpi = self.root.winfo_fpixels('1i')  # Pixels per inch
        scaling_factor = current_dpi / default_dpi
        # Apply scaling only for 175% or 200% (or higher)
        if scaling_factor >= 1.75:
            return scaling_factor
        return 1.0  # No scaling for < 175%

    def scale_size(self, size: int) -> int:
        """Scale a size (e.g., font size, width, height) based on the scaling factor."""
        return int(size * self.scaling_factor)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA') or os.path.expanduser("~")
        db_dir = os.path.join(app_data, "ShinanoPOS")
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory {db_dir}: {e}")
            messagebox.showerror("Error", f"Cannot create database directory: {e}", parent=self.root)
            raise

        db_path = os.path.join(db_dir, db_name)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir_db = os.path.join(app_dir, db_name)

        if os.path.exists(app_dir_db) and not os.path.exists(db_path):
            try:
                import shutil
                shutil.copy(app_dir_db, db_path)
                print(f"Copied database from {app_dir_db} to {db_path}")
            except (shutil.Error, OSError) as e:
                print(f"Error copying database: {e}")
                messagebox.showerror("Error", f"Failed to copy database: {e}", parent=self.root)
                raise
        elif not os.path.exists(app_dir_db) and not os.path.exists(db_path):
            print(f"Database not found at {app_dir_db}. A new database will be created at {db_path}")

        if os.path.exists(db_path):
            try:
                os.chmod(db_path, 0o666)
            except OSError as e:
                print(f"Error setting permissions on {db_path}: {e}")

        print(f"Database path: {db_path}")
        return db_path

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def style_config(self) -> None:
        style = ttk.Style()
        style.configure("Treeview", 
                        rowheight=self.scale_size(30), 
                        font=("Helvetica", self.scale_size(20)),
                        background="#F5F6F5",  # Soft White
                        foreground="#2C3E50",  # Dark Slate
                        fieldbackground="#F5F6F5")
        style.configure("Treeview.Heading", 
                        font=("Helvetica", self.scale_size(20), "bold"),
                        background="#1B263B",  # Deep Ocean Blue
                        foreground="#F5F6F5")  # Soft White
        style.configure("Cart.Treeview", 
                        rowheight=self.scale_size(24), 
                        font=("Helvetica", self.scale_size(16)),
                        background="#F5F6F5",  # Soft White
                        foreground="#2C3E50",  # Dark Slate
                        fieldbackground="#F5F6F5")
        style.theme_use("clam")

    def toggle_fullscreen(self, event: Optional[tk.Event] = None) -> str:
        fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not fullscreen)
        return "break"

    def create_database(self) -> None:
        try:
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
                        retail_price REAL,
                        unit_price REAL,
                        quantity INTEGER,
                        supplier TEXT
                    )
                ''')
                # Check if columns exist and add/rename if missing
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'retail_price' not in columns and 'price' in columns:
                    cursor.execute("ALTER TABLE inventory RENAME COLUMN price TO retail_price")
                    print("Renamed price to retail_price in inventory table.")
                if 'unit_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN unit_price REAL")
                    print("Added unit_price column to inventory table.")
                if 'supplier' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN supplier TEXT")
                    print("Added supplier column to inventory table.")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        transaction_id TEXT PRIMARY KEY,
                        items TEXT,
                        total_amount REAL,
                        cash_paid REAL,
                        change_amount REAL,
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
                        amount REAL,
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
                        total_sales REAL,
                        unit_sales INTEGER,
                        net_profit REAL,
                        user TEXT
                    )
                ''')
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                            ("yamato", "ycb-0001", "Drug Lord", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                            ("kongo", "kcb-0001", "User", "Online"))
                self.conn.commit()
        except sqlite3.OperationalError as e:
            print(f"SQLite error in create_database: {e}, Database path: {self.db_path}")
            messagebox.showerror("Database Error", f"Failed to create database: {e}", parent=self.root)
            raise

    def initialize_inventory_with_receipt(self):
        sample_items = [
            ("MED001", "Pain Reliever", "Medicine", 10.00, 8.00, 100, "PharmaCorp"),
            ("SUP001", "Vitamin C", "Supplement", 5.00, 4.00, 200, "HealthSupplies Inc"),
            ("DEV001", "Thermometer", "Medical Device", 15.00, 12.00, 50, "MediTech Ltd"),
        ]
        with self.conn:
            cursor = self.conn.cursor()
            for item_id, name, item_type, retail_price, unit_price, quantity, supplier in sample_items:
                cursor.execute("INSERT OR IGNORE INTO inventory (item_id, name, type, retail_price, unit_price, quantity, supplier) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (item_id, name, item_type, retail_price, unit_price, quantity, supplier))
            self.conn.commit()

    def setup_gui(self) -> None:
        self.main_frame = tk.Frame(self.root, bg="#F4E1C1")  # Sandy Beige
        self.main_frame.pack(fill="both", expand=True)
        self.show_login()
        self.root.bind("<Shift-Return>", self.handle_shift_enter_key)
        self.root.bind("<Shift_R>", self.focus_cash_paid)
        # Maximize window on startup (cross-platform)
        try:
            self.root.state('zoomed')  # Maximize window (Windows, Linux, macOS)
        except tk.TclError as e:
            print(f"Error maximizing window: {e}")
            self.root.attributes('-fullscreen', False)  # Fallback to non-fullscreen
        self.root.configure(bg="#1B263B")  # Deep Ocean Blue
        # Ensure sidebar is visible initially
        self.sidebar_visible = True
        # Force layout update
        self.root.update_idletasks()

    def focus_cash_paid(self, event: Optional[tk.Event] = None) -> None:
   
        if self.current_user and hasattr(self, 'summary_entries') and "Cash Paid " in self.summary_entries:
            cash_paid_entry = self.summary_entries["Cash Paid "]
            cash_paid_entry.focus_set()
            cash_paid_entry.select_range(0, tk.END)  # Select existing text for quick editing
        else:
            if not self.current_user:
                messagebox.showerror("Error", "You must be logged in to use this function.", parent=self.root)
            else:
                messagebox.showerror("Error", "Cash Paid field is not available.", parent=self.root)

    def handle_shift_enter_key(self, event: Optional[tk.Event] = None) -> None:
        if self.cart and self.main_frame.winfo_exists() and self.current_user:
            self.confirm_checkout()
        else:
            if not self.cart:
                messagebox.showerror("Error", "Cart is empty.", parent=self.root)

    def clear_frame(self) -> None:
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.main_frame.pack(fill="both", expand=True)
        # Hide suggestion window when clearing the frame
        self.hide_suggestion_window()


    def toggle_sidebar(self) -> None:
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            self.hamburger_btn.config(text="☰")
            self.sidebar_visible = False
            # Expand content frame to fill available space
            self.main_frame.pack_configure(fill="both", expand=True)
        else:
            self.sidebar.pack(side="left", fill="y", before=self.header)
            self.hamburger_btn.config(text="✕")
            self.sidebar_visible = True
            # Ensure main frame still fills the window
            self.main_frame.pack_configure(fill="both", expand=True)
        
        # Force layout update to prevent glitches
        self.root.update_idletasks()
        
        # Restore maximized state if applicable
        try:
            if self.root.wm_state() == 'zoomed' or self.root.attributes('-fullscreen'):
                self.root.state('zoomed')  # Ensure maximized state
            else:
                self.root.state('normal')  # Restore normal state if not maximized
        except tk.TclError as e:
            print(f"Error restoring window state: {e}")
        
        # Log for debugging
        print(f"Sidebar toggled: {'Hidden' if not self.sidebar_visible else 'Shown'}, Window state: {self.root.wm_state()}")
        
    def setup_navigation(self, parent: tk.Frame) -> None:
        self.sidebar = tk.Frame(parent, bg="#1B263B", width=200)  # Deep Ocean Blue
        self.sidebar.pack(side="left", fill="y")

        self.header = tk.Frame(parent, bg="#F4E1C1")  # Sandy Beige
        self.header.pack(side="top", fill="x", pady=8)

        self.hamburger_btn = tk.Button(self.header, text="✕", command=self.toggle_sidebar,
                                    bg="#F5F6F5", fg="#2C3E50", font=("Helvetica", 18),  # Soft White, Dark Slate
                                    activebackground="#4DA8DA", activeforeground="#F5F6F5",  # Aqua Blue, Soft White
                                    padx=8, pady=4, bd=0)
        self.hamburger_btn.pack(side="left", padx=5)

        tk.Label(self.header, text="Gem's Pharmacy", font=("Helvetica", 18, "bold"),
                bg="#F4E1C1", fg="#2C3E50").pack(side="left", padx=12)  # Sandy Beige, Dark Slate
        tk.Label(self.header, text=datetime.now().strftime("%B %d, %Y %I:%M %p PST"),
                font=("Helvetica", 12), bg="#F4E1C1", fg="#2C3E50").pack(side="left", padx=12)  # Sandy Beige, Dark Slate
        tk.Label(self.header, text=f"{self.current_user} ({self.get_user_role()})" if self.current_user else "",
                font=("Helvetica", 12), bg="#F4E1C1", fg="#2C3E50").pack(side="right", padx=12)  # Sandy Beige, Dark Slate

        nav_buttons = []
        if self.get_user_role() == "Drug Lord":
            nav_buttons = [
                ("👤 Account Management", self.show_account_management),
                ("👥 Customer Management", self.show_customer_management),
                ("🚪 Logout", self.confirm_logout),
            ]
        else:
            nav_buttons = [
                ("🏠 Dashboard", self.show_dashboard),
                ("➡️ Transactions", self.show_transactions),
                ("📦 Inventory", self.show_inventory),
                ("📊 Sales Summary", self.show_sales_summary),
                ("👥 Customer Management", self.show_customer_management),
                ("🚪 Logout", self.confirm_logout),
            ]

        for text, command in nav_buttons:
            btn = tk.Button(self.sidebar, text=text, command=command,
                            bg="#1B263B" if "Dashboard" not in text else "#4DA8DA",  # Deep Ocean Blue, Aqua Blue
                            fg="#F5F6F5", font=("Helvetica", 14),  # Soft White
                            activebackground="#4DA8DA" if "Dashboard" in text else "#2C3E50",  # Aqua Blue, Dark Slate
                            activeforeground="#F5F6F5",  # Soft White
                            padx=12, pady=8, bd=0)
            btn.pack(fill="x", pady=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#4DA8DA" if "Dashboard" in b["text"] else "#2C3E50"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#1B263B" if "Dashboard" not in b["text"] else "#4DA8DA"))

    def get_user_role(self) -> str:
        if not self.current_user:
            return ""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT role FROM users WHERE username = ?", (self.current_user,))
            role = cursor.fetchone()
            return role[0] if role else "User"

    def create_password_auth_window(self, title: str, prompt: str, callback: Callable, **kwargs) -> tk.Toplevel:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("500x400")
        window.configure(bg="#1B263B")  # Deep Ocean Blue

        auth_box = tk.Frame(window, bg="#F5F6F5", padx=20, pady=20, bd=1, relief="flat")  # Soft White
        auth_box.pack(pady=20)

        tk.Label(auth_box, text=title, font=("Helvetica", 18, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=12)  # Soft White, Dark Slate
        tk.Label(auth_box, text=prompt, font=("Helvetica", 12),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=8)  # Soft White, Dark Slate

        tk.Label(auth_box, text="Admin Password", font=("Helvetica", 14),
                bg="#F5F6F5", fg="#2C3E50").pack()  # Soft White, Dark Slate
        password_entry = tk.Entry(auth_box, show="*", font=("Helvetica", 14), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(auth_box, text="Show Password", variable=show_password_var,
                    command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                    font=("Helvetica", 12), bg="#F5F6F5", fg="#2C3E50").pack(pady=8)  # Soft White, Dark Slate

        tk.Button(auth_box, text="Authenticate",
                command=lambda: callback(password_entry.get(), window, **kwargs),
                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                padx=12, pady=8, bd=0).pack(pady=12)

        password_entry.bind("<Return>", lambda e: callback(password_entry.get(), window, **kwargs))

        return window

    def confirm_logout(self) -> None:
        if messagebox.askyesno("Confirm Logout",
                               "Are you sure you want to log out? Any unsaved cart items will be cleared.",
                               parent=self.root):
            self.cart.clear()
            self.selected_item_index = None
            self.discount_var.set(False)
            self.discount_authenticated = False
            self.current_user = None
            self.show_login()

    def show_login(self) -> None:
        self.clear_frame()
        self.current_user = None
        login_frame = tk.Frame(self.main_frame, bg="#F4E1C1", padx=20, pady=20)  # Sandy Beige
        login_frame.pack(expand=True)

        login_box = tk.Frame(login_frame, bg="#F5F6F5", padx=20, pady=20, bd=1, relief="flat")  # Soft White
        login_box.pack(pady=20)

        tk.Label(login_box, text="Login", font=("Helvetica", 18, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=12)  # Soft White, Dark Slate
        tk.Label(login_box, text="Welcome to the POS! Please enter your credentials.",
                font=("Helvetica", 12), bg="#F5F6F5", fg="#2C3E50").pack(pady=8)  # Soft White, Dark Slate

        tk.Label(login_box, text="Username", font=("Helvetica", 14),
                bg="#F5F6F5", fg="#2C3E50").pack(anchor="w")  # Soft White, Dark Slate
        username_entry = tk.Entry(login_box, font=("Helvetica", 14), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        username_entry.pack(pady=5, fill="x")

        tk.Label(login_box, text="Password", font=("Helvetica", 14),
                bg="#F5F6F5", fg="#2C3E50").pack(anchor="w")  # Soft White, Dark Slate
        password_entry = tk.Entry(login_box, show="*", font=("Helvetica", 14), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(login_box, text="Show Password", variable=show_password_var,
                    command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                    font=("Helvetica", 12), bg="#F5F6F5", fg="#2C3E50").pack(anchor="w", pady=8)  # Soft White, Dark Slate

        tk.Button(login_box, text="Login", command=lambda: self.validate_login(username_entry.get(), password_entry.get()),
                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                padx=12, pady=8, bd=0).pack(pady=12)

        username_entry.bind("<Return>", lambda e: self.validate_login(username_entry.get(), password_entry.get()))
        password_entry.bind("<Return>", lambda e: self.validate_login(username_entry.get(), password_entry.get()))
            
    def validate_login(self, username: str, password: str) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?",
                           (username, password))
            user = cursor.fetchone()
            if user:
                self.current_user = username
                if self.get_user_role() == "Drug Lord":
                    self.show_account_management()
                else:
                    self.show_dashboard()
            else:
                messagebox.showerror("Error", "Invalid credentials", parent=self.root)

    def show_dashboard(self) -> None:
        if not self.current_user:
            self.show_login()
            return
        if self.get_user_role() == "Drug Lord":
            self.show_account_management()
            return
        self.clear_frame()
        self.style_config()  # Ensure styles are applied
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=self.scale_size(20), pady=self.scale_size(20))  # Soft White
        content_frame.pack(fill="both", expand=True, padx=(self.scale_size(10), 0))

        search_container = tk.Frame(content_frame, bg="#F4E1C1", padx=self.scale_size(8), pady=self.scale_size(8))  # Sandy Beige
        search_container.pack(fill="x", pady=self.scale_size(10))

        search_frame = tk.Frame(search_container, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        search_frame.pack(fill="x", padx=self.scale_size(2), pady=self.scale_size(2))

        tk.Label(search_frame, text="Search Item:", font=("Helvetica", self.scale_size(14)),
                bg="#F5F6F5", fg="#2C3E50").pack(side="left", padx=self.scale_size(12))  # Soft White, Dark Slate

        entry_frame = tk.Frame(search_frame, bg="#F5F6F5")  # Soft White
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, self.scale_size(12)), pady=self.scale_size(5))

        self.search_entry = tk.Entry(entry_frame, font=("Helvetica", self.scale_size(14)), bg="#F4E1C1", fg="#2C3E50", bd=0, highlightthickness=0)  # Sandy Beige, Dark Slate
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=self.scale_size(5))
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
        self.search_entry.bind("<FocusOut>", lambda e: self.hide_suggestion_window())

        self.clear_btn = tk.Button(entry_frame, text="✕", command=self.clear_search,
                                bg="#F4E1C1", fg="#2C3E50", font=("Helvetica", self.scale_size(12)),  # Sandy Beige, Dark Slate
                                activebackground="#4DA8DA", activeforeground="#F5F6F5",  # Aqua Blue, Soft White
                                bd=0, padx=self.scale_size(2), pady=self.scale_size(2))
        self.clear_btn.pack(side="right", padx=(0, self.scale_size(5)))
        self.clear_btn.pack_forget()

        tk.Button(search_frame, text="🛒", command=self.select_suggestion,
                bg="#2ECC71", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Seafoam Green, Soft White
                activebackground="#27AE60", activeforeground="#F5F6F5",  # Darker Seafoam Green, Soft White
                padx=self.scale_size(8), pady=self.scale_size(4), bd=0).pack(side="left", padx=self.scale_size(5))

        if self.get_user_role() == "Drug Lord":
            tk.Button(search_frame, text="🗑️", command=lambda: self.create_password_auth_window(
                "Authenticate Deletion", "Enter admin password to delete item", self.validate_delete_item_auth),
                bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Coral Red, Soft White
                activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                padx=self.scale_size(8), pady=self.scale_size(4), bd=0).pack(side="left", padx=self.scale_size(5))

        if not self.suggestion_window:
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.wm_overrideredirect(True)
            self.suggestion_window.configure(bg="#F5F6F5")  # Soft White
            self.suggestion_window.withdraw()
            self.suggestion_listbox = tk.Listbox(self.suggestion_window, height=5, font=("Helvetica", self.scale_size(12)),
                                                bg="#F5F6F5", fg="#2C3E50", selectbackground="#4DA8DA",  # Soft White, Dark Slate, Aqua Blue
                                                selectforeground="#F5F6F5", highlightthickness=0, bd=0,  # Soft White
                                                relief="flat")
            self.suggestion_listbox.pack(fill="both", expand=True)
            self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_suggestion)
            self.suggestion_listbox.bind("<Return>", self.select_suggestion)
            self.suggestion_listbox.bind("<Up>", self.move_selection_up)
            self.suggestion_listbox.bind("<Down>", self.move_selection_down)
            self.suggestion_listbox.bind("<Motion>", self.highlight_on_hover)

        main_content = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        main_content.pack(fill="both", expand=True)
        main_content.grid_rowconfigure(0, weight=1)
        main_content.grid_columnconfigure(0, weight=3)
        main_content.grid_columnconfigure(1, weight=1)

        cart_frame = tk.Frame(main_content, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        cart_frame.grid(row=0, column=0, sticky="nsew", padx=self.scale_size(5), pady=self.scale_size(5))
        cart_frame.grid_rowconfigure(1, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        columns = ("Product", "RetailPrice", "Quantity", "Subtotal")
        headers = ("NAME", "SRP", "QTY", "SUBTOTAL")
        self.cart_table = ttk.Treeview(cart_frame, columns=columns, show="headings", style="Cart.Treeview")
        for col, head in zip(columns, headers):
            self.cart_table.heading(col, text=head)
            if col == "Product":
                width = self.scale_size(150)
            elif col == "RetailPrice":
                width = self.scale_size(100)
            elif col == "Quantity":
                width = self.scale_size(50)
            else:
                width = self.scale_size(150)
            self.cart_table.column(col, 
                                width=width,
                                anchor="center" if col != "Product" else "w",
                                stretch=True)
        self.cart_table.grid(row=1, column=0, columnspan=4, sticky="nsew")
        self.cart_table.bind("<<TreeviewSelect>>", self.on_item_select)

        scrollbar = ttk.Scrollbar(cart_frame, orient="vertical", command=self.cart_table.yview)
        scrollbar.grid(row=1, column=4, sticky="ns")
        self.cart_table.configure(yscrollcommand=scrollbar.set)
        
        self.summary_frame = tk.Frame(main_content, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        self.summary_frame.grid(row=0, column=1, sticky="ns", padx=(self.scale_size(10), 0))
        self.summary_frame.grid_propagate(False)
        self.summary_frame.configure(width=self.scale_size(300))

        fields = ["Final Total ", "Cash Paid ", "Change "]
        self.summary_entries = {}
        for field in fields:
            tk.Label(self.summary_frame, text=field, font=("Helvetica", self.scale_size(20)),
                    bg="#F5F6F5", fg="#2C3E50").pack(pady=self.scale_size(2), anchor="w")  # Soft White, Dark Slate
            entry = tk.Entry(self.summary_frame, font=("Helvetica", self.scale_size(24)), bg="#F4E1C1",
                            fg="#2C3E50", highlightthickness=1, relief="flat")  # Sandy Beige, Dark Slate
            entry.pack(pady=self.scale_size(2), fill="x", ipady=self.scale_size(5))
            self.summary_entries[field] = entry
            if field != "Cash Paid ":
                entry.config(state="readonly")
                entry.insert(0, "0.00")
            else:
                entry.insert(0, "0.00")
                entry.bind("<KeyRelease>", self.update_change)

        button_frame = tk.Frame(self.summary_frame, bg="#F5F6F5")  # Soft White
        button_frame.pack(pady=self.scale_size(10), fill="x")

        # Debug: Print applied style and scaling factor
        style = ttk.Style()
        style.configure("Cart.Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5")  # Soft White, Dark Slate
        print(f"Cart Table Font: {style.lookup('Cart.Treeview', 'font')}")
        print(f"Scaling Factor: {self.scaling_factor}")

        self.update_cart_table()

    def clear_search(self) -> None:
        self.search_entry.delete(0, tk.END)
        self.hide_suggestion_window()
        self.clear_btn.pack_forget()

    def update_suggestions(self, event: Optional[tk.Event] = None) -> None:
        query = self.search_entry.get().strip()
        if not self.suggestion_window or not self.suggestion_window.winfo_exists():
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.wm_overrideredirect(True)
            self.suggestion_window.configure(bg="#ffffff")
            self.suggestion_listbox = tk.Listbox(self.suggestion_window, height=5, font=("Helvetica", 12),
                                                bg="#ffffff", fg="#000000", selectbackground="#2ecc71",
                                                selectforeground="#ffffff", highlightthickness=0, bd=0,
                                                relief="flat")
            self.suggestion_listbox.pack(fill="both", expand=True)
            self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_suggestion)
            self.suggestion_listbox.bind("<Return>", self.select_suggestion)
            self.suggestion_listbox.bind("<Up>", self.move_selection_up)
            self.suggestion_listbox.bind("<Down>", self.move_selection_down)
            self.suggestion_listbox.bind("<Motion>", self.highlight_on_hover)

        self.suggestion_listbox.delete(0, tk.END)
        if query:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT name, retail_price, quantity, supplier FROM inventory WHERE name LIKE ?",
                            (f"%{query}%",))
                suggestions = cursor.fetchall()

                if suggestions:
                    for name, retail_price, quantity, supplier in suggestions:
                        display_text = f"{name} - ₱{retail_price:.2f} (Stock: {quantity}, Supplier: {supplier or 'Unknown'})"
                        self.suggestion_listbox.insert(tk.END, display_text)
                    search_width = self.search_entry.winfo_width()
                    self.suggestion_window.geometry(f"{search_width}x{self.suggestion_listbox.winfo_reqheight()}+{self.search_entry.winfo_rootx()}+{self.search_entry.winfo_rooty() + self.search_entry.winfo_height()}")
                    self.suggestion_window.deiconify()
                    self.clear_btn.pack(side="right", padx=(0, 5))
                else:
                    self.hide_suggestion_window()
                    self.clear_btn.pack_forget()

    def highlight_on_hover(self, event: tk.Event) -> None:
        if self.suggestion_listbox and self.suggestion_listbox.winfo_exists():
            index = self.suggestion_listbox.index(f"@{event.x},{event.y}")
            if index >= 0 and index < self.suggestion_listbox.size():
                self.suggestion_listbox.selection_clear(0, tk.END)
                self.suggestion_listbox.selection_set(index)
                self.suggestion_listbox.see(index)

    def hide_suggestion_window(self) -> None:
        if hasattr(self, 'suggestion_window') and self.suggestion_window and self.suggestion_window.winfo_exists():
            self.suggestion_window.withdraw()
        if hasattr(self, 'clear_btn') and self.clear_btn.winfo_exists():
            self.clear_btn.pack_forget()

    def move_selection_up(self, event: tk.Event) -> None:
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            current_selection = self.suggestion_listbox.curselection()
            if current_selection:
                index = current_selection[0] - 1
                if index < 0:
                    index = self.suggestion_listbox.size() - 1
                self.suggestion_listbox.selection_clear(0, tk.END)
                self.suggestion_listbox.selection_set(index)
                self.suggestion_listbox.see(index)
            elif self.suggestion_listbox.size() > 0:
                self.suggestion_listbox.selection_set(0)
                self.suggestion_listbox.see(0)

    def move_selection_down(self, event: tk.Event) -> None:
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            current_selection = self.suggestion_listbox.curselection()
            if current_selection:
                index = current_selection[0] + 1
                if index >= self.suggestion_listbox.size():
                    index = 0
                self.suggestion_listbox.selection_clear(0, tk.END)
                self.suggestion_listbox.selection_set(index)
                self.suggestion_listbox.see(index)
            elif self.suggestion_listbox.size() > 0:
                self.suggestion_listbox.selection_set(0)
                self.suggestion_listbox.see(0)

    def select_suggestion(self, event: Optional[tk.Event] = None) -> None:
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            selection = self.suggestion_listbox.curselection()
            if selection:
                selected_text = self.suggestion_listbox.get(selection[0])
                item_name = selected_text.split(" - ")[0]
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT item_id, name, retail_price, quantity FROM inventory WHERE name = ?", (item_name,))
                    item = cursor.fetchone()
                    if item:
                        if item[3] <= 0:  # Check if stock is zero
                            messagebox.showerror("Error", f"Cannot add {item[1]} to cart: Out of stock", parent=self.root)
                            return
                        for cart_item in self.cart:
                            if cart_item["id"] == item[0]:
                                if cart_item["quantity"] + 1 > item[3]:
                                    messagebox.showerror("Error", f"Cannot add more {item[1]}: Only {item[3]} in stock", parent=self.root)
                                    return
                                cart_item["quantity"] += 1
                                cart_item["subtotal"] = (cart_item["retail_price"] * cart_item["quantity"]) - \
                                                        (cart_item["retail_price"] * cart_item["quantity"] * 0.2 if cart_item.get('discount_applied', False) else 0)
                                break
                        else:
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "retail_price": item[2],
                                "quantity": 1,
                                "subtotal": item[2],
                                "discount_applied": False
                            })
                        self.update_cart_table()
                        self.search_entry.delete(0, tk.END)
                        self.hide_suggestion_window()
                        self.clear_btn.pack_forget()

    def update_change(self, event: Optional[tk.Event] = None) -> None:
        try:
            cash_paid = float(self.summary_entries["Cash Paid "].get())
            final_total = float(self.summary_entries["Final Total "].get())
            change = cash_paid - final_total
            self.summary_entries["Change "].config(state="normal")
            self.summary_entries["Change "].delete(0, tk.END)
            self.summary_entries["Change "].insert(0, f"{change:.2f}")
            self.summary_entries["Change "].config(state="readonly")
        except ValueError:
            self.summary_entries["Change "].config(state="normal")
            self.summary_entries["Change "].delete(0, tk.END)
            self.summary_entries["Change "].insert(0, "0.00")
            self.summary_entries["Change "].config(state="readonly")

    def handle_discount_toggle_event(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty. Cannot apply discount.", parent=self.root)
            return
        if self.selected_item_index is None:
            messagebox.showerror("Error", "Please select an item to apply discount.", parent=self.root)
            return
        # Toggle discount for the selected item
        item = self.cart[self.selected_item_index]
        item['discount_applied'] = not item.get('discount_applied', False)
        if item['discount_applied'] and not self.discount_authenticated:
            self.create_password_auth_window(
                "Authenticate Discount",
                f"Enter admin password to apply 20% discount to {item['name']}",
                self.validate_discount_auth,
                item_index=self.selected_item_index
            )
        else:
            self.discount_authenticated = False
            self.update_cart_table()
            self.update_discount_status_label()

    def update_discount_status_label(self) -> None:
        if hasattr(self, 'discount_status_label') and self.discount_status_label.winfo_exists():
            discounted_items = [item['name'] for item in self.cart if item.get('discount_applied', False)]
            if discounted_items:
                self.discount_status_label.config(text=f"Discount Applied to: {', '.join(discounted_items)}")
            else:
                self.discount_status_label.config(text="Discount: Not Applied")

    def validate_discount_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        item_index = kwargs.get('item_index')
        if item_index is None or not (0 <= item_index < len(self.cart)):
            window.destroy()
            messagebox.showerror("Error", "Invalid item selected for discount.", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                self.discount_authenticated = True
                self.cart[item_index]['discount_applied'] = True
                self.update_cart_table()
                self.update_discount_status_label()
                window.destroy()
                messagebox.showinfo("Success", f"Discount applied to {self.cart[item_index]['name']}", parent=self.root)
            else:
                self.cart[item_index]['discount_applied'] = False
                self.discount_authenticated = False
                self.update_cart_table()
                self.update_discount_status_label()
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_cart_table(self) -> None:
        # CORRECTED: Removed update_quantity_display call
        if hasattr(self, 'cart_table') and self.cart_table.winfo_exists():
            for item in self.cart_table.get_children():
                self.cart_table.delete(item)
            for item in self.cart:
                discount = item['retail_price'] * item['quantity'] * 0.2 if item.get('discount_applied', False) else 0
                subtotal = (item['retail_price'] * item['quantity']) - discount
                item['subtotal'] = subtotal
                display_name = f"{item['name']} (20% OFF)" if item.get('discount_applied', False) else item['name']
                self.cart_table.insert("", "end", values=(
                    display_name, f"{item['retail_price']:.2f}", item['quantity'], f"{subtotal:.2f}"
                ))
            self.update_cart_totals()



    def on_item_select(self, event: tk.Event) -> None:
        selected_item = self.cart_table.selection()
        if selected_item:
            item_index = self.cart_table.index(selected_item[0])
            if 0 <= item_index < len(self.cart):
                self.selected_item_index = item_index
            else:
                self.selected_item_index = None
        else:
            self.selected_item_index = None
    
    def edit_quantity_window(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected or cart is empty", parent=self.root)
            return
        item = self.cart[self.selected_item_index]
        window = tk.Toplevel(self.root)
        window.title(f"Edit Quantity for {item['name']}")
        window.geometry("300x200")
        window.configure(bg="#F5F5DC")

        edit_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        edit_box.pack(pady=20)

        tk.Label(edit_box, text=f"Edit Quantity for {item['name']}", font=("Helvetica", 14, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=10)
        tk.Label(edit_box, text="Quantity", font=("Helvetica", 12),
                bg="#ffffff", fg="#8B5A2B").pack()
        quantity_entry = tk.Entry(edit_box, font=("Helvetica", 12), bg="#F5F5DC")
        quantity_entry.pack(pady=5, fill="x")
        quantity_entry.insert(0, str(item["quantity"]))
        quantity_entry.focus_set()


        def update_quantity():
            try:
                new_quantity = int(quantity_entry.get())
                if new_quantity < 0:
                    messagebox.showerror("Error", "Quantity cannot be negative.", parent=window)
                    return
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    inventory_qty = cursor.fetchone()[0]
                    if new_quantity > inventory_qty:
                        messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {inventory_qty}", parent=window)
                        return
                    item["quantity"] = new_quantity
                    discount = item['retail_price'] * new_quantity * 0.2 if item.get('discount_applied', False) else 0
                    item["subtotal"] = (item["retail_price"] * new_quantity) - discount
                    if new_quantity == 0:
                        self.cart.pop(self.selected_item_index)
                    self.selected_item_index = None
                    self.update_cart_table()
                    window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid quantity.", parent=window)

        tk.Button(edit_box, text="Update", command=update_quantity,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 12),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=10)
        quantity_entry.bind("<Return>", lambda e: update_quantity())

    def update_quantity_display(self) -> None:
        if self.selected_item_index is not None and 0 <= self.selected_item_index < len(self.cart):
            self.quantity_entry.delete(0, tk.END)
            self.quantity_entry.insert(0, str(self.cart[self.selected_item_index]["quantity"]))
        else:
            self.quantity_entry.delete(0, tk.END)

    def adjust_quantity(self, event: Optional[tk.Event] = None) -> None:
        if self.selected_item_index is None or not (0 <= self.selected_item_index < len(self.cart)):
            return
        try:
            new_quantity = int(self.quantity_entry.get())
            if new_quantity < 0:
                messagebox.showerror("Error", "Quantity cannot be negative.", parent=self.root)
                self.update_quantity_display()
                return
            item = self.cart[self.selected_item_index]
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                inventory_qty = cursor.fetchone()[0]
                if new_quantity > inventory_qty:
                    messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {inventory_qty}", parent=self.root)
                    self.update_quantity_display()
                    return
                item["quantity"] = new_quantity
                discount = item['retail_price'] * new_quantity * 0.2 if item.get('discount_applied', False) else 0
                item["subtotal"] = (item["retail_price"] * new_quantity) - discount
                if new_quantity == 0:
                    self.cart.pop(self.selected_item_index)
                self.update_cart_table()
                self.selected_item_index = None
                self.quantity_entry.config(state="disabled")
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity.", parent=self.root)
            self.update_quantity_display()

    def update_cart_totals(self) -> None:
        final_total = sum((item['retail_price'] * item['quantity']) - 
                         (item['retail_price'] * item['quantity'] * 0.2 if item.get('discount_applied', False) else 0) 
                         for item in self.cart)

        if "Final Total " in self.summary_entries and self.summary_entries["Final Total "].winfo_exists():
            self.summary_entries["Final Total "].config(state="normal")
            self.summary_entries["Final Total "].delete(0, tk.END)
            self.summary_entries["Final Total "].insert(0, f"{final_total:.2f}")
            self.summary_entries["Final Total "].config(state="readonly")

        self.update_change()

    def confirm_clear_cart(self) -> None:
        if messagebox.askyesno("Confirm Clear Cart",
                               "Are you sure you want to clear the cart? This action cannot be undone.",
                               parent=self.root):
            self.cart.clear()
            self.selected_item_index = None
            self.discount_var.set(False)
            self.discount_authenticated = False
            self.update_cart_table()

    def confirm_checkout(self) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty.", parent=self.root)
            return
        try:
            cash_paid = float(self.summary_entries["Cash Paid "].get())
            final_total = float(self.summary_entries["Final Total "].get())
            if cash_paid < final_total:
                messagebox.showerror("Error", "Insufficient cash paid.", parent=self.root)
                return
            if not hasattr(self, 'current_customer_id') or not self.current_customer_id:
                if not messagebox.askyesno(
                    "No Customer Information",
                    "No customer ID is selected. This may be because the customer refused to provide information. Proceed without customer details?",
                    parent=self.root
                ):
                    self.select_customer()
                    return
            if messagebox.askyesno("Confirm Checkout", "Proceed with checkout?", parent=self.root):
                self.process_checkout(cash_paid, final_total)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid cash amount.", parent=self.root)

    def generate_transaction_id(self) -> str:
   
        current_time = datetime.now()
        month_year = current_time.strftime("%m-%Y")  # Format: MM-YYYY
        
        with self.conn:
            cursor = self.conn.cursor()
            # Query the latest transaction ID for the current month and year
            cursor.execute("""
                SELECT transaction_id 
                FROM transactions 
                WHERE transaction_id LIKE ? 
                ORDER BY transaction_id DESC 
                LIMIT 1
            """, (f"{month_year}%",))
            last_transaction = cursor.fetchone()
            
            if last_transaction:
                # Extract the sequential number from the last transaction ID
                last_seq = int(last_transaction[0][-6:])  # Last 6 digits
                new_seq = last_seq + 1
            else:
                new_seq = 1  # Start at 1 if no transactions exist for this month/year
            
            # Format the new transaction ID
            transaction_id = f"{month_year}-{new_seq:06d}"  # Ensures 6-digit padding
            return transaction_id

    def process_checkout(self, cash_paid: float, final_total: float) -> None:
        try:
            transaction_id = self.generate_transaction_id()
            items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
            change = cash_paid - final_total
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sale_date = datetime.now().strftime("%Y-%m-%d")
            payment_method = getattr(self, 'current_payment_method', 'Cash')
            customer_id = getattr(self, 'current_customer_id', None)

            # Calculate unit sales and net profit
            unit_sales = sum(item["quantity"] for item in self.cart)
            net_profit = 0.0
            with self.conn:
                cursor = self.conn.cursor()
                # Validate stock and calculate net profit
                for item in self.cart:
                    cursor.execute("SELECT retail_price, unit_price, quantity FROM inventory WHERE item_id = ?",
                                  (item["id"],))
                    result = cursor.fetchone()
                    if not result:
                        raise ValueError(f"Item {item['id']} not found in inventory")
                    retail_price, unit_price, current_quantity = result
                    if current_quantity < item["quantity"]:
                        raise ValueError(f"Insufficient stock for item {item['id']}: {current_quantity} available")
                    net_profit += (retail_price - unit_price) * item["quantity"]
                    # Decrease inventory quantity
                    cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?",
                                  (item["quantity"], item["id"]))

                # Insert transaction
                cursor.execute('''
                    INSERT INTO transactions (transaction_id, items, total_amount, cash_paid, change_amount, timestamp, status, payment_method, customer_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (transaction_id, items, final_total, cash_paid, change, timestamp, "Completed", payment_method, customer_id))

                # Update daily_sales
                cursor.execute("SELECT total_sales, unit_sales, net_profit FROM daily_sales WHERE sale_date = ?", (sale_date,))
                existing_sale = cursor.fetchone()
                if existing_sale:
                    new_total_sales = existing_sale[0] + final_total
                    new_unit_sales = existing_sale[1] + unit_sales
                    new_net_profit = existing_sale[2] + net_profit
                    cursor.execute("UPDATE daily_sales SET total_sales = ?, unit_sales = ?, net_profit = ?, user = ? WHERE sale_date = ?",
                                  (new_total_sales, new_unit_sales, new_net_profit, self.current_user, sale_date))
                else:
                    cursor.execute("INSERT INTO daily_sales (sale_date, total_sales, unit_sales, net_profit, user) VALUES (?, ?, ?, ?, ?)",
                                  (sale_date, final_total, unit_sales, net_profit, self.current_user))

                # Insert transaction log
                cursor.execute('''
                    INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                    VALUES (?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), "Checkout", f"Completed transaction {transaction_id}", timestamp, self.current_user))

                self.conn.commit()

                # Clear UI elements
                self.cart.clear()
                self.selected_item_index = None
                self.update_cart_table()
                self.discount_authenticated = False
                self.discount_var.set(False)
                self.current_payment_method = None
                self.current_customer_id = None

                if "Cash Paid " in self.summary_entries and self.summary_entries["Cash Paid "].winfo_exists():
                    self.summary_entries["Cash Paid "].delete(0, tk.END)
                    self.summary_entries["Cash Paid "].insert(0, "0.00")
                if "Change " in self.summary_entries and self.summary_entries["Change "].winfo_exists():
                    self.summary_entries["Change "].config(state="normal")
                    self.summary_entries["Change "].delete(0, tk.END)
                    self.summary_entries["Change "].insert(0, "0.00")
                    self.summary_entries["Change "].config(state="readonly")

                if hasattr(self, 'customer_label') and self.customer_label.winfo_exists():
                    self.customer_label.config(text="No Customer Selected")

                messagebox.showinfo("Success", f"Transaction completed. Change: ₱{change:.2f}", parent=self.root)

                self.generate_receipt(transaction_id, timestamp, items, final_total, cash_paid, change)
                self.check_low_inventory()

        except (sqlite3.Error, ValueError) as e:
            print(f"Debug: Error in process_checkout: {e}")
            messagebox.showerror("Error", f"Failed to process transaction: {e}", parent=self.root)
        except Exception as e:
            print(f"Debug: Unexpected error in process_checkout: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)


    def generate_receipt(self, transaction_id: str, timestamp: str, items: str, total_amount: float, cash_paid: float, change: float) -> None:
        try:
            receipt_dir = os.path.join(os.path.dirname(self.db_path), "receipts")
            os.makedirs(receipt_dir, exist_ok=True)
            receipt_path = os.path.join(receipt_dir, f"receipt_{transaction_id}.pdf")
            
            c = canvas.Canvas(receipt_path, pagesize=letter)
            c.setFont("Helvetica", 12)
            
            c.drawString(100, 750, "Shinano Pharmacy Receipt")
            c.drawString(100, 730, f"Transaction ID: {transaction_id}")
            c.drawString(100, 710, f"Date: {timestamp}")
            c.drawString(100, 690, "-" * 50)
            
            y = 670
            c.drawString(100, y, "Item | Quantity | Price | Subtotal")
            y -= 20
            
            for item_str in items.split(";"):
                item_id, qty = item_str.split(":")
                qty = int(qty)
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT name, retail_price FROM inventory WHERE item_id = ?", (item_id,))
                    item_data = cursor.fetchone()
                    if item_data:
                        name, price = item_data
                        subtotal = price * qty
                        c.drawString(100, y, f"{name} | {qty} | ₱{price:.2f} | ₱{subtotal:.2f}")
                        y -= 20
            
            c.drawString(100, y - 20, "-" * 50)
            c.drawString(100, y - 40, f"Total: ₱{total_amount:.2f}")
            c.drawString(100, y - 60, f"Cash Paid: ₱{cash_paid:.2f}")
            c.drawString(100, y - 80, f"Change: ₱{change:.2f}")
            
            c.showPage()
            c.save()
            
            print(f"Receipt generated at {receipt_path}")
        except Exception as e:
            print(f"Error generating receipt: {e}")
            messagebox.showerror("Error", f"Failed to generate receipt: {e}", parent=self.root)

    def update_cart_table(self) -> None:
        # FIXED: Removed call to update_quantity_display
        if hasattr(self, 'cart_table') and self.cart_table.winfo_exists():
            for item in self.cart_table.get_children():
                self.cart_table.delete(item)
            for item in self.cart:
                discount = item['retail_price'] * item['quantity'] * 0.2 if item.get('discount_applied', False) else 0
                subtotal = (item['retail_price'] * item['quantity']) - discount
                item['subtotal'] = subtotal
                display_name = f"{item['name']} (20% OFF)" if item.get('discount_applied', False) else item['name']
                self.cart_table.insert("", "end", values=(
                    display_name, f"{item['retail_price']:.2f}", item['quantity'], f"{subtotal:.2f}"
                ))
            self.update_cart_totals()


    def update_cart_totals(self) -> None:
        subtotal = sum((item['retail_price'] * item['quantity']) - 
                    (item['retail_price'] * item['quantity'] * 0.2 if item.get('discount_applied', False) else 0) 
                    for item in self.cart)
        final_total = subtotal  # Final total is the sum of discounted subtotals

        # Update Subtotal
        if "Subtotal " in self.summary_entries and self.summary_entries["Subtotal "].winfo_exists():
            self.summary_entries["Subtotal "].config(state="normal")
            self.summary_entries["Subtotal "].delete(0, tk.END)
            self.summary_entries["Subtotal "].insert(0, f"{subtotal:.2f}")
            self.summary_entries["Subtotal "].config(state="readonly")

        # Update Final Total
        if "Final Total " in self.summary_entries and self.summary_entries["Final Total "].winfo_exists():
            self.summary_entries["Final Total "].config(state="normal")
            self.summary_entries["Final Total "].delete(0, tk.END)
            self.summary_entries["Final Total "].insert(0, f"{final_total:.2f}")
            self.summary_entries["Final Total "].config(state="readonly")

        # Update Change
        self.update_change()
    def show_inventory(self) -> None:
        if self.get_user_role() == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        self.create_password_auth_window(
            "Authenticate Inventory Access",
            "Enter admin password to access inventory",
            self.validate_inventory_access_auth
        )

    def validate_inventory_access_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                window.destroy()
                self.display_inventory()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def display_inventory(self) -> None:
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=self.scale_size(20), pady=self.scale_size(20))  # Soft White
        content_frame.pack(fill="both", expand=True, padx=(self.scale_size(10), 0))
        content_frame.grid_rowconfigure(1, weight=1)  # Table frame expands
        content_frame.grid_rowconfigure(2, weight=0)  # Button frame stays fixed
        content_frame.grid_columnconfigure(0, weight=1)

        # Search container
        search_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        search_frame.grid(row=0, column=0, sticky="ew", pady=self.scale_size(10))

        tk.Label(search_frame, text="Search:", font=("Helvetica", self.scale_size(14)),
                bg="#F5F6F5", fg="#2C3E50").pack(side="left")  # Soft White, Dark Slate
        self.inventory_search_entry = tk.Entry(search_frame, font=("Helvetica", self.scale_size(14)), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        self.inventory_search_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
        self.inventory_search_entry.bind("<KeyRelease>", self.update_inventory_table)

        tk.Label(search_frame, text="Filter:", font=("Helvetica", self.scale_size(14)),
                bg="#F5F6F5", fg="#2C3E50").pack(side="left", padx=(self.scale_size(6), self.scale_size(5)))  # Soft White, Dark Slate
        self.type_filter_var = tk.StringVar()
        self.type_filter_combobox = ttk.Combobox(search_frame, textvariable=self.type_filter_var,
                                                values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                                                state="readonly", font=("Helvetica", self.scale_size(14)))
        self.type_filter_combobox.pack(side="left", padx=self.scale_size(5))
        self.type_filter_combobox.set("All")
        self.type_filter_combobox.bind("<<ComboboxSelected>>", self.update_inventory_table)

        tk.Button(search_frame, text="Add Item",
                command=self.show_add_item,
                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Aqua Blue, Soft White
                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                padx=self.scale_size(12), pady=self.scale_size(8), bd=0).pack(side="right", padx=self.scale_size(5))

        # Inventory table frame
        inventory_frame = tk.Frame(content_frame, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        inventory_frame.grid(row=1, column=0, sticky="nsew", pady=self.scale_size(10))
        inventory_frame.grid_rowconfigure(0, weight=1)
        inventory_frame.grid_columnconfigure(0, weight=1)

        columns = ("Name", "Type", "RetailPrice", "Quantity", "Supplier")
        headers = ("NAME", "TYPE", "RETAIL PRICE", "QUANTITY", "SUPPLIER")
        self.inventory_table = ttk.Treeview(inventory_frame, columns=columns, show="headings", style="Treeview")
        for col, head in zip(columns, headers):
            self.inventory_table.heading(col, text=head)
            if col == "Name":
                width = self.scale_size(200)
            elif col == "Type":
                width = self.scale_size(200)
            elif col == "RetailPrice":
                width = self.scale_size(150)
            elif col == "Quantity":
                width = self.scale_size(120)
            else:  # Supplier
                width = self.scale_size(200)
            self.inventory_table.column(col, 
                                    width=width,
                                    anchor="center" if col != "Name" else "w",
                                    stretch=True)
        self.inventory_table.grid(row=0, column=0, sticky="nsew")

        # Add vertical scrollbar
        scrollbar = ttk.Scrollbar(inventory_frame, orient="vertical", command=self.inventory_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.inventory_table.configure(yscrollcommand=scrollbar.set)

        # Button frame for Update and Delete buttons
        button_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        button_frame.grid(row=2, column=0, sticky="ew", pady=self.scale_size(10))

        self.update_item_btn = tk.Button(button_frame, text="Update Item",
                                        command=self.show_update_item_from_selection,
                                        bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Aqua Blue, Soft White
                                        activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                        padx=self.scale_size(12), pady=self.scale_size(8), bd=0, state="disabled")
        self.update_item_btn.grid(row=0, column=0, padx=self.scale_size(5), sticky="w")

        self.delete_item_btn = tk.Button(button_frame, text="Delete Item",
                                        command=self.confirm_delete_item,
                                        bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Coral Red, Soft White
                                        activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                        padx=self.scale_size(12), pady=self.scale_size(8), bd=0, state="disabled")
        self.delete_item_btn.grid(row=0, column=1, padx=self.scale_size(5), sticky="w")

        # Bind right-click for update and double-click for delete
        self.inventory_table.bind("<Button-3>", self.on_inventory_right_click)
        self.inventory_table.bind("<Double-1>", lambda e: self.confirm_delete_item())
        self.inventory_table.bind("<<TreeviewSelect>>", self.on_inventory_select)

        # Apply Treeview styling
        style = ttk.Style()
        style.configure("Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5")  # Soft White, Dark Slate

        self.update_inventory_table()
        self.root.update_idletasks()

    def confirm_delete_item(self) -> None:
        selected_item = self.inventory_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        item_name = self.inventory_table.item(selected_item)["values"][0]
        if messagebox.askyesno("Confirm Deletion",
                              f"Are you sure you want to delete '{item_name}'? This action cannot be undone.",
                              parent=self.root):
            self.create_password_auth_window(
                "Authenticate Deletion",
                "Enter admin password to delete item",
                self.validate_delete_item_auth,
                selected_item=selected_item
            )

    def validate_delete_item_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                item_name = self.inventory_table.item(selected_item)["values"][0]
                cursor.execute("SELECT item_id FROM inventory WHERE name = ?", (item_name,))
                item_id = cursor.fetchone()[0]
                cursor.execute("DELETE FROM inventory WHERE item_id = ?", (item_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Delete Item", f"Deleted item {item_id}: {item_name}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_markup(self, unit_price_entry: tk.Entry, retail_price_entry: tk.Entry, markup_label: tk.Label, profitability_label: tk.Label, error_label: tk.Label) -> None:
        try:
            unit_price = float(unit_price_entry.get() or 0)
            retail_price = float(retail_price_entry.get() or 0)
            if unit_price > 0:
                markup = ((retail_price - unit_price) / unit_price) * 100
                markup_label.config(text=f"{markup:.2f}%")
                if markup > 0:
                    profitability_label.config(text="Profitable", fg="#6F4E37")
                elif markup == 0:
                    profitability_label.config(text="Break-even", fg="#D3C7A2")
                else:
                    profitability_label.config(text="Not Profitable", fg="#3C2F2F")
            else:
                markup_label.config(text="0.00%")
                profitability_label.config(text="N/A", fg="#2C1B18")
            error_label.config(text="")
        except ValueError:
            markup_label.config(text="0.00%")
            profitability_label.config(text="N/A", fg="#2C1B18")
            error_label.config(text="Enter valid prices", fg="#3C2F2F")



    def show_add_item(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New Item to Inventory")
        window.geometry("600x450")  # Increased width for 2-column layout
        window.configure(bg="#F5F5DC")

        add_box = tk.Frame(window, bg="#FFF8E7", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20, padx=20, fill="both", expand=True)

        tk.Label(add_box, text="Add New Item to Inventory", font=("Helvetica", 18, "bold"),
                bg="#FFF8E7", fg="#2C1B18").grid(row=0, column=0, columnspan=4, pady=15)

        # Fields matching show_update_item, excluding Type which is handled separately
        fields = ["Item ID (Barcode)", "Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
        entries = {}
        field_indices = {
            "Item ID (Barcode)": 0,
            "Name": 1,
            "Unit Price": 4,
            "Retail Price": 3,
            "Quantity": 5,
            "Supplier": 6
        }
        
        for i, field in enumerate(fields):
            row = (i // 2) + 1  # Calculate row (2 fields per row)
            col = (i % 2) * 2   # Calculate column (0 or 2)
            
            frame = tk.Frame(add_box, bg="#FFF8E7")
            frame.grid(row=row, column=col, columnspan=2, sticky="ew", pady=5)
            
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry
            if field == "Item ID (Barcode)":
                entry.insert(0, f"ITEM-{str(uuid.uuid4())[:8]}")
                entry.config(state="readonly")

        next_row = (len(fields) + 1) // 2 + 1

        markup_frame = tk.Frame(add_box, bg="#FFF8E7")
        markup_frame.grid(row=next_row, column=0, columnspan=2, sticky="ew", pady=5)
        tk.Label(markup_frame, text="Markup %", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
        markup_label = tk.Label(markup_frame, text="0.00%", font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18", width=10, anchor="w")
        markup_label.pack(side="left", fill="x", expand=True, padx=5)

        profitability_frame = tk.Frame(add_box, bg="#FFF8E7")
        profitability_frame.grid(row=next_row, column=2, columnspan=2, sticky="ew", pady=5)
        tk.Label(profitability_frame, text="Profitability", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
        profitability_label = tk.Label(profitability_frame, text="N/A", font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18", width=15, anchor="w")
        profitability_label.pack(side="left", fill="x", expand=True, padx=5)

        type_frame = tk.Frame(add_box, bg="#FFF8E7")
        type_frame.grid(row=next_row + 1, column=0, columnspan=4, sticky="ew", pady=5)
        tk.Label(type_frame, text="Type", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack()
        type_var = tk.StringVar(value="Medicine")
        ttk.Combobox(type_frame, textvariable=type_var,
                    values=["Medicine", "Supplement", "Medical Device", "Beverage", 
                            "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                    state="readonly", font=("Helvetica", 14)).pack(fill="x", pady=5)

        price_error_label = tk.Label(add_box, text="", font=("Helvetica", 12), bg="#FFF8E7", fg="#3C2F2F")
        price_error_label.grid(row=next_row + 2, column=0, columnspan=4, pady=5)

        def validate_and_update(event: Optional[tk.Event] = None) -> None:
            try:
                retail_price = float(entries["Retail Price"].get()) if entries["Retail Price"].get().strip() else 0.0
                unit_price = float(entries["Unit Price"].get()) if entries["Unit Price"].get().strip() else 0.0
                if retail_price <= unit_price and retail_price != 0.0:
                    price_error_label.config(text="Retail Price must be greater than Unit Price", fg="#3C2F2F")
                else:
                    price_error_label.config(text="")
            except ValueError:
                price_error_label.config(text="Invalid price format", fg="#3C2F2F")
            self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

        entries["Retail Price"].bind("<KeyRelease>", validate_and_update)
        entries["Unit Price"].bind("<KeyRelease>", validate_and_update)

        # Initial markup calculation
        self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

        button_frame = tk.Frame(add_box, bg="#FFF8E7")
        button_frame.grid(row=next_row + 3, column=0, columnspan=4, pady=15)
        tk.Button(button_frame, text="Add Item",
                command=lambda: self.add_item(
                    entries["Item ID (Barcode)"].get(),
                    entries["Name"].get(),
                    type_var.get(),
                    entries["Retail Price"].get(),
                    entries["Unit Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    window
                ),
                bg="#6F4E37", fg="#FFF8E7", font=("Helvetica", 14),
                activebackground="#8B5A2B", activeforeground="#FFF8E7",
                padx=12, pady=8, bd=0).pack()

        add_box.columnconfigure(0, weight=1)
        add_box.columnconfigure(2, weight=1)

    def add_item(self, item_id: str, name: str, item_type: str, retail_price: str, unit_price: str, quantity: str, supplier: str, window: tk.Toplevel) -> None:
        try:
            retail_price = float(retail_price) if retail_price.strip() else 0.0
            unit_price = float(unit_price) if unit_price.strip() else 0.0  # Allow optional unit_price
            quantity = int(quantity) if quantity.strip() else 0
            if not all([name, item_type]):
                messagebox.showerror("Error", "Name and Type are required", parent=self.root)
                return
            if retail_price <= 0:
                messagebox.showerror("Error", "Retail Price must be greater than zero", parent=self.root)
                return
            if unit_price < 0:
                messagebox.showerror("Error", "Unit Price cannot be negative", parent=self.root)
                return
            if quantity < 0:
                messagebox.showerror("Error", "Quantity cannot be negative", parent=self.root)
                return
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())

            # Debugging: Log values before insertion
            print(f"Inserting into inventory: item_id={item_id}, name={name}, type={item_type}, "
                f"retail_price={retail_price}, unit_price={unit_price}, quantity={quantity}, supplier={supplier}")

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inventory (item_id, name, type, retail_price, unit_price, quantity, supplier) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (item_id, name, item_type, retail_price, unit_price, quantity, supplier))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Add Item", f"Added item {item_id}: {name}, {quantity} units, Supplier: {supplier}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()

                # Debugging: Verify insertion
                cursor.execute("SELECT item_id, name, type, retail_price, unit_price, quantity, supplier FROM inventory WHERE item_id = ?", (item_id,))
                result = cursor.fetchone()
                print(f"Inserted record: {result}")

                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item added successfully", parent=self.root)
                if quantity <= 5:
                    self.check_low_inventory()
        except ValueError:
            messagebox.showerror("Error", "Invalid retail price, unit price, or quantity", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)


    def on_inventory_right_click(self, event: tk.Event) -> None:
        # Check if exactly one item is selected
        selected = self.inventory_table.selection()
        if len(selected) == 1:
            self.show_update_item_from_selection()
        else:
            messagebox.showinfo("Selection Error", "Please select exactly one item to update.", parent=self.root)

    def show_update_item_from_selection(self) -> None:
        selected_item = self.inventory_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        item_id = selected_item[0]  # Get the item_id from the Treeview's iid
        self.show_update_item(item_id)

    def show_update_item(self, item_id: str) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id, name, type, retail_price, unit_price, quantity, supplier FROM inventory WHERE item_id = ?", (item_id,))
            item = cursor.fetchone()
            if item:
                window = tk.Toplevel(self.root)
                window.title("Update Item")
                window.geometry("600x450")  # Increased width for 2-column layout
                window.configure(bg="#F5F5DC")

                update_box = tk.Frame(window, bg="#FFF8E7", padx=20, pady=20, bd=1, relief="flat")
                update_box.pack(pady=20, padx=20, fill="both", expand=True)

                tk.Label(update_box, text="Update Item in Inventory", font=("Helvetica", 18, "bold"),
                         bg="#FFF8E7", fg="#2C1B18").grid(row=0, column=0, columnspan=4, pady=15)

                fields = ["Item ID (Barcode)", "Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
                entries = {}
                field_indices = {
                    "Item ID (Barcode)": 0,
                    "Name": 1,
                    "Unit Price": 4,
                    "Retail Price": 3,
                    "Quantity": 5,
                    "Supplier": 6
                }
                for i, field in enumerate(fields):
                    row = (i // 2) + 1  # Calculate row (2 fields per row)
                    col = (i % 2) * 2   # Calculate column (0 or 2)
                    
                    frame = tk.Frame(update_box, bg="#FFF8E7")
                    frame.grid(row=row, column=col, columnspan=2, sticky="ew", pady=5)
                    
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18")
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entries[field] = entry
                    value = item[field_indices[field]] if field_indices[field] < len(item) and item[field_indices[field]] is not None else ""
                    entry.insert(0, str(value))

                next_row = (len(fields) + 1) // 2 + 1

                markup_frame = tk.Frame(update_box, bg="#FFF8E7")
                markup_frame.grid(row=next_row, column=0, columnspan=2, sticky="ew", pady=5)
                tk.Label(markup_frame, text="Markup %", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
                markup_label = tk.Label(markup_frame, text="0.00%", font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18", width=10, anchor="w")
                markup_label.pack(side="left", fill="x", expand=True, padx=5)

                profitability_frame = tk.Frame(update_box, bg="#FFF8E7")
                profitability_frame.grid(row=next_row, column=2, columnspan=2, sticky="ew", pady=5)
                tk.Label(profitability_frame, text="Profitability", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
                profitability_label = tk.Label(profitability_frame, text="N/A", font=("Helvetica", 14), bg="#F5F5DC", fg="#2C1B18", width=15, anchor="w")
                profitability_label.pack(side="left", fill="x", expand=True, padx=5)

                type_frame = tk.Frame(update_box, bg="#FFF8E7")
                type_frame.grid(row=next_row + 1, column=0, columnspan=4, sticky="ew", pady=5)
                tk.Label(type_frame, text="Type", font=("Helvetica", 14), bg="#FFF8E7", fg="#2C1B18").pack()
                type_var = tk.StringVar(value=item[2] if item[2] else "Medicine")
                ttk.Combobox(type_frame, textvariable=type_var,
                             values=["Medicine", "Supplement", "Medical Device", "Beverage", 
                                     "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                             state="readonly", font=("Helvetica", 14)).pack(fill="x", pady=5)

                price_error_label = tk.Label(update_box, text="", font=("Helvetica", 12), bg="#FFF8E7", fg="#3C2F2F")
                price_error_label.grid(row=next_row + 2, column=0, columnspan=4, pady=5)

                def validate_and_update(event: Optional[tk.Event] = None) -> None:
                    # Validate prices
                    try:
                        retail_price = float(entries["Retail Price"].get()) if entries["Retail Price"].get().strip() else 0.0
                        unit_price = float(entries["Unit Price"].get()) if entries["Unit Price"].get().strip() else 0.0
                        if retail_price <= unit_price and retail_price != 0.0:
                            price_error_label.config(text="Retail Price must be greater than Unit Price", fg="#3C2F2F")
                        else:
                            price_error_label.config(text="")
                    except ValueError:
                        price_error_label.config(text="Invalid price format", fg="#3C2F2F")
                    # Update markup and profitability
                    self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

                # Initial markup calculation
                self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

                entries["Retail Price"].bind("<KeyRelease>", validate_and_update)
                entries["Unit Price"].bind("<KeyRelease>", validate_and_update)

                button_frame = tk.Frame(update_box, bg="#FFF8E7")
                button_frame.grid(row=next_row + 3, column=0, columnspan=4, pady=15)
                tk.Button(button_frame, text="Update Item",
                          command=lambda: self.update_item(
                              entries["Item ID (Barcode)"].get(),
                              entries["Name"].get(),
                              type_var.get(),
                              entries["Retail Price"].get(),
                              entries["Unit Price"].get(),
                              entries["Quantity"].get(),
                              entries["Supplier"].get(),
                              item[0],
                              window
                          ),
                          bg="#6F4E37", fg="#FFF8E7", font=("Helvetica", 14),
                          activebackground="#8B5A2B", activeforeground="#FFF8E7",
                          padx=12, pady=8, bd=0).pack()

                update_box.columnconfigure(0, weight=1)
                update_box.columnconfigure(2, weight=1)
            else:
                messagebox.showerror("Error", f"Item with ID {item_id} not found", parent=self.root)

    def update_item(self, item_id: str, name: str, item_type: str, retail_price: str, unit_price: str, quantity: str, supplier: str, original_item_id: str, window: tk.Toplevel) -> None:
        try:
            retail_price = float(retail_price) if retail_price.strip() else 0.0
            unit_price = float(unit_price) if unit_price.strip() else 0.0  # Allow optional unit_price
            quantity = int(quantity) if quantity.strip() else 0
            if retail_price <= 0:
                messagebox.showerror("Error", "Retail Price must be greater than zero", parent=self.root)
                return
            if unit_price < 0:
                messagebox.showerror("Error", "Unit Price cannot be negative", parent=self.root)
                return
            if quantity < 0:
                messagebox.showerror("Error", "Quantity cannot be negative", parent=self.root)
                return
            if not all([name, item_type]):
                messagebox.showerror("Error", "Name and Type are required", parent=self.root)
                return
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else original_item_id
            with self.conn:
                cursor = self.conn.cursor()
                if item_id != original_item_id:
                    cursor.execute("SELECT item_id FROM inventory WHERE item_id = ?", (item_id,))
                    if cursor.fetchone():
                        messagebox.showerror("Error", "Item ID already exists", parent=self.root)
                        return
                cursor.execute("""
                    UPDATE inventory
                    SET item_id = ?, name = ?, type = ?, retail_price = ?, unit_price = ?, quantity = ?, supplier = ?
                    WHERE item_id = ?
                """, (item_id, name, item_type, retail_price, unit_price, quantity, supplier, original_item_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Update Item", f"Updated item {item_id}: {name}, {quantity} units, Retail Price: {retail_price:.2f}, Supplier: {supplier}",
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", f"Item '{name}' updated successfully", parent=self.root)
                # Check for low inventory after updating
                if quantity <= 5:
                    self.check_low_inventory()
        except ValueError:
            messagebox.showerror("Error", "Invalid retail price, unit price, or quantity", parent=self.root)
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to update item: {e}", parent=self.root)


    def on_inventory_select(self, event: Optional[tk.Event] = None) -> None:
        selected = self.inventory_table.selection()
        if selected:
            self.update_item_btn.config(state="normal")
            self.delete_item_btn.config(state="normal")
        else:
            self.update_item_btn.config(state="disabled")
            self.delete_item_btn.config(state="disabled")

    def check_low_inventory(self) -> None:
        try:
            threshold = 10  # Define low stock threshold (adjustable)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT item_id, name, quantity FROM inventory WHERE quantity <= ?", (threshold,))
                low_items = cursor.fetchall()
                
                if low_items:
                    message = "The following items are low in stock:\n\n"
                    for item_id, name, quantity in low_items:
                        message += f"{name} (ID: {item_id}) - Quantity: {quantity}\n"
                    messagebox.showwarning("Low Inventory Alert", message, parent=self.root)
                # Optionally, log the check in transaction_log
                cursor.execute(
                    "INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "Check Inventory", f"Checked low inventory, found {len(low_items)} items",
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user or "System")
                )
                self.conn.commit()
        except sqlite3.Error as e:
            print(f"Database error in check_low_inventory: {e}")
            messagebox.showerror("Database Error", f"Failed to check inventory: {e}", parent=self.root)
        except Exception as e:
            print(f"Unexpected error in check_low_inventory: {e}")
            messagebox.showerror("Error", f"Unexpected error checking inventory: {e}", parent=self.root)
    

    def update_inventory_table(self, event: Optional[tk.Event] = None) -> None:
        # Clear existing items in the Treeview
        for item in self.inventory_table.get_children():
            self.inventory_table.delete(item)
        
        # Configure tag for low inventory (red background, white text for visibility)
        self.inventory_table.tag_configure('low_stock', background='#FF5555', foreground='white')
        
        with self.conn:
            cursor = self.conn.cursor()
            query = self.inventory_search_entry.get().strip()
            type_filter = self.type_filter_var.get()
            sql = "SELECT item_id, name, type, retail_price, quantity, supplier FROM inventory"
            params = []
            conditions = []
            if query:
                conditions.append("(name LIKE ?)")
                params.append(f"%{query}%")
            if type_filter != "All":
                conditions.append("type = ?")
                params.append(type_filter)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            cursor.execute(sql, params)
            for item in cursor.fetchall():
                item_id, name, item_type, retail_price, quantity, supplier = item
                # Ensure quantity is an integer
                try:
                    quantity = int(float(quantity))  # Handle potential float values
                except (ValueError, TypeError):
                    quantity = 0  # Fallback if quantity is invalid
                # Apply 'low_stock' tag if quantity <= 5
                tags = ('low_stock',) if quantity <= 5 else ()
                # Insert item into Treeview with item_id as iid
                self.inventory_table.insert("", "end", iid=item_id, values=(
                    name, item_type, f"{retail_price:.2f}", quantity, supplier or "Unknown"
                ), tags=tags)
                # Debug print to verify tagging
                print(f"Item: {name}, ID: {item_id}, Quantity: {quantity}, Tags: {tags}")

    def treeview_scroll(self, event: tk.Event, canvas: tk.Canvas = None, treeview: ttk.Treeview = None) -> str:
        """Handle mouse wheel scrolling for a Treeview widget, optionally within a Canvas."""
        if canvas is not None:
            # For Treeview inside a Canvas (e.g., transactions_table)
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        elif treeview is not None:
            # For standalone Treeview (e.g., cart_table, unpaid_table, etc.)
            if event.delta:
                treeview.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                treeview.yview_scroll(-1, "units")
            elif event.num == 5:
                treeview.yview_scroll(1, "units")
        return "break"

    def show_transactions(self, event: Optional[tk.Event] = None) -> None:
        if self.get_user_role() == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=20, pady=20)  # Soft White
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Transaction ID:", font=("Helvetica", 14),
                bg="#F5F6F5", fg="#2C3E50").pack(side="left")  # Soft White, Dark Slate
        self.search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<KeyRelease>", self.update_transactions_table)
        tk.Button(search_frame, text="Refresh Transactions", command=self.update_transactions_table,
                bg="#2ECC71", fg="#F5F6F5", font=("Helvetica", 14),  # Seafoam Green, Soft White
                activebackground="#27AE60", activeforeground="#F5F6F5",  # Darker Seafoam Green, Soft White
                padx=12, pady=8, bd=0).pack(side="left", padx=5)

        transactions_frame = tk.Frame(content_frame, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        transactions_frame.pack(fill="both", expand=True, pady=10)
        transactions_frame.grid_rowconfigure(1, weight=1)
        transactions_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(transactions_frame, bg="#F5F6F5")  # Soft White
        canvas.grid(row=1, column=0, sticky="nsew")

        v_scrollbar = ttk.Scrollbar(transactions_frame, orient="vertical", command=canvas.yview)
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        h_scrollbar = ttk.Scrollbar(transactions_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")

        canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        tree_frame = tk.Frame(canvas, bg="#F5F6F5")  # Soft White
        canvas_window = canvas.create_window((0, 0), window=tree_frame, anchor="nw")

        columns = ("TransactionID", "ItemsList", "TotalAmount", "CashPaid", "ChangeAmount", "Timestamp", "Status", "PaymentMethod", "CustomerID")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT ", "CASH PAID ", "CHANGE ", "TIMESTAMP", "STATUS", "PAYMENT METHOD", "CUSTOMER ID")
        self.transactions_table = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20, style="Treeview")
        for col, head in zip(columns, headers):
            self.transactions_table.heading(col, text=head)
            width = 300 if col == "ItemsList" else 150
            self.transactions_table.column(col, width=width, anchor="center" if col != "ItemsList" else "w")
        self.transactions_table.pack(fill="both", expand=True)

        # Apply Treeview styling
        style = ttk.Style()
        style.configure("Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5")  # Soft White, Dark Slate

        # Update canvas scroll region when tree_frame size changes
        def configure_canvas(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        tree_frame.bind("<Configure>", configure_canvas)

        # Add mouse wheel bindings for vertical scrolling
        self.transactions_table.bind("<MouseWheel>", lambda event: self.treeview_scroll(event, canvas=canvas))
        self.transactions_table.bind("<Button-4>", lambda event: self.treeview_scroll(event, canvas=canvas))
        self.transactions_table.bind("<Button-5>", lambda event: self.treeview_scroll(event, canvas=canvas))

        # Existing horizontal scrolling bindings
        def scroll_horizontal(event):
            if event.state & 0x1:  # Shift key pressed
                if event.delta > 0:
                    canvas.xview_scroll(-1, "units")
                elif event.delta < 0:
                    canvas.xview_scroll(1, "units")
            return "break"

        def scroll_horizontal_unix(event):
            if event.state & 0x1:  # Shift key pressed
                if event.num == 4:
                    canvas.xview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.xview_scroll(1, "units")
            return "break"

        self.transactions_table.bind("<Shift-MouseWheel>", scroll_horizontal)
        self.transactions_table.bind("<Shift-Button-4>", scroll_horizontal_unix)
        self.transactions_table.bind("<Shift-Button-5>", scroll_horizontal_unix)

        def update_scroll_region(event=None):
            total_width = sum(self.transactions_table.column(col, "width") for col in columns)
            total_height = self.transactions_table.winfo_reqheight()
            canvas.configure(scrollregion=(0, 0, total_width, total_height))
            canvas.itemconfig(canvas_window, width=total_width)

        self.transactions_table.bind("<Configure>", update_scroll_region)

        self.update_transactions_table()
        self.transactions_table.bind("<<TreeviewSelect>>", self.on_transaction_select)

        self.transaction_button_frame = tk.Frame(transactions_frame, bg="#F5F6F5")  # Soft White
        self.transaction_button_frame.grid(row=3, column=0, columnspan=9, pady=10)
        self.print_btn = tk.Button(self.transaction_button_frame, text="Print Receipt", command=self.print_receipt,
                                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                padx=12, pady=8, bd=0, state="disabled")
        self.print_btn.pack(side="left", padx=5)
        self.edit_transaction_btn = tk.Button(self.transaction_button_frame, text="Edit Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Edit", "Enter admin password to edit transaction",
                                                self.validate_edit_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                                            activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                            padx=12, pady=8, bd=0, state="disabled")
        self.edit_transaction_btn.pack(side="left", padx=5)
        self.delete_transaction_btn = tk.Button(self.transaction_button_frame, text="Delete Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Deletion", "Enter admin password to delete transaction",
                                                self.validate_delete_main_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", 14),  # Coral Red, Soft White
                                            activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                            padx=12, pady=8, bd=0, state="disabled")
        self.delete_transaction_btn.pack(side="left", padx=5)
        self.refund_btn = tk.Button(self.transaction_button_frame, text="Refund",
                                    command=lambda: self.create_password_auth_window(
                                        "Authenticate Refund", "Enter admin password to process refund",
                                        self.validate_refund_auth, selected_item=self.transactions_table.selection()),
                                    bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", 14),  # Coral Red, Soft White
                                    activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                    padx=12, pady=8, bd=0, state="disabled")
        self.refund_btn.pack(side="left", padx=5)

    def update_transactions_table(self, event=None) -> None:
        # print("Updating transactions table, event:", event)
        for item in self.transactions_table.get_children():
            self.transactions_table.delete(item)
        
        search_term = ""
        try:
            if hasattr(self, 'search_entry') and self.search_entry.winfo_exists():
                search_term = self.search_entry.get().strip()
                print(f"Search term: '{search_term}'")
            else:
                print("No valid search_entry available")
        except tk.TclError as e:
            print(f"TclError accessing search_entry: {e}")
        
        with self.conn:
            cursor = self.conn.cursor()
            try:
                if search_term:
                    # Case-insensitive search for TransactionID
                    cursor.execute("SELECT * FROM transactions WHERE UPPER(transaction_id) LIKE UPPER(?)", (f"%{search_term}%",))
                else:
                    cursor.execute("SELECT * FROM transactions")
                transactions = cursor.fetchall()
                print(f"Fetched {len(transactions)} transactions")
                
                for transaction in transactions:
                    items_str = transaction[1]
                    item_names = []
                    for item_data in items_str.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                                name = cursor.fetchone()
                                if name:
                                    item_names.append(f"{name[0]} (x{qty})")
                            except ValueError as e:
                                print(f"Error parsing item_data '{item_data}': {e}")
                    items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names) if item_names else "No items"
                    self.transactions_table.insert("", "end", values=(
                        transaction[0], items_display, f"{transaction[2]:.2f}",
                        f"{transaction[3]:.2f}", f"{transaction[4]:.2f}",
                        transaction[5], transaction[6], transaction[7] or "Cash",
                        transaction[8] or "None"
                    ))
            except Exception as e:
                print(f"Database error: {e}")
                messagebox.showerror("Database Error", f"Failed to fetch transactions: {e}", parent=self.root)

    def on_transaction_select(self, event: tk.Event) -> None:
        selected_item = self.transactions_table.selection()
        state = "normal" if selected_item else "disabled"
        self.print_btn.config(state=state)
        self.edit_transaction_btn.config(state=state)
        self.delete_transaction_btn.config(state=state)
        self.refund_btn.config(state=state)


    def validate_delete_main_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return

        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                try:
                    cursor.execute("SELECT status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                    status = cursor.fetchone()
                    if not status:
                        window.destroy()
                        messagebox.showerror("Error", "Transaction not found", parent=self.root)
                        return
                    if status[0] == "Held":
                        window.destroy()
                        messagebox.showerror("Error", "Cannot delete unpaid transactions from this view. Use Unpaid Transactions view.", parent=self.root)
                        return
                    cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                    log_id = f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}"
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                (log_id, "Delete Main Transaction", f"Deleted main transaction {transaction_id}",
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    self.update_transactions_table()
                    window.destroy()
                    messagebox.showinfo("Success", f"Transaction {transaction_id} deleted successfully", parent=self.root)
                except sqlite3.Error as e:
                    messagebox.showerror("Error", f"Failed to delete transaction: {e}", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)


    def validate_edit_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                window.destroy()
                self.show_edit_transaction(transaction_id)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def show_edit_transaction(self, transaction_id: str) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT items, total_amount, cash_paid, change_amount, status, payment_method, customer_id FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if not transaction:
                messagebox.showerror("Error", "Transaction not found", parent=self.root)
                return
            if transaction[4] == "Returned":
                messagebox.showerror("Error", "Cannot edit a returned transaction", parent=self.root)
                return

            items = transaction[0].split(";")
            edit_items = []
            for item_data in items:
                if item_data:
                    try:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, price, quantity FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            edit_items.append({"id": item_id, "name": item[0], "price": float(item[1]), "original_quantity": int(qty), "current_quantity": int(qty), "inventory_quantity": int(item[2])})
                    except ValueError:
                        continue

            if not edit_items:
                messagebox.showerror("Error", "No valid items to edit", parent=self.root)
                return

            window = tk.Toplevel(self.root)
            window.title(f"Edit Transaction {transaction_id}")
            window.geometry("600x400")
            window.configure(bg="#F5F5DC")

            content_frame = tk.Frame(window, bg="#FFF8E7", padx=20, pady=20)
            content_frame.pack(fill="both", expand=True)

            tk.Label(content_frame, text=f"Edit Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                    bg="#FFF8E7", fg="#2C1B18").pack(pady=10)

            columns = ("Item", "OriginalQuantity", "NewQuantity")
            headers = ("ITEM", "ORIGINAL QTY", "NEW QTY")
            edit_table = ttk.Treeview(content_frame, columns=columns, show="headings")
            for col, head in zip(columns, headers):
                edit_table.heading(col, text=head)
                edit_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
            edit_table.pack(fill="both", expand=True)

            # Apply Treeview styling
            style = ttk.Style()
            style.configure("Treeview", background="#FFF8E7", foreground="#2C1B18", fieldbackground="#FFF8E7")

            quantity_entries = {}
            for item in edit_items:
                item_iid = edit_table.insert("", "end", values=(item["name"], item["original_quantity"], item["current_quantity"]))
                quantity_entries[item_iid] = {"item": item, "entry": None}

            def update_quantity_fields():
                for item_iid in edit_table.get_children():
                    item_data = quantity_entries[item_iid]["item"]
                    frame = tk.Frame(content_frame, bg="#FFF8E7")
                    frame.pack(fill="x", pady=2)
                    tk.Label(frame, text=item_data["name"], font=("Helvetica", 12), bg="#FFF8E7", fg="#2C1B18").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 12), bg="#F5F5DC", fg="#2C1B18", width=10)
                    entry.insert(0, str(item_data["current_quantity"]))
                    entry.pack(side="left", padx=5)
                    quantity_entries[item_iid]["entry"] = entry
                    edit_table.item(item_iid, values=(item_data["name"], item_data["original_quantity"], item_data["current_quantity"]))

            update_quantity_fields()

            tk.Button(content_frame, text="Confirm Changes",
                    command=lambda: self.process_edit_transaction(transaction_id, edit_items, quantity_entries, transaction[2], transaction[5], transaction[6], window),
                    bg="#6F4E37", fg="#FFF8E7", font=("Helvetica", 14),
                    activebackground="#8B5A2B", activeforeground="#FFF8E7",
                    padx=12, pady=8, bd=0).pack(pady=10)
            
    
    def process_edit_transaction(self, transaction_id: str, edit_items: List[Dict], quantity_entries: Dict, cash_paid: float, payment_method: str, customer_id: str, window: tk.Toplevel) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                new_items = []
                total_amount = 0.0
                for item_iid in quantity_entries:
                    item = quantity_entries[item_iid]["item"]
                    try:
                        new_qty = int(quantity_entries[item_iid]["entry"].get())
                        if new_qty < 0:
                            messagebox.showerror("Error", f"Quantity for {item['name']} cannot be negative", parent=self.root)
                            return
                        # Calculate quantity difference
                        qty_diff = new_qty - item["original_quantity"]
                        # Check inventory availability
                        available_qty = item["inventory_quantity"] - qty_diff
                        if available_qty < 0:
                            messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {item['inventory_quantity']}", parent=self.root)
                            return
                        item["current_quantity"] = new_qty
                        total_amount += item["price"] * new_qty
                        if new_qty > 0:
                            new_items.append(f"{item['id']}:{new_qty}")
                        # Update inventory
                        cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", (qty_diff, item["id"]))
                    except ValueError:
                        messagebox.showerror("Error", f"Invalid quantity for {item['name']}", parent=self.root)
                        return

                if not new_items:
                    messagebox.showerror("Error", "Transaction must have at least one item", parent=self.root)
                    return

                # Update transaction
                items_str = ";".join(new_items)
                change_amount = cash_paid - total_amount if cash_paid >= total_amount else 0.0
                cursor.execute("""
                    UPDATE transactions SET items = ?, total_amount = ?, cash_paid = ?, change_amount = ? 
                    WHERE transaction_id = ?
                """, (items_str, total_amount, cash_paid, change_amount, transaction_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}", 
                            "Edit Transaction", f"Edited transaction {transaction_id}", 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_transactions_table()
                window.destroy()
                messagebox.showinfo("Success", f"Transaction {transaction_id} updated successfully", parent=self.root)
                self.check_low_inventory()
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to update transaction: {e}", parent=self.root)

    def print_receipt(self) -> None:
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        selected_item = self.transactions_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        items = self.transactions_table.item(selected_item)["values"][1].split(", ")
        total_amount = float(self.transactions_table.item(selected_item)["values"][2])
        cash_paid = float(self.transactions_table.item(selected_item)["values"][3])
        change = float(self.transactions_table.item(selected_item)["values"][4])
        timestamp = self.transactions_table.item(selected_item)["values"][5]

        downloads_path = os.path.expanduser("~/Downloads")
        pdf_path = os.path.join(downloads_path, f"Receipt_{transaction_id}.pdf")

        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica", 12)

        # Header
        c.drawString(100, 750, "Shinano POS")
        c.drawString(100, 732, "Gem's Pharmacy.")
        # c.drawString(100, 714, "VAT REG TIN: 123-456-789-000")
        # c.drawString(100, 696, "SN: 987654321 MIN: 123456789")
        c.drawString(100, 678, "123 Pharmacy Drive, Health City Tel #555-0123")
        c.drawString(100, 650, f"Date: {timestamp}")
        c.drawString(100, 632, f"TRANSACTION CODE: {transaction_id}")

        # Prepare table data
        data = [["Name", "Qty", "Price"]]
        total_qty = 0
        missing_items = []
        for item in items:
            if item:
                name, qty = item.rsplit(" (x", 1) if " (x" in item else (item, "0")
                qty = int(qty.strip(")")) if qty != "0" else 0
                item_name = name.strip()
                retail_price = 0.0
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT retail_price FROM inventory WHERE name = ?", (item_name,))
                    result = cursor.fetchone()
                    if result:
                        retail_price = float(result[0])
                    else:
                        missing_items.append(item_name)
                data.append([item_name, str(qty), f"{retail_price:.2f}"])
                total_qty += qty

        # Show warning for missing items
        if missing_items:
            messagebox.showwarning("Warning", f"Items not found in inventory: {', '.join(missing_items)}", parent=self.root)

        # Add total row
        data.append(["Total", str(total_qty), f"{total_amount:.2f}"])

        # Create table
        table = Table(data)
        table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 12),
            ('FONT', (0, 1), (-1, -2), 'Helvetica', 12),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))

        # Calculate table position
        table_width = 400
        table_x = (letter[0] - table_width) / 2
        table_y = 600
        table.wrapOn(c, table_width, 400)
        table.drawOn(c, table_x, table_y - len(data) * 20)

        # Footer information
        y = table_y - len(data) * 20 - 20
        c.drawString(100, y - 40, f"CASH: {cash_paid:.2f}")
        c.drawString(100, y - 60, f"CHANGE: {change:.2f}")
        c.drawString(100, y - 80, f"VAT SALE: {(total_amount * 0.12):.2f}")
        c.drawString(100, y - 100, f"NON-VAT SALE: {(total_amount * 0.88):.2f}")

        c.save()
        try:
            webbrowser.open(f"file://{pdf_path}")
            messagebox.showinfo("Success", f"Opening receipt: {pdf_path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to print receipt: {e}", parent=self.root)

    def print_sales_report(self, month, year, total_unit_sales, daily_sales):
                try:
                    month = int(month)
                    year = int(year)
                except ValueError:
                    messagebox.showerror("Error", "Invalid month or year for report.", parent=self.root)
                    return

                # Generate report filename
                filename = f"sales_report_{year}-{month:02d}.txt"
                month_name = datetime.strptime(str(month), "%m").strftime("%B")

                # Create report content
                report = f"Sales Report for {month_name} {year}\n"
                report += "=" * 50 + "\n\n"
                report += f"Unit Cost for the Month: ${total_unit_sales:.2f}\n\n"
                report += "Daily Sales Summary:\n"
                report += f"{'Date':<12} {'Total Sales':>12} {'Unit Cost':>15} {'Net Profit':>12}\n"
                report += "-" * 50 + "\n"

                if daily_sales:
                    total_grand_sales = sum(data["grand_sales"] for data in daily_sales.values())
                    total_net_profit = total_grand_sales - total_unit_sales
                    for date in sorted(daily_sales.keys()):
                        grand_sales = daily_sales[date]["grand_sales"]
                        unit_sales = daily_sales[date]["unit_sales"]
                        net_profit = grand_sales - unit_sales
                        report += f"{date:<12} {grand_sales:>12.2f} {unit_sales:>15.2f} {net_profit:>12.2f}\n"
                    report += "-" * 50 + "\n"
                    report += f"{'Total':<12} {total_grand_sales:>12.2f} {total_unit_sales:>15.2f} {total_net_profit:>12.2f}\n"
                else:
                    report += "No transactions found for the selected period.\n"

                # Save report to file
                try:
                    with open(filename, "w") as f:
                        f.write(report)
                    messagebox.showinfo("Success", f"Sales report saved to {filename}", parent=self.root)
                except IOError as e:
                    messagebox.showerror("Error", f"Failed to save report: {e}", parent=self.root)

    def show_sales_summary(self) -> None:
        if not hasattr(self, 'root') or self.root is None:
            messagebox.showerror("Error", "Application root is not defined", parent=self.root)
            return
        try:
            if self.get_user_role() == "Drug Lord":
                messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
                self.show_account_management()
                return
        except AttributeError as e:
            messagebox.showerror("Error", f"User role could not be determined: {e}", parent=self.root)
            return
        try:
            self.clear_frame()
            self.style_config()  # Ensure sea-themed styles are applied
        except AttributeError as e:
            messagebox.showerror("Error", f"Unable to clear frame: {e}", parent=self.root)
            return

        # Main frame with pack layout for responsiveness
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)

        try:
            self.setup_navigation(main_frame)
        except AttributeError as e:
            messagebox.showwarning("Warning", f"Navigation setup failed: {e}; continuing without navigation.", parent=self.root)

        # Create canvas for scrollable content
        canvas = tk.Canvas(main_frame, bg="#F5F6F5", highlightthickness=0)  # Soft White
        canvas.pack(side="left", fill="both", expand=True)

        # Add vertical and horizontal scrollbars
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.pack(side="bottom", fill="x")
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Create scrollable frame inside canvas
        content_frame = tk.Frame(canvas, bg="#F5F6F5")  # Soft White
        canvas.create_window((0, 0), window=content_frame, anchor="nw")

        # Mouse wheel scrolling handlers
        def on_canvas_mouse_wheel(event):
            if v_scrollbar.winfo_ismapped():
                delta = -1 if (event.delta > 0 or event.num == 4) else 1 if (event.delta < 0 or event.num == 5) else 0
                if delta != 0:
                    canvas.yview_scroll(delta, "units")
            return "break"

        def on_canvas_shift_mouse_wheel(event):
            if h_scrollbar.winfo_ismapped():
                delta = -1 if (event.delta > 0 or event.num == 4) else 1 if (event.delta < 0 or event.num == 5) else 0
                if delta != 0:
                    canvas.xview_scroll(delta, "units")
            return "break"

        def on_table_mouse_wheel(table, v_scrollbar, h_scrollbar):
            def handler(event):
                if v_scrollbar.winfo_ismapped():
                    delta = -1 if (event.delta > 0 or event.num == 4) else 1 if (event.delta < 0 or event.num == 5) else 0
                    if delta != 0:
                        table.yview_scroll(delta, "units")
                return "break"
            return handler

        def on_table_shift_mouse_wheel(table, h_scrollbar):
            def handler(event):
                if h_scrollbar.winfo_ismapped():
                    delta = -1 if (event.delta > 0 or event.num == 4) else 1 if (event.delta < 0 or event.num == 5) else 0
                    if delta != 0:
                        table.xview_scroll(delta, "units")
                return "break"
            return handler

        # Function to bind canvas scrolling
        def bind_canvas_scrolling():
            canvas.bind("<Button-1>", lambda e: canvas.focus_set())
            canvas.bind("<MouseWheel>", on_canvas_mouse_wheel)
            canvas.bind("<Button-4>", on_canvas_mouse_wheel)
            canvas.bind("<Button-5>", on_canvas_mouse_wheel)
            canvas.bind("<Shift-MouseWheel>", on_canvas_shift_mouse_wheel)
            canvas.bind("<Shift-Button-4>", on_canvas_shift_mouse_wheel)
            canvas.bind("<Shift-Button-5>", on_canvas_shift_mouse_wheel)

        # Function to bind table scrolling
        def bind_table_scrolling(table, v_scrollbar, h_scrollbar):
            table.bind("<Button-1>", lambda e: table.focus_set())
            table.bind("<MouseWheel>", on_table_mouse_wheel(table, v_scrollbar, h_scrollbar))
            table.bind("<Button-4>", on_table_mouse_wheel(table, v_scrollbar, h_scrollbar))
            table.bind("<Button-5>", on_table_mouse_wheel(table, v_scrollbar, h_scrollbar))
            table.bind("<Shift-MouseWheel>", on_table_shift_mouse_wheel(table, h_scrollbar))
            table.bind("<Shift-Button-4>", on_table_shift_mouse_wheel(table, h_scrollbar))
            table.bind("<Shift-Button-5>", on_table_shift_mouse_wheel(table, h_scrollbar))

        # Update scroll region and handle resizing
        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            window_width = self.root.winfo_width()
            base_column_width = max(self.scale_size(100), window_width // 6)
            for col in columns:
                monthly_table.column(col, width=base_column_width if col != "Month" else int(base_column_width * 1.5), stretch=True)
            for col in daily_columns:
                daily_table.column(col, width=base_column_width if col != "Date" else int(base_column_width * 1.5), stretch=True)
            month_combobox.configure(width=max(5, window_width // 100))
            year_combobox.configure(width=max(7, window_width // 80))
            apply_filter_btn.configure(padx=self.scale_size(12), pady=self.scale_size(8))
            print_report_btn.configure(padx=self.scale_size(12), pady=self.scale_size(8))

        content_frame.bind("<Configure>", update_scroll_region)
        self.root.bind("<Configure>", update_scroll_region)

        # Configure content_frame grid for responsiveness
        content_frame.configure(padx=self.scale_size(20), pady=self.scale_size(20))
        content_frame.grid_rowconfigure(0, weight=0)
        content_frame.grid_rowconfigure(1, weight=0)
        content_frame.grid_rowconfigure(2, weight=1)
        content_frame.grid_rowconfigure(3, weight=0)
        content_frame.grid_rowconfigure(4, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)

        # Filter frame with responsive grid layout
        filter_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        filter_frame.grid(row=0, column=0, sticky="ew", pady=self.scale_size(10))
        filter_frame.grid_columnconfigure(1, weight=1)
        filter_frame.grid_columnconfigure(3, weight=1)
        filter_frame.grid_columnconfigure(4, weight=0)
        filter_frame.grid_columnconfigure(5, weight=0)

        tk.Label(filter_frame, text="Month:", font=("Helvetica", self.scale_size(14)),
                bg="#F5F6F5", fg="#2C3E50").grid(row=0, column=0, padx=self.scale_size(5), sticky="w")  # Soft White, Dark Slate
        month_var = tk.StringVar(value=str(datetime.now().month))
        month_combobox = ttk.Combobox(filter_frame, textvariable=month_var, values=[str(i) for i in range(1, 13)],
                                    font=("Helvetica", self.scale_size(14)), width=5, state="readonly")
        month_combobox.grid(row=0, column=1, padx=self.scale_size(5), sticky="ew")

        tk.Label(filter_frame, text="Year:", font=("Helvetica", self.scale_size(14)),
                bg="#F5F6F5", fg="#2C3E50").grid(row=0, column=2, padx=self.scale_size(5), sticky="w")  # Soft White, Dark Slate
        year_var = tk.StringVar(value=str(datetime.now().year))
        year_combobox = ttk.Combobox(filter_frame, textvariable=year_var,
                                    values=[str(i) for i in range(2020, datetime.now().year + 1)],
                                    font=("Helvetica", self.scale_size(14)), width=7, state="readonly")
        year_combobox.grid(row=0, column=3, padx=self.scale_size(5), sticky="ew")

        apply_filter_btn = tk.Button(filter_frame, text="Apply Filter",
                                    command=lambda: self.update_tables(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame),
                                    bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Aqua Blue, Soft White
                                    activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                    padx=self.scale_size(12), pady=self.scale_size(8), bd=0)
        apply_filter_btn.grid(row=0, column=4, padx=self.scale_size(5), sticky="ew")

        print_report_btn = tk.Button(filter_frame, text="Print Report",
                                    command=lambda: self.print_sales_report(month_var.get(), year_var.get()),
                                    bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", self.scale_size(14)),  # Aqua Blue, Soft White
                                    activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                    padx=self.scale_size(12), pady=self.scale_size(8), bd=0)
        print_report_btn.grid(row=0, column=5, padx=self.scale_size(5), sticky="ew")

        # Monthly sales summary
        tk.Label(content_frame, text="Monthly Sales Summary", font=("Helvetica", self.scale_size(18), "bold"),
                bg="#F5F6F5", fg="#2C3E50").grid(row=1, column=0, pady=self.scale_size(10), sticky="w")  # Soft White, Dark Slate
        monthly_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        monthly_frame.grid(row=2, column=0, sticky="nsew", pady=self.scale_size(5))
        monthly_frame.grid_rowconfigure(0, weight=1)
        monthly_frame.grid_columnconfigure(0, weight=1)
        monthly_frame.grid_columnconfigure(1, weight=0)

        columns = ("Month", "TotalSales", "UnitCost", "NetProfit")
        headers = ("MONTH", "TOTAL SALES", "UNIT COST", "NET PROFIT")
        monthly_table = ttk.Treeview(monthly_frame, columns=columns, show="headings", height=10, style="Treeview")
        for col, head in zip(columns, headers):
            monthly_table.heading(col, text=head)
            monthly_table.column(col, width=self.scale_size(150), anchor="center" if col != "Month" else "w", stretch=True)
        monthly_table.grid(row=0, column=0, sticky="nsew")

        monthly_v_scrollbar = ttk.Scrollbar(monthly_frame, orient="vertical", command=monthly_table.yview)
        monthly_v_scrollbar.grid(row=0, column=1, sticky="ns")
        monthly_table.configure(yscrollcommand=monthly_v_scrollbar.set)

        monthly_h_scrollbar = ttk.Scrollbar(monthly_frame, orient="horizontal", command=monthly_table.xview)
        monthly_h_scrollbar.grid(row=1, column=0, sticky="ew")
        monthly_table.configure(xscrollcommand=monthly_h_scrollbar.set)

        # Daily sales summary
        tk.Label(content_frame, text="Daily Sales Summary", font=("Helvetica", self.scale_size(18), "bold"),
                bg="#F5F6F5", fg="#2C3E50").grid(row=3, column=0, pady=self.scale_size(10), sticky="w")  # Soft White, Dark Slate
        daily_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        daily_frame.grid(row=4, column=0, sticky="nsew", pady=self.scale_size(5))
        daily_frame.grid_rowconfigure(0, weight=1)
        daily_frame.grid_columnconfigure(0, weight=1)
        daily_frame.grid_columnconfigure(1, weight=0)

        daily_columns = ("Date", "TotalSales", "UnitCost", "NetProfit")
        daily_headers = ("DATE", "TOTAL SALES", "UNIT COST", "NET PROFIT")
        daily_table = ttk.Treeview(daily_frame, columns=daily_columns, show="headings", height=10, style="Treeview")
        for col, head in zip(daily_columns, daily_headers):
            daily_table.heading(col, text=head)
            daily_table.column(col, width=self.scale_size(150), anchor="center" if col != "Date" else "w", stretch=True)
        daily_table.grid(row=0, column=0, sticky="nsew")

        daily_v_scrollbar = ttk.Scrollbar(daily_frame, orient="vertical", command=daily_table.yview)
        daily_v_scrollbar.grid(row=0, column=1, sticky="ns")
        daily_table.configure(yscrollcommand=daily_v_scrollbar.set)

        daily_h_scrollbar = ttk.Scrollbar(daily_frame, orient="horizontal", command=daily_table.xview)
        daily_h_scrollbar.grid(row=1, column=0, sticky="ew")
        daily_table.configure(xscrollcommand=daily_h_scrollbar.set)

        # Apply Treeview styling
        style = ttk.Style()
        style.configure("Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5",
                        rowheight=self.scale_size(30), font=("Helvetica", self.scale_size(12)))

        # Bind Enter/Leave events for context-sensitive scrolling
        monthly_table.bind("<Enter>", lambda e: bind_table_scrolling(monthly_table, monthly_v_scrollbar, monthly_h_scrollbar))
        monthly_table.bind("<Leave>", lambda e: bind_canvas_scrolling())
        daily_table.bind("<Enter>", lambda e: bind_table_scrolling(daily_table, daily_v_scrollbar, daily_h_scrollbar))
        daily_table.bind("<Leave>", lambda e: bind_canvas_scrolling())

        # Initially bind canvas scrolling
        bind_canvas_scrolling()

        # Populate tables
        self.update_tables(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame)

        # Ensure canvas scrolls to the top initially
        canvas.update_idletasks()
        canvas.yview_moveto(0)
        canvas.xview_moveto(0)
    
    def update_tables(self, month_var: tk.StringVar, year_var: tk.StringVar, monthly_table: ttk.Treeview, daily_table: ttk.Treeview, monthly_frame: tk.Frame, daily_frame: tk.Frame) -> None:
        # Clear existing table data
        for item in monthly_table.get_children():
            monthly_table.delete(item)
        for item in daily_table.get_children():
            daily_table.delete(item)

        try:
            month = month_var.get()
            year = year_var.get()
            with self.conn:
                cursor = self.conn.cursor()
                # Debug: Check table row counts
                cursor.execute("SELECT count(*) FROM daily_sales")
                daily_sales_count = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM transactions")
                transactions_count = cursor.fetchone()[0]
                print(f"Debug: daily_sales rows: {daily_sales_count}, transactions rows: {transactions_count}")

                # Monthly sales: Aggregate total sales, total unit cost, and net profit
                cursor.execute('''
                    SELECT strftime('%m', t.timestamp) AS month,
                           SUM(t.total_amount) AS total_sales,
                           SUM(CASE
                               WHEN instr(t.items, ':') > 0 THEN
                                   CAST(SUBSTR(t.items, instr(t.items, ':') + 1) AS INTEGER) * i.unit_price
                               ELSE 0
                           END) AS total_unit_cost,
                           SUM(d.net_profit) AS net_profit
                    FROM transactions t
                    JOIN inventory i ON instr(t.items, i.item_id) > 0
                    JOIN daily_sales d ON strftime('%Y-%m-%d', t.timestamp) = d.sale_date
                    WHERE strftime('%Y', t.timestamp) = ?
                    GROUP BY strftime('%m', t.timestamp)
                    ORDER BY month
                ''', (year,))
                monthly_data = cursor.fetchall()
                print(f"Debug: Monthly data for {year}: {monthly_data}")
                month_names = {str(i).zfill(2): name for i, name in enumerate(
                    ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"], 1)}
                for row in monthly_data:
                    month_num = row[0]
                    monthly_table.insert("", "end", values=(
                        month_names.get(month_num, month_num),
                        f"{row[1] if row[1] is not None else 0:.2f}",
                        f"{row[2] if row[2] is not None else 0:.2f}",
                        f"{row[3] if row[3] is not None else 0:.2f}"
                    ))

                # Daily sales: Aggregate total sales, total unit cost, and net profit
                cursor.execute('''
                    SELECT strftime('%Y-%m-%d', t.timestamp) AS sale_date,
                           SUM(t.total_amount) AS total_sales,
                           SUM(CASE
                               WHEN instr(t.items, ':') > 0 THEN
                                   CAST(SUBSTR(t.items, instr(t.items, ':') + 1) AS INTEGER) * i.unit_price
                               ELSE 0
                           END) AS total_unit_cost,
                           SUM(d.net_profit) AS net_profit
                    FROM transactions t
                    JOIN inventory i ON instr(t.items, i.item_id) > 0
                    JOIN daily_sales d ON strftime('%Y-%m-%d', t.timestamp) = d.sale_date
                    WHERE strftime('%Y', t.timestamp) = ? AND strftime('%m', t.timestamp) = ?
                    GROUP BY strftime('%Y-%m-%d', t.timestamp)
                    ORDER BY sale_date DESC
                ''', (year, month.zfill(2)))
                daily_data = cursor.fetchall()
                print(f"Debug: Daily data for {year}-{month.zfill(2)}: {daily_data}")
                for row in daily_data:
                    daily_table.insert("", "end", values=(
                        row[0],
                        f"{row[1] if row[1] is not None else 0:.2f}",
                        f"{row[2] if row[2] is not None else 0:.2f}",
                        f"{row[3] if row[3] is not None else 0:.2f}"
                    ))

                # If no data, display a message
                if not monthly_data:
                    monthly_table.insert("", "end", values=("No data", "0.00", "0.00", "0.00"))
                if not daily_data:
                    daily_table.insert("", "end", values=("No data", "0.00", "0.00", "0.00"))

        except sqlite3.Error as e:
            print(f"Debug: SQLite error in update_tables: {e}")
            messagebox.showerror("Error", f"Failed to update sales tables: {e}", parent=self.root)


    def print_sales_report(self, month: str, year: str) -> None:
        try:
            month = int(month)
            year = int(year)
        except ValueError:
            messagebox.showerror("Error", "Invalid month or year selected.", parent=self.root)
            return

        start_date = f"{year}-{month:02d}-01"
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        end_date = f"{next_year}-{next_month:02d}-01"

        try:
            # Prepare data for the report
            monthly_sales = {}
            daily_sales = {}
            with self.conn:
                cursor = self.conn.cursor()
                # Monthly calculations
                cursor.execute("""
                    SELECT strftime('%Y-%m', timestamp) AS month, items, total_amount
                    FROM transactions
                    WHERE status = 'Completed' AND timestamp >= ? AND timestamp < ?
                """, (start_date, end_date))
                for month_str, items, total_amount in cursor.fetchall():
                    if month_str not in monthly_sales:
                        monthly_sales[month_str] = {"unit_sales": 0.0, "grand_sales": 0.0}
                    unit_sales = 0.0
                    for item_data in items.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                qty = int(qty)
                                cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?",
                                            (item_id,))
                                item = cursor.fetchone()
                                if item:
                                    unit_sales += item[0] * qty
                            except (ValueError, IndexError):
                                continue
                    monthly_sales[month_str]["unit_sales"] += unit_sales
                    monthly_sales[month_str]["grand_sales"] += total_amount

                # Daily calculations
                cursor.execute("""
                    SELECT strftime('%Y-%m-%d', timestamp) AS date, items, total_amount
                    FROM transactions
                    WHERE status = 'Completed' AND timestamp >= ? AND timestamp < ?
                """, (start_date, end_date))
                total_unit_sales = 0.0
                total_grand_sales = 0.0
                for date, items, total_amount in cursor.fetchall():
                    if date not in daily_sales:
                        daily_sales[date] = {"unit_sales": 0.0, "grand_sales": 0.0}
                    unit_sales = 0.0
                    for item_data in items.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                qty = int(qty)
                                cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?",
                                            (item_id,))
                                item = cursor.fetchone()
                                if item:
                                    unit_sales += item[0] * qty
                            except (ValueError, IndexError):
                                continue
                    daily_sales[date]["grand_sales"] += total_amount
                    daily_sales[date]["unit_sales"] += unit_sales
                    total_unit_sales += unit_sales
                    total_grand_sales += total_amount

            # Generate PDF report
            receipt_dir = os.path.join(os.path.dirname(self.db_path), "reports")
            os.makedirs(receipt_dir, exist_ok=True)
            report_path = os.path.join(receipt_dir, f"sales_report_{year}_{month:02d}.pdf")
            c = canvas.Canvas(report_path, pagesize=letter)
            c.setFont("Helvetica", 12)

            # Header
            c.drawString(100, 750, "Shinano Pharmacy Sales Report")
            c.drawString(100, 730, f"Period: {year}-{month:02d}")
            c.drawString(100, 710, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            c.drawString(100, 690, "-" * 60)

            # Monthly Sales
            y = 670
            c.drawString(100, y, "Monthly Sales Summary")
            y -= 20
            c.drawString(100, y, "Month | Total Sales | Unit Cost | Net Profit")
            y -= 20
            if monthly_sales:
                for month_str in sorted(monthly_sales.keys()):
                    grand_sales = monthly_sales[month_str]["grand_sales"]
                    unit_sales = monthly_sales[month_str]["unit_sales"]
                    net_profit = grand_sales - unit_sales
                    c.drawString(100, y, f"{month_str} | ₱{grand_sales:.2f} | ₱{unit_sales:.2f} | ₱{net_profit:.2f}")
                    y -= 20
            else:
                c.drawString(100, y, "No monthly sales data available")
                y -= 20

            y -= 20
            c.drawString(100, y, "-" * 60)
            y -= 20

            # Daily Sales
            c.drawString(100, y, "Daily Sales Summary")
            y -= 20
            c.drawString(100, y, "Date | Total Sales | Unit Cost | Net Profit")
            y -= 20
            if daily_sales:
                for date in sorted(daily_sales.keys()):
                    grand_sales = daily_sales[date]["grand_sales"]
                    unit_sales = daily_sales[date]["unit_sales"]
                    net_profit = grand_sales - unit_sales
                    c.drawString(100, y, f"{date} | ₱{grand_sales:.2f} | ₱{unit_sales:.2f} | ₱{net_profit:.2f}")
                    y -= 20
                y -= 20
                total_net_profit = total_grand_sales - total_unit_sales
                c.drawString(100, y, f"Total | ₱{total_grand_sales:.2f} | ₱{total_unit_sales:.2f} | ₱{total_net_profit:.2f}")
            else:
                c.drawString(100, y, "No daily sales data available")

            c.showPage()
            c.save()

            # Open the report
            try:
                webbrowser.open(f"file://{os.path.abspath(report_path)}")
                messagebox.showinfo("Success", f"Sales report generated at {report_path}", parent=self.root)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open report: {e}", parent=self.root)

        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database query error: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {e}", parent=self.root)


    

    def show_account_management(self) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to access this section.", parent=self.root)
            self.show_dashboard()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        # Create a canvas for scrolling the entire content
        canvas = tk.Canvas(main_frame, bg="#F5F6F5")  # Soft White
        canvas.pack(side="left", fill="both", expand=True)

        # Add scrollbar for the canvas
        content_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        content_scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=content_scrollbar.set)

        # Create content_frame inside the canvas
        content_frame = tk.Frame(canvas, bg="#F5F6F5", padx=20, pady=20)  # Soft White
        canvas.create_window((0, 0), window=content_frame, anchor="nw")

        # Update canvas scroll region when content_frame size changes
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        content_frame.bind("<Configure>", configure_canvas)

        # Mouse wheel binding for the entire content (Windows)
        def on_mouse_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", on_mouse_wheel)

        tk.Label(content_frame, text="Account Management", font=("Helvetica", 18, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10, anchor="w")  # Soft White, Dark Slate

        # Users table with its own scrollbar
        users_frame = tk.Frame(content_frame, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        users_frame.pack(fill="both", expand=True, pady=10)

        columns = ("Username", "Role", "Status")
        headers = ("USERNAME", "ROLE", "STATUS")
        users_scrollbar = ttk.Scrollbar(users_frame, orient="vertical")
        self.users_table = ttk.Treeview(users_frame, columns=columns, show="headings", style="Treeview", yscrollcommand=users_scrollbar.set)
        users_scrollbar.config(command=self.users_table.yview)
        users_scrollbar.pack(side="right", fill="y")
        for col, head in zip(columns, headers):
            self.users_table.heading(col, text=head)
            self.users_table.column(col, width=150, anchor="center")
        self.users_table.pack(fill="both", expand=True)
        self.update_users_table()
        self.users_table.bind("<<TreeviewSelect>>", self.on_user_select)

        # Mouse wheel binding for users table (Windows)
        def on_users_mouse_wheel(event):
            self.users_table.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.users_table.bind("<MouseWheel>", on_users_mouse_wheel)

        self.users_button_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        self.users_button_frame.pack(fill="x", pady=10)
        self.update_user_btn = tk.Button(self.users_button_frame, text="Update", command=self.show_update_user,
                                        bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                                        activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                        padx=12, pady=8, bd=0, state="disabled")
        self.update_user_btn.pack(side="left", padx=5)
        self.delete_user_btn = tk.Button(self.users_button_frame, text="Delete",
                                        command=lambda: self.create_password_auth_window(
                                            "Authenticate Deletion", "Enter admin password to delete user",
                                            self.validate_delete_user_auth, selected_item=self.users_table.selection()),
                                        bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", 14),  # Coral Red, Soft White
                                        activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                        padx=12, pady=8, bd=0, state="disabled")
        self.delete_user_btn.pack(side="left", padx=5)

        button_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        button_frame.pack(fill="x")
        tk.Button(button_frame, text="Add New User", command=self.show_add_user,
                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                padx=12, pady=8, bd=0).pack(side="left", padx=5)

        tk.Label(content_frame, text="Transaction Log", font=("Helvetica", 18, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=10, anchor="w")  # Soft White, Dark Slate
        
        # Log table with its own scrollbar
        log_frame = tk.Frame(content_frame, bg="#F5F6F5", bd=1, relief="flat")  # Soft White
        log_frame.pack(fill="both", expand=True, pady=10)
        columns = ("Action", "Details", "Timestamp", "User")
        headers = ("ACTION", "DETAILS", "TIMESTAMP", "USER")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical")
        self.log_table = ttk.Treeview(log_frame, columns=columns, show="headings", style="Treeview", yscrollcommand=log_scrollbar.set)
        log_scrollbar.config(command=self.log_table.yview)
        log_scrollbar.pack(side="right", fill="y")
        for col, head in zip(columns, headers):
            self.log_table.heading(col, text=head)
            self.log_table.column(col, width=150 if col != "Details" else 300, anchor="center" if col != "Details" else "w")
        self.log_table.pack(fill="both", expand=True)
        self.update_log_table()

        # Mouse wheel binding for log table (Windows)
        def on_log_mouse_wheel(event):
            self.log_table.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.log_table.bind("<MouseWheel>", on_log_mouse_wheel)
    def update_users_table(self) -> None:
        for item in self.users_table.get_children():
            self.users_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT username, role, status FROM users")
            for user in cursor.fetchall():
                self.users_table.insert("", "end", values=user)

    def on_user_select(self, event: tk.Event) -> None:
        selected_item = self.users_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_user_btn.config(state=state)
        self.delete_user_btn.config(state=state)

    def show_add_user(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New User")
        window.geometry("400x400")
        window.configure(bg="#F4E1C1")  # Sandy Beige

        add_box = tk.Frame(window, bg="#F5F6F5", padx=20, pady=20, bd=1, relief="flat")  # Soft White
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New User", font=("Helvetica", 18, "bold"),
                bg="#F5F6F5", fg="#2C3E50").pack(pady=15)  # Soft White, Dark Slate

        fields = ["Username", "Password"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#F5F6F5")  # Soft White
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#F5F6F5", fg="#2C3E50").pack(side="left")  # Soft White, Dark Slate
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F4E1C1", fg="#2C3E50", show="*" if field == "Password" else "")  # Sandy Beige, Dark Slate
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        role_var = tk.StringVar()
        tk.Label(add_box, text="Role", font=("Helvetica", 14), bg="#F5F6F5", fg="#2C3E50").pack(pady=5)  # Soft White, Dark Slate
        ttk.Combobox(add_box, textvariable=role_var, values=["User", "Drug Lord"],
                    state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(add_box, text="Add User",
                command=lambda: self.add_user(entries["Username"].get(), entries["Password"].get(),
                                            role_var.get(), window),
                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 14),  # Aqua Blue, Soft White
                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_user(self, username: str, password: str, role: str, window: tk.Toplevel) -> None:
        if not all([username, password, role]):
            messagebox.showerror("Error", "All fields are required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                              (username, password, role))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Add User", f"Added user {username}", 
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_users_table()
                window.destroy()
                messagebox.showinfo("Success", "User added successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists", parent=self.root)

    def show_update_user(self) -> None:
        selected_item = self.users_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        username = self.users_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user:
                window = tk.Toplevel(self.root)
                window.title("Update User")
                window.geometry("400x400")
                window.configure(bg="#F5F5DC")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
                update_box.pack(pady=20)

                tk.Label(update_box, text="Update User", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#8B5A2B").pack(pady=15)

                fields = ["Username", "Password"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#8B5A2B").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F5F5DC", show="*" if field == "Password" else "")
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entries[field] = entry
                    entry.insert(0, user[i])

                role_var = tk.StringVar(value=user[2])
                tk.Label(update_box, text="Role", font=("Helvetica", 14), bg="#ffffff", fg="#8B5A2B").pack(pady=5)
                ttk.Combobox(update_box, textvariable=role_var, values=["User", "Drug Lord"],
                            state="readonly", font=("Helvetica", 14)).pack(pady=5)

                tk.Button(update_box, text="Update User",
                         command=lambda: self.update_user(entries["Username"].get(), entries["Password"].get(),
                                                        role_var.get(), user[0], window),
                         bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                         activebackground="#27ae60", activeforeground="#ffffff",
                         padx=12, pady=8, bd=0).pack(pady=15)

    def update_user(self, username: str, password: str, role: str, original_username: str, window: tk.Toplevel) -> None:
        if not all([username, password, role]):
            messagebox.showerror("Error", "All fields are required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                if username != original_username:
                    cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
                    if cursor.fetchone():
                        messagebox.showerror("Error", "Username already exists", parent=self.root)
                        return
                cursor.execute("UPDATE users SET username = ?, password = ?, role = ? WHERE username = ?",
                              (username, password, role, original_username))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Update User", f"Updated user {username}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                if original_username == self.current_user:
                    self.current_user = username
                self.update_users_table()
                window.destroy()
                messagebox.showinfo("Success", "User updated successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists", parent=self.root)

    def validate_delete_user_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                username = self.users_table.item(selected_item)["values"][0]
                if username == self.current_user:
                    window.destroy()
                    messagebox.showerror("Error", "Cannot delete the currently logged-in user", parent=self.root)
                    return
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Delete User", f"Deleted user {username}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_users_table()
                window.destroy()
                messagebox.showinfo("Success", "User deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_log_table(self) -> None:
        for item in self.log_table.get_children():
            self.log_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT action, details, timestamp, user FROM transaction_log ORDER BY timestamp DESC")
            for log in cursor.fetchall():
                self.log_table.insert("", "end", values=log)

    def show_customer_management(self) -> None:
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F5F5DC")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Customer Management", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=10, anchor="w")

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#8B5A2B").pack(side="left")
        self.customer_search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#F5F5DC")
        self.customer_search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.customer_search_entry.bind("<KeyRelease>", self.update_customer_table)
        tk.Button(search_frame, text="Add New Customer", command=self.show_add_customer,
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
                 padx=12, pady=8, bd=0).pack(side="right", padx=5)

        customers_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        customers_frame.pack(fill="both", expand=True, pady=10)
        columns = ("CustomerID", "Name", "Contact", "Address")
        headers = ("CUSTOMER ID", "NAME", "CONTACT", "ADDRESS")
        self.customer_table = ttk.Treeview(customers_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.customer_table.heading(col, text=head)
            self.customer_table.column(col, width=150 if col != "Name" else 200, anchor="center" if col != "Name" else "w")
        self.customer_table.pack(fill="both", expand=True)
        self.update_customer_table()
        self.customer_table.bind("<<TreeviewSelect>>", self.on_customer_select)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        self.update_customer_btn = tk.Button(button_frame, text="Update Customer",
                                           command=self.show_update_customer,
                                           bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                           activebackground="#2980b9", activeforeground="#ffffff",
                                           padx=12, pady=8, bd=0, state="disabled")
        self.update_customer_btn.pack(side="left", padx=5)
        self.delete_customer_btn = tk.Button(button_frame, text="Delete Customer",
                                           command=lambda: self.create_password_auth_window(
                                               "Authenticate Deletion", "Enter admin password to delete customer",
                                               self.validate_delete_customer_auth, selected_item=self.customer_table.selection()),
                                           bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                           activebackground="#c0392b", activeforeground="#ffffff",
                                           padx=12, pady=8, bd=0, state="disabled")
        self.delete_customer_btn.pack(side="left", padx=5)

    def update_customer_table(self, event: Optional[tk.Event] = None) -> None:
        for item in self.customer_table.get_children():
            self.customer_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            query = self.customer_search_entry.get().strip()
            sql = "SELECT customer_id, name, contact, address FROM customers WHERE name LIKE ?" if query else "SELECT customer_id, name, contact, address FROM customers"
            cursor.execute(sql, (f"%{query}%",) if query else ())
            for customer in cursor.fetchall():
                self.customer_table.insert("", "end", values=customer)

    def on_customer_select(self, event: tk.Event) -> None:
        selected_item = self.customer_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_customer_btn.config(state=state)
        self.delete_customer_btn.config(state=state)

    def generate_customer_id(self) -> str:
   
        current_time = datetime.now()
        month_year = current_time.strftime("%m-%Y")  # Format: MM-YYYY
        
        with self.conn:
            cursor = self.conn.cursor()
            # Query the latest customer ID for the current month and year
            cursor.execute("""
                SELECT customer_id 
                FROM customers 
                WHERE customer_id LIKE ? 
                ORDER BY customer_id DESC 
                LIMIT 1
            """, (f"{month_year}-C%",))
            last_customer = cursor.fetchone()
            
            if last_customer:
                # Extract the sequential number from the last customer ID
                last_seq = int(last_customer[0][-5:])  # Last 5 digits
                new_seq = last_seq + 1
            else:
                new_seq = 1  # Start at 1 if no customers exist for this month/year
            
            # Format the new customer ID
            customer_id = f"{month_year}-C{new_seq:05d}"  # Ensures 5-digit padding
            return customer_id

    def show_add_customer(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New Customer")
        window.geometry("400x400")
        window.configure(bg="#F5F5DC")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=15)

        fields = ["Customer ID", "Name", "Contact", "Address"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#8B5A2B").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F5F5DC")
            if field == "Customer ID":
                entry.insert(0, self.generate_customer_id())
                entry.config(state="readonly")  # Make Customer ID read-only
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        tk.Button(add_box, text="Add Customer",
                command=lambda: self.add_customer(entries["Customer ID"].get(), entries["Name"].get(),
                                                entries["Contact"].get(), entries["Address"].get(), window),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_customer(self, customer_id: str, name: str, contact: str, address: str, window: tk.Toplevel) -> None:
        if not name:
            messagebox.showerror("Error", "Name is required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO customers VALUES (?, ?, ?, ?)",
                            (customer_id, name, contact, address))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Add Customer", f"Added customer {name} with ID {customer_id}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_customer_table()
                window.destroy()
                messagebox.showinfo("Success", "Customer added successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Customer ID already exists", parent=self.root)

    def show_update_customer(self) -> None:
        selected_item = self.customer_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        customer_id = self.customer_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT customer_id, name, contact, address FROM customers WHERE customer_id = ?", (customer_id,))
            customer = cursor.fetchone()
            if customer:
                window = tk.Toplevel(self.root)
                window.title("Update Customer")
                window.geometry("400x400")
                window.configure(bg="#F5F5DC")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
                update_box.pack(pady=20)

                tk.Label(update_box, text="Update Customer", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#8B5A2B").pack(pady=15)

                fields = ["Customer ID", "Name", "Contact", "Address"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#8B5A2B").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#F5F5DC")
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entries[field] = entry
                    entry.insert(0, customer[i])

                tk.Button(update_box, text="Update Customer",
                         command=lambda: self.update_customer(entries["Customer ID"].get(), entries["Name"].get(),
                                                            entries["Contact"].get(), entries["Address"].get(),
                                                            customer[0], window),
                         bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                         activebackground="#27ae60", activeforeground="#ffffff",
                         padx=12, pady=8, bd=0).pack(pady=15)

    def update_customer(self, customer_id: str, name: str, contact: str, address: str, original_customer_id: str, window: tk.Toplevel) -> None:
        if not name:
            messagebox.showerror("Error", "Name is required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                if customer_id != original_customer_id:
                    cursor.execute("SELECT customer_id FROM customers WHERE customer_id = ?", (customer_id,))
                    if cursor.fetchone():
                        messagebox.showerror("Error", "Customer ID already exists", parent=self.root)
                        return
                cursor.execute("UPDATE customers SET customer_id = ?, name = ?, contact = ?, address = ? WHERE customer_id = ?",
                            (customer_id, name, contact, address, original_customer_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Update Customer", f"Updated customer {name} with ID {customer_id}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_customer_table()
                window.destroy()
                messagebox.showinfo("Success", "Customer updated successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Customer ID already exists", parent=self.root)

    def validate_delete_customer_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                customer_id = self.customer_table.item(selected_item)["values"][0]
                cursor.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Delete Customer", f"Deleted customer {customer_id}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_customer_table()
                window.destroy()
                messagebox.showinfo("Success", "Customer deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def select_customer(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Select Customer")
        window.geometry("600x400")
        window.configure(bg="#F5F5DC")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Select Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=10)

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=5)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#8B5A2B").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#F5F5DC")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        customers_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        customers_frame.pack(fill="both", expand=True, pady=10)
        columns = ("CustomerID", "Name", "Contact")
        headers = ("CUSTOMER ID", "NAME", "CONTACT")
        customer_table = ttk.Treeview(customers_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            customer_table.heading(col, text=head)
            customer_table.column(col, width=150 if col != "Name" else 200, anchor="center" if col != "Name" else "w")
        customer_table.pack(fill="both", expand=True)

        def update_customer_selection_table(event: Optional[tk.Event] = None) -> None:
            for item in customer_table.get_children():
                customer_table.delete(item)
            with self.conn:
                cursor = self.conn.cursor()
                query = search_entry.get().strip()
                sql = "SELECT customer_id, name, contact FROM customers WHERE name LIKE ?" if query else "SELECT customer_id, name, contact FROM customers"
                cursor.execute(sql, (f"%{query}%",) if query else ())
                for customer in cursor.fetchall():
                    customer_table.insert("", "end", values=customer)

        search_entry.bind("<KeyRelease>", update_customer_selection_table)
        update_customer_selection_table()

        def confirm_selection():
            selected_item = customer_table.selection()
            if not selected_item:
                messagebox.showerror("Error", "No customer selected", parent=window)
                return
            customer_id = customer_table.item(selected_item)["values"][0]
            customer_name = customer_table.item(selected_item)["values"][1]
            self.current_customer_id = customer_id
            self.customer_id_label.config(text=f"{customer_name} ({customer_id})")
            window.destroy()

        tk.Button(content_frame, text="Confirm Selection", command=confirm_selection,
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
                 padx=12, pady=8, bd=0).pack(pady=10)

    

    def validate_fund_auth(self, password: str, amount: str, fund_type: str, window: tk.Toplevel) -> None:
        try:
            amount = float(amount)
            if amount < 0:
                raise ValueError("Amount cannot be negative")
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
                admin_password = cursor.fetchone()
                if admin_password and password == admin_password[0]:
                    cursor.execute("INSERT INTO funds (fund_id, type, amount, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                (str(uuid.uuid4()), fund_type, amount,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                (str(uuid.uuid4()), f"{fund_type}", f"Recorded {fund_type} of {amount}",
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    window.destroy()
                    messagebox.showinfo("Success", f"{fund_type} recorded successfully", parent=self.root)
                else:
                    window.destroy()
                    messagebox.showerror("Error", "Invalid admin password", parent=self.root)
        except ValueError:
            window.destroy()
            messagebox.showerror("Error", "Invalid amount", parent=self.root)

    def void_selected_items(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected or cart is empty", parent=self.root)
            return
        item = self.cart[self.selected_item_index]
        if messagebox.askyesno("Confirm Void",
                            f"Are you sure you want to void {item['name']} from the cart?",
                            parent=self.root):
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Void Item", f"Voided item {item['name']} from cart",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            self.cart.pop(self.selected_item_index)
            self.update_cart_table()
            self.selected_item_index = None
            if hasattr(self, 'quantity_entry'):
                self.quantity_entry.config(state="disabled")
            messagebox.showinfo("Success", "Item voided successfully", parent=self.root)

    def void_order(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        if messagebox.askyesno("Confirm Void Order",
                            "Are you sure you want to void the entire order?",
                            parent=self.root):
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Void Order", "Voided entire order",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            self.cart.clear()
            self.selected_item_index = None
            self.discount_var.set(False)
            self.discount_authenticated = False
            self.update_cart_table()
            messagebox.showinfo("Success", "Order voided successfully", parent=self.root)
    

    def hold_transaction(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        transaction_id = str(uuid.uuid4())
        items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
        total_amount = sum(item["subtotal"] for item in self.cart)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (transaction_id, items, total_amount, 0.0, 0.0, timestamp, "Held", "Cash", 
                           getattr(self, 'current_customer_id', None)))
            cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                          (str(uuid.uuid4()), "Hold Transaction", f"Held transaction {transaction_id}",
                           timestamp, self.current_user))
            self.conn.commit()
        self.cart.clear()
        self.selected_item_index = None
        self.discount_var.set(False)
        self.discount_authenticated = False
        self.update_cart_table()
        messagebox.showinfo("Success", f"Transaction held with ID: {transaction_id}", parent=self.root)

    def view_unpaid_transactions(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Unpaid Transactions")
        window.geometry("800x400")
        window.configure(bg="#F5F5DC")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Unpaid Transactions", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=10)

        columns = ("TransactionID", "ItemsList", "TotalAmount", "Timestamp")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "TIMESTAMP")
        unpaid_table = ttk.Treeview(content_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            unpaid_table.heading(col, text=head)
            unpaid_table.column(col, width=150 if col != "ItemsList" else 300, anchor="center" if col != "ItemsList" else "w")
        unpaid_table.pack(fill="both", expand=True)

        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT transaction_id, items, total_amount, timestamp FROM transactions WHERE status = 'Held'")
            for transaction in cursor.fetchall():
                items_str = transaction[1]
                item_names = []
                for item_data in items_str.split(";"):
                    if item_data:
                        try:
                            item_id, qty = item_data.split(":")
                            cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                            name = cursor.fetchone()
                            if name:
                                item_names.append(f"{name[0]} (x{qty})")
                        except ValueError:
                            continue  # Skip malformed item data
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names)
                unpaid_table.insert("", "end", values=(transaction[0], items_display, f"{transaction[2]:.2f}", transaction[3]))

        unpaid_table.bind("<<TreeviewSelect>>", lambda e: self.on_unpaid_transaction_select(unpaid_table))

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)

        self.resume_btn = tk.Button(button_frame, text="Resume Transaction", 
                                    command=lambda: self.resume_transaction(unpaid_table, window),
                                    bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                                    activebackground="#27ae60", activeforeground="#ffffff",
                                    padx=12, pady=8, bd=0, state="disabled")
        self.resume_btn.pack(side="left", padx=5)

        self.delete_btn = tk.Button(button_frame, text="Delete Transaction",
                                    command=lambda: self.delete_unpaid_transaction(unpaid_table, window),
                                    bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                    activebackground="#c0392b", activeforeground="#ffffff",
                                    padx=12, pady=8, bd=0, state="disabled")
        self.delete_btn.pack(side="left", padx=5)
        
    def on_unpaid_transaction_select(self, unpaid_table: ttk.Treeview) -> None:
        selected_item = unpaid_table.selection()
        state = "normal" if selected_item else "disabled"
        self.resume_btn.config(state=state)
        self.delete_btn.config(state=state)
    
    def resume_transaction(self, unpaid_table: ttk.Treeview, window: tk.Toplevel) -> None:
        selected_item = unpaid_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=window)
            return
        transaction_id = unpaid_table.item(selected_item)["values"][0]
        self.cart.clear()
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT items, total_amount, customer_id FROM transactions WHERE transaction_id = ?", (transaction_id,))
                transaction = cursor.fetchone()
                if not transaction:
                    messagebox.showerror("Error", "Transaction not found", parent=window)
                    return
                for item_data in transaction[0].split(";"):
                    if item_data:
                        try:
                            item_id, qty = item_data.split(":")
                            cursor.execute("SELECT item_id, name, price FROM inventory WHERE item_id = ?", (item_id,))
                            item = cursor.fetchone()
                            if item:
                                self.cart.append({
                                    "id": item[0],
                                    "name": item[1],
                                    "price": item[2],
                                    "quantity": int(qty),
                                    "subtotal": item[2] * int(qty)
                                })
                            else:
                                messagebox.showwarning("Warning", f"Item ID {item_id} not found in inventory", parent=window)
                        except ValueError:
                            continue  # Skip malformed item data
                self.current_customer_id = transaction[2]
                if self.current_customer_id:
                    cursor.execute("SELECT name FROM customers WHERE customer_id = ?", (self.current_customer_id,))
                    customer_name = cursor.fetchone()
                    if customer_name:
                        self.customer_id_label.config(text=f"{customer_name[0]} ({self.current_customer_id})")
                    else:
                        self.customer_id_label.config(text="None Selected")
                else:
                    self.customer_id_label.config(text="None Selected")
                cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                log_id = f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}"
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (log_id, "Resume Transaction", f"Resumed and deleted transaction {transaction_id}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            
            window.destroy()
            
            # Ensure dashboard is fully set up
            self.show_dashboard()
            
            # Verify and update cart table
            if hasattr(self, 'cart_table') and self.cart_table.winfo_exists():
                # Clear existing items
                for item in self.cart_table.get_children():
                    self.cart_table.delete(item)
                # Insert cart items
                for item in self.cart:
                    self.cart_table.insert("", "end", values=(
                        item["name"], f"{item['price']:.2f}", item["quantity"], f"{item['subtotal']:.2f}"
                    ))
                # Re-grid cart table and parent frame
                self.cart_table.grid(row=1, column=0, columnspan=4, sticky="nsew")
                if self.cart_table.winfo_parent():
                    parent = self.cart_table.winfo_parent()
                    parent_frame = self.cart_table._nametowidget(parent)
                    parent_frame.grid(row=0, column=0, sticky="nsew")
                # Update totals and quantity
                self.update_cart_totals()
                self.update_quantity_display()
            else:
                messagebox.showwarning("Warning", "Cart table not initialized, retrying dashboard setup")
                self.show_dashboard()
                self.update_cart_table()
            
            # Force UI refresh
            self.root.update_idletasks()
            self.root.update()
            
            # Show success message after UI is fully updated
            self.root.after(200, lambda: messagebox.showinfo("Success", f"Transaction {transaction_id} resumed and removed from unpaid transactions", parent=self.root))
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to resume transaction: {e}", parent=self.root)

    def delete_unpaid_transaction(self, unpaid_table: ttk.Treeview, window: tk.Toplevel) -> None:
        if not unpaid_table or not isinstance(unpaid_table, ttk.Treeview):
            if window:
                window.destroy()
            messagebox.showerror("Error", "Invalid transaction table", parent=self.root)
            return

        selected_item = unpaid_table.selection()
        if not selected_item:
            if window:
                window.destroy()
            messagebox.showerror("Error", "No unpaid transaction selected", parent=self.root)
            return

        transaction_id = unpaid_table.item(selected_item)["values"][0]
        if not messagebox.askyesno("Confirm Deletion",
                                f"Are you sure you want to delete transaction {transaction_id}?",
                                parent=self.root):
            return

        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                log_id = f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}"
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (log_id, "Delete Unpaid Transaction", f"Deleted unpaid transaction {transaction_id}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                if window:
                    window.destroy()  # Close the unpaid transactions window
                messagebox.showinfo("Success", f"Unpaid transaction {transaction_id} deleted successfully", parent=self.root)
            except sqlite3.Error as e:
                messagebox.showerror("Error", f"Failed to delete unpaid transaction: {e}", parent=self.root)

    def mode_of_payment(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Select Payment Method")
        window.geometry("400x450")
        window.configure(bg="#F5F5DC")

        payment_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        payment_box.pack(pady=20)

        tk.Label(payment_box, text="Select Payment Method", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=15)

        payment_var = tk.StringVar()
        payment_options = ["Cash", "Credit Card", "Debit Card", "Mobile Payment"]
        for option in payment_options:
            tk.Radiobutton(payment_box, text=option, variable=payment_var, value=option,
                          font=("Helvetica", 16), bg="#ffffff", fg="#8B5A2B").pack(anchor="w", pady=5)

        tk.Button(payment_box, text="Confirm",
                 command=lambda: self.set_payment_method(payment_var.get(), window),
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
                 padx=12, pady=8, bd=0).pack(pady=15)

    def set_payment_method(self, payment_method: str, window: tk.Toplevel) -> None:
        if not payment_method:
            messagebox.showerror("Error", "Please select a payment method", parent=self.root)
            return
        self.current_payment_method = payment_method
        window.destroy()
        messagebox.showinfo("Success", f"Payment method set to {payment_method}", parent=self.root)

    def return_transaction(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Return Transaction")
        window.geometry("400x300")
        window.configure(bg="#F5F5DC")

        return_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        return_box.pack(pady=20)

        tk.Label(return_box, text="Return Transaction", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#8B5A2B").pack(pady=15)

        tk.Label(return_box, text="Transaction ID", font=("Helvetica", 14), bg="#ffffff", fg="#8B5A2B").pack()
        transaction_id_entry = tk.Entry(return_box, font=("Helvetica", 14), bg="#F5F5DC")
        transaction_id_entry.pack(pady=5, fill="x")

        tk.Button(return_box, text="Submit",
                 command=lambda: self.create_password_auth_window(
                     "Authenticate Return", "Enter admin password to process return",
                     self.validate_return_auth, transaction_id=transaction_id_entry.get(), window=window),
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
                 padx=12, pady=8, bd=0).pack(pady=15)

    def validate_refund_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        transaction_id = kwargs.get("transaction_id")
        return_window = kwargs.get("window", window)  # Default to auth window if not provided

        # Extract transaction_id from selected_item if not provided
        if not transaction_id and selected_item:
            try:
                transaction_id = self.transactions_table.item(selected_item[0])["values"][0]
            except (IndexError, KeyError):
                window.destroy()
                messagebox.showerror("Error", "No transaction selected or invalid selection", parent=self.root)
                return

        if not transaction_id:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return

        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                self.show_return_transaction(transaction_id)
                window.destroy()
                if return_window != window:
                    return_window.destroy()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def show_return_transaction(self, transaction_id: str) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if not transaction:
                messagebox.showerror("Error", "Transaction ID not found", parent=self.root)
                return
            if transaction[6] == "Returned":
                messagebox.showerror("Error", "Transaction has already been returned", parent=self.root)
                return

            items = transaction[1].split(";")
            return_items = []
            missing_items = []
            for item_data in items:
                if item_data:
                    try:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, retail_price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            return_items.append({"id": item_id, "name": item[0], "quantity": int(qty), "retail_price": float(item[1])})
                        else:
                            missing_items.append(item_id)
                    except ValueError:
                        missing_items.append(item_data)

            if missing_items:
                messagebox.showwarning("Warning", f"Some items not found in inventory: {', '.join(missing_items)}", parent=self.root)
                if not return_items:
                    messagebox.showerror("Error", "No valid items to return", parent=self.root)
                    return

            window = tk.Toplevel(self.root)
            window.title(f"Return Transaction {transaction_id}")
            window.geometry("600x400")
            window.configure(bg="#F5F5DC")

            content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
            content_frame.pack(fill="both", expand=True)

            tk.Label(content_frame, text=f"Return Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#8B5A2B").pack(pady=10)

            columns = ("Item", "Quantity", "RetailPrice")
            headers = ("ITEM", "QUANTITY", "RETAIL PRICE")
            return_table = ttk.Treeview(content_frame, columns=columns, show="headings")
            for col, head in zip(columns, headers):
                return_table.heading(col, text=head)
                return_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
            return_table.pack(fill="both", expand=True)

            for item in return_items:
                return_table.insert("", "end", values=(item["name"], item["quantity"], f"{item['retail_price']:.2f}"))

            tk.Button(content_frame, text="Confirm Return",
                    command=lambda: self.process_return(transaction_id, return_items, window),
                    bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                    activebackground="#27ae60", activeforeground="#ffffff",
                    padx=12, pady=8, bd=0).pack(pady=10)

    def process_return(self, transaction_id: str, return_items: List[Dict], window: tk.Toplevel) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                status = cursor.fetchone()
                if not status:
                    messagebox.showerror("Error", "Transaction not found", parent=self.root)
                    return
                if status[0] == "Returned":
                    messagebox.showerror("Error", "Transaction has already been returned", parent=self.root)
                    return

                for item in return_items:
                    cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    result = cursor.fetchone()
                    if result is None:
                        messagebox.showerror("Error", f"Item {item['name']} not found in inventory", parent=self.root)
                        return
                    cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?",
                                (item["quantity"], item["id"]))

                cursor.execute("UPDATE transactions SET status = 'Returned' WHERE transaction_id = ?",
                            (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Return Transaction", f"Returned transaction {transaction_id}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                window.destroy()
                messagebox.showinfo("Success", "Transaction returned successfully", parent=self.root)
                if hasattr(self, 'transactions_table'):
                    self.update_transactions_table()
                self.check_low_inventory()
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to process return: {e}", parent=self.root)

if __name__ == "__main__":
    root = tk.Tk()
    app = PharmacyPOS(root)
    root.mainloop()