import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime
import uuid
from PIL import Image, ImageTk
from typing import Optional, List, Dict, Callable
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
from pathlib import Path
import csv

class PharmacyPOS:
    def __init__(self, root: tk.Tk):
        print(f"Running script: {__file__}")
        self.root = root
        self.root.title("ARI Pharma POS")
        self.root.geometry("1280x720")
        self.root.configure(bg="#f5f6f5")
        
        try:
            icon_image = ImageTk.PhotoImage(Image.open("images/medkitpos.png"))
            self.root.iconphoto(True, icon_image)
        except Exception as e:
            print(f"Error loading icon: {e}")
        
        self.db_path = self.get_writable_db_path()
        try:
            self.conn = sqlite3.connect(self.db_path)
            if not self.check_database():
                raise sqlite3.OperationalError("Database validation failed")
        except sqlite3.OperationalError as e:
            print(f"Failed to connect to database at {self.db_path}: {e}")
            messagebox.showerror("Database Error", f"Cannot access database: {e}", parent=self.root)
            raise
        
        self.current_user: Optional[str] = None
        self.cart: List[Dict] = []
        self.selected_item_index: Optional[int] = None
        self.discount_authenticated: bool = False
        self.discount_var = tk.BooleanVar()
        self.sidebar_visible: bool = True
        self.suggestion_window: Optional[tk.Toplevel] = None
        self.suggestion_listbox: Optional[tk.Listbox] = None
        
        self.style_config()
        self.create_database()
        self.initialize_inventory_with_receipt()
        self.setup_gui()
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", lambda e: self.root.attributes('-fullscreen', False))
        self.root.bind("<F1>", self.opening_closing_fund)
        self.root.bind("<F3>", self.void_selected_items)
        self.root.bind("<F4>", self.void_order)
        self.root.bind("<F5>", self.hold_transaction)
        self.root.bind("<F6>", self.view_unpaid_transactions)
        self.root.bind("<F8>", self.mode_of_payment)
        self.root.bind("<F10>", self.return_transaction)
        self.root.bind("<F11>", self.add_expenses)
        self.root.bind("<F12>", self.add_del_customer)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA') or os.path.expanduser("~")
        db_dir = os.path.join(app_data, "ARIPharmaPOS")
        os.makedirs(db_dir, exist_ok=True)  # Create folder if it doesn't exist
        db_path = os.path.join(db_dir, db_name)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir_db = os.path.join(app_dir, db_name)
        
        # Copy database from app directory if it exists and db_path doesn't
        if os.path.exists(app_dir_db) and not os.path.exists(db_path):
            import shutil
            try:
                shutil.copy(app_dir_db, db_path)
                print(f"Copied database from {app_dir_db} to {db_path}")
            except Exception as e:
                print(f"Error copying database: {e}")
                messagebox.showerror("Database Error", f"Failed to copy database: {e}", parent=self.root)
                raise
        
        # If db_path doesn't exist, create an empty database file
        if not os.path.exists(db_path):
            try:
                # Open a connection to create the file
                conn = sqlite3.connect(db_path)
                conn.close()
                print(f"Created new database file at {db_path}")
            except sqlite3.Error as e:
                print(f"Error creating database file: {e}")
                messagebox.showerror("Database Error", f"Failed to create database file: {e}", parent=self.root)
                raise
        
        # Set permissions for directory and file
        try:
            os.chmod(db_dir, 0o777)  # Ensure directory is writable
            os.chmod(db_path, 0o666)  # Ensure file is writable
            print(f"Set permissions for {db_path}")
        except OSError as e:
            print(f"Error setting permissions on {db_path}: {e}")
            messagebox.showerror("Database Error", f"Failed to set permissions on database: {e}", parent=self.root)
            raise
        
        print(f"Database path: {db_path}")
        return db_path

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def style_config(self) -> None:
        style = ttk.Style()
        style.configure("Treeview", rowheight=30, font=("Helvetica", 12))
        style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))
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
                        price REAL,
                        quantity INTEGER,
                        cost_price REAL DEFAULT 0.0
                    )
                ''')
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'cost_price' not in columns:
                    cursor.execute("ALTER TABLE inventory ADD COLUMN cost_price REAL DEFAULT 0.0")
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
                        customer_id TEXT,
                        user_id TEXT,
                        discount_amount REAL DEFAULT 0.0
                    )
                ''')
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
                    CREATE TABLE IF NOT EXISTS expenses (
                        expense_id TEXT PRIMARY KEY,
                        description TEXT,
                        amount REAL,
                        category TEXT,
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
                    CREATE TABLE IF NOT EXISTS transaction_log (
                        log_id TEXT PRIMARY KEY,
                        action TEXT,
                        details TEXT,
                        timestamp TEXT,
                        user TEXT
                    )
                ''')
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                            ("Yamato", "ycsb-0001", "Drug Lord", "Online"))
                cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                            ("Kongo", "kcfb-0001", "User", "Online"))
                self.conn.commit()
        except sqlite3.OperationalError as e:
            print(f"SQLite error in create_database: {e}, Database path: {self.db_path}")
            messagebox.showerror("Database Error", f"Failed to create database: {e}", parent=self.root)
            raise

    def initialize_inventory_with_receipt(self):
        sample_items = [
            ("MED001", "Pain Reliever", "Medicine", 10.00, 100, 7.00),
            ("SUP001", "Vitamin C", "Supplement", 5.00, 200, 3.50),
            ("DEV001", "Thermometer", "Medical Device", 15.00, 50, 10.00),
        ]
        with self.conn:
            cursor = self.conn.cursor()
            for item_id, name, item_type, price, quantity, cost_price in sample_items:
                cursor.execute("INSERT OR IGNORE INTO inventory (item_id, name, type, price, quantity, cost_price) VALUES (?, ?, ?, ?, ?, ?)",
                              (item_id, name, item_type, price, quantity, cost_price))
            self.conn.commit()

    def setup_gui(self) -> None:
        self.main_frame = tk.Frame(self.root, bg="#f5f6f5")
        self.main_frame.pack(fill="both", expand=True)
        self.show_login()
        self.root.bind("<Return>", self.handle_enter_key)

    def handle_enter_key(self, event: Optional[tk.Event] = None) -> None:
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
        print("Setting up navigation buttons...")
        self.sidebar = tk.Frame(parent, bg="#1a1a1a", width=200)
        self.sidebar.pack(side="left", fill="y")

        self.header = tk.Frame(parent, bg="#f5f6f5")
        self.header.pack(side="top", fill="x", pady=8)
        
        self.hamburger_btn = tk.Button(self.header, text="✕", command=self.toggle_sidebar,
                                      bg="#f5f6f5", fg="#1a1a1a", font=("Helvetica", 18),
                                      activebackground="#e0e0e0", activeforeground="#1a1a1a",
                                      padx=8, pady=4, bd=0)
        self.hamburger_btn.pack(side="left", padx=5)
        
        tk.Label(self.header, text="ARI Pharma", font=("Helvetica", 18, "bold"), 
                 bg="#f5f6f5", fg="#1a1a1a").pack(side="left", padx=12)
        tk.Label(self.header, text=datetime.now().strftime("%B %d, %Y %I:%M %p PST"), 
                 font=("Helvetica", 12), bg="#f5f6f5", fg="#666").pack(side="left", padx=12)
        tk.Label(self.header, text=f"{self.current_user} ({self.get_user_role()})" if self.current_user else "", 
                 font=("Helvetica", 12), bg="#f5f6f5", fg="#666").pack(side="right", padx=12)

        nav_buttons = [
            ("🏠 Dashboard", self.show_dashboard),
            ("➡️ My Transactions", self.show_user_transactions),
            ("📊 Sales Summary", self.show_sales_summary),
        ]
        if self.get_user_role() == "Drug Lord":
            print("Adding Drug Lord buttons...")
            nav_buttons.extend([
                ("📜 All Transactions", self.show_transactions),
                ("📦 Inventory", self.show_inventory),
                ("👤 Account Management", self.show_account_management),
                ("📤 Export Sales", self.export_sales_data),
            ])
        nav_buttons.append(("🚪 Logout", self.confirm_logout))
        print("Navigation buttons:", [(text, cmd.__name__) for text, cmd in nav_buttons])

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

    def create_auth_window(self, title: str, prompt: str, callback: Callable, **kwargs) -> tk.Toplevel:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("350x400")
        window.configure(bg="#f5f6f5")

        auth_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        auth_box.pack(pady=20)

        tk.Label(auth_box, text=title, font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=12)
        tk.Label(auth_box, text=prompt, font=("Helvetica", 12), 
                 bg="#ffffff", fg="#666").pack(pady=8)

        if "Drug Lord" in prompt:
            tk.Label(auth_box, text="Admin Password", font=("Helvetica", 14), 
                     bg="#ffffff", fg="#1a1a1a").pack()
            password_entry = tk.Entry(auth_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
            password_entry.pack(pady=5, fill="x")
        else:
            tk.Label(auth_box, text="Username", font=("Helvetica", 14), 
                     bg="#ffffff", fg="#1a1a1a").pack()
            username_entry = tk.Entry(auth_box, font=("Helvetica", 14), bg="#f5f6f5")
            username_entry.pack(pady=5, fill="x")
            tk.Label(auth_box, text="Password", font=("Helvetica", 14), 
                     bg="#ffffff", fg="#1a1a1a").pack()
            password_entry = tk.Entry(auth_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
            password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(auth_box, text="Show Password", variable=show_password_var,
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                       font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(pady=8)

        tk.Button(auth_box, text="Authenticate", 
                  command=lambda: callback(
                      username_entry.get() if "Drug Lord" not in prompt else None,
                      password_entry.get(), window, **kwargs),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=12)

        password_entry.bind("<Return>", lambda e: callback(
            username_entry.get() if "Drug Lord" not in prompt else None,
            password_entry.get(), window, **kwargs))
        
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

        tk.Label(login_box, text="MedKitPOS Login", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=12)
        tk.Label(login_box, text="Welcome to ARI Pharma! Please enter your credentials.", 
                 font=("Helvetica", 12), bg="#ffffff", fg="#666").pack(pady=8)

        tk.Label(login_box, text="Username", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        username_entry = tk.Entry(login_box, font=("Helvetica", 14), bg="#f5f6f5")
        username_entry.pack(pady=5, fill="x")

        tk.Label(login_box, text="Password", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        password_entry = tk.Entry(login_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(login_box, text="Show Password", variable=show_password_var,
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                       font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(pady=8)

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
                self.show_dashboard()
            else:
                messagebox.showerror("Error", "Invalid credentials", parent=self.root)

    def show_dashboard(self) -> None:
        if not self.current_user:
            self.show_login()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        stats_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        stats_frame.pack(fill="x", pady=10)
        
        today = datetime.now().strftime("%Y-%m-%d")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT SUM(total_amount), SUM(discount_amount) FROM transactions WHERE strftime('%Y-%m-%d', timestamp) = ? AND status = 'Completed'", (today,))
            today_sales, today_discount = cursor.fetchone()
            today_sales = today_sales or 0.0
            today_discount = today_discount or 0.0
            
            cursor.execute("SELECT items FROM transactions WHERE strftime('%Y-%m-%d', timestamp) = ? AND status = 'Completed'", (today,))
            today_profit = 0.0
            for row in cursor.fetchall():
                items = row[0]
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        qty = int(qty)
                        cursor.execute("SELECT price, cost_price FROM inventory WHERE item_id = ?", (item_id,))
                        price, cost_price = cursor.fetchone()
                        today_profit += (price - cost_price) * qty

        tk.Label(stats_frame, text=f"Today's Sales: ${today_sales:.2f}", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left", padx=20)
        tk.Label(stats_frame, text=f"Today's Discounts: ${today_discount:.2f}", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left", padx=20)
        tk.Label(stats_frame, text=f"Today's Profit: ${today_profit:.2f}", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left", padx=20)

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
            tk.Button(search_frame, text="🗑️", command=lambda: self.create_auth_window(
                "Authenticate Deletion", "Enter admin credentials to delete item", self.validate_delete_item_auth),
                      bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                      activebackground="#c0392b", activeforeground="#ffffff",
                      padx=8, pady=4, bd=0).pack(side="left", padx=5)

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

        columns = ("Product", "UnitPrice", "Quantity", "Subtotal")
        headers = ("PRODUCT DETAILS", "UNIT PRICE ", "QUANTITY", "SUBTOTAL ")
        self.cart_table = ttk.Treeview(cart_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.cart_table.heading(col, text=head)
            self.cart_table.column(col, width=150 if col != "Product" else 300, 
                                   anchor="center" if col != "Product" else "w")
        self.cart_table.grid(row=1, column=0, columnspan=4, sticky="nsew")
        self.cart_table.bind("<<TreeviewSelect>>", self.on_item_select)
        cart_frame.grid_rowconfigure(1, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        summary_frame = tk.Frame(main_content, bg="#ffffff", bd=1, relief="flat")
        summary_frame.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        summary_frame.grid_propagate(False)
        summary_frame.configure(width=300)

        tk.Checkbutton(summary_frame, text="Apply 20% Discount (Senior/PWD)", 
                       variable=self.discount_var, command=self.handle_discount_toggle,
                       font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)

        tk.Label(summary_frame, text="Customer ID", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
        self.customer_id_label = tk.Label(summary_frame, text="None Selected", font=("Helvetica", 12), 
                                         bg="#ffffff", fg="#666")
        self.customer_id_label.pack(pady=2, anchor="w")
        tk.Button(summary_frame, text="Select Customer", command=self.select_customer,
                  bg="#3498db", fg="#ffffff", font=("Helvetica", 12),
                  activebackground="#2980b9", activeforeground="#ffffff",
                  padx=8, pady=4, bd=0).pack(pady=5, fill="x")

        tk.Label(summary_frame, text="Selected Item Quantity", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
        self.quantity_entry = tk.Entry(summary_frame, font=("Helvetica", 14), bg="#f5f6f5", state="disabled")
        self.quantity_entry.pack(pady=2, fill="x")
        self.quantity_entry.bind("<Return>", self.adjust_quantity)
        self.quantity_entry.bind("<FocusOut>", self.adjust_quantity)

        fields = ["Subtotal ", "Discount ", "Final Total ", "Cash Paid ", "Change ", "Profit "]
        self.summary_entries = {}
        for field in fields:
            tk.Label(summary_frame, text=field, font=("Helvetica", 14), 
                     bg="#ffffff", fg="#1a1a1a").pack(pady=2, anchor="w")
            entry = tk.Entry(summary_frame, font=("Helvetica", 14), bg="#f5f6f5")
            entry.pack(pady=2, fill="x")
            self.summary_entries[field] = entry
            if field != "Cash Paid ":
                entry.config(state="readonly")
                entry.insert(0, "0.00")
            else:
                entry.insert(0, "0.00")
                entry.bind("<KeyRelease>", self.update_change)

        button_frame = tk.Frame(summary_frame, bg="#ffffff")
        button_frame.pack(pady=10, fill="x")
        tk.Button(button_frame, text="Clear Cart", command=self.confirm_clear_cart,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=5, fill="x")
        tk.Button(button_frame, text="Checkout", command=self.confirm_checkout,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=5, fill="x")

        tk.Label(content_frame, text="ARI Pharmaceuticals Inc.", font=("Helvetica", 16, "bold"), bg="#ffffff").pack(pady=10)
        tk.Label(content_frame, text=f"Database path: {self.db_path}", font=("Helvetica", 12), bg="#ffffff").pack(pady=5)
        tk.Label(content_frame, text="If you see no features, ensure the database is accessible and contains valid data.", 
                 font=("Helvetica", 10, "italic"), bg="#ffffff").pack(pady=5)

    def check_database(self) -> bool:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if not cursor.fetchone():
                    messagebox.showerror("Database Error", "Users table not found in database.", parent=self.root)
                    return False
                cursor.execute("SELECT * FROM users WHERE role = 'Drug Lord'")
                if not cursor.fetchone():
                    messagebox.showerror("Database Error", "No Drug Lord user found in database.", parent=self.root)
                    return False
                return True
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to access database: {e}", parent=self.root)
            return False

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
                cursor.execute("SELECT name FROM inventory WHERE name LIKE ?", 
                               (f"%{query}%",))
                suggestions = [row[0] for row in cursor.fetchall()]
            
            if suggestions:
                for name in suggestions:
                    self.suggestion_listbox.insert(tk.END, name)
                search_width = self.search_entry.winfo_width()
                self.suggestion_window.geometry(f"{search_width}x{self.suggestion_listbox.winfo_reqheight()}+{self.search_entry.winfo_rootx()}+{self.search_entry.winfo_rooty() + self.search_entry.winfo_height()}")
                self.suggestion_window.deiconify()
                self.clear_btn.pack(side="right", padx=(0, 5))
            else:
                self.hide_suggestion_window()
                self.clear_btn.pack_forget()
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
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT * FROM inventory WHERE name = ?", (selected_text,))
                    item = cursor.fetchone()
                    if item:
                        for cart_item in self.cart:
                            if cart_item["id"] == item[0]:
                                cart_item["quantity"] += 1
                                cart_item["subtotal"] = cart_item["price"] * cart_item["quantity"]
                                break
                        else:
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "price": item[3],
                                "quantity": 1,
                                "subtotal": item[3],
                                "cost_price": item[5]
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

    def handle_discount_toggle(self) -> None:
        if self.discount_var.get() and not self.discount_authenticated:
            self.create_auth_window("Authenticate Discount", 
                                   "Enter admin credentials to apply 20% discount", 
                                   self.validate_discount_auth)
        else:
            self.discount_authenticated = False
            self.update_cart_totals()

    def validate_discount_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                self.discount_authenticated = True
                self.update_cart_totals()
                window.destroy()
                messagebox.showinfo("Success", "Discount authentication successful", parent=self.root)
            else:
                self.discount_var.set(False)
                self.discount_authenticated = False
                self.update_cart_totals()
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def update_cart_table(self) -> None:
        for item in self.cart_table.get_children():
            self.cart_table.delete(item)
        for item in self.cart:
            self.cart_table.insert("", "end", values=(
                item["name"], f"{item['price']:.2f}", item["quantity"], f"{item['subtotal']:.2f}"
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

                old_quantity = item["quantity"]
                quantity_diff = new_quantity - old_quantity

                if quantity_diff > 0 and inventory_qty < quantity_diff:
                    messagebox.showerror("Error", "Insufficient stock in inventory.", parent=self.root)
                    self.update_quantity_display()
                    return

                item["quantity"] = new_quantity
                item["subtotal"] = item["price"] * item["quantity"]
                cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", 
                               (quantity_diff, item["id"]))
                self.conn.commit()

                if new_quantity == 0:
                    cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                   (old_quantity, item["id"]))
                    self.conn.commit()
                    self.cart.pop(self.selected_item_index)
                    self.selected_item_index = None if not self.cart else min(self.selected_item_index, len(self.cart) - 1)

                self.update_cart_table()
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid integer quantity.", parent=self.root)
            self.update_quantity_display()

    def update_cart_totals(self) -> None:
        subtotal = sum(item["subtotal"] for item in self.cart)
        discount = subtotal * 0.2 if self.discount_var.get() and self.discount_authenticated else 0
        final_total = subtotal - discount
        profit = sum((item["price"] - item["cost_price"]) * item["quantity"] for item in self.cart)
        profit = profit * 0.8 if self.discount_var.get() and self.discount_authenticated else profit

        for field in ["Subtotal ", "Discount ", "Final Total ", "Profit "]:
            self.summary_entries[field].config(state="normal")
            self.summary_entries[field].delete(0, tk.END)
            self.summary_entries[field].insert(0, f"{subtotal:.2f}" if field == "Subtotal " else 
                                              f"{discount:.2f}" if field == "Discount " else 
                                              f"{final_total:.2f}" if field == "Final Total " else 
                                              f"{profit:.2f}")
            self.summary_entries[field].config(state="readonly")

        self.update_change()

    def confirm_clear_cart(self) -> None:
        if messagebox.askyesno("Confirm Clear Cart", 
                               "Are you sure you want to clear the cart? This action cannot be undone.",
                               parent=self.root):
            with self.conn:
                cursor = self.conn.cursor()
                for item in self.cart:
                    cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                   (item["quantity"], item["id"]))
            self.conn.commit()
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

    def process_checkout(self, cash_paid: float, final_total: float) -> None:
        transaction_id = str(uuid.uuid4())
        items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
        change = cash_paid - final_total
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payment_method = getattr(self, 'current_payment_method', 'Cash')
        customer_id = getattr(self, 'current_customer_id', None)
        discount_amount = float(self.summary_entries["Discount "].get())
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                           (transaction_id, items, final_total, cash_paid, change, timestamp, 
                            "Completed", payment_method, customer_id, self.current_user, discount_amount))
            for item in self.cart:
                cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", 
                               (item["quantity"], item["id"]))
            cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                           (str(uuid.uuid4()), "Checkout", f"Completed transaction {transaction_id}", 
                            timestamp, self.current_user))
            self.conn.commit()
        self.summary_entries["Change "].config(state="normal")
        self.summary_entries["Change "].delete(0, tk.END)
        self.summary_entries["Change "].insert(0, f"{change:.2f}")
        self.summary_entries["Change "].config(state="readonly")
        messagebox.showinfo("Success", f"Transaction completed! ID: {transaction_id}", parent=self.root)
        self.customer_id_label.config(text="None Selected")
        self.cart.clear()
        self.selected_item_index = None
        self.discount_var.set(False)
        self.discount_authenticated = False
        self.current_payment_method = None
        self.current_customer_id = None
        self.update_cart_table()

    def show_inventory(self) -> None:
        if not self.current_user or self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to access this section.", parent=self.root)
            return
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
        tk.Button(search_frame, text="Add New Item", command=self.show_add_item,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(side="right", padx=5)

        inventory_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        inventory_frame.pack(fill="both", expand=True, pady=10)

        columns = ("Name", "Price", "Quantity", "Cost Price")
        headers = ("NAME", "PRICE", "QUANTITY", "COST PRICE")
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
        self.delete_item_btn = tk.Button(button_frame, text="Delete Item", 
                                        command=lambda: self.create_auth_window(
                                            "Authenticate Deletion", "Enter admin credentials to delete item", 
                                            self.validate_delete_item_auth, selected_item=self.inventory_table.selection()),
                                        bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#c0392b", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.delete_item_btn.pack(side="left", padx=5)

        self.inventory_table.bind("<<TreeviewSelect>>", self.on_inventory_select)

    def update_inventory_table(self, event: Optional[tk.Event] = None) -> None:
        for item in self.inventory_table.get_children():
            self.inventory_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            query = self.inventory_search_entry.get().strip()
            sql = "SELECT name, price, quantity, cost_price FROM inventory WHERE name LIKE ?" if query else "SELECT name, price, quantity, cost_price FROM inventory"
            cursor.execute(sql, (f"%{query}%",) if query else ())
            for item in cursor.fetchall():
                self.inventory_table.insert("", "end", values=(item[0], f"{item[1]:.2f}", item[2], f"{item[3]:.2f}"))

    def show_add_item(self) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to add items.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Add New Item to Inventory")
        window.geometry("400x450")
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New Item to Inventory", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID (Barcode)", "Product Name", "Price ", "Quantity", "Cost Price"]
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
                     values=["Medicine", "Supplement", "Medical Device", "Other"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(add_box, text="Add Item", 
                  command=lambda: self.add_item(
                      entries["Item ID (Barcode)"].get(),
                      entries["Product Name"].get(),
                      type_var.get(),
                      entries["Price "].get(),
                      entries["Quantity"].get(),
                      entries["Cost Price"].get(),
                      window
                  ),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def add_item(self, item_id: str, name: str, item_type: str, price: str, quantity: str, cost_price: str, window: tk.Toplevel) -> None:
        try:
            price = float(price)
            quantity = int(quantity)
            cost_price = float(cost_price)
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return
            name = name.capitalize()
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)", 
                               (item_id, name, item_type, price, quantity, cost_price))
                self.conn.commit()
            self.update_inventory_table()
            window.destroy()
            messagebox.showinfo("Success", "Item added successfully", parent=self.root)
        except ValueError:
            messagebox.showerror("Error", "Invalid price, quantity, or cost price", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def on_inventory_table_click(self, event: tk.Event) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to update items.", parent=self.root)
            return
        selected_item = self.inventory_table.selection()
        if not selected_item:
            return
        item_name = self.inventory_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM inventory WHERE name = ?", (item_name,))
            item = cursor.fetchone()
            if item:
                self.show_update_item(item)

    def show_update_item(self, item: tuple) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to update items.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Update Item")
        window.geometry("400x450")
        window.configure(bg="#f5f6f5")

        update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        update_box.pack(pady=20)

        tk.Label(update_box, text="Update Item in Inventory", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID (Barcode)", "Product Name", "Price ", "Quantity", "Cost Price"]
        entries = {}
        for i, field in enumerate(fields):
            frame = tk.Frame(update_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry
            entry.insert(0, item[0] if i == 0 else item[1] if i == 1 else str(item[3]) if i == 2 else str(item[4]) if i == 3 else str(item[5]))

        type_var = tk.StringVar(value=item[2])
        tk.Label(update_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        ttk.Combobox(update_box, textvariable=type_var, 
                     values=["Medicine", "Supplement", "Medical Device", "Other"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(update_box, text="Update Item", 
                  command=lambda: self.update_item(
                      entries["Item ID (Barcode)"].get(),
                      entries["Product Name"].get(),
                      type_var.get(),
                      entries["Price "].get(),
                      entries["Quantity"].get(),
                      entries["Cost Price"].get(),
                      item[0],
                      window
                  ),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def update_item(self, item_id: str, name: str, item_type: str, price: str, quantity: str, cost_price: str, original_item_id: str, window: tk.Toplevel) -> None:
        try:
            price = float(price)
            quantity = int(quantity)
            cost_price = float(cost_price)
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return
            name = name.capitalize()
            item_id = item_id.strip() if item_id.strip() else original_item_id
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE inventory 
                    SET item_id = ?, name = ?, type = ?, price = ?, quantity = ?, cost_price = ?
                    WHERE item_id = ?
                """, (item_id, name, item_type, price, quantity, cost_price, original_item_id))
                self.conn.commit()
            self.update_inventory_table()
            window.destroy()
            messagebox.showinfo("Success", "Item updated successfully", parent=self.root)
        except ValueError:
            messagebox.showerror("Error", "Invalid price, quantity, or cost price", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def on_inventory_select(self, event: tk.Event) -> None:
        selected_item = self.inventory_table.selection()
        self.delete_item_btn.config(state="normal" if selected_item else "disabled")

    def validate_delete_item_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item", self.inventory_table.selection())
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                item_name = self.inventory_table.item(selected_item)["values"][0]
                cursor.execute("SELECT item_id FROM inventory WHERE name = ?", (item_name,))
                item_id = cursor.fetchone()[0]
                cursor.execute("DELETE FROM inventory WHERE item_id = ?", (item_id,))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def show_transactions(self) -> None:
        if not self.current_user or self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to access this section.", parent=self.root)
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5").pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(search_frame, text="Refresh Transactions", command=self.update_transactions_table,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(side="left", padx=5)

        transactions_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        transactions_frame.pack(fill="both", expand=True, pady=10)
        transactions_frame.grid_rowconfigure(1, weight=1)
        transactions_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(transactions_frame, bg="#ffffff")
        canvas.grid(row=1, column=0, sticky="nsew")

        h_scrollbar = ttk.Scrollbar(transactions_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")

        tree_frame = tk.Frame(canvas, bg="#ffffff")
        canvas_window = canvas.create_window((0, 0), window=tree_frame, anchor="nw")

        columns = ("TransactionID", "ItemsList", "TotalAmount", "CashPaid", "ChangeAmount", "Timestamp", "Status", "PaymentMethod", "CustomerID", "Discount")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT ", "CASH PAID ", "CHANGE ", "TIMESTAMP", "STATUS", "PAYMENT METHOD", "CUSTOMER ID", "DISCOUNT")
        self.transactions_table = ttk.Treeview(tree_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.transactions_table.heading(col, text=head)
            width = 300 if col == "ItemsList" else 150
            self.transactions_table.column(col, width=width, anchor="center" if col != "ItemsList" else "w")
        self.transactions_table.pack(fill="both", expand=True)

        def update_scroll_region(event=None):
            total_width = sum(self.transactions_table.column(col, "width") for col in columns)
            canvas.configure(scrollregion=(0, 0, total_width, self.transactions_table.winfo_height()))
            canvas.itemconfig(canvas_window, width=total_width)

        self.transactions_table.bind("<Configure>", update_scroll_region)
        canvas.configure(xscrollcommand=h_scrollbar.set)

        def scroll_horizontal(event):
            if event.state & 0x1:
                if event.delta > 0:
                    canvas.xview_scroll(-1, "units")
                elif event.delta < 0:
                    canvas.xview_scroll(1, "units")
                return "break"

        def scroll_horizontal_unix(event):
            if event.state & 0x1:
                if event.num == 4:
                    canvas.xview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.xview_scroll(1, "units")
                return "break"

        self.transactions_table.bind("<Shift-MouseWheel>", scroll_horizontal)
        self.transactions_table.bind("<Shift-Button-4>", scroll_horizontal_unix)
        self.transactions_table.bind("<Shift-Button-5>", scroll_horizontal_unix)

        self.update_transactions_table()
        self.transactions_table.bind("<<TreeviewSelect>>", self.on_transaction_select)

        self.transaction_button_frame = tk.Frame(transactions_frame, bg="#ffffff")
        self.transaction_button_frame.grid(row=3, column=0, columnspan=9, pady=10)
        self.print_btn = tk.Button(self.transaction_button_frame, text="Print Receipt", command=self.print_receipt,
                                   bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                                   activebackground="#27ae60", activeforeground="#ffffff",
                                   padx=12, pady=8, bd=0, state="disabled")
        self.print_btn.pack(side="left", padx=5)
        self.save_pdf_btn = tk.Button(self.transaction_button_frame, text="Save PDF", command=self.save_receipt_pdf,
                                      bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                      activebackground="#2980b9", activeforeground="#ffffff",
                                      padx=12, pady=8, bd=0, state="disabled")
        self.save_pdf_btn.pack(side="left", padx=5)
        self.refund_btn = tk.Button(self.transaction_button_frame, text="Refund", 
                                    command=lambda: self.create_auth_window(
                                        "Authenticate Refund", "Enter admin credentials to process refund", 
                                        self.validate_refund_auth, selected_item=self.transactions_table.selection()),
                                    bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                    activebackground="#c0392b", activeforeground="#ffffff",
                                    padx=12, pady=8, bd=0, state="disabled")
        self.refund_btn.pack(side="left", padx=5)

    def update_transactions_table(self) -> None:
        for item in self.transactions_table.get_children():
            self.transactions_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions")
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
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names) if item_names else "No items"
                self.transactions_table.insert("", "end", values=(
                    transaction[0], items_display, f"{transaction[2]:.2f}", 
                    f"{transaction[3]:.2f}", f"{transaction[4]:.2f}", 
                    transaction[5], transaction[6], transaction[7] or "Cash", 
                    transaction[8] or "None", f"{transaction[10]:.2f}"
                ))

    def show_user_transactions(self) -> None:
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5").pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(search_frame, text="Refresh Transactions", command=self.update_user_transactions_table,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(side="left", padx=5)

        transactions_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        transactions_frame.pack(fill="both", expand=True, pady=10)
        transactions_frame.grid_rowconfigure(1, weight=1)
        transactions_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(transactions_frame, bg="#ffffff")
        canvas.grid(row=1, column=0, sticky="nsew")

        h_scrollbar = ttk.Scrollbar(transactions_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")

        tree_frame = tk.Frame(canvas, bg="#ffffff")
        canvas_window = canvas.create_window((0, 0), window=tree_frame, anchor="nw")

        columns = ("TransactionID", "ItemsList", "TotalAmount", "Timestamp", "Status", "Discount")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "TIMESTAMP", "STATUS", "DISCOUNT")
        self.user_transactions_table = ttk.Treeview(tree_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.user_transactions_table.heading(col, text=head)
            width = 300 if col == "ItemsList" else 150
            self.user_transactions_table.column(col, width=width, anchor="center" if col != "ItemsList" else "w")
        self.user_transactions_table.pack(fill="both", expand=True)

        def update_scroll_region(event=None):
            total_width = sum(self.user_transactions_table.column(col, "width") for col in columns)
            canvas.configure(scrollregion=(0, 0, total_width, self.user_transactions_table.winfo_height()))
            canvas.itemconfig(canvas_window, width=total_width)

        self.user_transactions_table.bind("<Configure>", update_scroll_region)
        canvas.configure(xscrollcommand=h_scrollbar.set)

        def scroll_horizontal(event):
            if event.state & 0x1:
                if event.delta > 0:
                    canvas.xview_scroll(-1, "units")
                elif event.delta < 0:
                    canvas.xview_scroll(1, "units")
                return "break"

        def scroll_horizontal_unix(event):
            if event.state & 0x1:
                if event.num == 4:
                    canvas.xview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.xview_scroll(1, "units")
                return "break"

        self.user_transactions_table.bind("<Shift-MouseWheel>", scroll_horizontal)
        self.user_transactions_table.bind("<Shift-Button-4>", scroll_horizontal_unix)
        self.user_transactions_table.bind("<Shift-Button-5>", scroll_horizontal_unix)

        self.update_user_transactions_table()

    def update_user_transactions_table(self) -> None:
        for item in self.user_transactions_table.get_children():
            self.user_transactions_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE user_id = ?", (self.current_user,))
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
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names) if item_names else "No items"
                self.user_transactions_table.insert("", "end", values=(
                    transaction[0], items_display, f"{transaction[2]:.2f}", 
                    transaction[5], transaction[6], f"{transaction[10]:.2f}"
                ))

    def on_transaction_select(self, event: tk.Event) -> None:
        selected_item = self.transactions_table.selection()
        if selected_item:
            self.print_btn.config(state="normal")
            self.save_pdf_btn.config(state="normal")
            self.refund_btn.config(state="normal")
        else:
            self.print_btn.config(state="disabled")
            self.save_pdf_btn.config(state="disabled")
            self.refund_btn.config(state="disabled")

    def print_receipt(self) -> None:
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
                items = transaction[1]
                receipt_text = "ARI Pharma Receipt\n"
                receipt_text += "-" * 40 + "\n"
                receipt_text += f"Transaction ID: {transaction[0]}\n"
                receipt_text += f"Date: {transaction[5]}\n"
                receipt_text += f"Cashier: {transaction[9]}\n"
                receipt_text += f"Customer ID: {transaction[8] or 'None'}\n"
                receipt_text += "-" * 40 + "\n"
                receipt_text += "Items:\n"
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            receipt_text += f"{item[0]} (x{qty}) @ ${item[1]:.2f} = ${float(item[1]) * int(qty):.2f}\n"
                receipt_text += "-" * 40 + "\n"
                receipt_text += f"Subtotal: ${transaction[2] + transaction[10]:.2f}\n"
                receipt_text += f"Discount: ${transaction[10]:.2f}\n"
                receipt_text += f"Total: ${transaction[2]:.2f}\n"
                receipt_text += f"Cash Paid: ${transaction[3]:.2f}\n"
                receipt_text += f"Change: ${transaction[4]:.2f}\n"
                receipt_text += f"Payment Method: {transaction[7] or 'Cash'}\n"
                receipt_text += "-" * 40 + "\n"
                receipt_text += "Thank you for shopping at ARI Pharma!\n"
                print(receipt_text)
                messagebox.showinfo("Receipt Printed", "Receipt has been printed to console.", parent=self.root)

    def save_receipt_pdf(self) -> None:
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
                items = transaction[1]
                downloads_path = str(Path.home() / "Downloads")
                pdf_path = os.path.join(downloads_path, f"Receipt_{transaction_id}.pdf")
                c = canvas.Canvas(pdf_path, pagesize=letter)
                c.setFont("Helvetica", 12)
                y = 750
                c.drawString(100, y, "ARI Pharma Receipt")
                y -= 20
                c.drawString(100, y, "-" * 40)
                y -= 20
                c.drawString(100, y, f"Transaction ID: {transaction[0]}")
                y -= 20
                c.drawString(100, y, f"Date: {transaction[5]}")
                y -= 20
                c.drawString(100, y, f"Cashier: {transaction[9]}")
                y -= 20
                c.drawString(100, y, f"Customer ID: {transaction[8] or 'None'}")
                y -= 20
                c.drawString(100, y, "-" * 40)
                y -= 20
                c.drawString(100, y, "Items:")
                y -= 20
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name, price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            c.drawString(100, y, f"{item[0]} (x{qty}) @ ${item[1]:.2f} = ${float(item[1]) * int(qty):.2f}")
                            y -= 20
                c.drawString(100, y, "-" * 40)
                y -= 20
                c.drawString(100, y, f"Subtotal: ${transaction[2] + transaction[10]:.2f}")
                y -= 20
                c.drawString(100, y, f"Discount: ${transaction[10]:.2f}")
                y -= 20
                c.drawString(100, y, f"Total: ${transaction[2]:.2f}")
                y -= 20
                c.drawString(100, y, f"Cash Paid: ${transaction[3]:.2f}")
                y -= 20
                c.drawString(100, y, f"Change: ${transaction[4]:.2f}")
                y -= 20
                c.drawString(100, y, f"Payment Method: {transaction[7] or 'Cash'}")
                y -= 20
                c.drawString(100, y, "-" * 40)
                y -= 20
                c.drawString(100, y, "Thank you for shopping at ARI Pharma!")
                c.showPage()
                c.save()
                messagebox.showinfo("Success", f"Receipt saved as PDF at {pdf_path}", parent=self.root)

    def validate_refund_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item", self.transactions_table.selection())
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                transaction_id = self.transactions_table.item(selected_item)["values"][0]
                cursor.execute("SELECT items FROM transactions WHERE transaction_id = ?", (transaction_id,))
                items = cursor.fetchone()[0]
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                       (int(qty), item_id))
                cursor.execute("UPDATE transactions SET status = 'Refunded' WHERE transaction_id = ?", 
                               (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                               (str(uuid.uuid4()), "Refund", f"Refunded transaction {transaction_id}", 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_transactions_table()
                window.destroy()
                messagebox.showinfo("Success", "Refund processed successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def show_sales_summary(self) -> None:
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        filter_frame = tk.Frame(content_frame, bg="#ffffff")
        filter_frame.pack(fill="x", pady=10)

        tk.Label(filter_frame, text="Date Range:", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left")
        start_date = tk.Entry(filter_frame, font=("Helvetica", 14), bg="#f5f6f5", width=12)
        start_date.pack(side="left", padx=5)
        tk.Label(filter_frame, text="to", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left")
        end_date = tk.Entry(filter_frame, font=("Helvetica", 14), bg="#f5f6f5", width=12)
        end_date.pack(side="left", padx=5)
        tk.Button(filter_frame, text="Filter", command=lambda: self.update_sales_summary(start_date.get(), end_date.get()),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(side="left", padx=5)

        summary_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        summary_frame.pack(fill="both", expand=True, pady=10)

        columns = ("Date", "TotalSales", "TotalDiscount", "TotalProfit")
        headers = ("DATE", "TOTAL SALES", "TOTAL DISCOUNT", "TOTAL PROFIT")
        self.sales_summary_table = ttk.Treeview(summary_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.sales_summary_table.heading(col, text=head)
            self.sales_summary_table.column(col, width=150, anchor="center")
        self.sales_summary_table.pack(fill="both", expand=True)
        self.update_sales_summary()

    def update_sales_summary(self, start_date: str = "", end_date: str = "") -> None:
        for item in self.sales_summary_table.get_children():
            self.sales_summary_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            sql = "SELECT strftime('%Y-%m-%d', timestamp) as date, SUM(total_amount), SUM(discount_amount) FROM transactions WHERE status = 'Completed'"
            params = []
            if start_date and end_date:
                try:
                    datetime.strptime(start_date, "%Y-%m-%d")
                    datetime.strptime(end_date, "%Y-%m-%d")
                    sql += " AND date(timestamp) BETWEEN ? AND ?"
                    params.extend([start_date, end_date])
                except ValueError:
                    messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD.", parent=self.root)
                    return
            sql += " GROUP BY date"
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                date, total_sales, total_discount = row
                total_profit = 0.0
                cursor.execute("SELECT items FROM transactions WHERE strftime('%Y-%m-%d', timestamp) = ? AND status = 'Completed'", (date,))
                for item_row in cursor.fetchall():
                    items = item_row[0]
                    for item_data in items.split(";"):
                        if item_data:
                            item_id, qty = item_data.split(":")
                            qty = int(qty)
                            cursor.execute("SELECT price, cost_price FROM inventory WHERE item_id = ?", (item_id,))
                            price, cost_price = cursor.fetchone()
                            total_profit += (price - cost_price) * qty
                self.sales_summary_table.insert("", "end", values=(
                    date, f"{total_sales:.2f}", f"{total_discount:.2f}", f"{total_profit:.2f}"
                ))

    def show_account_management(self) -> None:
        if not self.current_user or self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to access this section.", parent=self.root)
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)
        tk.Button(button_frame, text="Add New User", command=self.show_add_user,
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(side="left", padx=5)

        users_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        users_frame.pack(fill="both", expand=True, pady=10)

        columns = ("Username", "Role", "Status")
        headers = ("USERNAME", "ROLE", "STATUS")
        self.users_table = ttk.Treeview(users_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.users_table.heading(col, text=head)
            self.users_table.column(col, width=150, anchor="center")
        self.users_table.pack(fill="both", expand=True)
        self.update_users_table()
        self.users_table.bind("<Double-1>", self.on_user_table_click)

        action_frame = tk.Frame(content_frame, bg="#ffffff")
        action_frame.pack(fill="x", pady=10)
        self.edit_user_btn = tk.Button(action_frame, text="Edit User", 
                                       command=self.show_edit_user,
                                       bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                       activebackground="#2980b9", activeforeground="#ffffff",
                                       padx=12, pady=8, bd=0, state="disabled")
        self.edit_user_btn.pack(side="left", padx=5)
        self.delete_user_btn = tk.Button(action_frame, text="Delete User", 
                                         command=lambda: self.create_auth_window(
                                             "Authenticate Deletion", "Enter admin credentials to delete user", 
                                             self.validate_delete_user_auth, selected_item=self.users_table.selection()),
                                         bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                         activebackground="#c0392b", activeforeground="#ffffff",
                                         padx=12, pady=8, bd=0, state="disabled")
        self.delete_user_btn.pack(side="left", padx=5)
        self.users_table.bind("<<TreeviewSelect>>", self.on_user_select)

    def update_users_table(self) -> None:
        for item in self.users_table.get_children():
            self.users_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT username, role, status FROM users")
            for user in cursor.fetchall():
                self.users_table.insert("", "end", values=user)

    def show_add_user(self) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to add users.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Add New User")
        window.geometry("350x450")
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New User", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(add_box, text="Username", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        username_entry = tk.Entry(add_box, font=("Helvetica", 14), bg="#f5f6f5")
        username_entry.pack(pady=5, fill="x")

        tk.Label(add_box, text="Password", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        password_entry = tk.Entry(add_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(add_box, text="Show Password", variable=show_password_var,
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                       font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(pady=8)

        role_var = tk.StringVar(value="User")
        tk.Label(add_box, text="Role", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(add_box, textvariable=role_var, values=["User", "Drug Lord"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        status_var = tk.StringVar(value="Online")
        tk.Label(add_box, text="Status", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(add_box, textvariable=status_var, values=["Online", "Offline"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(add_box, text="Add User", 
                  command=lambda: self.add_user(
                      username_entry.get(), password_entry.get(), 
                      role_var.get(), status_var.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def add_user(self, username: str, password: str, role: str, status: str, window: tk.Toplevel) -> None:
        if not username or not password:
            messagebox.showerror("Error", "Username and Password are required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?)", 
                               (username, password, role, status))
                self.conn.commit()
            self.update_users_table()
            window.destroy()
            messagebox.showinfo("Success", "User added successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists", parent=self.root)

    def on_user_table_click(self, event: tk.Event) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to edit users.", parent=self.root)
            return
        selected_item = self.users_table.selection()
        if not selected_item:
            return
        username = self.users_table.item(selected_item)["values"][0]
        self.show_edit_user()

    def show_edit_user(self) -> None:
        selected_item = self.users_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        username = self.users_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if not user:
                messagebox.showerror("Error", "User not found", parent=self.root)
                return

        window = tk.Toplevel(self.root)
        window.title("Edit User")
        window.geometry("350x450")
        window.configure(bg="#f5f6f5")

        edit_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        edit_box.pack(pady=20)

        tk.Label(edit_box, text="Edit User", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(edit_box, text="Username", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        username_entry = tk.Entry(edit_box, font=("Helvetica", 14), bg="#f5f6f5")
        username_entry.pack(pady=5, fill="x")
        username_entry.insert(0, user[0])
        username_entry.config(state="readonly")

        tk.Label(edit_box, text="Password", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        password_entry = tk.Entry(edit_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")
        password_entry.insert(0, user[1])

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(edit_box, text="Show Password", variable=show_password_var,
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                       font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(pady=8)

        role_var = tk.StringVar(value=user[2])
        tk.Label(edit_box, text="Role", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(edit_box, textvariable=role_var, values=["User", "Drug Lord"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        status_var = tk.StringVar(value=user[3])
        tk.Label(edit_box, text="Status", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(edit_box, textvariable=status_var, values=["Online", "Offline"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(edit_box, text="Update User", 
                  command=lambda: self.update_user(
                      username_entry.get(), password_entry.get(), 
                      role_var.get(), status_var.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def update_user(self, username: str, password: str, role: str, status: str, window: tk.Toplevel) -> None:
        if not password:
            messagebox.showerror("Error", "Password is required", parent=self.root)
            return
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE users SET password = ?, role = ?, status = ? WHERE username = ?", 
                               (password, role, status, username))
                self.conn.commit()
            self.update_users_table()
            window.destroy()
            messagebox.showinfo("Success", "User updated successfully", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to update user: {e}", parent=self.root)

    def on_user_select(self, event: tk.Event) -> None:
        selected_item = self.users_table.selection()
        if selected_item:
            self.edit_user_btn.config(state="normal")
            self.delete_user_btn.config(state="normal")
        else:
            self.edit_user_btn.config(state="disabled")
            self.delete_user_btn.config(state="disabled")

    def validate_delete_user_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item", self.users_table.selection())
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No user selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                username = self.users_table.item(selected_item)["values"][0]
                if username == self.current_user:
                    window.destroy()
                    messagebox.showerror("Error", "Cannot delete the currently logged-in user", parent=self.root)
                    return
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'Drug Lord'")
                if cursor.fetchone()[0] == 1 and self.users_table.item(selected_item)["values"][1] == "Drug Lord":
                    window.destroy()
                    messagebox.showerror("Error", "Cannot delete the last Drug Lord user", parent=self.root)
                    return
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                self.conn.commit()
                self.update_users_table()
                window.destroy()
                messagebox.showinfo("Success", "User deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def export_sales_data(self) -> None:
        if not self.current_user or self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to export sales data.", parent=self.root)
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", 
                                                 filetypes=[("CSV files", "*.csv")],
                                                 parent=self.root)
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Transaction ID", "Items", "Total Amount", "Cash Paid", 
                                 "Change", "Timestamp", "Status", "Payment Method", 
                                 "Customer ID", "User", "Discount"])
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT * FROM transactions")
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
                        items_display = ", ".join(item_names) if item_names else "No items"
                        writer.writerow([
                            transaction[0], items_display, transaction[2], 
                            transaction[3], transaction[4], transaction[5], 
                            transaction[6], transaction[7] or "Cash", 
                            transaction[8] or "None", transaction[9], transaction[10]
                        ])
            messagebox.showinfo("Success", f"Sales data exported to {file_path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export sales data: {e}", parent=self.root)

    def select_customer(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Select Customer")
        window.geometry("500x400")
        window.configure(bg="#f5f6f5")

        customer_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        customer_box.pack(pady=20, fill="both", expand=True)

        tk.Label(customer_box, text="Select Customer", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        search_frame = tk.Frame(customer_box, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)

        customers_frame = tk.Frame(customer_box, bg="#ffffff", bd=1, relief="flat")
        customers_frame.pack(fill="both", expand=True, pady=10)

        columns = ("CustomerID", "Name", "Contact")
        headers = ("CUSTOMER ID", "NAME", "CONTACT")
        customer_table = ttk.Treeview(customers_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            customer_table.heading(col, text=head)
            customer_table.column(col, width=150, anchor="center" if col != "Name" else "w")
        customer_table.pack(fill="both", expand=True)

        def update_customer_table(event=None):
            for item in customer_table.get_children():
                customer_table.delete(item)
            with self.conn:
                cursor = self.conn.cursor()
                query = search_entry.get().strip()
                sql = "SELECT customer_id, name, contact FROM customers WHERE name LIKE ?" if query else "SELECT customer_id, name, contact FROM customers"
                cursor.execute(sql, (f"%{query}%",) if query else ())
                for customer in cursor.fetchall():
                    customer_table.insert("", "end", values=customer)

        search_entry.bind("<KeyRelease>", update_customer_table)
        update_customer_table()

        tk.Button(customer_box, text="Select", 
                  command=lambda: self.set_customer(customer_table.selection(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

        customer_table.bind("<Double-1>", lambda e: self.set_customer(customer_table.selection(), window))

    def set_customer(self, selected_item: tuple, window: tk.Toplevel) -> None:
        if not selected_item:
            messagebox.showerror("Error", "No customer selected", parent=self.root)
            return
        customer_id = self.customer_table.item(selected_item)["values"][0]
        customer_name = self.customer_table.item(selected_item)["values"][1]
        self.current_customer_id = customer_id
        self.customer_id_label.config(text=f"{customer_name} ({customer_id})")
        window.destroy()

    def opening_closing_fund(self, event: Optional[tk.Event] = None) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to manage funds.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Manage Fund")
        window.geometry("350x400")
        window.configure(bg="#f5f6f5")

        fund_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        fund_box.pack(pady=20)

        tk.Label(fund_box, text="Manage Fund", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(fund_box, text="Amount", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        amount_entry = tk.Entry(fund_box, font=("Helvetica", 14), bg="#f5f6f5")
        amount_entry.pack(pady=5, fill="x")

        type_var = tk.StringVar(value="Opening")
        tk.Label(fund_box, text="Type", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(fund_box, textvariable=type_var, values=["Opening", "Closing"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(fund_box, text="Submit", 
                  command=lambda: self.add_fund(amount_entry.get(), type_var.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def add_fund(self, amount: str, fund_type: str, window: tk.Toplevel) -> None:
        try:
            amount = float(amount)
            if amount <= 0:
                messagebox.showerror("Error", "Amount must be positive", parent=self.root)
                return
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO funds (fund_id, type, amount, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                               (str(uuid.uuid4()), fund_type, amount, 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            window.destroy()
            messagebox.showinfo("Success", f"{fund_type} fund added successfully", parent=self.root)
        except ValueError:
            messagebox.showerror("Error", "Invalid amount", parent=self.root)

    def void_selected_items(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected or cart is empty", parent=self.root)
            return
        self.create_auth_window("Authenticate Void", 
                               "Enter admin credentials to void selected items", 
                               self.validate_void_items_auth)

    def validate_void_items_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                item = self.cart[self.selected_item_index]
                with self.conn:
                    cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                   (item["quantity"], item["id"]))
                    self.conn.commit()
                self.cart.pop(self.selected_item_index)
                self.selected_item_index = None if not self.cart else min(self.selected_item_index, len(self.cart) - 1)
                self.update_cart_table()
                window.destroy()
                messagebox.showinfo("Success", "Item voided successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def void_order(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        self.create_auth_window("Authenticate Void Order", 
                               "Enter admin credentials to void entire order", 
                               self.validate_void_order_auth)

    def validate_void_order_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                with self.conn:
                    for item in self.cart:
                        cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                       (item["quantity"], item["id"]))
                    self.conn.commit()
                self.cart.clear()
                self.selected_item_index = None
                self.discount_var.set(False)
                self.discount_authenticated = False
                self.update_cart_table()
                window.destroy()
                messagebox.showinfo("Success", "Order voided successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def hold_transaction(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        transaction_id = str(uuid.uuid4())
        items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
        total_amount = float(self.summary_entries["Final Total "].get())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO transactions (transaction_id, items, total_amount, timestamp, status, user_id, discount_amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (transaction_id, items, total_amount, timestamp, "Held", 
                            self.current_user, float(self.summary_entries["Discount "].get())))
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
        window.geometry("600x400")
        window.configure(bg="#f5f6f5")

        unpaid_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        unpaid_box.pack(pady=20, fill="both", expand=True)

        tk.Label(unpaid_box, text="Unpaid Transactions", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        columns = ("TransactionID", "TotalAmount", "Timestamp")
        headers = ("TRANSACTION ID", "TOTAL AMOUNT", "TIMESTAMP")
        unpaid_table = ttk.Treeview(unpaid_box, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            unpaid_table.heading(col, text=head)
            unpaid_table.column(col, width=200, anchor="center")
        unpaid_table.pack(fill="both", expand=True)

        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT transaction_id, total_amount, timestamp FROM transactions WHERE status = 'Held'")
            for transaction in cursor.fetchall():
                unpaid_table.insert("", "end", values=(
                    transaction[0], f"{transaction[1]:.2f}", transaction[2]
                ))

        tk.Button(unpaid_box, text="Load Transaction", 
                  command=lambda: self.load_held_transaction(unpaid_table.selection(), window, unpaid_table),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

        unpaid_table.bind("<Double-1>", lambda e: self.load_held_transaction(unpaid_table.selection(), window, unpaid_table))

    def load_held_transaction(self, selected_item: tuple, window: tk.Toplevel, unpaid_table: ttk.Treeview) -> None:
        if not selected_item:
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = unpaid_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT items, discount_amount FROM transactions WHERE transaction_id = ?", (transaction_id,))
            transaction = cursor.fetchone()
            if transaction:
                self.cart.clear()
                items = transaction[0]
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        qty = int(qty)
                        cursor.execute("SELECT * FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "price": item[3],
                                "quantity": qty,
                                "subtotal": item[3] * qty,
                                "cost_price": item[5]
                            })
                if transaction[1] > 0:
                    self.discount_var.set(True)
                    self.discount_authenticated = True
                self.update_cart_table()
                cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                self.conn.commit()
                window.destroy()
                self.show_dashboard()
                messagebox.showinfo("Success", "Held transaction loaded", parent=self.root)

    def mode_of_payment(self, event: Optional[tk.Event] = None) -> None:
        window = tk.Toplevel(self.root)
        window.title("Select Payment Method")
        window.geometry("350x300")
        window.configure(bg="#f5f6f5")

        payment_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        payment_box.pack(pady=20)

        tk.Label(payment_box, text="Select Payment Method", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        payment_var = tk.StringVar(value="Cash")
        for method in ["Cash", "Credit Card", "Debit Card", "Mobile Payment"]:
            tk.Radiobutton(payment_box, text=method, variable=payment_var, value=method,
                           font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(anchor="w")

        tk.Button(payment_box, text="Confirm", 
                  command=lambda: self.set_payment_method(payment_var.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def set_payment_method(self, method: str, window: tk.Toplevel) -> None:
        self.current_payment_method = method
        window.destroy()
        messagebox.showinfo("Success", f"Payment method set to {method}", parent=self.root)

    def return_transaction(self, event: Optional[tk.Event] = None) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to process returns.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Return Transaction")
        window.geometry("350x400")
        window.configure(bg="#f5f6f5")

        return_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        return_box.pack(pady=20)

        tk.Label(return_box, text="Return Transaction", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(return_box, text="Transaction ID", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        transaction_id_entry = tk.Entry(return_box, font=("Helvetica", 14), bg="#f5f6f5")
        transaction_id_entry.pack(pady=5, fill="x")

        tk.Button(return_box, text="Process Return", 
                  command=lambda: self.create_auth_window(
                      "Authenticate Return", "Enter admin credentials to process return", 
                      self.validate_return_auth, transaction_id=transaction_id_entry.get(), window=window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def validate_return_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        transaction_id = kwargs.get("transaction_id")
        return_window = kwargs.get("window")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                cursor.execute("SELECT items, status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                transaction = cursor.fetchone()
                if not transaction:
                    window.destroy()
                    messagebox.showerror("Error", "Transaction ID not found", parent=self.root)
                    return
                if transaction[1] == "Refunded":
                    window.destroy()
                    messagebox.showerror("Error", "Transaction already refunded", parent=self.root)
                    return
                items = transaction[0]
                for item_data in items.split(";"):
                    if item_data:
                        item_id, qty = item_data.split(":")
                        cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", 
                                       (int(qty), item_id))
                cursor.execute("UPDATE transactions SET status = 'Refunded' WHERE transaction_id = ?", 
                               (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                               (str(uuid.uuid4()), "Return", f"Returned transaction {transaction_id}", 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                window.destroy()
                return_window.destroy()
                messagebox.showinfo("Success", "Return processed successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

    def add_expenses(self, event: Optional[tk.Event] = None) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to add expenses.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Add Expense")
        window.geometry("350x400")
        window.configure(bg="#f5f6f5")

        expense_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        expense_box.pack(pady=20)

        tk.Label(expense_box, text="Add Expense", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(expense_box, text="Description", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        description_entry = tk.Entry(expense_box, font=("Helvetica", 14), bg="#f5f6f5")
        description_entry.pack(pady=5, fill="x")

        tk.Label(expense_box, text="Amount", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        amount_entry = tk.Entry(expense_box, font=("Helvetica", 14), bg="#f5f6f5")
        amount_entry.pack(pady=5, fill="x")

        category_var = tk.StringVar(value="Utilities")
        tk.Label(expense_box, text="Category", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        ttk.Combobox(expense_box, textvariable=category_var, 
                     values=["Utilities", "Supplies", "Maintenance", "Other"], 
                     state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(expense_box, text="Add Expense", 
                  command=lambda: self.add_expense(
                      description_entry.get(), amount_entry.get(), 
                      category_var.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=15)

    def add_expense(self, description: str, amount: str, category: str, window: tk.Toplevel) -> None:
        try:
            amount = float(amount)
            if amount <= 0:
                messagebox.showerror("Error", "Amount must be positive", parent=self.root)
                return
            if not description:
                messagebox.showerror("Error", "Description is required", parent=self.root)
                return
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO expenses (expense_id, description, amount, category, timestamp, user) VALUES (?, ?, ?, ?, ?, ?)",
                               (str(uuid.uuid4()), description, amount, category, 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
            window.destroy()
            messagebox.showinfo("Success", "Expense added successfully", parent=self.root)
        except ValueError:
            messagebox.showerror("Error", "Invalid amount", parent=self.root)

    def add_del_customer(self, event: Optional[tk.Event] = None) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to manage customers.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Manage Customer")
        window.geometry("400x500")
        window.configure(bg="#f5f6f5")

        customer_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        customer_box.pack(pady=20)

        tk.Label(customer_box, text="Manage Customer", font=("Helvetica", 18, "bold"), 
                 bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(customer_box, text="Customer ID", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        customer_id_entry = tk.Entry(customer_box, font=("Helvetica", 14), bg="#f5f6f5")
        customer_id_entry.pack(pady=5, fill="x")

        tk.Label(customer_box, text="Name", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        name_entry = tk.Entry(customer_box, font=("Helvetica", 14), bg="#f5f6f5")
        name_entry.pack(pady=5, fill="x")

        tk.Label(customer_box, text="Contact", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        contact_entry = tk.Entry(customer_box, font=("Helvetica", 14), bg="#f5f6f5")
        contact_entry.pack(pady=5, fill="x")

        tk.Label(customer_box, text="Address", font=("Helvetica", 14), 
                 bg="#ffffff", fg="#1a1a1a").pack()
        address_entry = tk.Entry(customer_box, font=("Helvetica", 14), bg="#f5f6f5")
        address_entry.pack(pady=5, fill="x")

        tk.Button(customer_box, text="Add Customer", 
                  command=lambda: self.add_customer(
                      customer_id_entry.get(), name_entry.get(), 
                      contact_entry.get(), address_entry.get(), window),
                  bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#27ae60", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=10)

        tk.Button(customer_box, text="Delete Customer", 
                  command=lambda: self.create_auth_window(
                      "Authenticate Deletion", "Enter admin credentials to delete customer", 
                      self.validate_delete_customer_auth, customer_id=customer_id_entry.get(), window=window),
                  bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                  activebackground="#c0392b", activeforeground="#ffffff",
                  padx=12, pady=8, bd=0).pack(pady=10)

    def add_customer(self, customer_id: str, name: str, contact: str, address: str, window: tk.Toplevel) -> None:
        if not name:
            messagebox.showerror("Error", "Name is required", parent=self.root)
            return
        customer_id = customer_id.strip() if customer_id.strip() else str(uuid.uuid4())
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO customers VALUES (?, ?, ?, ?)", 
                               (customer_id, name, contact, address))
                self.conn.commit()
            window.destroy()
            messagebox.showinfo("Success", "Customer added successfully", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Customer ID already exists", parent=self.root)

    def validate_delete_customer_auth(self, username: str, password: str, window: tk.Toplevel, **kwargs) -> None:
        customer_id = kwargs.get("customer_id")
        customer_window = kwargs.get("window")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE password = ? AND role = 'Drug Lord'", 
                           (password,))
            if cursor.fetchone():
                cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
                if not cursor.fetchone():
                    window.destroy()
                    messagebox.showerror("Error", "Customer ID not found", parent=self.root)
                    return
                cursor.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
                self.conn.commit()
                window.destroy()
                customer_window.destroy()
                messagebox.showinfo("Success", "Customer deleted successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin credentials", parent=self.root)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = PharmacyPOS(root)
        root.mainloop()
    except Exception as e:
        print(f"Application failed to start: {e}")
        messagebox.showerror("Startup Error", f"Failed to start application: {e}")