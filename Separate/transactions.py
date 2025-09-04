import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
from datetime import datetime
from typing import Optional, List, Dict
import uuid
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from tkinter import simpledialog
import webbrowser

class TransactionManager:
    def __init__(self, root, current_user, user_role):
        self.root = root
        self.root.title("Transaction Management")
        self.root.geometry("1200x700")
        self.root.configure(bg="#F5F6F5")
        self.current_user = current_user
        self.user_role = user_role
        self.db_path = self.get_writable_db_path()
        self.conn = sqlite3.connect(self.db_path)
        self.transaction_table = None
        self.search_entry = None
        self.print_btn = None
        self.edit_transaction_btn = None
        self.delete_transaction_btn = None
        self.refund_btn = None
        self.transaction_button_frame = None
        self.main_frame = tk.Frame(self.root, bg="#F5F6F5")
        self.main_frame.pack(fill="both", expand=True)
        self.create_database()
        self.show_transactions()

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

    def create_database(self):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    items TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    cash_paid REAL,
                    change_amount REAL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payment_method TEXT,
                    customer_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transaction_log (
                    log_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    details TEXT,
                    timestamp TEXT NOT NULL,
                    user TEXT
                )
            """)
            self.conn.commit()

    def scale_size(self, size: int) -> int:
        base_resolution = 1920
        current_width = self.root.winfo_screenwidth()
        scaling_factor = current_width / base_resolution
        return int(size * scaling_factor)

    def create_password_auth_window(self, title: str, prompt: str, callback, **kwargs):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(f"{self.scale_size(400)}x{self.scale_size(200)}")
        window.configure(bg="#F5F5DC")
        tk.Label(window, text=prompt, font=("Helvetica", self.scale_size(14)), bg="#F5F5DC", fg="#2C1B18").pack(pady=self.scale_size(10))
        password_entry = tk.Entry(window, show="*", font=("Helvetica", self.scale_size(14)), bg="#F5F5DC", fg="#2C1B18")
        password_entry.pack(pady=self.scale_size(10))
        tk.Button(window, text="Submit",
                  command=lambda: callback(password_entry.get(), window, **kwargs),
                  bg="#6F4E37", fg="#FFF8E7", font=("Helvetica", self.scale_size(14))).pack(pady=self.scale_size(10))

    def get_user_role(self):
        return self.user_role

    def show_account_management(self):
        # Placeholder: Redirect to account management (not implemented here)
        self.root.destroy()

    def setup_navigation(self, main_frame):
        # Placeholder: Add navigation bar if needed (e.g., back to dashboard)
        pass

    def treeview_scroll(self, event, canvas):
        if event.delta > 0:
            canvas.yview_scroll(-1, "units")
        elif event.delta < 0:
            canvas.yview_scroll(1, "units")
        return "break"

    def check_low_inventory(self):
        try:
            threshold = 10
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT item_id, name, quantity FROM inventory WHERE quantity <= ?", (threshold,))
                low_items = cursor.fetchall()
                if low_items:
                    message = "The following items are low in stock:\n\n" + "\n".join(
                        f"{name} (ID: {item_id}) - Quantity: {quantity}" for item_id, name, quantity in low_items
                    )
                    messagebox.showwarning("Low Inventory Alert", message, parent=self.root)
                cursor.execute("""
                    INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), "Check Inventory", f"Checked low inventory, found {len(low_items)} items",
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user or "System"))
                self.conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to check inventory: {e}", parent=self.root)

    def show_transactions(self, event: Optional[tk.Event] = None) -> None:
        if self.user_role == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        elif self.user_role != "Manager":
            messagebox.showerror("Access Denied", "Only Managers can access Transaction Management.", parent=self.root)
            self.root.destroy()
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")  # Sandy Beige
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=20, pady=20)  # Soft White
        content_frame.pack(fill="both", expand=True, padx=(10, 0))

        search_frame = tk.Frame(content_frame, bg="#F5F6F5")  # Soft White
        search_frame.pack(fill="x", pady=10)
        tk.Label(search_frame, text="Search by Transaction ID:", font=("Helvetica", 18),
                bg="#F5F6F5", fg="#2C3E50").pack(side="left")  # Soft White, Dark Slate
        self.search_entry = tk.Entry(search_frame, font=("Helvetica", 18), bg="#F4E1C1", fg="#2C3E50")  # Sandy Beige, Dark Slate
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<KeyRelease>", self.update_transactions_table)
        tk.Button(search_frame, text="Refresh Transactions", command=self.update_transactions_table,
                bg="#2ECC71", fg="#F5F6F5", font=("Helvetica", 18),  # Seafoam Green, Soft White
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

        style = ttk.Style()
        style.configure("Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5")  # Soft White, Dark Slate

        def configure_canvas(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        tree_frame.bind("<Configure>", configure_canvas)

        self.transactions_table.bind("<MouseWheel>", lambda event: self.treeview_scroll(event, canvas=canvas))
        self.transactions_table.bind("<Button-4>", lambda event: self.treeview_scroll(event, canvas=canvas))
        self.transactions_table.bind("<Button-5>", lambda event: self.treeview_scroll(event, canvas=canvas))

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
                                bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 18),  # Aqua Blue, Soft White
                                activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                padx=12, pady=8, bd=0, state="disabled")
        self.print_btn.pack(side="left", padx=5)
        self.edit_transaction_btn = tk.Button(self.transaction_button_frame, text="Edit Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Edit", "Enter admin password to edit transaction",
                                                self.validate_edit_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#4DA8DA", fg="#F5F6F5", font=("Helvetica", 18),  # Aqua Blue, Soft White
                                            activebackground="#2C3E50", activeforeground="#F5F6F5",  # Dark Slate, Soft White
                                            padx=12, pady=8, bd=0, state="disabled")
        self.edit_transaction_btn.pack(side="left", padx=5)
        self.delete_transaction_btn = tk.Button(self.transaction_button_frame, text="Delete Transaction",
                                            command=lambda: self.create_password_auth_window(
                                                "Authenticate Deletion", "Enter admin password to delete transaction",
                                                self.validate_delete_main_transaction_auth, selected_item=self.transactions_table.selection()),
                                            bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", 18),  # Coral Red, Soft White
                                            activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                            padx=12, pady=8, bd=0, state="disabled")
        self.delete_transaction_btn.pack(side="left", padx=5)
        self.refund_btn = tk.Button(self.transaction_button_frame, text="Refund",
                                    command=lambda: self.create_password_auth_window(
                                        "Authenticate Refund", "Enter admin password to process refund",
                                        self.validate_refund_auth, selected_item=self.transactions_table.selection()),
                                    bg="#E74C3C", fg="#F5F6F5", font=("Helvetica", 18),  # Coral Red, Soft White
                                    activebackground="#C0392B", activeforeground="#F5F6F5",  # Darker Coral Red, Soft White
                                    padx=12, pady=8, bd=0, state="disabled")
        self.refund_btn.pack(side="left", padx=5)

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def show_transactions_old(self):
        if self.user_role == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.root.destroy()
            return
        elif self.user_role == "Pharmacist":
            self.display_transactions()
        else:
            self.create_password_auth_window(
                "Authenticate Transaction Access",
                "Enter admin password to access transactions",
                self.validate_transaction_access_auth
            )

    def validate_transaction_access_auth(self, password: str, window: tk.Toplevel, **kwargs):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
                window.destroy()
                self.display_transactions()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def display_transactions(self):
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")
        main_frame.pack(fill="both", expand=True)

        content_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=self.scale_size(20), pady=self.scale_size(20))
        content_frame.pack(fill="both", expand=True, padx=(self.scale_size(10), 0))
        content_frame.grid_rowconfigure(1, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)

        tk.Label(content_frame, text="Transaction History", font=("Helvetica", 18, "bold"),
                 bg="#F5F6F5", fg="#2C3E50").grid(row=0, column=0, sticky="w", pady=self.scale_size(10))

        columns = ("ID", "Action", "Details", "Timestamp", "User")
        headers = ("ID", "ACTION", "DETAILS", "TIMESTAMP", "USER")
        self.transaction_table = ttk.Treeview(content_frame, columns=columns, show="headings", style="Treeview")
        for col, head in zip(columns, headers):
            self.transaction_table.heading(col, text=head)
            self.transaction_table.column(col, width=self.scale_size(200), anchor="center")
        self.transaction_table.grid(row=1, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.transaction_table.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.transaction_table.configure(yscrollcommand=scrollbar.set)

        style = ttk.Style()
        style.configure("Treeview", background="#F5F6F5", foreground="#2C3E50", fieldbackground="#F5F6F5")

        self.update_transaction_table()

    def update_transaction_table(self, event: Optional[tk.Event] = None):
        for item in self.transaction_table.get_children():
            self.transaction_table.delete(item)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT log_id, action, details, timestamp, user FROM transaction_log")
            for log_id, action, details, timestamp, user in cursor.fetchall():
                self.transaction_table.insert("", "end", iid=log_id, values=(log_id, action, details, timestamp, user or "System"))

    def update_transactions_table(self, event=None) -> None:
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
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
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
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
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
                        cursor.execute("SELECT name, retail_price, quantity FROM inventory WHERE item_id = ?", (item_id,))
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
                    bg="#6F4E37", fg="#FFF8E7", font=("Helvetica", 18),
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
                        qty_diff = new_qty - item["original_quantity"]
                        available_qty = item["inventory_quantity"] - qty_diff
                        if available_qty < 0:
                            messagebox.showerror("Error", f"Insufficient stock for {item['name']}. Available: {item['inventory_quantity']}", parent=self.root)
                            return
                        item["current_quantity"] = new_qty
                        total_amount += item["price"] * new_qty
                        if new_qty > 0:
                            new_items.append(f"{item['id']}:{new_qty}")
                        cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", (qty_diff, item["id"]))
                    except ValueError:
                        messagebox.showerror("Error", f"Invalid quantity for {item['name']}", parent=self.root)
                        return

                if not new_items:
                    messagebox.showerror("Error", "Transaction must have at least one item", parent=self.root)
                    return

                items_str = ";".join(new_items)

                # 🔹 Ask for new cash input since total changed
                new_cash_paid = simpledialog.askfloat(
                    "Update Cash", 
                    f"New total is {total_amount:.2f}. Enter new cash paid:", 
                    parent=self.root
                )

                if new_cash_paid is None:
                    return  # Cancel if user closes the dialog

                change_amount = new_cash_paid - total_amount if new_cash_paid >= total_amount else 0.0

                cursor.execute("""
                    UPDATE transactions SET items = ?, total_amount = ?, cash_paid = ?, change_amount = ? 
                    WHERE transaction_id = ?
                """, (items_str, total_amount, new_cash_paid, change_amount, transaction_id))

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

        c.drawString(100, 750, "Shinano POS")
        c.drawString(100, 732, "Gem's Pharmacy.")
        c.drawString(100, 678, "123 Pharmacy Drive, Health City Tel #555-0123")
        c.drawString(100, 650, f"Date: {timestamp}")
        c.drawString(100, 632, f"TRANSACTION CODE: {transaction_id}")

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

        if missing_items:
            messagebox.showwarning("Warning", f"Items not found in inventory: {', '.join(missing_items)}", parent=self.root)

        data.append(["Total", str(total_qty), f"{total_amount:.2f}"])

        table = Table(data)
        table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 12),
            ('FONT', (0, 1), (-1, -2), 'Helvetica', 12),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))

        table_width = 400
        table_x = (letter[0] - table_width) / 2
        table_y = 600
        table.wrapOn(c, table_width, 400)
        table.drawOn(c, table_x, table_y - len(data) * 20)

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

    def validate_refund_auth(self, password: str, window: tk.Toplevel, **kwargs):
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
                window.destroy()
                self.process_refund(transaction_id)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def process_refund(self, transaction_id: str):
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT items, status FROM transactions WHERE transaction_id = ?", (transaction_id,))
                transaction = cursor.fetchone()
                if not transaction:
                    messagebox.showerror("Error", "Transaction not found", parent=self.root)
                    return
                if transaction[1] == "Returned":
                    messagebox.showerror("Error", "Transaction already refunded", parent=self.root)
                    return

                items = transaction[0].split(";")
                for item_data in items:
                    if item_data:
                        try:
                            item_id, qty = item_data.split(":")
                            qty = int(qty)
                            cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE item_id = ?", (qty, item_id))
                        except ValueError:
                            continue

                cursor.execute("UPDATE transactions SET status = 'Returned' WHERE transaction_id = ?", (transaction_id,))
                cursor.execute("INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                              (f"{datetime.now().strftime('%m-%Y')}-{str(uuid.uuid4())[:6]}",
                               "Refund Transaction", f"Refunded transaction {transaction_id}",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                self.conn.commit()
                self.update_transactions_table()
                messagebox.showinfo("Success", f"Transaction {transaction_id} refunded successfully", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to process refund: {e}", parent=self.root)

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

