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
        self.root.bind("<F1>", self.opening_closing_fund)
        self.root.bind("<F2>", self.void_selected_items)
        self.root.bind("<F3>", self.void_order)
        self.root.bind("<F4>", self.hold_transaction)
        self.root.bind("<F5>", self.view_unpaid_transactions)
        self.root.bind("<F6>", self.mode_of_payment)
        self.root.bind("<F7>", self.handle_discount_toggle_event)
        # self.root.bind("<F8>", self.return_transaction)
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
                    supplier TEXT
                )
            ''')
            # Check if supplier column exists in inventory table
            cursor.execute("PRAGMA table_info(inventory)")
            columns = [col[1] for col in cursor.fetchall()]
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
            ("MED001", "Pain Reliever", "Medicine", 10.00, 100, "PharmaCorp"),
            ("SUP001", "Vitamin C", "Supplement", 5.00, 200, "HealthSupplies Inc"),
            ("DEV001", "Thermometer", "Medical Device", 15.00, 50, "MediTech Ltd"),
        ]
        with self.conn:
            cursor = self.conn.cursor()
            for item_id, name, item_type, price, quantity, supplier in sample_items:
                cursor.execute("INSERT OR IGNORE INTO inventory (item_id, name, type, price, quantity, supplier) VALUES (?, ?, ?, ?, ?, ?)",
                            (item_id, name, item_type, price, quantity, supplier))
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
                bg="#ffffff", fg="#1a1a1a").pack(anchor="w")  # Changed to left align
        username_entry = tk.Entry(login_box, font=("Helvetica", 14), bg="#f5f6f5")
        username_entry.pack(pady=5, fill="x")

        tk.Label(login_box, text="Password", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(anchor="w")  # Changed to left align
        password_entry = tk.Entry(login_box, show="*", font=("Helvetica", 14), bg="#f5f6f5")
        password_entry.pack(pady=5, fill="x")

        show_password_var = tk.BooleanVar()
        tk.Checkbutton(login_box, text="Show Password", variable=show_password_var,
                    command=lambda: password_entry.config(show="" if show_password_var.get() else "*"),
                    font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(anchor="w", pady=8)  # Changed to left align

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

        columns = ("Product", "UnitPrice", "Quantity", "Subtotal")
        headers = ("PRODUCT DETAILS", "SRP ", "QUANTITY", "SUBTOTAL ")
        self.cart_table = ttk.Treeview(cart_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.cart_table.heading(col, text=head)
            self.cart_table.column(col, width=150 if col != "Product" else 300,
                                anchor="center" if col != "Product" else "w")
        self.cart_table.grid(row=1, column=0, columnspan=4, sticky="nsew")
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
                cursor.execute("SELECT name, price, quantity, supplier FROM inventory WHERE name LIKE ? OR supplier LIKE ?",
                        (f"%{query}%", f"%{query}%"))
            suggestions = cursor.fetchall()

            if suggestions:
                for name, price, quantity, supplier in suggestions:
                    display_text = f"{name} - ₱{price:.2f} (Stock: {quantity}, Supplier: {supplier or 'Unknown'})"
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
                                cart_item["subtotal"] = cart_item["price"] * cart_item["quantity"]
                                break
                        else:
                            self.cart.append({
                                "id": item[0],
                                "name": item[1],
                                "price": item[3],
                                "quantity": 1,
                                "subtotal": item[3]
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
        # Toggle the discount variable
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
            # Update the discount status label
            self.update_discount_status_label()

    def update_discount_status_label(self) -> None:
        # Update the label in the summary_frame to reflect discount status
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
                self.update_discount_status_label()  # Update label
                window.destroy()
                messagebox.showinfo("Success", "Discount authentication successful", parent=self.root)
            else:
                self.discount_var.set(False)
                self.discount_authenticated = False
                self.update_cart_totals()
                self.update_discount_status_label()  # Update label
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_cart_table(self) -> None:
        if hasattr(self, 'cart_table') and self.cart_table.winfo_exists():
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
                if new_quantity > inventory_qty:
                    messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {inventory_qty}", parent=self.root)
                    self.update_quantity_display()
                    return
                item["quantity"] = new_quantity
                item["subtotal"] = item["price"] * new_quantity
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

            # Check for low inventory after commit
            self.check_low_inventory()

            # Update and clear fields
            self.summary_entries["Change "].config(state="normal")
            self.summary_entries["Change "].delete(0, tk.END)
            self.summary_entries["Change "].insert(0, f"{change:.2f}")
            self.summary_entries["Change "].config(state="readonly")

            # Clear the Cash Paid field
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

        columns = ("Name", "Type", "Price", "Quantity", "Supplier")
        headers = ("NAME", "TYPE", "PRICE", "QUANTITY", "SUPPLIER")
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
        window.geometry("400x550")  # Adjusted size for new field
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New Item to Inventory", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Item ID (Barcode)", "Product Name", "Price", "Quantity", "Supplier"]
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
                    entries["Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    window
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def add_item(self, item_id: str, name: str, item_type: str, price: str, quantity: str, supplier: str, window: tk.Toplevel) -> None:
        try:
            price = float(price)
            quantity = int(quantity)
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)",
                            (item_id, name, item_type, price, quantity, supplier))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Add Item", f"Added item {item_id}: {name}, {quantity} units, Supplier: {supplier}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item added successfully", parent=self.root)
                # Check for low inventory after adding
                if quantity <= 5:
                    self.check_low_inventory()
        except ValueError:
            messagebox.showerror("Error", "Invalid price or quantity", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def on_inventory_table_click(self, event: tk.Event) -> None:
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
        window.geometry("400x500")
        window.configure(bg="#f5f6f5")

        update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        update_box.pack(pady=20)

        tk.Label(update_box, text="Update Item", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        # Fetch item_id from database using name as a unique identifier
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id FROM inventory WHERE name = ?", (item[0],))
            result = cursor.fetchone()
            item_id = result[0] if result else str(uuid.uuid4())  # Generate new ID if not found

        fields = ["Item ID", "Product Name", "Price", "Quantity", "Supplier"]
        entries = {}
        for field in fields:
            frame = tk.Frame(update_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        # Populate fields with correct values from the item tuple
        entries["Item ID"].insert(0, item_id or "")
        entries["Product Name"].insert(0, item[0] or "")  # name
        entries["Price"].insert(0, str(item[2]) if item[2] is not None else "")  # price
        entries["Quantity"].insert(0, str(item[3]) if item[3] is not None else "")  # quantity
        entries["Supplier"].insert(0, item[4] or "")  # supplier

        type_var = tk.StringVar(value=item[1] or "")  # type
        tk.Label(update_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        type_combobox = ttk.Combobox(update_box, textvariable=type_var,
                                    values=["Medicine", "Supplement", "Medical Device", "Beverage", "Personal Hygiene", "Baby Product", "Toiletries", "Other"],
                                    state="readonly", font=("Helvetica", 14))
        type_combobox.pack(pady=5)

        tk.Button(update_box, text="Update Item",
                command=lambda: self.update_item(
                    entries["Item ID"].get(),
                    entries["Product Name"].get(),
                    type_var.get(),
                    entries["Price"].get(),
                    entries["Quantity"].get(),
                    entries["Supplier"].get(),
                    item_id,  # Original item_id from database
                    window
                ),
                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                activebackground="#27ae60", activeforeground="#ffffff",
                padx=12, pady=8, bd=0).pack(pady=15)

    def update_item(self, item_id: str, name: str, item_type: str, price: str, quantity: str, supplier: str, original_item_id: str, window: tk.Toplevel) -> None:
        try:
            price = float(price)
            quantity = int(quantity)
            if not all([name, item_type]):
                messagebox.showerror("Error", "Product Name and Type are required", parent=self.root)
                return
            name = name.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("UPDATE inventory SET item_id = ?, name = ?, type = ?, price = ?, quantity = ?, supplier = ? WHERE item_id = ?",
                            (item_id, name, item_type, price, quantity, supplier, original_item_id))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), "Update Item", f"Updated item {item_id}: {name}, {quantity} units, Supplier: {supplier}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item updated successfully", parent=self.root)
                # Check for low inventory after updating
                if quantity <= 5:
                    self.check_low_inventory()
        except ValueError:
            messagebox.showerror("Error", "Invalid price or quantity", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def on_inventory_select(self, event: tk.Event) -> None:
        selected_item = self.inventory_table.selection()
        state = "normal" if selected_item else "disabled"
        self.update_item_btn.config(state=state)
        self.delete_item_btn.config(state=state)

    def check_low_inventory(self) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id, quantity FROM inventory")
            for item_id, quantity in cursor.fetchall():
                if quantity <= 5:
                    cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                    name = cursor.fetchone()[0]
                    messagebox.showwarning("Inventory Alert", f"Low stock for {name}: Only {quantity} units left", parent=self.root)
    

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
            sql = "SELECT name, type, price, quantity, supplier FROM inventory"
            params = []
            conditions = []
            if query:
                conditions.append("(name LIKE ? OR supplier LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if type_filter != "All":
                conditions.append("type = ?")
                params.append(type_filter)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            cursor.execute(sql, params)
            for item in cursor.fetchall():
                name, item_type, price, quantity, supplier = item
                # Ensure quantity is an integer
                try:
                    quantity = int(float(quantity))  # Handle potential float values
                except (ValueError, TypeError):
                    quantity = 0  # Fallback if quantity is invalid
                # Apply 'low_stock' tag if quantity <= 5
                tags = ('low_stock',) if quantity <= 5 else ()
                # Insert item into Treeview with appropriate tag
                self.inventory_table.insert("", "end", values=(
                    name, item_type, f"{price:.2f}", quantity, supplier or "Unknown"
                ), tags=tags)
                # Debug print to verify tagging
                print(f"Item: {name}, Quantity: {quantity}, Tags: {tags}")

    def show_transactions(self, event: Optional[tk.Event] = None) -> None:
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

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Transaction ID:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        search_entry.bind("<KeyRelease>", self.update_transactions_table)
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

        columns = ("TransactionID", "ItemsList", "TotalAmount", "CashPaid", "ChangeAmount", "Timestamp", "Status", "PaymentMethod", "CustomerID")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT ", "CASH PAID ", "CHANGE ", "TIMESTAMP", "STATUS", "PAYMENT METHOD", "CUSTOMER ID")
        self.transactions_table = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)
        for col, head in zip(columns, headers):
            self.transactions_table.heading(col, text=head)
            width = 300 if col == "ItemsList" else 150
            self.transactions_table.column(col, width=width, anchor="center" if col != "ItemsList" else "w")
        self.transactions_table.pack(fill="both", expand=True)

        def update_scroll_region(event=None):
            total_width = sum(self.transactions_table.column(col, "width") for col in columns)
            total_height = self.transactions_table.winfo_reqheight()
            canvas.configure(scrollregion=(0, 0, total_width, total_height))
            canvas.itemconfig(canvas_window, width=total_width)

        self.transactions_table.bind("<Configure>", update_scroll_region)
        canvas.configure(xscrollcommand=h_scrollbar.set)
        
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

        self.update_transactions_table()
        self.transactions_table.bind("<<TreeviewSelect>>", self.on_transaction_select)

        self.transaction_button_frame = tk.Frame(transactions_frame, bg="#ffffff")
        self.transaction_button_frame.grid(row=3, column=0, columnspan=9, pady=10)
        self.print_btn = tk.Button(self.transaction_button_frame, text="Print Receipt", command=self.print_receipt,
                                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                                activebackground="#27ae60", activeforeground="#ffffff",
                                padx=12, pady=8, bd=0, state="disabled")
        self.print_btn.pack(side="left", padx=5)
        self.edit_transaction_btn = tk.Button(self.transaction_button_frame, text="Edit Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Edit", "Enter admin password to edit transaction",
                                                self.validate_edit_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#3498db", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#2980b9", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.edit_transaction_btn.pack(side="left", padx=5)
        self.delete_transaction_btn = tk.Button(self.transaction_button_frame, text="Delete Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Deletion", "Enter admin password to delete transaction",
                                                self.validate_delete_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                            activebackground="#c0392b", activeforeground="#ffffff",
                                            padx=12, pady=8, bd=0, state="disabled")
        self.delete_transaction_btn.pack(side="left", padx=5)
        self.refund_btn = tk.Button(self.transaction_button_frame, text="Refund",
                                    command=lambda: self.create_password_auth_window(
                                        "Authenticate Refund", "Enter admin password to process refund",
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
                    transaction[8] or "None"
                ))

    def on_transaction_select(self, event: tk.Event) -> None:
        selected_item = self.transactions_table.selection()
        state = "normal" if selected_item else "disabled"
        self.print_btn.config(state=state)
        self.edit_transaction_btn.config(state=state)
        self.delete_transaction_btn.config(state=state)
        self.refund_btn.config(state=state)


    def validate_delete_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
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
                    # Verify transaction exists and get items for inventory update
                    cursor.execute("SELECT items, status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                    transaction = cursor.fetchone()
                    if not transaction:
                        window.destroy()
                        messagebox.showerror("Error", "Transaction not found", parent=self.root)
                        return
                    if transaction[1] == "Returned":
                        window.destroy()
                        messagebox.showerror("Error", "Cannot delete a returned transaction", parent=self.root)
                        return
                    # Delete the transaction
                    cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                    log_id = f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}"
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                (log_id, "Delete Transaction", f"Deleted transaction {transaction_id}",
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    self.update_transactions_table()
                    window.destroy()
                    messagebox.showinfo("Success", f"Transaction {transaction_id} deleted successfully", parent=self.root)
                except sqlite3.Error as e:
                    window.destroy()
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
            window.configure(bg="#f5f6f5")

            content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
            content_frame.pack(fill="both", expand=True)

            tk.Label(content_frame, text=f"Edit Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=10)

            columns = ("Item", "OriginalQuantity", "NewQuantity")
            headers = ("ITEM", "ORIGINAL QTY", "NEW QTY")
            edit_table = ttk.Treeview(content_frame, columns=columns, show="headings")
            for col, head in zip(columns, headers):
                edit_table.heading(col, text=head)
                edit_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
            edit_table.pack(fill="both", expand=True)

            quantity_entries = {}
            for item in edit_items:
                item_iid = edit_table.insert("", "end", values=(item["name"], item["original_quantity"], item["current_quantity"]))
                quantity_entries[item_iid] = {"item": item, "entry": None}

            def update_quantity_fields():
                for item_iid in edit_table.get_children():
                    item_data = quantity_entries[item_iid]["item"]
                    frame = tk.Frame(content_frame, bg="#ffffff")
                    frame.pack(fill="x", pady=2)
                    tk.Label(frame, text=item_data["name"], font=("Helvetica", 12), bg="#ffffff", fg="#1a1a1a").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 12), bg="#f5f6f5", width=10)
                    entry.insert(0, str(item_data["current_quantity"]))
                    entry.pack(side="left", padx=5)
                    quantity_entries[item_iid]["entry"] = entry
                    edit_table.item(item_iid, values=(item_data["name"], item_data["original_quantity"], item_data["current_quantity"]))

            update_quantity_fields()

            tk.Button(content_frame, text="Confirm Changes",
                    command=lambda: self.process_edit_transaction(transaction_id, edit_items, quantity_entries, transaction[2], transaction[5], transaction[6], window),
                    bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                    activebackground="#27ae60", activeforeground="#ffffff",
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
        c.drawString(100, 732, "ARI PHARMACEUTICALS INC.")
        c.drawString(100, 714, "VAT REG TIN: 123-456-789-000")
        c.drawString(100, 696, "SN: 987654321 MIN: 123456789")
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
                price = 0.0
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT price FROM inventory WHERE name = ?", (item_name,))
                    result = cursor.fetchone()
                    if result:
                        price = float(result[0])
                    else:
                        missing_items.append(item_name)
                data.append([item_name, str(qty), f"{price:.2f}"])
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

            tk.Label(content_frame, text="Monthly Sales Summary", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")
            monthly_table = ttk.Treeview(content_frame, columns=("Month", "TotalSales", "TotalExpenses", "Profit"), show="headings")
            monthly_table.heading("Month", text="Month")
            monthly_table.heading("TotalSales", text="Total Sales")
            monthly_table.heading("TotalExpenses", text="Total Expenses")
            monthly_table.heading("Profit", text="Profit")
            monthly_table.column("Month", width=200, anchor="w")
            monthly_table.column("TotalSales", width=150, anchor="center")
            monthly_table.column("TotalExpenses", width=150, anchor="center")
            monthly_table.column("Profit", width=150, anchor="center")
            monthly_table.pack(fill="x", pady=5)

            tk.Label(content_frame, text="Daily Sales Summary", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")
            daily_table = ttk.Treeview(content_frame, columns=("Date", "DailySales", "DailyExpenses", "DailyProfit"), show="headings")
            daily_table.heading("Date", text="Date")
            daily_table.heading("DailySales", text="Total Sales")
            daily_table.heading("DailyExpenses", text="Total Expenses")
            daily_table.heading("DailyProfit", text="Profit")
            daily_table.column("Date", width=200, anchor="w")
            daily_table.column("DailySales", width=150, anchor="center")
            daily_table.column("DailyExpenses", width=150, anchor="center")
            daily_table.column("DailyProfit", width=150, anchor="center")
            daily_table.pack(fill="x", pady=5)

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT strftime('%Y-%m', timestamp) AS month, SUM(total_amount) FROM transactions WHERE status = 'Completed' GROUP BY month")
                monthly_sales = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}
                cursor.execute("SELECT strftime('%Y-%m', timestamp) AS month, SUM(amount) FROM expenses GROUP BY month")
                monthly_expenses = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}

                for month in sorted(set(monthly_sales.keys()) | set(monthly_expenses.keys())):
                    sales = monthly_sales.get(month, 0.0)
                    expenses = monthly_expenses.get(month, 0.0)
                    profit = sales - expenses
                    monthly_table.insert("", "end", values=(month, f"{sales:.2f}", f"{expenses:.2f}", f"{profit:.2f}"))

                cursor.execute("SELECT strftime('%Y-%m-%d', timestamp) AS date, SUM(total_amount) FROM transactions WHERE status = 'Completed' GROUP BY date")
                daily_sales = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}
                cursor.execute("SELECT strftime('%Y-%m-%d', timestamp) AS date, SUM(amount) FROM expenses GROUP BY date")
                daily_expenses = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}

                for date in sorted(set(daily_sales.keys()) | set(daily_expenses.keys())):
                    sales = daily_sales.get(date, 0.0)
                    expenses = daily_expenses.get(date, 0.0)
                    profit = sales - expenses
                    daily_table.insert("", "end", values=(date, f"{sales:.2f}", f"{expenses:.2f}", f"{profit:.2f}"))

    def show_account_management(self) -> None:
        if self.get_user_role() != "Drug Lord":
            messagebox.showerror("Access Denied", "You do not have permission to access this section.", parent=self.root)
            self.show_dashboard()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Account Management", font=("Helvetica", 18, "bold"),
                 bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")

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
        self.users_table.bind("<<TreeviewSelect>>", self.on_user_select)
        users_frame.pack(fill="both", expand=True)

        self.users_button_frame = tk.Frame(content_frame, bg="#ffffff")
        self.users_button_frame.pack(fill="x", pady=10)
        self.update_user_btn = tk.Button(self.users_button_frame, text="Update", command=self.show_update_user,
                                        bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#27ae60", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.update_user_btn.pack(side="left", padx=5)
        self.delete_user_btn = tk.Button(self.users_button_frame, text="Delete",
                                        command=lambda: self.create_password_auth_window(
                                            "Authenticate Deletion", "Enter admin password to delete user",
                                            self.validate_delete_user_auth, selected_item=self.users_table.selection()),
                                        bg="#e74c3c", fg="#ffffff", font=("Helvetica", 14),
                                        activebackground="#c0392b", activeforeground="#ffffff",
                                        padx=12, pady=8, bd=0, state="disabled")
        self.delete_user_btn.pack(side="left", padx=5)

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x")
        tk.Button(button_frame, text="Add New User", command=self.show_add_user,
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
                 padx=12, pady=8, bd=0).pack(side="left", padx=5)

        tk.Label(content_frame, text="Transaction Log", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")
        log_frame = tk.Frame(content_frame, bg="#ffffff", bd=1, relief="flat")
        log_frame.pack(fill="both", expand=True, pady=10)
        columns = ("Action", "Details", "Timestamp", "User")
        headers = ("ACTION", "DETAILS", "TIMESTAMP", "USER")
        self.log_table = ttk.Treeview(log_frame, columns=columns, show="headings")
        for col, head in zip(columns, headers):
            self.log_table.heading(col, text=head)
            self.log_table.column(col, width=150 if col != "Details" else 300, anchor="center" if col != "Details" else "w")
        self.log_table.pack(fill="both", expand=True)
        self.update_log_table()

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
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New User", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Username", "Password"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5", show="*" if field == "Password" else "")
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        role_var = tk.StringVar()
        tk.Label(add_box, text="Role", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
        ttk.Combobox(add_box, textvariable=role_var, values=["User", "Drug Lord"],
                    state="readonly", font=("Helvetica", 14)).pack(pady=5)

        tk.Button(add_box, text="Add User",
                 command=lambda: self.add_user(entries["Username"].get(), entries["Password"].get(),
                                              role_var.get(), window),
                 bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                 activebackground="#27ae60", activeforeground="#ffffff",
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
                window.configure(bg="#f5f6f5")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
                update_box.pack(pady=20)

                tk.Label(update_box, text="Update User", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=15)

                fields = ["Username", "Password"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5", show="*" if field == "Password" else "")
                    entry.pack(side="left", fill="x", expand=True, padx=5)
                    entries[field] = entry
                    entry.insert(0, user[i])

                role_var = tk.StringVar(value=user[2])
                tk.Label(update_box, text="Role", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
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
        main_frame = tk.Frame(self.main_frame, bg="#f5f6f5")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        tk.Label(content_frame, text="Customer Management", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10, anchor="w")

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        self.customer_search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
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
        window.configure(bg="#f5f6f5")

        add_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        add_box.pack(pady=20)

        tk.Label(add_box, text="Add New Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        fields = ["Customer ID", "Name", "Contact", "Address"]
        entries = {}
        for field in fields:
            frame = tk.Frame(add_box, bg="#ffffff")
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
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
                window.configure(bg="#f5f6f5")

                update_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
                update_box.pack(pady=20)

                tk.Label(update_box, text="Update Customer", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=15)

                fields = ["Customer ID", "Name", "Contact", "Address"]
                entries = {}
                for i, field in enumerate(fields):
                    frame = tk.Frame(update_box, bg="#ffffff")
                    frame.pack(fill="x", pady=5)
                    tk.Label(frame, text=field, font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", 14), bg="#f5f6f5")
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
        window.configure(bg="#f5f6f5")

        content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
        content_frame.pack(fill="both", expand=True)

        tk.Label(content_frame, text="Select Customer", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=10)

        search_frame = tk.Frame(content_frame, bg="#ffffff")
        search_frame.pack(fill="x", pady=5)
        tk.Label(search_frame, text="Search by Name:", font=("Helvetica", 14),
                bg="#ffffff", fg="#1a1a1a").pack(side="left")
        search_entry = tk.Entry(search_frame, font=("Helvetica", 14), bg="#f5f6f5")
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

    def opening_closing_fund(self, event: Optional[tk.Event] = None) -> None:
        if not self.current_user:
            messagebox.showerror("Error", "You must be logged in to manage funds.", parent=self.root)
            return
        self.create_password_auth_window(
            "Authenticate Fund Access",
            "Enter admin password to access fund management",
            self.validate_fund_access_auth
        )

    def validate_fund_access_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                window.destroy()
                # Show the fund management window
                fund_window = tk.Toplevel(self.root)
                fund_window.title("Manage Fund")
                fund_window.geometry("400x300")
                fund_window.configure(bg="#f5f6f5")

                fund_box = tk.Frame(fund_window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
                fund_box.pack(pady=20)

                tk.Label(fund_box, text="Manage Fund", font=("Helvetica", 18, "bold"),
                        bg="#ffffff", fg="#1a1a1a").pack(pady=15)

                tk.Label(fund_box, text="Amount", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack()
                amount_entry = tk.Entry(fund_box, font=("Helvetica", 14), bg="#f5f6f5")
                amount_entry.pack(pady=5, fill="x")

                type_var = tk.StringVar()
                tk.Label(fund_box, text="Type", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(pady=5)
                ttk.Combobox(fund_box, textvariable=type_var, values=["Opening Fund", "Closing Fund"],
                            state="readonly", font=("Helvetica", 14)).pack(pady=5)

                tk.Button(fund_box, text="Submit",
                        command=lambda: self.validate_fund_auth(
                            password=password,  # Pass validated password
                            amount=amount_entry.get(),
                            fund_type=type_var.get(),
                            window=fund_window  # Pass fund_window as the window to close
                        ),
                        bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                        activebackground="#27ae60", activeforeground="#ffffff",
                        padx=12, pady=8, bd=0).pack(pady=15)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

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
        self.create_password_auth_window(
            "Authenticate Void", "Enter admin password to void selected item",
            self.validate_void_selected_auth)

    def validate_void_selected_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                if self.selected_item_index is not None:
                    item = self.cart.pop(self.selected_item_index)
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                  (str(uuid.uuid4()), "Void Item", f"Voided item {item['name']} from cart",
                                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    self.update_cart_table()
                    self.selected_item_index = None
                    self.quantity_entry.config(state="disabled")
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
            "Authenticate Void Order", "Enter admin password to void entire order",
            self.validate_void_order_auth)

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
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (str(uuid.uuid4()), "Void Order", "Voided entire order",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_cart_table()
                window.destroy()
                messagebox.showinfo("Success", "Order voided successfully", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

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
                        item_id, qty = item_data.split(":")
                        cursor.execute("SELECT name FROM inventory WHERE item_id = ?", (item_id,))
                        name = cursor.fetchone()
                        if name:
                            item_names.append(f"{name[0]} (x{qty})")
                items_display = ", ".join(item_names)[:100] + "..." if len(", ".join(item_names)) > 100 else ", ".join(item_names)
                unpaid_table.insert("", "end", values=(transaction[0], items_display, f"{transaction[2]:.2f}", transaction[3]))

        unpaid_table.bind("<<TreeviewSelect>>", lambda e: self.on_unpaid_transaction_select(unpaid_table))

        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="x", pady=10)

        self.resume_btn = tk.Button(button_frame, text="Resume Transaction", command=lambda: self.resume_transaction(unpaid_table, window),
                                bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                                activebackground="#27ae60", activeforeground="#ffffff",
                                padx=12, pady=8, bd=0, state="disabled")
        self.resume_btn.pack(side="left", padx=5)

        self.delete_btn = tk.Button(button_frame, text="Delete Transaction",
                                command=lambda: self.create_password_auth_window(
                                    "Authenticate Deletion", "Enter admin password to delete transaction",
                                    self.validate_delete_transaction_auth, unpaid_table=unpaid_table, window=window),
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


    def validate_delete_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        unpaid_table = kwargs.get("unpaid_table")
        parent_window = kwargs.get("window")
        selected_item = unpaid_table.selection()
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = unpaid_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord' LIMIT 1")
            admin_password = cursor.fetchone()
            if admin_password and password == admin_password[0]:
                try:
                    cursor.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))
                    log_id = f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}"  # Example: 07-2025-abc123
                    cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                                (log_id, "Delete Transaction", f"Deleted unpaid transaction {transaction_id}",
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    window.destroy()
                    parent_window.destroy()
                    messagebox.showinfo("Success", f"Transaction {transaction_id} deleted successfully", parent=self.root)
                except sqlite3.Error as e:
                    messagebox.showerror("Error", f"Failed to delete transaction: {e}", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

       

    def mode_of_payment(self, event: Optional[tk.Event] = None) -> None:
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Select Payment Method")
        window.geometry("400x450")
        window.configure(bg="#f5f6f5")

        payment_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        payment_box.pack(pady=20)

        tk.Label(payment_box, text="Select Payment Method", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        payment_var = tk.StringVar()
        payment_options = ["Cash", "Credit Card", "Debit Card", "Mobile Payment"]
        for option in payment_options:
            tk.Radiobutton(payment_box, text=option, variable=payment_var, value=option,
                          font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack(anchor="w", pady=5)

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
        window.configure(bg="#f5f6f5")

        return_box = tk.Frame(window, bg="#ffffff", padx=20, pady=20, bd=1, relief="flat")
        return_box.pack(pady=20)

        tk.Label(return_box, text="Return Transaction", font=("Helvetica", 18, "bold"),
                bg="#ffffff", fg="#1a1a1a").pack(pady=15)

        tk.Label(return_box, text="Transaction ID", font=("Helvetica", 14), bg="#ffffff", fg="#1a1a1a").pack()
        transaction_id_entry = tk.Entry(return_box, font=("Helvetica", 14), bg="#f5f6f5")
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
                        cursor.execute("SELECT name, price FROM inventory WHERE item_id = ?", (item_id,))
                        item = cursor.fetchone()
                        if item:
                            return_items.append({"id": item_id, "name": item[0], "quantity": int(qty), "price": float(item[1])})
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
            window.configure(bg="#f5f6f5")

            content_frame = tk.Frame(window, bg="#ffffff", padx=20, pady=20)
            content_frame.pack(fill="both", expand=True)

            tk.Label(content_frame, text=f"Return Transaction {transaction_id}", font=("Helvetica", 18, "bold"),
                    bg="#ffffff", fg="#1a1a1a").pack(pady=10)

            columns = ("Item", "Quantity", "Price")
            headers = ("ITEM", "QUANTITY", "PRICE")
            return_table = ttk.Treeview(content_frame, columns=columns, show="headings")
            for col, head in zip(columns, headers):
                return_table.heading(col, text=head)
                return_table.column(col, width=150 if col != "Item" else 200, anchor="center" if col != "Item" else "w")
            return_table.pack(fill="both", expand=True)

            for item in return_items:
                return_table.insert("", "end", values=(item["name"], item["quantity"], f"{item['price']:.2f}"))

            tk.Button(content_frame, text="Confirm Return",
                    command=lambda: self.process_return(transaction_id, return_items, window),
                    bg="#2ecc71", fg="#ffffff", font=("Helvetica", 14),
                    activebackground="#27ae60", activeforeground="#ffffff",
                    padx=12, pady=8, bd=0).pack(pady=10)

    def process_return(self, transaction_id: str, return_items: List[Dict], window: tk.Toplevel) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                # Verify transaction is not already returned
                cursor.execute("SELECT status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                status = cursor.fetchone()
                if not status:
                    messagebox.showerror("Error", "Transaction not found", parent=self.root)
                    return
                if status[0] == "Returned":
                    messagebox.showerror("Error", "Transaction has already been returned", parent=self.root)
                    return

                # Update inventory for each returned item
                for item in return_items:
                    cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    result = cursor.fetchone()
                    if result is None:
                        messagebox.showerror("Error", f"Item {item['name']} not found in inventory", parent=self.root)
                        return
                    cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?",
                                (item["quantity"], item["id"]))

                # Mark transaction as returned
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