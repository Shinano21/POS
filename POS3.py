import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import uuid
from PIL import Image, ImageTk
from typing import Optional, List, Dict, Callable
import os
from pathlib import Path
import webbrowser

class PharmacyPOS:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Shinano POS")
        self.root.geometry("1280x720")
        self.root.configure(bg="#f5f6f5")

        try:
            icon_image = ImageTk.PhotoImage(Image.open("images/medkitpos.png"))
            self.root.iconphoto(True, icon_image)
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
        self.root.bind("<F2>", self.void_selected_items)
        self.root.bind("<F3>", self.void_order)
        self.root.bind("<F4>", self.hold_transaction)
        self.root.bind("<F5>", self.view_unpaid_transactions)
        self.root.bind("<F6>", self.mode_of_payment)
        self.root.bind("<F7>", self.handle_discount_toggle_event)
        self.root.bind("<F8>", self.return_transaction)
        self.root.bind("<F9>", self.select_customer)
        self.root.bind("<Shift_R>", self.focus_cash_paid)

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
        style.configure("Treeview", rowheight=30, font=("Helvetica", 14))
        style.configure("Treeview.Heading", font=("Helvetica", 14, "bold"))
        style.theme_use("clam")

    def toggle_fullscreen(self, event: Optional[tk.Event] = None) -> str:
        fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not fullscreen)
        return "break"

    def create_database(self) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                # Diagnostic: Print current table structure
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [col[1] for col in cursor.fetchall()]
                print("Inventory table columns:", columns)
                
                # Create inventory table with 8 columns (including created_at)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS inventory (
                        item_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        type TEXT NOT NULL,
                        unit_price REAL NOT NULL DEFAULT 0.0,
                        retail_price REAL NOT NULL DEFAULT 0.0,
                        quantity INTEGER NOT NULL DEFAULT 0,
                        supplier TEXT,
                        created_at TEXT
                    )
                ''')
                # Check and add missing columns
                if 'unit_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN unit_price REAL NOT NULL DEFAULT 0.0")
                if 'retail_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN retail_price REAL NOT NULL DEFAULT 0.0")
                if 'quantity' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN quantity INTEGER NOT NULL DEFAULT 0")
                if 'supplier' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN supplier TEXT")
                if 'created_at' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN created_at TEXT")
                
                # Update NULL values and ensure defaults
                cursor.execute("UPDATE inventory SET unit_price = 0.0 WHERE unit_price IS NULL")
                cursor.execute("UPDATE inventory SET retail_price = 0.0 WHERE retail_price IS NULL")
                cursor.execute("UPDATE inventory SET quantity = 0 WHERE quantity IS NULL")
                cursor.execute("UPDATE inventory SET created_at = ? WHERE created_at IS NULL", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
                
                # Create other tables
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT,
                        role TEXT,
                        status TEXT DEFAULT 'Online'
                    )
                ''')
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
            ("MED001", "Pain Reliever", "Medicine", 10.00, 900.00, 900, "Tedey Groups"),
            ("SUP001", "Vitamin C", "Supplement", 4.00, 5.00, 200, "HealthSupplies Inc"),
            ("DEV001", "Thermometer", "Medical Device", 12.00, 15.00, 50, "MediTech Ltd"),
        ]
        with self.conn:
            cursor = self.conn.cursor()
            for item_id, name, item_type, unit_price, retail_price, quantity, supplier in sample_items:
                cursor.execute("""
                    INSERT OR IGNORE INTO inventory 
                    (item_id, name, type, unit_price, retail_price, quantity, supplier, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (item_id, name, item_type, unit_price, retail_price, quantity, supplier, 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            self.conn.commit()

    def setup_gui(self) -> None:
        self.main_frame = tk.Frame(self.root, bg="#f5f6f5")
        self.main_frame.pack(fill="both", expand=True)
        self.show_login()
        self.root.bind("<Shift-Return>", self.handle_shift_enter_key)
        self.root.bind("<Shift_R>", self.focus_cash_paid)

    def focus_cash_paid(self, event: Optional[tk.Event] = None) -> None:
        if self.current_user and hasattr(self, 'summary_entries') and "Cash Paid " in self.summary_entries:
            cash_paid_entry = self.summary_entries["Cash Paid "]
            cash_paid_entry.focus_set()
            cash_paid_entry.select_range(0, tk.END)
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

    def toggle_sidebar(self) -> None:
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            self.hamburger_btn.config(text="☰")
            self.sidebar_visible = False
        else:
            self.sidebar.pack(side="left", fill="y", before=self.header)
            self.hamburger_btn.config(text="✕")
            self.sidebar_visible = True

    def setup_navigation(self, parent: tk.Frame) -> None:
        self.sidebar = tk.Frame(parent, bg="#1a1a1a", width=200)
        self.sidebar.pack(side="left", fill="y")

        self.header = tk.Frame(parent, bg="#f5f6f5")
        self.header.pack(side="top", fill="x", pady=8)

        self.hamburger_btn = tk.Button(self.header, text="✕", command=self.toggle_sidebar,
                                      bg="#f5f6f5", fg="#1a1a1a", font=("Helvetica", 18),
                                      activebackground="#e0e0e0", activeforeground="#1a1a1a",
                                      padx=8, pady=4, bd=0)
        self.hamburger_btn.pack(side="left", padx=5)

        tk.Label(self.header, text=" WELCOME!", font=("Helvetica", 18, "bold"),
                 bg="#f5f6f5", fg="#1a1a1a").pack(side="left", padx=12)
        tk.Label(self.header, text=datetime.now().strftime("%B %d, %Y %I:%M %p PST"),
                 font=("Helvetica", 12), bg="#f5f6f5", fg="#666").pack(side="left", padx=12)
        tk.Label(self.header, text=f"{self.current_user} ({self.get_user_role()})" if self.current_user else "",
                 font=("Helvetica", 12), bg="#f5f6f5", fg="#666").pack(side="right", padx=12)

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
                            bg="#1a1a1a" if "Dashboard" not in text else "#2ecc71",
                            fg="#ffffff", font=("Helvetica", 14),
                            activebackground="#2ecc71" if "Dashboard" in text else "#2c2c2c",
                            activeforeground="#ffffff",
                            padx=12, pady=8, bd=0)
            btn.pack(fill="x", pady=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#2ecc71" if "Dashboard" in b["text"] else "#2c2c2c"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#1a1a1a" if "Dashboard" not in b["text"] else "#2ecc71"))

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
        window.configure(bg="#f5f6f5")

        auth_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        auth_box.pack(pady=20)

        tk.Label(auth_box, text=title, font=("Helvetica", 18, "bold"),
                 bg="#ffffff", fg="#1a1a1a").pack(pady=12)
        tk.Label(auth_box, text=prompt, font=("Helvetica", 12),
                 bg="#ffffff", fg="#666").pack(pady=8)

        tk.Label(auth_box, text="Admin Password", font=("Helvetica", 14),
                 bg="#ffffff", fg="#1a1a1a").pack()
        password_entry = tk.Entry(auth_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(auth_box, text="Show Password", variable=show_password_var,
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                       font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(pady=8)

        tk.Button(auth_box, text="Authenticate",
                  command=lambda: callback(password_entry.get(), window, **kwargs),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
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
        login_frame = tk.Frame(self.main_frame, bg="#f5f6f5", padx=20, pady=20)
        login_frame.pack(expand=True)

        login_box = tk.Frame(login_frame, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        login_box.pack(pady=20)

        tk.Label(login_box, text="Login", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=12)
        tk.Label(login_box, text="Welcome to the POS! Please enter your credentials.",
                font=("Helvetica", 12), bg="#ffffff", fg="#666").pack(pady=8)

        tk.Label(login_box, text="Username", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(anchor="w")
        username_entry = tk.Entry(login_box, font=("Helvetica", 14), bg="#f5f6f5")
        username_entry.pack(pady=5, fill="x")

        tk.Label(login_box, text="Password", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(anchor="w")
        password_entry = tk.Entry(login_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(login_box, text="Show Password", variable=show_password_var,
                    command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                    font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(anchor="w", pady=8)

        tk.Button(login_box, text="Login", command=lambda: self.validate_login(username_entry.get(), password_entry.get()),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
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
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_container = tk.Frame(content_frame, bg="#f5f6f5", padx=8, pady=8)
        search_container.pack(fill="x", pady=10)

        search_frame = tk.Frame(search_container, bg="#ffffff", bd=1, relief="flat")
        search_frame.pack(fill="x", padx=2, pady=2)

        tk.Label(search_frame, text="Search Item:", font=("Helvetica", 14),
                bg="#ffffff", fg="#333").pack(side="left", padx=12)

        entry_frame = tk.Frame(search_frame, bg="#f5f6f5")
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=5)

        self.search_entry = tk.Entry(entry_frame, font=("Helvetica", 14), bg="#f5f6f5", bd=0, highlightthickness=0)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
        self.search_entry.bind("<FocusOut>", lambda e: self.hide_suggestion_window())

        self.clear_btn = tk.Button(entry_frame, text="✕", command=self.clear_search,
                                bg="#f5f6f5", fg="#666", font=("Helvetica", 12),
                                activebackground="#e0e0e0", activeforeground="#1a1a1a",
                                bd=0, padx=2, pady=2)
        self.clear_btn.pack(side="right", padx=(0, 5))
        self.clear_btn.pack_forget()

        tk.Button(search_frame, text="🛒", command=self.select_suggestion,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=8, pady=4, bd=0).pack(side="left", padx=5)

        if self.get_user_role() == "Drug Lord":
            tk.Button(search_frame, text="🗑️", command=lambda: self.create_password_auth_window(
                "Authenticate Deletion", "Enter admin password to delete item", self.validate_delete_item_auth),
                bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#c0392b", activeforeground="#ffffff",
                padx=8, pady=4, bd=0).pack(side="left", padx=5)

        if not self.suggestion_window:
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.wm_overrideredirect(True)
            self.suggestion_window.configure(bg="#ffffff")
            self.suggestion_window.withdraw()
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

        main_content = tk.Frame(content_frame, bg="#ffffff")
        main_content.pack(fill="both", expand=True)
        main_content.grid_rowconfigure(0, weight=1)
        main_content.grid_columnconfigure(0, weight=3)
        main_content.grid_columnconfigure(1, weight=1)

        cart_frame = tk.Frame(main_content, bg="#ffffff", bd=1, relief="flat")
        cart_frame.grid(row=0, column=0, sticky="nsew", padx=0)

        columns = ("Product", "UnitPrice", "RetailPrice", "Quantity", "Subtotal")
        headers = ("PRODUCT DETAILS", "UNIT PRICE", "RETAIL PRICE", "QUANTITY", "SUBTOTAL")
        self.cart_table = ttk.Treeview(cart_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.cart_table.heading(col, text=head)
            self.cart_table.column(col, width=150 if col != "Product" else 300,
                                anchor="center" if col != "Product" else "w")
        self.cart_table.grid(row=1, column=0, columnspan=5, sticky="nsew")
        self.cart_table.bind("<<TreeviewSelect>>", self.on_item_select)
        cart_frame.grid_rowconfigure(1, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        self.summary_frame = tk.Frame(main_content, bg="#ffffff", bd=1, relief="flat")
        self.summary_frame.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        self.summary_frame.grid_propagate(False)
        self.summary_frame.configure(width=300)

        self.discount_status_label = tk.Label(self.summary_frame, text="Discount: Not Applied",
                                            font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a")
        self.discount_status_label.pack(pady=5)

        tk.Label(self.summary_frame, text="Customer ID", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
        self.customer_id_label = tk.Label(self.summary_frame, text="None Selected", font=("Helvetica", 12),
                                        bg="#ffffff", fg="#666")
        self.customer_id_label.pack(pady=2, anchor="w")
        tk.Button(self.summary_frame, text="Select Customer", command=self.select_customer,
                bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#2980b9", activeforeground="#ffffff",
                padx=8, pady=4, bd=0).pack(pady=5, fill="x")

        tk.Label(self.summary_frame, text="Item Quantity", font=("Helvetica", 18),
                bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
        self.quantity_entry = tk.Entry(self.summary_frame, font=("Helvetica", 18), bg="#f5f6f5", state="disabled")
        self.quantity_entry.pack(pady=2, fill="x")
        self.quantity_entry.bind("<Return>", self.adjust_quantity)
        self.quantity_entry.bind("<FocusOut>", self.adjust_quantity)

        fields = ["Subtotal ", "Discount ", "Final Total ", "Cash Paid ", "Change "]
        self.summary_entries = {}
        for field in fields:
            tk.Label(self.summary_frame, text=field, font=("Helvetica", 18),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
            entry = tk.Entry(self.summary_frame, font=("Helvetica", 18), bg="#f5f6f5")
            entry.pack(pady=2, fill="x")
            self.summary_entries[field] = entry
            if field != "Cash Paid ":
                entry.config(state="readonly")
                entry.insert(0, "0.00")
            else:
                entry.insert(0, "0.00")
                entry.bind("<KeyRelease>", self.update_change)

        button_frame = tk.Frame(self.summary_frame, bg="#ffffff")
        button_frame.pack(pady=10, fill="x")

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
                cursor.execute("SELECT name, retail_price, quantity, supplier FROM inventory WHERE name LIKE ? OR supplier LIKE ?",
                            (f"%{query}%", f"%{query}%"))
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
                self.clear_btn.pack

    def highlight_on_hover(self, event: tk.Event) -> None:
        if self.suggestion_listbox and self.suggestion_listbox.winfo_exists():
            index = self.suggestion_listbox.index(f"@{event.x},{event.y}")
            if index >= 0 and index < self.suggestion_listbox.size():
                self.suggestion_listbox.selection_clear(0, tk.END)
                self.suggestion_listbox.selection_set(index)
                self.suggestion_listbox.see(index)

    def hide_suggestion_window(self) -> None:
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            self.suggestion_window.withdraw()

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
                    cursor.execute("SELECT * FROM inventory WHERE name = ?", (item_name,))
                    item = cursor.fetchone()
                    if item:
                        for cart_item in self.cart:
                            if cart_item["id"] == item[0]:
                                cart_item["quantity"] += 1
                                cart_item["subtotal"] = cart_item["retail_price"] * cart_item["quantity"]
                                break
                        else:
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "unit_price": item[3],
                                "retail_price": item[4],
                                "quantity": 1,
                                "subtotal": item[4]
                            })
                        self.update_cart_table()
                        self.search_entry.delete(0, tk.END)
                        self.hide_suggestion_window()
                        self.clear_btn.pack_forget()
                        self.update_quantity_display()

    def update_change(self, event: Optional[tk.Event] = None) -> None:
        try:
            cash_paid = float(self.summary_entries["Cash Paid "].get())
            final_total = float(self.summary_entries["Final Total "].get())
            change = max(cash_paid - final_total, 0)
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
        self.discount_var.set(not self.discount_var.get())
        if self.discount_var.get() and not self.discount_authenticated:
            self.create_password_auth_window(
                "Authenticate Discount",
                "Enter admin password to apply 20% discount",
                self.validate_discount_auth
            )
        else:
            self.discount_authenticated = False
            self.update_cart_totals()
            self.update_discount_status_label()

    def update_discount_status_label(self) -> None:
        for widget in self.summary_frame.winfo_children():
            if isinstance(widget, tk.Label) and widget.cget("text").startswith("Discount:"):
                widget.config(text=f"Discount: {'Applied' if self.discount_var.get() else 'Not Applied'}")

    def validate_discount_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                self.discount_authenticated = True
                self.update_cart_totals()
                self.update_discount_status_label()
                window.destroy()
                messagebox.showinfo("Success", "Discount authentication successful", parent=self.root)
            else:
                self.discount_var.set(False)
                self.discount_authenticated = False
                self.update_cart_totals()
                self.update_discount_status_label()
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_cart_table(self) -> None:
        for item in self.cart_table.get_children():
            self.cart_table.delete(item)
        for item in self.cart:
            self.cart_table.insert("", "end", values=(
                item["name"], f"{item['unit_price']:.2f}", f"{item['retail_price']:.2f}", 
                item["quantity"], f"{item['subtotal']:.2f}"
            ))
        self.update_cart_totals()
        self.update_quantity_display()

    def on_item_select(self, event: tk.Event) -> None:
        selected_item = self.cart_table.selection()
        if selected_item:
            item_index = self.cart_table.index(selected_item[0])
            if 0 <= item_index < len(self.cart):
                self.selected_item_index = item_index
                self.quantity_entry.config(state="normal")
                self.update_quantity_display()
            else:
                self.selected_item_index = None
                self.quantity_entry.config(state="disabled")
                self.quantity_entry.delete(0, tk.END)

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
                item["subtotal"] = item["retail_price"] * new_quantity
                if new_quantity == 0:
                    self.cart.pop(self.selected_item_index)
                self.update_cart_table()
                self.selected_item_index = None
                self.quantity_entry.config(state="disabled")
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity.", parent=self.root)
            self.update_quantity_display()

    def update_cart_totals(self) -> None:
        subtotal = sum(item["subtotal"] for item in self.cart)
        discount = subtotal * 0.2 if self.discount_var.get() and self.discount_authenticated else 0
        final_total = subtotal - discount

        for field in ["Subtotal ", "Discount ", "Final Total "]:
            self.summary_entries[field].config(state="normal")
            self.summary_entries[field].delete(0, tk.END)
            self.summary_entries[field].insert(0, f"{subtotal:.2f}" if field == "Subtotal " else
                                             f"{discount:.2f}" if field == "Discount " else f"{final_total:.2f}")
            self.summary_entries[field].config(state="readonly")

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
        month_year = current_time.strftime("%m-%Y")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT transaction_id 
                FROM transactions 
                WHERE transaction_id LIKE ? 
                ORDER BY transaction_id DESC 
                LIMIT 1
            """, (f"{month_year}%",))
            last_transaction = cursor.fetchone()
            if last_transaction:
                last_seq = int(last_transaction[0][-6:])
                new_seq = last_seq + 1
            else:
                new_seq = 1
            transaction_id = f"{month_year}-{new_seq:06d}"
            return transaction_id

    def process_checkout(self, cash_paid: float, final_total: float) -> None:
        try:
            transaction_id = self.generate_transaction_id()
            items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
            change = cash_paid - final_total
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payment_method = getattr(self, 'current_payment_method', 'Cash')
            customer_id = getattr(self, 'current_customer_id', None)

            with self.conn:
                cursor = self.conn.cursor()
                for item in self.cart:
                    cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    current_qty = cursor.fetchone()[0]
                    if current_qty < item["quantity"]:
                        raise ValueError(f"Insufficient stock for {item['name']}: {current_qty} available, {item['quantity']} requested")

                cursor.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (transaction_id, items, final_total, cash_paid, change, timestamp,
                             "Completed", payment_method, customer_id))

                for item in self.cart:
                    cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?",
                                (item["quantity"], item["id"]))

                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Checkout", f"Completed transaction {transaction_id}",
                             timestamp, self.current_user))

                self.conn.commit()

            self.check_low_inventory()

            self.summary_entries["Change "].config(state="normal")
            self.summary_entries["Change "].delete(0, tk.END)
            self.summary_entries["Change "].insert(0, f"{change:.2f}")
            self.summary_entries["Change "].config(state="readonly")

            self.summary_entries["Cash Paid "].delete(0, tk.END)
            self.summary_entries["Cash Paid "].insert(0, "0.00")

            messagebox.showinfo("Success", f"Transaction completed! ID: {transaction_id}", parent=self.root)
            self.customer_id_label.config(text="None Selected")
            self.cart.clear()
            self.selected_item_index = None
            self.discount_var.set(False)
            self.discount_authenticated = False
            self.current_payment_method = None
            self.current_customer_id = None
            self.update_cart_table()
        except (sqlite3.OperationalError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to process transaction: {e}", parent=self.root)

    def check_low_inventory(self) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name, quantity FROM inventory WHERE quantity <= 5")
            low_items = cursor.fetchall()
            if low_items:
                message = "\n".join([f"{name}: {qty} left" for name, qty in low_items])
                messagebox.showwarning("Low Inventory", f"Low stock for:\n{message}", parent=self.root)

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
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)

        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        self.inventory_search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        self.inventory_search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.inventory_search_entry.bind("<KeyRelease>", self.update_inventory_table)

        tk.Label(search_frame, text="Filter by Type:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left", padx=(10, 5))
        self.type_filter_var = tk.StringVar()
        self.type_filter_combobox = ttk.Combobox(search_frame, textvariable=self.type_filter_var,
                                                values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                                                state="readonly", font=("Helvetica", 14))
        self.type_filter_combobox.pack(side="left", padx=5)
        self.type_filter_combobox.set("All")
        self.type_filter_combobox.bind("<<ComboboxSelected>>", self.update_inventory_table)

        tk.Button(search_frame, text="Add New Item",
                command=self.show_add_item,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="right", padx=5)

        inventory_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        inventory_frame.pack(fill="both", expand=True, pady=10)

        columns = ("Name", "Type", "UnitPrice", "RetailPrice", "Quantity", "Supplier")
        headers = ("NAME", "TYPE", "UNIT PRICE", "RETAIL PRICE", "QUANTITY", "SUPPLIER")
        self.inventory_table = ttk.Treeview(inventory_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.inventory_table.heading(col, text=head)
            self.inventory_table.column(col, width=150 if col != "Name" else 300,
                                    anchor="center" if col != "Name" else "w")
        self.inventory_table.grid(row=1, column=0, columnspan=3, sticky="nsew")
        self.update_inventory_table()
        self.inventory_table.bind("<Double-1>", self.on_inventory_table_click)
        inventory_frame.grid_rowconfigure(1, weight=1)
        inventory_frame.grid_columnconfigure(0, weight=1)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        self.update_item_btn = tk.Button(button_frame, text="Update Item",
                                        command=self.show_update_item_from_selection,
                                        bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#2980b9", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.update_item_btn.pack(side="left", padx=5)
        self.delete_item_btn = tk.Button(button_frame, text="Delete Item",
                                        command=self.confirm_delete_item,
                                        bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#c0392b", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.delete_item_btn.pack(side="left", padx=5)

        self.inventory_table.bind("<<TreeviewSelect>>", self.on_inventory_select)

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

    def show_add_item(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New Item to Inventory")
        window.geometry("400x600")
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New Item to Inventory", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID (Barcode)", "Product Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        type_var = tk.StringVar()
        tk.Label(add_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        ttk.Combobox(add_box, textvariable=type_var,
                    values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                    state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(add_box, text="Add Item",
                command=lambda: self.add_item(
                    entries["Item ID (Barcode)"].get(),
                    entries["Product Name"].get(),
                    type_var.get(),
                    entries["Unit Price"].get(),
                    entries["Retail Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    window
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_item(self, item_id: str, name: str, item_type: str, unit_price: str, retail_price: str, quantity: str, supplier: str, window: tk.Toplevel) -> None:
        try:
            unit_price = float(unit_price)
            retail_price = float(retail_price)
            quantity = int(quantity)
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return
            if unit_price > retail_price:
                messagebox.showerror("Error", "Unit Price cannot be greater than Retail Price", parent=self.root)
                return
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inventory (item_id, name, type, unit_price, retail_price, quantity, supplier, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (item_id, name, item_type, unit_price, retail_price, quantity, supplier, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Add Item", f"Added item {item_id}: {name}, {quantity} units, Supplier: {supplier}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item added successfully", parent=self.root)
                if quantity <= 5:
                    self.check_low_inventory()
        except ValueError:
            messagebox.showerror("Error", "Invalid price or quantity", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def show_update_item_from_selection(self) -> None:
        selected_item = self.inventory_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        item_name = self.inventory_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inventory WHERE name = ?", (item_name,))
            item = cursor.fetchone()
            if item:
                self.show_update_item(item)

    def show_update_item(self, item: tuple) -> None:
        window = tk.Toplevel(self.root)
        window.title("Update Item")
        window.geometry("400x600")
        window.configure(bg="#f5f6f5")

        update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        update_box.pack(pady=20)

        tk.Label(update_box, text="Update Item", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID (Barcode)", "Product Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
        entries = {}
        for field in fields:
            frame = tk.Frame(update_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a", anchor="e").pack(side="left", padx=5)
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            if field in ["Unit Price", "Retail Price"]:
                entry.configure(validate="key", validatecommand=(self.root.register(lambda s: s.replace(".", "").isdigit() or s == "" or s == "."), "%P"))
            elif field == "Quantity":
                entry.configure(validate="key", validatecommand=(self.root.register(lambda s: s.isdigit() or s == ""), "%P"))
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry
            # Populate fields with correct mapping
            if field == "Item ID (Barcode)":
                entry.insert(0, item[0])
                entry.config(state="readonly")
            elif field == "Product Name":
                entry.insert(0, item[1])
            elif field == "Unit Price":
                entry.insert(0, str(item[3]) if item[3] is not None else "0.0")
            elif field == "Retail Price":
                entry.insert(0, str(item[4]) if item[4] is not None else "0.0")
            elif field == "Quantity":
                entry.insert(0, str(item[5]) if item[5] is not None else "0")
            elif field == "Supplier":
                entry.insert(0, item[6] if item[6] else "Unknown")

        type_var = tk.StringVar(value=item[2])  # Set initial value to existing type
        tk.Label(update_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        ttk.Combobox(update_box, textvariable=type_var,
                    values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                    state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(update_box, text="Update Item",
                command=lambda: self.update_item(
                    entries["Item ID (Barcode)"].get(),
                    entries["Product Name"].get(),
                    type_var.get(),
                    entries["Unit Price"].get(),
                    entries["Retail Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    window,  # Pass the window object
                    item[0]  # Pass the original item_id
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def show_update_item(self, item: tuple) -> None:
        window = tk.Toplevel(self.root)
        window.title("Update Item")
        window.geometry("400x550")
        window.configure(bg="#f5f6f5")

        update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        update_box.pack(pady=20)

        tk.Label(update_box, text="Update Item", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID", "Product Name", "Price", "Quantity", "Supplier", "Expiry Date (YYYY-MM-DD)"]
        entries = {}
        for i, field in enumerate(fields):
            frame = tk.Frame(update_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            if field == "Price":
                entry.configure(validate="key", validatecommand=(self.root.register(lambda s: s.replace(".", "").isdigit() or s == "" or s == "."), "%P"))
            elif field == "Quantity":
                entry.configure(validate="key", validatecommand=(self.root.register(lambda s: s.isdigit() or s == ""), "%P"))
            elif field == "Item ID":
                entry.configure(state="readonly")  # Prevent editing Item ID
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry
            entry.insert(0, item[i] or "")

        type_var = tk.StringVar(value=item[2])
        tk.Label(update_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        ttk.Combobox(update_box, textvariable=type_var,
                    values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                    state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(update_box, text="Update Item",
                command=lambda: self.update_item(
                    entries["Item ID"].get(),
                    entries["Product Name"].get(),
                    type_var.get(),
                    entries["Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    entries["Expiry Date (YYYY-MM-DD)"].get(),
                    window,  # Pass window first
                    item[0]  # Pass original_item_id last
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)
    
    def update_item(self, item_id: str, name: str, item_type: str, price: str, quantity: str, supplier: str, expiry_date: str, window: tk.Toplevel, original_item_id: str) -> None:
        try:
            # Validate numeric inputs
            try:
                price = float(price) if price.strip() else 0.0
                quantity = int(quantity) if quantity.strip() else 0
                if price < 0 or quantity < 0:
                    messagebox.showerror("Error", "Price and Quantity must be non-negative", parent=self.root)
                    return
            except ValueError:
                messagebox.showerror("Error", "Price must be a valid number and Quantity must be a valid integer", parent=self.root)
                return

            # Validate required fields
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return

            # Validate expiry date format if provided
            if expiry_date.strip():
                try:
                    datetime.strptime(expiry_date, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Error", "Invalid expiry date format. Use YYYY-MM-DD", parent=self.root)
                    return
            else:
                expiry_date = None  # Set to None if empty

            # Sanitize inputs
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else original_item_id

            # Check if item_id exists
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM inventory WHERE item_id = ?", (original_item_id,))
                if cursor.fetchone()[0] == 0:
                    messagebox.showerror("Error", f"Item ID {original_item_id} does not exist", parent=self.root)
                    return

                # Update inventory table
                cursor.execute("""
                    UPDATE inventory 
                    SET item_id = ?, name = ?, type = ?, price = ?, quantity = ?, supplier = ?, expiry_date = ?, created_at = ?
                    WHERE item_id = ?
                """, (item_id, name, item_type, price, quantity, supplier, expiry_date, 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), original_item_id))

                # Log the update
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Update Item", 
                            f"Updated item {item_id}: {name}, {quantity} units, Supplier: {supplier}, Expiry: {expiry_date or 'None'}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))

                self.conn.commit()

            # Update UI and close window
            self.update_inventory_table()
            window.destroy()
            messagebox.showinfo("Success", "Item updated successfully", parent=self.root)

            # Check for low inventory and expiry
            if quantity <= 5:
                self.check_low_inventory()
            if expiry_date:
                self.check_expiry_dates()

        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error: {e}", parent=self.root)

    def on_inventory_table_click(self, event: tk.Event) -> None:
        selected_item = self.inventory_table.selection()
        if selected_item:
            item_name = self.inventory_table.item(selected_item)["values"][0]
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM inventory WHERE name = ?", (item_name,))
                item = cursor.fetchone()
                if item:
                    self.show_update_item(item)

    def update_inventory_table(self, event: Optional[tk.Event] = None) -> None:
        for item in self.inventory_table.get_children():
            self.inventory_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            query = self.inventory_search_entry.get().strip()
            type_filter = self.type_filter_var.get()
            sql = "SELECT name, type, unit_price, retail_price, quantity, supplier FROM inventory WHERE name LIKE ?"
            params = [f"%{query}%"]
            if type_filter and type_filter != "All":
                sql += " AND type = ?"
                params.append(type_filter)
            cursor.execute(sql, params)
            for item in cursor.fetchall():
                self.inventory_table.insert("", "end", values=(
                    item[0], item[1], f"{item[2]:.2f}", f"{item[3]:.2f}", item[4], item[5]
                ))

    def on_inventory_select(self, event: tk.Event) -> None:
        selected_item = self.inventory_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_item_btn.config(state=state)
        self.delete_item_btn.config(state=state)

    def show_transactions(self) -> None:
        if self.get_user_role() == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Transaction History", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Transaction ID:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        self.transaction_search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        self.transaction_search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.transaction_search_entry.bind("<KeyRelease>", self.update_transactions_table)

        transactions_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        transactions_frame.pack(fill="both", expand=True, pady=10)
        columns = ("TransactionID", "ItemsList", "TotalAmount", "Status", "Timestamp")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "STATUS", "TIMESTAMP")
        self.transactions_table = ttk.Treeview(transactions_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.transactions_table.heading(col, text=head)
            self.transactions_table.column(col, width=150 if col != "ItemsList" else 300,
                                        anchor="center" if col != "ItemsList" else "w")
        self.transactions_table.pack(fill="both", expand=True)
        self.update_transactions_table()
        self.transactions_table.bind("<<TreeviewSelect>>", self.on_transaction_select)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        self.view_transaction_btn = tk.Button(button_frame, text="View Transaction",
                                            command=self.view_selected_transaction,
                                            bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#2980b9", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.view_transaction_btn.pack(side="left", padx=5)
        self.edit_transaction_btn = tk.Button(button_frame, text="Edit Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Edit", "Enter admin password to edit transaction",
                                                self.validate_edit_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#f1c40f", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#e1b12c", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.edit_transaction_btn.pack(side="left", padx=5)
        self.return_transaction_btn = tk.Button(button_frame, text="Return Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Return", "Enter admin password to process return",
                                                self.validate_refund_auth, selected_item=self.transactions_table.selection()),
                                            bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#c0392b", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.return_transaction_btn.pack(side="left", padx=5)

    def on_transaction_select(self, event: tk.Event) -> None:
        selected_item = self.transactions_table.selection()
        state = "normal" if selected_item else "disabled"
        self.view_transaction_btn.config(state=state)
        self.edit_transaction_btn.config(state=state)
        self.return_transaction_btn.config(state=state)

    def update_transactions_table(self, event: Optional[tk.Event] = None) -> None:
        for item in self.transactions_table.get_children():
            self.transactions_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            query = self.transaction_search_entry.get().strip()
            sql = "SELECT transaction_id, items, total_amount, status, timestamp FROM transactions WHERE transaction_id LIKE ?"
            cursor.execute(sql, (f"%{query}%",))
            for transaction in cursor.fetchall():
                items_str = transaction[1]
                item_names = []
                for item_data in items_str.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                        name = cursor.fetchone()
                        if name:
                            item_names.append(f"{name[0]} (x{qty})")
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names)
                self.transactions_table.insert("", "end", values=(
                    transaction[0], items_display, f"{transaction[2]:.2f}", transaction[3], transaction[4]
                ))

    def view_selected_transaction(self) -> None:
        selected_item = self.transactions_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if transaction:
                window = tk.Toplevel(self.root)
                window.title(f"Transaction Details {transaction_id}")
                window.geometry("600x400")
                window.configure(bg="#f5f6f5")

                content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
                content_frame.pack(fill="both", expand=True)

                tk.Label(content_frame, text=f"Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=10)

                details_frame = tk.Frame(content_frame, bg="#ffffff")
                details_frame.pack(fill="both", expand=True)

                fields = ["Transaction ID", "Total Amount", "Cash Paid", "Change", "Status", "Timestamp", "Payment Method", "Customer ID"]
                for i, field in enumerate(fields):
                    tk.Label(details_frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(anchor="w")
                    tk.Label(details_frame, text=transaction[i] if transaction[i] else "None", font=("Helvetica", 14), bg="#ffffff", fg="#666").pack(anchor="w")

                tk.Label(details_frame, text="Items", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(anchor="w", pady=(10, 0))
                items_frame = tk.Frame(details_frame, bg="#ffffff")
                items_frame.pack(fill="both", expand=True)
                columns = ("Item", "Quantity", "RetailPrice", "Subtotal")
                headers = ("ITEM", "QUANTITY", "RETAIL PRICE", "SUBTOTAL")
                items_table = ttk.Treeview(items_frame, columns=columns, show="headings")
                for col, head in zip(columns, headers):
                    items_table.heading(col, text=head)
                    items_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
                items_table.pack(fill="both", expand=True)

                items = transaction[1].split(";")
                for item_data in items:
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, retail_price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            items_table.insert("", "end", values=(item[0], qty, f"{item[1]:.2f}", f"{float(item[1]) * int(qty):.2f}"))

    def validate_edit_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                transaction_id = self.transactions_table.item(selected_item[0])["values"][0]
                self.show_edit_transaction(transaction_id)
                window.destroy()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def show_edit_transaction(self, transaction_id: str) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if not transaction:
                messagebox.showerror("Error", "Transaction ID not found", parent=self.root)
                return
            if transaction[6] != "Completed":
                messagebox.showerror("Error", "Only completed transactions can be edited", parent=self.root)
                return

            items = transaction[1].split(";")
            edit_items = []
            for item_data in items:
                if item_data:
                    item_id, qty = item_data.split(":")
                    cursor.execute("SELECT item_id, name, unit_price, retail_price FROM inventory WHERE item_id = ?", (item_id,))
                    item = cursor.fetchone()
                    if item:
                        edit_items.append({"id": item[0], "name": item[1], "unit_price": item[2], "retail_price": item[3], "quantity": int(qty)})

            window = tk.Toplevel(self.root)
            window.title(f"Edit Transaction {transaction_id}")
            window.geometry("800x600")
            window.configure(bg="#f5f6f5")

            content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
            content_frame.pack(fill="both", expand=True)

            tk.Label(content_frame, text=f"Edit Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=10)

            items_frame = tk.Frame(content_frame, bg="#ffffff")
            items_frame.pack(fill="both", expand=True)
            columns = ("Item", "UnitPrice", "RetailPrice", "Quantity", "Subtotal")
            headers = ("ITEM", "UNIT PRICE", "RETAIL PRICE", "QUANTITY", "SUBTOTAL")
            edit_table = ttk.Treeview(items_frame, columns=columns, show="headings")
            for col, head in zip(columns, headers):
                edit_table.heading(col, text=head)
                edit_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
            edit_table.pack(fill="both", expand=True)

            for item in edit_items:
                edit_table.insert("", "end", values=(
                    item["name"], f"{item['unit_price']:.2f}", f"{item['retail_price']:.2f}", 
                    item["quantity"], f"{item['retail_price'] * item['quantity']:.2f}"
                ))

            edit_table.bind("<<TreeviewSelect>>", lambda e: self.on_edit_item_select(edit_table, edit_items))

            quantity_frame = tk.Frame(content_frame, bg="#ffffff")
            quantity_frame.pack(fill="x", pady=10)
            tk.Label(quantity_frame, text="Adjust Quantity:", font=("Helvetica", 14),
                    bg="#ffffff", fg="#1a1a1a").pack(side="left")
            self.edit_quantity_entry = tk.Entry(quantity_frame, font=("Helvetica", 14), bg="#f5f6f5", state="disabled")
            self.edit_quantity_entry.pack(side="left", padx=5)
            self.edit_quantity_entry.bind("<Return>", lambda e: self.adjust_edit_quantity(edit_table, edit_items))
            self.edit_quantity_entry.bind("<FocusOut>", lambda e: self.adjust_edit_quantity(edit_table, edit_items))

            tk.Button(content_frame, text="Confirm Edit",
                    command=lambda: self.process_edit_transaction(transaction_id, edit_items, window),
                    bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                    activebackground="#27ae60", activeforeground="#ffffff",
                    padx=12, pady=8, bd=0).pack(pady=10)

    def on_edit_item_select(self, edit_table: ttk.Treeview, edit_items: List[Dict]) -> None:
        selected_item = edit_table.selection()
        if selected_item:
            item_index = edit_table.index(selected_item[0])
            if 0 <= item_index < len(edit_items):
                self.edit_quantity_entry.config(state="normal")
                self.edit_quantity_entry.delete(0, tk.END)
                self.edit_quantity_entry.insert(0, str(edit_items[item_index]["quantity"]))
            else:
                self.edit_quantity_entry.config(state="disabled")
                self.edit_quantity_entry.delete(0, tk.END)
        else:
            self.edit_quantity_entry.config(state="disabled")
            self.edit_quantity_entry.delete(0, tk.END)

    def adjust_edit_quantity(self, edit_table: ttk.Treeview, edit_items: List[Dict]) -> None:
        selected_item = edit_table.selection()
        if not selected_item:
            return
        item_index = edit_table.index(selected_item[0])
        if not (0 <= item_index < len(edit_items)):
            return
        try:
            new_quantity = int(self.edit_quantity_entry.get())
            if new_quantity < 0:
                messagebox.showerror("Error", "Quantity cannot be negative.", parent=self.root)
                self.edit_quantity_entry.delete(0, tk.END)
                self.edit_quantity_entry.insert(0, str(edit_items[item_index]["quantity"]))
                return
            item = edit_items[item_index]
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                inventory_qty = cursor.fetchone()[0]
                original_qty = item["quantity"]
                qty_difference = new_quantity - original_qty
                if inventory_qty < qty_difference:
                    messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {inventory_qty}", parent=self.root)
                    self.edit_quantity_entry.delete(0, tk.END)
                    self.edit_quantity_entry.insert(0, str(original_qty))
                    return
                item["quantity"] = new_quantity
                item["subtotal"] = item["retail_price"] * new_quantity
                if new_quantity == 0:
                    edit_items.pop(item_index)
                edit_table.delete(*edit_table.get_children())
                for item in edit_items:
                    edit_table.insert("", "end", values=(
                        item["name"], f"{item['unit_price']:.2f}", f"{item['retail_price']:.2f}", 
                        item["quantity"], f"{item['subtotal']:.2f}"
                    ))
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity.", parent=self.root)
            self.edit_quantity_entry.delete(0, tk.END)
            self.edit_quantity_entry.insert(0, str(edit_items[item_index]["quantity"]))

    def process_edit_transaction(self, transaction_id: str, edit_items: List[Dict], window: tk.Toplevel) -> None:
        try:
            if not edit_items:
                messagebox.showerror("Error", "Transaction must have at least one item.", parent=self.root)
                return
            subtotal = sum(item["subtotal"] for item in edit_items)
            discount = subtotal * 0.2 if self.discount_var.get() and self.discount_authenticated else 0
            final_total = subtotal - discount
            cash_paid = float(self.summary_entries["Cash Paid "].get()) if self.summary_entries["Cash Paid "].get() else 0
            change = max(cash_paid - final_total, 0)
            items_str = ";".join([f"{item['id']}:{item['quantity']}" for item in edit_items])
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT items FROM transactions WHERE transaction_id = ?", (transaction_id,))
                original_items = cursor.fetchone()[0].split(";")
                for item_data in original_items:
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", (int(qty), item_id))
                for item in edit_items:
                    cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    current_qty = cursor.fetchone()[0]
                    if current_qty < item["quantity"]:
                        raise ValueError(f"Insufficient stock for {item['name']}: {current_qty} available")
                    cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", (item["quantity"], item["id"]))
                cursor.execute("""
                    UPDATE transactions 
                    SET items = ?, total_amount = ?, cash_paid = ?, change_amount = ?, timestamp = ?
                    WHERE transaction_id = ?
                """, (items_str, final_total, cash_paid, change, timestamp, transaction_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Edit Transaction", f"Edited transaction {transaction_id}",
                               timestamp, self.current_user))
                self.conn.commit()
            window.destroy()
            self.update_transactions_table()
            messagebox.showinfo("Success", f"Transaction {transaction_id} updated successfully", parent=self.root)
        except (sqlite3.OperationalError, ValueError) as e:
            messagebox.showerror("Error", f"Failed to update transaction: {e}", parent=self.root)

    def validate_refund_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                transaction_id = self.transactions_table.item(selected_item[0])["values"][0]
                self.process_return_transaction(transaction_id)
                window.destroy()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def process_return_transaction(self, transaction_id: str) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT items, total_amount, status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                transaction = cursor.fetchone()
                if not transaction:
                    messagebox.showerror("Error", "Transaction not found", parent=self.root)
                    return
                if transaction[2] == "Returned":
                    messagebox.showerror("Error", "Transaction already returned", parent=self.root)
                    return
                items = transaction[1].split(";")
                for item_data in items:
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", (int(qty), item_id))
                cursor.execute("UPDATE transactions SET status = 'Returned' WHERE transaction_id = ?", (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Return Transaction", f"Returned transaction {transaction_id}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            self.update_transactions_table()
            messagebox.showinfo("Success", f"Transaction {transaction_id} returned successfully", parent=self.root)
        except sqlite3.OperationalError as e:
            messagebox.showerror("Error", f"Failed to process return: {e}", parent=self.root)

    def void_selected_items(self, event: Optional[tk.Event] = None) -> None:
        if self.selected_item_index is not None and 0 <= self.selected_item_index < len(self.cart):
            self.create_password_auth_window(
                "Authenticate Void",
                "Enter admin password to void selected items",
                self.validate_void_auth
            )

    def validate_void_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                if self.selected_item_index is not None:
                    item = self.cart.pop(self.selected_item_index)
                    self.update_cart_table()
                    self.selected_item_index = None
                    self.quantity_entry.config(state="disabled")
                    self.quantity_entry.delete(0, tk.END)
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                  (str(uuid.uuid4()), "Void Item", f"Voided item {item['name']} from cart",
                                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                window.destroy()
                messagebox.showinfo("Success", "Item voided successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def void_order(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        self.create_password_auth_window(
            "Authenticate Void Order",
            "Enter admin password to void entire order",
            self.validate_void_order_auth
        )

    def validate_void_order_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                self.cart.clear()
                self.selected_item_index = None
                self.discount_var.set(False)
                self.discount_authenticated = False
                self.update_cart_table()
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Void Order", "Voided entire cart",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                window.destroy()
                messagebox.showinfo("Success", "Order voided successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def hold_transaction(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        try:
            transaction_id = self.generate_transaction_id()
            items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
            subtotal = sum(item["subtotal"] for item in self.cart)
            discount = subtotal * 0.2 if self.discount_var.get() and self.discount_authenticated else 0
            final_total = subtotal - discount
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            customer_id = getattr(self, 'current_customer_id', None)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO transactions (transaction_id, items, total_amount, cash_paid, change_amount, timestamp, status, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (transaction_id, items, final_total, 0, 0, timestamp, "Held", customer_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Hold Transaction", f"Held transaction {transaction_id}",
                               timestamp, self.current_user))
                self.conn.commit()
            self.cart.clear()
            self.selected_item_index = None
            self.discount_var.set(False)
            self.discount_authenticated = False
            self.current_customer_id = None
            self.customer_id_label.config(text="None Selected")
            self.update_cart_table()
            messagebox.showinfo("Success", f"Transaction {transaction_id} held successfully", parent=self.root)
        except sqlite3.OperationalError as e:
            messagebox.showerror("Error", f"Failed to hold transaction: {e}", parent=self.root)

    def view_unpaid_transactions(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Unpaid Transactions")
        window.geometry("800x600")
        window.configure(bg="#f5f6f5")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Unpaid Transactions", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        columns = ("TransactionID", "ItemsList", "TotalAmount", "Timestamp")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "TIMESTAMP")
        unpaid_table = ttk.Treeview(content_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            unpaid_table.heading(col, text=head)
            unpaid_table.column(col, width=150 if col != "ItemsList" else 300,
                              anchor="center" if col != "ItemsList" else "w")
        unpaid_table.pack(fill="both", expand=True)

        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT transaction_id, items, total_amount, timestamp FROM transactions WHERE status = 'Held'")
            for transaction in cursor.fetchall():
                items_str = transaction[1]
                item_names = []
                for item_data in items_str.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                        name = cursor.fetchone()
                        if name:
                            item_names.append(f"{name[0]} (x{qty})")
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names)
                unpaid_table.insert("", "end", values=(
                    transaction[0], items_display, f"{transaction[2]:.2f}", transaction[3]
                ))

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        tk.Button(button_frame, text="Resume Transaction",
                command=lambda: self.resume_transaction(unpaid_table, window),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)
        tk.Button(button_frame, text="Delete Transaction",
                command=lambda: self.create_password_auth_window(
                    "Authenticate Delete",
                    "Enter admin password to delete transaction",
                    self.validate_delete_transaction_auth,
                    unpaid_table=unpaid_table, window=window
                ),
                bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#c0392b", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)

    def validate_delete_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        unpaid_table = kwargs.get("unpaid_table")
        parent_window = kwargs.get("window")
        selected_item = unpaid_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                transaction_id = unpaid_table.item(selected_item[0])["values"][0]
                cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Delete Transaction", f"Deleted transaction {transaction_id}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                unpaid_table.delete(selected_item[0])
                messagebox.showinfo("Success", f"Transaction {transaction_id} deleted successfully", parent=self.root)
                if not unpaid_table.get_children():
                    parent_window.destroy()
            else:
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def resume_transaction(self, unpaid_table: ttk.Treeview, window: tk.Toplevel) -> None:
        selected_item = unpaid_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = unpaid_table.item(selected_item[0])["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT items, total_amount, customer_id FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if transaction:
                self.cart.clear()
                items = transaction[1].split(";")
                for item_data in items:
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT item_id, name, unit_price, retail_price, quantity FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            if int(qty) > item[4]:
                                messagebox.showerror("Error", f"Insufficient stock for {item[1]}. Available: {item[4]}", parent=self.root)
                                return
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "unit_price": item[2],
                                "retail_price": item[3],
                                "quantity": int(qty),
                                "subtotal": float(item[3]) * int(qty)
                            })
                self.current_customer_id = transaction[2]
                self.customer_id_label.config(text=transaction[2] if transaction[2] else "None Selected")
                cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Resume Transaction", f"Resumed transaction {transaction_id}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_cart_table()
                self.show_dashboard()
                window.destroy()
                messagebox.showinfo("Success", f"Transaction {transaction_id} resumed successfully", parent=self.root)

    def mode_of_payment(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Select Payment Method")
        window.geometry("400x300")
        window.configure(bg="#f5f6f5")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Select Payment Method", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        payment_methods = ["Cash", "Credit Card", "Debit Card", "Digital Wallet"]
        for method in payment_methods:
            tk.Button(content_frame, text=method,
                     command=lambda m=method: self.set_payment_method(m, window),
                     bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                     activebackground="#27ae60", activeforeground="#ffffff",
                     padx=12, pady=8, bd=0).pack(fill="x", pady=5)

    def set_payment_method(self, method: str, window: tk.Toplevel) -> None:
        self.current_payment_method = method
        window.destroy()
        messagebox.showinfo("Success", f"Payment method set to {method}", parent=self.root)

    def return_transaction(self, event: Optional[tk.Event] = None) -> None:
        self.show_transactions()

    def select_customer(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Select Customer")
        window.geometry("600x400")
        window.configure(bg="#f5f6f5")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Select Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        columns = ("CustomerID", "Name", "Contact")
        headers = ("CUSTOMER ID", "NAME", "CONTACT")
        self.customer_table = ttk.Treeview(content_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.customer_table.heading(col, text=head)
            self.customer_table.column(col, width=150, anchor="center")
        self.customer_table.pack(fill="both", expand=True)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        tk.Button(button_frame, text="Select",
                command=lambda: self.set_customer(self.customer_table, window),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)
        tk.Button(button_frame, text="Add New Customer",
                command=self.show_add_customer,
                bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#2980b9", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)

        search_entry.bind("<KeyRelease>", lambda e: self.update_customer_table(search_entry.get()))
        self.update_customer_table()

    def update_customer_table(self, query: str = "") -> None:
        for item in self.customer_table.get_children():
            self.customer_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT customer_id, name, contact FROM customers WHERE name LIKE ?", (f"%{query}%",))
            for customer in cursor.fetchall():
                self.customer_table.insert("", "end", values=customer)

    def set_customer(self, customer_table: ttk.Treeview, window: tk.Toplevel) -> None:
        selected_item = customer_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        customer_id = customer_table.item(selected_item)["values"][0]
        self.current_customer_id = customer_id
        self.customer_id_label.config(text=customer_id)
        window.destroy()
        messagebox.showinfo("Success", f"Customer {customer_id} selected", parent=self.root)

    def show_add_customer(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New Customer")
        window.geometry("400x400")
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        add_box.pack(fill="both", expand=True)

        tk.Label(add_box, text="Add New Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        fields = ["Name", "Contact", "Address"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        tk.Button(add_box, text="Add Customer",
                command=lambda: self.add_customer(
                    entries["Name"].get(),
                    entries["Contact"].get(),
                    entries["Address"].get(),
                    window
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_customer(self, name: str, contact: str, address: str, window: tk.Toplevel) -> None:
        try:
            if not name:
                messagebox.showerror("Error", "Name is required", parent=self.root)
                return
            current_time = datetime.now()
            month_year = current_time.strftime("%Y-%m")
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT customer_id FROM customers WHERE customer_id LIKE ? ORDER BY customer_id DESC LIMIT 1",
                              (f"{month_year}%",))
                last_customer = cursor.fetchone()
                if last_customer:
                    last_seq = int(last_customer[0][-6:])
                    new_seq = last_seq + 1
                else:
                    new_seq = 1
                customer_id = f"{month_year}-C{new_seq:05d}"
                cursor.execute("INSERT INTO customers (customer_id, name, contact, address) VALUES (?, ?, ?, ?)",
                              (customer_id, name.capitalize(), contact, address))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Add Customer", f"Added customer {customer_id}: {name}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                window.destroy()
                messagebox.showinfo("Success", f"Customer {customer_id} added successfully", parent=self.root)
                if hasattr(self, 'customer_table'):
                    self.update_customer_table()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Customer ID already exists", parent=self.root)

    def show_customer_management(self) -> None:
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Customer Management", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        columns = ("CustomerID", "Name", "Contact", "Address")
        headers = ("CUSTOMER ID", "NAME", "CONTACT", "ADDRESS")
        self.customer_table = ttk.Treeview(content_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.customer_table.heading(col, text=head)
            self.customer_table.column(col, width=150, anchor="center")
        self.customer_table.pack(fill="both", expand=True)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        tk.Button(button_frame, text="Add Customer",
                command=self.show_add_customer,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)
        self.update_customer_btn = tk.Button(button_frame, text="Update Customer",
                                            command=self.show_update_customer,
                                            bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#2980b9", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.update_customer_btn.pack(side="left", padx=5)
        self.delete_customer_btn = tk.Button(button_frame, text="Delete Customer",
                                            command=self.confirm_delete_customer,
                                            bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#c0392b", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.delete_customer_btn.pack(side="left", padx=5)

        self.customer_table.bind("<<TreeviewSelect>>", self.on_customer_select)
        search_entry.bind("<KeyRelease>", lambda e: self.update_customer_table(search_entry.get()))
        self.update_customer_table()

    def on_customer_select(self, event: tk.Event) -> None:
        selected_item = self.customer_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_customer_btn.config(state=state)
        self.delete_customer_btn.config(state=state)

    def show_update_customer(self) -> None:
        selected_item = self.customer_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        customer_id = self.customer_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
            customer = cursor.fetchone()
            if customer:
                window = tk.Toplevel(self.root)
                window.title("Update Customer")
                window.geometry("400x400")
                window.configure(bg="#f5f6f5")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
                update_box.pack(fill="both", expand=True)

                tk.Label(update_box, text="Update Customer", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=10)

                fields = ["Customer ID", "Name", "Contact", "Address"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entry.insert(0, customer[i])
                    entries[field] = entry
                    if field == "Customer ID":
                        entry.config(state="readonly")

                tk.Button(update_box, text="Update Customer",
                        command=lambda: self.update_customer(
                            entries["Customer ID"].get(),
                            entries["Name"].get(),
                            entries["Contact"].get(),
                            entries["Address"].get(),
                            window
                        ),
                        bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                        activebackground="#27ae60", activeforeground="#ffffff",
                        padx=12, pady=8, bd=0).pack(pady=15)

    def update_customer(self, customer_id: str, name: str, contact: str, address: str, window: tk.Toplevel) -> None:
        try:
            if not name:
                messagebox.showerror("Error", "Name is required", parent=self.root)
                return
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE customers SET name = ?, contact = ?, address = ? WHERE customer_id = ?",
                              (name.capitalize(), contact, address, customer_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Update Customer", f"Updated customer {customer_id}: {name}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_customer_table()
                window.destroy()
                messagebox.showinfo("Success", "Customer updated successfully", parent=self.root)
        except sqlite3.OperationalError as e:
            messagebox.showerror("Error", f"Failed to update customer: {e}", parent=self.root)

    def confirm_delete_customer(self) -> None:
        selected_item = self.customer_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        customer_id = self.customer_table.item(selected_item)["values"][0]
        if messagebox.askyesno("Confirm Deletion",
                              f"Are you sure you want to delete customer '{customer_id}'? This action cannot be undone.",
                              parent=self.root):
            self.create_password_auth_window(
                "Authenticate Deletion",
                "Enter admin password to delete customer",
                self.validate_delete_customer_auth,
                customer_id=customer_id
            )

    def validate_delete_customer_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        customer_id = kwargs.get("customer_id")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
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

    def show_sales_summary(self) -> None:
        if self.get_user_role() == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Sales Summary", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        date_frame = tk.Frame(content_frame, bg="#ffffff")
        date_frame.pack(fill="x", pady=10)
        tk.Label(date_frame, text="Date Range:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        self.start_date = tk.Entry(date_frame, font=("Helvetica", 14), bg="#f5f6f5")
        self.start_date.pack(side="left", padx=5)
        self.start_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        tk.Label(date_frame, text="to", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        self.end_date = tk.Entry(date_frame, font=("Helvetica", 14), bg="#f5f6f5")
        self.end_date.pack(side="left", padx=5)
        self.end_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        tk.Button(date_frame, text="Apply",
                command=self.update_sales_summary,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)

        summary_frame = tk.Frame(content_frame, bg="#ffffff")
        summary_frame.pack(fill="x", pady=10)
        fields = ["Total Capital", "Gross Profit", "Net Income"]
        self.sales_summary_entries = {}
        for field in fields:
            tk.Label(summary_frame, text=field, font=("Helvetica", 14),
                    bg="#ffffff", fg="#1a1a1a").pack(anchor="w")
            entry = tk.Entry(summary_frame, font=("Helvetica", 14), bg="#f5f6f5", state="readonly")
            entry.pack(fill="x", pady=2)
            self.sales_summary_entries[field] = entry

        transactions_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        transactions_frame.pack(fill="both", expand=True, pady=10)
        columns = ("TransactionID", "ItemsList", "TotalAmount", "Timestamp")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "TIMESTAMP")
        self.sales_transactions_table = ttk.Treeview(transactions_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.sales_transactions_table.heading(col, text=head)
            self.sales_transactions_table.column(col, width=150 if col != "ItemsList" else 300,
                                               anchor="center" if col != "ItemsList" else "w")
        self.sales_transactions_table.pack(fill="both", expand=True)

        self.update_sales_summary()

    def update_sales_summary(self) -> None:
        try:
            start_date = datetime.strptime(self.start_date.get(), "%Y-%m-%d")
            end_date = datetime.strptime(self.end_date.get(), "%Y-%m-%d")
            if start_date > end_date:
                messagebox.showerror("Error", "Start date cannot be after end date", parent=self.root)
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD", parent=self.root)
            return

        for item in self.sales_transactions_table.get_children():
            self.sales_transactions_table.delete(item)

        total_capital = 0
        total_revenue = 0
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT transaction_id, items, total_amount, timestamp 
                FROM transactions 
                WHERE status = 'Completed' AND timestamp BETWEEN ? AND ?
            """, (start_date.strftime("%Y-%m-%d 00:00:00"), end_date.strftime("%Y-%m-%d 23:59:59")))
            for transaction in cursor.fetchall():
                items_str = transaction[1]
                item_names = []
                for item_data in items_str.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, unit_price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            item_names.append(f"{item[0]} (x{qty})")
                            total_capital += float(item[1]) * int(qty)
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names)
                self.sales_transactions_table.insert("", "end", values=(
                    transaction[0], items_display, f"{transaction[2]:.2f}", transaction[3]
                ))
                total_revenue += transaction[2]

        gross_profit = total_revenue - total_capital
        net_income = gross_profit  # No expenses to subtract as per requirements

        for field, value in [("Total Capital", total_capital), ("Gross Profit", gross_profit), ("Net Income", net_income)]:
            self.sales_summary_entries[field].config(state="normal")
            self.sales_summary_entries[field].delete(0, tk.END)
            self.sales_summary_entries[field].insert(0, f"{value:.2f}")
            self.sales_summary_entries[field].config(state="readonly")

    def show_account_management(self) -> None:
        if not self.current_user or self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "Only admins can access this section.", parent=self.root)
            self.show_login()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Account Management", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Username:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        columns = ("Username", "Role", "Status")
        headers = ("USERNAME", "ROLE", "STATUS")
        self.user_table = ttk.Treeview(content_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.user_table.heading(col, text=head)
            self.user_table.column(col, width=150, anchor="center")
        self.user_table.pack(fill="both", expand=True)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        tk.Button(button_frame, text="Add User",
                command=self.show_add_user,
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(side="left", padx=5)
        self.update_user_btn = tk.Button(button_frame, text="Update User",
                                        command=self.show_update_user,
                                        bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#2980b9", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.update_user_btn.pack(side="left", padx=5)
        self.delete_user_btn = tk.Button(button_frame, text="Delete User",
                                        command=self.confirm_delete_user,
                                        bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#c0392b", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.delete_user_btn.pack(side="left", padx=5)

        self.user_table.bind("<<TreeviewSelect>>", self.on_user_select)
        search_entry.bind("<KeyRelease>", lambda e: self.update_user_table(search_entry.get()))
        self.update_user_table()

    def update_user_table(self, query: str = "") -> None:
        for item in self.user_table.get_children():
            self.user_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT username, role, status FROM users WHERE username LIKE ?", (f"%{query}%",))
            for user in cursor.fetchall():
                self.user_table.insert("", "end", values=user)

    def on_user_select(self, event: tk.Event) -> None:
        selected_item = self.user_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_user_btn.config(state=state)
        self.delete_user_btn.config(state=state)

    def show_add_user(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Add New User")
        window.geometry("400x400")
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        add_box.pack(fill="both", expand=True)

        tk.Label(add_box, text="Add New User", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        fields = ["Username", "Password", "Role"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            if field == "Role":
                role_var = tk.StringVar()
                entry = ttk.Combobox(frame, textvariable=role_var, values=["User", "Drug Lord"],
                                    state="readonly", font=("Helvetica", 14))
            else:
                entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5", show="*" if field == "Password" else "")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        tk.Button(add_box, text="Add User",
                command=lambda: self.add_user(
                    entries["Username"].get(),
                    entries["Password"].get(),
                    entries["Role"].get(),
                    window
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_user(self, username: str, password: str, role: str, window: tk.Toplevel) -> None:
        try:
            if not username or not password or not role:
                messagebox.showerror("Error", "All fields are required", parent=self.root)
                return
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)",
                              (username, password, role, "Online"))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Add User", f"Added user {username} with role {role}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_user_table()
                window.destroy()
                messagebox.showinfo("Success", "User added successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists", parent=self.root)

    def show_update_user(self) -> None:
        selected_item = self.user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        username = self.user_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT username, password, role, status FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user:
                window = tk.Toplevel(self.root)
                window.title("Update User")
                window.geometry("400x400")
                window.configure(bg="#f5f6f5")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
                update_box.pack(fill="both", expand=True)

                tk.Label(update_box, text="Update User", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=10)

                fields = ["Username", "Password", "Role", "Status"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
                    if field == "Role":
                        role_var = tk.StringVar(value=user[i])
                        entry = ttk.Combobox(frame, textvariable=role_var, values=["User", "Drug Lord"],
                                            state="readonly", font=("Helvetica", 14))
                    elif field == "Status":
                        status_var = tk.StringVar(value=user[i])
                        entry = ttk.Combobox(frame, textvariable=status_var, values=["Online", "Offline"],
                                            state="readonly", font=("Helvetica", 14))
                    else:
                        entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5", show="*" if field == "Password" else "")
                        entry.insert(0, user[i])
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entries[field] = entry
                    if field == "Username":
                        entry.config(state="readonly")

                tk.Button(update_box, text="Update User",
                        command=lambda: self.update_user(
                            entries["Username"].get(),
                            entries["Password"].get(),
                            entries["Role"].get(),
                            entries["Status"].get(),
                            window
                        ),
                        bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                        activebackground="#27ae60", activeforeground="#ffffff",
                        padx=12, pady=8, bd=0).pack(pady=15)

    def update_user(self, username: str, password: str, role: str, status: str, window: tk.Toplevel) -> None:
        try:
            if not password or not role or not status:
                messagebox.showerror("Error", "All fields are required", parent=self.root)
                return
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE users SET password = ?, role = ?, status = ? WHERE username = ?",
                              (password, role, status, username))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Update User", f"Updated user {username} to role {role}, status {status}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_user_table()
                window.destroy()
                messagebox.showinfo("Success", "User updated successfully", parent=self.root)
        except sqlite3.OperationalError as e:
            messagebox.showerror("Error", f"Failed to update user: {e}", parent=self.root)

    def confirm_delete_user(self) -> None:
        selected_item = self.user_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        username = self.user_table.item(selected_item)["values"][0]
        if username == self.current_user:
            messagebox.showerror("Error", "Cannot delete the current user", parent=self.root)
            return
        if messagebox.askyesno("Confirm Deletion",
                              f"Are you sure you want to delete user '{username}'? This action cannot be undone.",
                              parent=self.root):
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Delete User", f"Deleted user {username}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_user_table()
                messagebox.showinfo("Success", "User deleted successfully", parent=self.root)

if __name__ == "__main__":
    root = tk.Tk()
    app = PharmacyPOS(root)
    root.mainloop()                                    