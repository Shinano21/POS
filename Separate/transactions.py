import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
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
import webbrowser
import ctypes
from ctypes import wintypes

class TransactionManager:
    def __init__(self, root, current_user, user_role):
        self.root = root
        self.root.title("Transaction Management")
        self.root.configure(bg="#F8F9FA")  # Bootstrap light background
        self.root.state('zoomed')  # Maximized window
        self.root.resizable(True, True)
        self.current_user = current_user
        self.user_role = user_role
        self.db_path = self.get_writable_db_path()
        self.conn = None  # Initialize connection lazily
        self.transaction_table = None
        self.search_entry = None
        self.print_btn = None
        self.edit_transaction_btn = None
        self.delete_transaction_btn = None
        self.refund_btn = None
        self.transaction_button_frame = None
        self.main_frame = tk.Frame(self.root, bg="#F8F9FA")
        self.main_frame.pack(fill="both", expand=True)
        self.show_transactions()
        self.enable_windows_controls()

        #Binding keys
        self.root.bind("<F1>", lambda e: self.print_receipt())
        self.root.bind("<F2>", lambda e: self.edit_transaction_btn.invoke())
        self.root.bind("<F3>", lambda e: self.delete_transaction_btn.invoke())
        self.root.bind("<F4>", lambda e: self.refund_btn.invoke())
        self.root.bind("<F5>", lambda e: self.update_transactions_table())
        self.root.bind("<F11>", self.toggle_maximize_restore)
        self.root.bind("<Escape>", lambda e: self.root.state('normal'))
        


    def enable_windows_controls(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
        style |= 0x00020000  # WS_MINIMIZEBOX
        style |= 0x00010000  # WS_MAXIMIZEBOX
        style |= 0x00080000  # WS_SYSMENU
        ctypes.windll.user32.SetWindowLongW(hwnd, -16, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

    def get_display_scaling(self) -> float:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            scaling_factor = dpi / 96.0
            supported_scales = [1.25, 1.5, 1.75, 2.0]
            scaling_factor = min(supported_scales, key=lambda x: abs(x - scaling_factor))
            return scaling_factor
        except:
            return 1.75  # Fallback to 175%

    def scale_size(self, size: int) -> int:
        scaling_factor = self.get_display_scaling()
        return int(size * scaling_factor)

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

    def create_password_auth_window(self, title: str, prompt: str, callback, **kwargs):
        window = tk.Toplevel(self.root)
        window.title(title)

        # Scale dimensions
        win_w, win_h = self.scale_size(500), self.scale_size(250)
        scr_w, scr_h = window.winfo_screenwidth(), window.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")
        window.configure(bg="#F8F9FA")

        # Larger fonts for accessibility
        font_label = ("Helvetica", max(self.scale_size(20), 20), "bold")
        font_entry = ("Helvetica", max(self.scale_size(20), 20))
        font_btn   = ("Helvetica", max(self.scale_size(20), 20), "bold")

        tk.Label(window, text=prompt, font=font_label, bg="#F8F9FA", fg="#212529").pack(pady=self.scale_size(15))
        password_entry = tk.Entry(window, show="*", font=font_entry, bg="#FFFFFF", fg="#212529")
        password_entry.pack(pady=self.scale_size(15), ipadx=10, ipady=8)

        def validate_and_submit(event=None):
            password = password_entry.get().strip()
            if not password:
                messagebox.showerror("Error", "Password is required", parent=window)
                return
            callback(password, window, **kwargs)

        password_entry.bind("<Return>", validate_and_submit)

        tk.Button(window, text="✓ Submit",
                command=validate_and_submit,
                bg="#007BFF", fg="#FFFFFF", font=font_btn,
                activebackground="#0056B3", activeforeground="#FFFFFF",
                relief="flat", padx=15, pady=8).pack(pady=self.scale_size(15))

        password_entry.focus_set()


    def get_user_role(self):
        return self.user_role

    def show_account_management(self):
        self.root.destroy()

    def setup_navigation(self, main_frame):
        nav_frame = tk.Frame(main_frame, bg="#343A40")  # Bootstrap dark navbar
        nav_frame.pack(fill="x")

    def toggle_maximize_restore(self, event=None):
        if self.root.state() == 'zoomed':
            self.root.state('normal')
        else:
            self.root.state('zoomed')

    def treeview_scroll(self, event, canvas):
        if event.delta > 0:
            canvas.yview_scroll(-1, "units")
        elif event.delta < 0:
            canvas.yview_scroll(1, "units")
        return "break"

    def check_low_inventory(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
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
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def style_config(self):
        style = ttk.Style()
        style.configure("Treeview", background="#FFFFFF", foreground="#212529",
                        rowheight=self.scale_size(30), font=("Helvetica", self.scale_size(16)))
        style.map("Treeview", background=[("selected", "#007BFF")], foreground=[("selected", "#FFFFFF")])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        style.configure("Treeview.Heading", font=("Helvetica", self.scale_size(16), "bold"), background="#E9ECEF", foreground="#212529")

    def show_transactions(self, event: Optional[tk.Event] = None) -> None:
        if self.user_role == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        elif self.user_role != "Manager":
            self.create_password_auth_window(
                "Authenticate Transaction Access",
                "Enter admin password to access transactions",
                self.validate_transaction_access_auth
            )
            return
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F8F9FA")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F8F9FA", padx=self.scale_size(20), pady=self.scale_size(20))
        content_frame.pack(fill="both", expand=True, padx=(self.scale_size(10), 0))

        search_frame = tk.Frame(content_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
        search_frame.pack(fill="x", pady=self.scale_size(10))
        tk.Label(search_frame, text="Search by Transaction ID:", font=("Helvetica", self.scale_size(18)),
                 bg="#FFFFFF", fg="#212529").pack(side="left", padx=self.scale_size(10))
        self.search_entry = tk.Entry(search_frame, font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529")
        self.search_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
        self.search_entry.bind("<KeyRelease>", self.update_transactions_table)
        tk.Button(search_frame, text="🔄", command=self.update_transactions_table,
                  bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                  activebackground="#0056B3", activeforeground="#FFFFFF",
                  relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack(side="left", padx=self.scale_size(5))

        transactions_frame = tk.Frame(content_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
        transactions_frame.pack(fill="both", expand=True, pady=self.scale_size(10))
        transactions_frame.grid_rowconfigure(1, weight=1)
        transactions_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(transactions_frame, bg="#FFFFFF")
        canvas.grid(row=1, column=0, sticky="nsew")

        v_scrollbar = ttk.Scrollbar(transactions_frame, orient="vertical", command=canvas.yview)
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        h_scrollbar = ttk.Scrollbar(transactions_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")

        canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        tree_frame = tk.Frame(canvas, bg="#FFFFFF")
        canvas_window = canvas.create_window((0, 0), window=tree_frame, anchor="nw")

        columns = ("TransactionID", "ItemsList", "TotalAmount", "CashPaid", "ChangeAmount", "Timestamp", "Status", "PaymentMethod", "CustomerID")
        headers = ("TRANSACTION ID", "ITEMS", "TOTAL AMOUNT", "CASH PAID", "CHANGE", "TIMESTAMP", "STATUS", "PAYMENT METHOD", "CUSTOMER ID")
        self.transactions_table = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20, style="Treeview")
        for col, head in zip(columns, headers):
            self.transactions_table.heading(col, text=head)
            width = self.scale_size(300) if col == "ItemsList" else self.scale_size(150)
            self.transactions_table.column(col, width=width, anchor="center" if col != "ItemsList" else "w")
        self.transactions_table.pack(fill="both", expand=True)

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

        self.transaction_button_frame = tk.Frame(transactions_frame, bg="#FFFFFF")
        self.transaction_button_frame.grid(row=3, column=0, columnspan=9, pady=self.scale_size(10))
        self.print_btn = tk.Button(self.transaction_button_frame, text="🖨", command=self.print_receipt,
                                   bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                                   activebackground="#218838", activeforeground="#FFFFFF",
                                   relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.print_btn.pack(side="left", padx=self.scale_size(5))
        self.edit_transaction_btn = tk.Button(self.transaction_button_frame, text="✏",
                                             command=lambda: self.create_password_auth_window(
                                                 "Authenticate Edit", "Enter admin password to edit transaction",
                                                 self.validate_edit_transaction_auth, selected_item=self.transactions_table.selection()),
                                             bg="#FFC107", fg="#212529", font=("Helvetica", self.scale_size(18), "bold"),
                                             activebackground="#E0A800", activeforeground="#212529",
                                             relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.edit_transaction_btn.pack(side="left", padx=self.scale_size(5))
        self.delete_transaction_btn = tk.Button(self.transaction_button_frame, text="🗑",
                                               command=lambda: self.create_password_auth_window(
                                                   "Authenticate Deletion", "Enter admin password to delete transaction",
                                                   self.validate_delete_main_transaction_auth, selected_item=self.transactions_table.selection()),
                                               bg="#DC3545", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                                               activebackground="#C82333", activeforeground="#FFFFFF",
                                               relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.delete_transaction_btn.pack(side="left", padx=self.scale_size(5))
        self.refund_btn = tk.Button(self.transaction_button_frame, text="🔄",
                                    command=lambda: self.create_password_auth_window(
                                        "Authenticate Refund", "Enter admin password to process refund",
                                        self.validate_refund_auth, selected_item=self.transactions_table.selection()),
                                    bg="#DC3545", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                                    activebackground="#C82333", activeforeground="#FFFFFF",
                                    relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.refund_btn.pack(side="left", padx=self.scale_size(5))

        self.style_config()

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def validate_transaction_access_auth(self, password: str, window: tk.Toplevel, **kwargs):
        try:
            self.conn = sqlite3.connect(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
                admin_passwords = [row[0] for row in cursor.fetchall()]
                if password in admin_passwords:
                    window.destroy()
                    self.show_transactions()
                else:
                    window.destroy()
                    messagebox.showerror("Error", "Invalid admin password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def update_transaction_table(self, event: Optional[tk.Event] = None):
        if not hasattr(self, 'transaction_table') or self.transaction_table is None:
            return
        for item in self.transaction_table.get_children():
            self.transaction_table.delete(item)
        try:
            self.conn = sqlite3.connect(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT log_id, action, details, timestamp, user FROM transaction_log")
                for log_id, action, details, timestamp, user in cursor.fetchall():
                    self.transaction_table.insert("", "end", iid=log_id, values=(log_id, action, details, timestamp, user or "System"))
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to fetch transaction logs: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

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
        
        try:
            self.conn = sqlite3.connect(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
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
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            messagebox.showerror("Database Error", f"Failed to fetch transactions: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

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
        try:
            self.conn = sqlite3.connect(self.db_path)
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
                admin_passwords = [row[0] for row in cursor.fetchall()]
                if password in admin_passwords:
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
                else:
                    window.destroy()
                    messagebox.showerror("Error", "Invalid admin password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to delete transaction: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def validate_edit_transaction_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        try:
            self.conn = sqlite3.connect(self.db_path)
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
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def validate_edit_transaction_fields(self, quantity_entries: Dict, parent: tk.Toplevel) -> bool:
        """Validate that quantity fields are non-negative integers and at least one item has quantity > 0."""
        has_non_zero_quantity = False
        for item_iid in quantity_entries:
            item = quantity_entries[item_iid]["item"]
            entry = quantity_entries[item_iid]["entry"]
            try:
                qty = int(entry.get().strip())
                if qty < 0:
                    messagebox.showerror("Error", f"Quantity for {item['name']} cannot be negative", parent=parent)
                    return False
                if qty > 0:
                    has_non_zero_quantity = True
            except ValueError:
                messagebox.showerror("Error", f"Invalid quantity for {item['name']}. Please enter a valid number", parent=parent)
                return False
        if not has_non_zero_quantity:
            messagebox.showerror("Error", "Transaction must have at least one item with quantity greater than zero", parent=parent)
            return False
        return True

    def show_edit_transaction(self, transaction_id: str) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
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
                window.geometry(f"{self.scale_size(600)}x{self.scale_size(400)}")
                window.configure(bg="#F8F9FA")

                content_frame = tk.Frame(window, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
                content_frame.pack(fill="both", expand=True, padx=self.scale_size(20), pady=self.scale_size(20))

                tk.Label(content_frame, text=f"Edit Transaction {transaction_id}", font=("Helvetica", self.scale_size(18), "bold"),
                         bg="#FFFFFF", fg="#212529").pack(pady=self.scale_size(10))

                columns = ("Item", "OriginalQuantity", "NewQuantity")
                headers = ("ITEM", "ORIGINAL QTY", "NEW QTY")
                edit_table = ttk.Treeview(content_frame, columns=columns, show="headings", style="Treeview")
                for col, head in zip(columns, headers):
                    edit_table.heading(col, text=head)
                    edit_table.column(col, width=self.scale_size(150) if col != "Item" else self.scale_size(200), anchor="center" if col != "Item" else "w")
                edit_table.pack(fill="both", expand=True)

                quantity_entries = {}
                vcmd_int = (self.root.register(lambda P: P.isdigit() or P == ""), "%P")

                def update_quantity_fields():
                    for item_iid in edit_table.get_children():
                        edit_table.delete(item_iid)
                    quantity_entries.clear()
                    for item in edit_items:
                        item_iid = edit_table.insert("", "end", values=(item["name"], item["original_quantity"], item["current_quantity"]))
                        frame = tk.Frame(content_frame, bg="#FFFFFF")
                        frame.pack(fill="x", pady=self.scale_size(2))
                        tk.Label(frame, text=item["name"], font=("Helvetica", self.scale_size(12)), bg="#FFFFFF", fg="#212529").pack(side="left")
                        entry = tk.Entry(frame, font=("Helvetica", self.scale_size(12)), bg="#FFFFFF", fg="#212529", width=10, validate="key", validatecommand=vcmd_int)
                        entry.insert(0, str(item["current_quantity"]))
                        entry.pack(side="left", padx=self.scale_size(5))
                        entry.bind("<Return>", lambda event: self.validate_edit_transaction_fields(quantity_entries, window) and self.process_edit_transaction(transaction_id, edit_items, quantity_entries, transaction[2], transaction[5], transaction[6], window))
                        quantity_entries[item_iid] = {"item": item, "entry": entry}
                        edit_table.item(item_iid, values=(item["name"], item["original_quantity"], item["current_quantity"]))
                        entry.focus_set()  # Set focus to the first entry

                update_quantity_fields()

                tk.Button(content_frame, text="✓ Confirm Changes",
                          command=lambda: self.validate_edit_transaction_fields(quantity_entries, window) and self.process_edit_transaction(transaction_id, edit_items, quantity_entries, transaction[2], transaction[5], transaction[6], window),
                          bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                          activebackground="#0056B3", activeforeground="#FFFFFF",
                          relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack(pady=self.scale_size(10))
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def process_edit_transaction(self, transaction_id: str, edit_items: List[Dict], quantity_entries: Dict, cash_paid: float, payment_method: str, customer_id: str, window: tk.Toplevel) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
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
                        available_qty = item["inventory_quantity"] + item["original_quantity"] - new_qty
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

                new_cash_paid = simpledialog.askfloat(
                    "Update Cash",
                    f"New total is {total_amount:.2f}. Enter new cash paid:",
                    parent=self.root
                )

                if new_cash_paid is None:
                    return

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
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

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

        try:
            self.conn = sqlite3.connect(self.db_path)
            c = canvas.Canvas(pdf_path, pagesize=letter)
            c.setFont("Helvetica", self.scale_size(12))

            c.drawString(self.scale_size(100), self.scale_size(750), "Shinano POS")
            c.drawString(self.scale_size(100), self.scale_size(732), "Gem's Pharmacy")
            c.drawString(self.scale_size(100), self.scale_size(678), "123 Pharmacy Drive, Health City Tel #555-0123")
            c.drawString(self.scale_size(100), self.scale_size(650), f"Date: {timestamp}")
            c.drawString(self.scale_size(100), self.scale_size(632), f"TRANSACTION CODE: {transaction_id}")

            data = [["Name", "Qty", "Price"]]
            total_qty = 0
            missing_items = []
            with self.conn:
                cursor = self.conn.cursor()
                for item in items:
                    if item:
                        name, qty = item.rsplit(" (x", 1) if " (x" in item else (item, "0")
                        qty = int(qty.strip(")")) if qty != "0" else 0
                        item_name = name.strip()
                        retail_price = 0.0
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

            table = Table(data, colWidths=[self.scale_size(200), self.scale_size(100), self.scale_size(100)])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#007BFF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), self.scale_size(12)),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#F8F9FA"), colors.HexColor("#E9ECEF")])
            ]))

            table_width = self.scale_size(400)
            table_x = (letter[0] - table_width) / 2
            table_y = self.scale_size(600)
            table.wrapOn(c, table_width, self.scale_size(400))
            table.drawOn(c, table_x, table_y - len(data) * self.scale_size(20))

            y = table_y - len(data) * self.scale_size(20) - self.scale_size(20)
            c.drawString(self.scale_size(100), y - self.scale_size(40), f"CASH: {cash_paid:.2f}")
            c.drawString(self.scale_size(100), y - self.scale_size(60), f"CHANGE: {change:.2f}")
            c.drawString(self.scale_size(100), y - self.scale_size(80), f"VAT SALE: {(total_amount * 0.12):.2f}")
            c.drawString(self.scale_size(100), y - self.scale_size(100), f"NON-VAT SALE: {(total_amount * 0.88):.2f}")

            c.showPage()
            c.save()
            try:
                webbrowser.open(f"file://{pdf_path}")
                messagebox.showinfo("Success", f"Opening receipt: {pdf_path}", parent=self.root)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open receipt: {e}", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def validate_refund_auth(self, password: str, window: tk.Toplevel, **kwargs):
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No transaction selected", parent=self.root)
            return
        transaction_id = self.transactions_table.item(selected_item)["values"][0]
        try:
            self.conn = sqlite3.connect(self.db_path)
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
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def process_refund(self, transaction_id: str):
        try:
            self.conn = sqlite3.connect(self.db_path)
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
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()