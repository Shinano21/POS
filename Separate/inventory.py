import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import csv
import uuid
import os
import shutil
from datetime import datetime
from typing import Optional
import ctypes
from ctypes import wintypes

class InventoryManager:
    def __init__(self, root, current_user, user_role, back_callback=None):
        self.root = root
        self.root.title("Inventory Management")
        self.root.configure(bg="#F8F9FA")  # Bootstrap light background
        self.root.state('zoomed')
        self.root.resizable(True, True)
        self.current_user = current_user
        self.user_role = user_role
        self.back_callback = back_callback
        self.db_path = self.get_writable_db_path()
        self.conn = sqlite3.connect(self.db_path)
        self.inventory_search_entry = None
        self.type_filter_var = None
        self.type_filter_combobox = None
        self.inventory_table = None
        self.update_item_btn = None
        self.delete_item_btn = None
        self.main_frame = tk.Frame(self.root, bg="#F8F9FA")
        self.main_frame.pack(fill="both", expand=True)
        self.show_inventory()
        self.enable_windows_controls()

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

    def enable_windows_controls_toplevel(self, window):
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
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
            return 1.75  # Fallback to 175% if detection fails

    def scale_size(self, size: int) -> int:
        scaling_factor = self.get_display_scaling()
        return int(size * scaling_factor)

    def setup_navigation(self, main_frame):
        nav_frame = tk.Frame(main_frame, bg="#343A40")  # Bootstrap dark navbar
        nav_frame.pack(fill="x")

    def toggle_maximize_restore(self, event=None):
        if self.root.state() == 'zoomed':
            self.root.state('normal')
        else:
            self.root.state('zoomed')

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA') or os.path.expanduser("~")
        db_dir = os.path.join(app_data, "ShinanoPOS")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, db_name)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir_db = os.path.join(app_dir, db_name)

        if os.path.exists(app_dir_db) and not os.path.exists(db_path):
            shutil.copy(app_dir_db, db_path)
        elif not os.path.exists(app_dir_db) and not os.path.exists(db_path):
            print(f"Database not found at {app_dir_db}. Creating new database at {db_path}")

        if os.path.exists(db_path):
            os.chmod(db_path, 0o666)
        return db_path

    def create_password_auth_window(self, title: str, prompt: str, callback, **kwargs):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(f"{self.scale_size(400)}x{self.scale_size(200)}")
        window.configure(bg="#F8F9FA")
        self.enable_windows_controls_toplevel(window)
        tk.Label(window, text=prompt, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529").pack(pady=self.scale_size(10))
        password_entry = tk.Entry(window, show="*", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529")
        password_entry.pack(pady=self.scale_size(10))
        
        def validate_and_submit(event=None):
            password = password_entry.get().strip()
            if not password:
                messagebox.showerror("Error", "Password is required", parent=window)
                return
            callback(password, window, **kwargs)

        password_entry.bind("<Return>", validate_and_submit)
        tk.Button(window, text="✓ Submit",
                 command=validate_and_submit,
                 bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                 activebackground="#0056B3", activeforeground="#FFFFFF",
                 relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack(pady=self.scale_size(10))
        password_entry.focus_set()

    def show_inventory(self):
        if self.user_role == "Drug Lord":
            self.create_password_auth_window(
                "Authenticate Inventory Access",
                "Enter admin password to access inventory",
                self.validate_inventory_access_auth
            )
        elif self.user_role == "Manager":
            self.display_inventory()
        else:
            messagebox.showerror("Access Denied", "Only Managers can access Inventory Management.", parent=self.root)
            self.root.destroy()

    def validate_inventory_access_auth(self, password: str, window: tk.Toplevel, **kwargs):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
                window.destroy()
                self.display_inventory()
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def display_inventory(self):
        self.clear_frame()
        main_frame = tk.Frame(self.main_frame, bg="#F8F9FA")
        main_frame.pack(fill="both", expand=True)
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
        content_frame.pack(fill="both", expand=True, padx=self.scale_size(20), pady=self.scale_size(20))
        content_frame.grid_rowconfigure(1, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)

        search_frame = tk.Frame(content_frame, bg="#FFFFFF")
        search_frame.grid(row=0, column=0, sticky="ew", pady=self.scale_size(10))

        tk.Label(search_frame, text="Search:", font=("Helvetica", self.scale_size(18)),
                bg="#FFFFFF", fg="#212529").pack(side="left")
        self.inventory_search_entry = tk.Entry(search_frame, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529")
        self.inventory_search_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
        self.inventory_search_entry.bind("<KeyRelease>", self.update_inventory_table)

        tk.Label(search_frame, text="Filter:", font=("Helvetica", self.scale_size(18)),
                bg="#FFFFFF", fg="#212529").pack(side="left", padx=(self.scale_size(6), self.scale_size(5)))
        self.type_filter_var = tk.StringVar()
        categories = self.get_item_types() + ["Other", "All"]
        self.type_filter_combobox = ttk.Combobox(search_frame, textvariable=self.type_filter_var,
                                                values=categories, state="readonly", font=("Helvetica", self.scale_size(18)))
        self.type_filter_combobox.pack(side="left", padx=self.scale_size(5))
        self.type_filter_combobox.set("All")
        self.type_filter_combobox.bind("<<ComboboxSelected>>", self.update_inventory_table)

        tk.Button(search_frame, text="✚",
                 command=self.show_add_item,
                 bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                 activebackground="#0056B3", activeforeground="#FFFFFF",
                 relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack(side="right", padx=self.scale_size(5))

        tk.Button(search_frame, text="📤",
                 command=self.upload_inventory_csv,
                 bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                 activebackground="#0056B3", activeforeground="#FFFFFF",
                 relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack(side="right", padx=self.scale_size(5))

        inventory_frame = tk.Frame(content_frame, bg="#FFFFFF")
        inventory_frame.grid(row=1, column=0, sticky="nsew", pady=self.scale_size(10))
        inventory_frame.grid_rowconfigure(0, weight=1)
        inventory_frame.grid_columnconfigure(0, weight=1)

        columns = ("Name", "Type", "RetailPrice", "Quantity", "Supplier")
        headers = ("NAME", "TYPE", "RETAIL PRICE", "QUANTITY", "SUPPLIER")
        self.inventory_table = ttk.Treeview(inventory_frame, columns=columns, show="headings", style="Treeview")
        for col, head in zip(columns, headers):
            self.inventory_table.heading(col, text=head)
            width = self.scale_size(200) if col == "Name" else self.scale_size(150) if col in ["Type", "Supplier"] else self.scale_size(120)
            self.inventory_table.column(col, width=width, anchor="center" if col != "Name" else "w", stretch=True)
        self.inventory_table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(inventory_frame, orient="vertical", command=self.inventory_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.inventory_table.configure(yscrollcommand=scrollbar.set)

        button_frame = tk.Frame(content_frame, bg="#FFFFFF")
        button_frame.grid(row=2, column=0, sticky="ew", pady=self.scale_size(10))

        self.update_item_btn = tk.Button(button_frame, text="📝",
                                        command=self.show_update_item_from_selection,
                                        bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                                        activebackground="#0056B3", activeforeground="#FFFFFF",
                                        relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.update_item_btn.grid(row=0, column=0, padx=self.scale_size(5), sticky="w")

        self.delete_item_btn = tk.Button(button_frame, text="🗑️",
                                        command=self.confirm_delete_item,
                                        bg="#DC3545", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                                        activebackground="#C82333", activeforeground="#FFFFFF",
                                        relief="flat", padx=self.scale_size(12), pady=self.scale_size(6), state="disabled")
        self.delete_item_btn.grid(row=0, column=1, padx=self.scale_size(5), sticky="w")

        if self.user_role == "Manager" and self.back_callback:
            tk.Button(button_frame, text="← Back",
                     command=self.back_to_manager_dashboard,
                     bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                     activebackground="#0056B3", activeforeground="#FFFFFF",
                     relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).grid(row=0, column=2, padx=self.scale_size(5), sticky="w")

        style = ttk.Style()
        style.configure("Treeview", background="#FFFFFF", foreground="#212529", fieldbackground="#FFFFFF",
                        rowheight=self.scale_size(30), font=("Helvetica", self.scale_size(14)))
        style.map("Treeview", background=[("selected", "#007BFF")], foreground=[("selected", "#FFFFFF")])
        style.configure("Treeview.Heading", font=("Helvetica", self.scale_size(14), "bold"), background="#E9ECEF", foreground="#212529")
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        style.configure("Treeview.low_stock", background="#DC3545", foreground="#FFFFFF")

        self.inventory_table.bind("<<TreeviewSelect>>", self.on_inventory_select)
        self.inventory_table.bind("<Button-3>", self.on_inventory_right_click)
        self.update_inventory_table()
        self.root.update_idletasks()

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def upload_inventory_csv(self):
        if not self.current_user:
            messagebox.showerror("Error", "You must be logged in to upload inventory", parent=self.root)
            return

        file_path = filedialog.askopenfilename(title="Select CSV File", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return

        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                expected_headers = ["BARCODE", "ITEM DESCRIPTION", "ON HAND", "SUPPLIER", "CATEGORY", "UNIT COST", "SELLING PRICE"]
                if not all(header in reader.fieldnames for header in expected_headers):
                    messagebox.showerror("Error", f"CSV file must contain headers: {', '.join(expected_headers)}", parent=self.root)
                    return

                with self.conn:
                    cursor = self.conn.cursor()
                    items_added = 0
                    items_skipped = 0
                    for row in reader:
                        try:
                            item_id = row["BARCODE"].strip()
                            name = row["ITEM DESCRIPTION"].strip()
                            quantity = int(row["ON HAND"].strip())
                            supplier = row["SUPPLIER"].strip()
                            item_type = row["CATEGORY"].strip()
                            unit_price = float(row["UNIT COST"].strip())
                            retail_price = float(row["SELLING PRICE"].strip())

                            if not item_id:
                                item_id = f"GEN-{uuid.uuid4().hex[:8].upper()}"
                            if not name:
                                continue
                            if quantity < 0 or unit_price < 0 or retail_price < 0:
                                messagebox.showwarning("Warning", f"Invalid data for item {name}: Negative values not allowed", parent=self.root)
                                continue

                            name = name.capitalize()
                            cursor.execute("SELECT COUNT(*) FROM inventory WHERE LOWER(name) = LOWER(?) AND type = ? AND supplier = ?", (name, item_type, supplier))
                            if cursor.fetchone()[0]:
                                items_skipped += 1
                                continue

                            cursor.execute("""
                                INSERT INTO inventory (item_id, name, type, retail_price, unit_price, quantity, supplier)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (item_id, name, item_type, retail_price, unit_price, quantity, supplier))
                            items_added += 1

                        except (ValueError, KeyError) as e:
                            messagebox.showwarning("Warning", f"Invalid data for item {row.get('ITEM DESCRIPTION', 'unknown')}: {e}", parent=self.root)
                            continue

                    cursor.execute("""
                        INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                        VALUES (?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), "Upload Inventory CSV",
                        f"Added {items_added} items, skipped {items_skipped} duplicates from CSV",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()

            self.update_inventory_table()
            self.refresh_type_comboboxes()
            messagebox.showinfo("Success", f"Inventory updated: {items_added} items added, {items_skipped} duplicates skipped", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process CSV file: {e}", parent=self.root)

    def confirm_delete_item(self):
        selected_item = self.inventory_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        item_name = self.inventory_table.item(selected_item[0])["values"][0]
        if messagebox.askyesno("Confirm Deletion",
                            f"Are you sure you want to delete '{item_name}'? This action cannot be undone.",
                            parent=self.root):
            self.create_password_auth_window(
                "Authenticate Deletion",
                "Enter admin password to delete item",
                self.validate_delete_item_auth,
                selected_item=selected_item[0]
            )

    def validate_delete_item_auth(self, password: str, window: tk.Toplevel, **kwargs):
        selected_item = kwargs.get("selected_item")
        if not selected_item:
            window.destroy()
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
            admin_passwords = [row[0] for row in cursor.fetchall()]
            if password in admin_passwords:
                cursor.execute("SELECT item_id, name FROM inventory WHERE item_id = ?", (selected_item,))
                item = cursor.fetchone()
                if item:
                    item_id, item_name = item
                    cursor.execute("DELETE FROM inventory WHERE item_id = ?", (item_id,))
                    cursor.execute("""
                        INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                        VALUES (?, ?, ?, ?, ?)
                    """, (str(uuid.uuid4()), "Delete Item", f"Deleted item {item_id}: {item_name}",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))
                    self.conn.commit()
                    self.update_inventory_table()
                    window.destroy()
                    messagebox.showinfo("Success", "Item deleted successfully", parent=self.root)
                else:
                    window.destroy()
                    messagebox.showerror("Error", f"Item with ID {selected_item} not found", parent=self.root)
            else:
                window.destroy()
                messagebox.showerror("Error", "Invalid admin password", parent=self.root)

    def update_markup(self, unit_price_entry: tk.Entry, retail_price_entry: tk.Entry, markup_label: tk.Label, profitability_label: tk.Label, error_label: tk.Label):
        try:
            unit_price = float(unit_price_entry.get() or 0)
            retail_price = float(retail_price_entry.get() or 0)
            if unit_price > 0:
                markup = ((retail_price - unit_price) / unit_price) * 100
                markup_label.config(text=f"{markup:.2f}%")
                profitability_label.config(
                    text="Profitable" if markup > 0 else "Break-even" if markup == 0 else "Not Profitable",
                    fg="#28A745" if markup > 0 else "#6C757D" if markup == 0 else "#DC3545"
                )
            else:
                markup_label.config(text="0.00%")
                profitability_label.config(text="N/A", fg="#212529")
            error_label.config(text="")
        except ValueError:
            markup_label.config(text="0.00%")
            profitability_label.config(text="N/A", fg="#212529")
            error_label.config(text="Enter valid prices", fg="#DC3545")

    def validate_required_fields(self, entries: dict, type_var: tk.StringVar, custom_type_entry: tk.Entry, parent: tk.Toplevel) -> bool:
        """Validate that required fields are filled and Type is valid."""
        required_fields = ["Name", "Retail Price"]
        for field in required_fields:
            if not entries[field].get().strip():
                messagebox.showerror("Error", f"{field} is required", parent=parent)
                return False
        if type_var.get() == "Other" and not custom_type_entry.get().strip():
            messagebox.showerror("Error", "Please enter a custom type when 'Other' is selected", parent=parent)
            return False
        return True

    def show_add_item(self):
        window = tk.Toplevel(self.root)
        window.title("Add New Item to Inventory")
        window.geometry(f"{self.scale_size(800)}x{self.scale_size(520)}")
        window.configure(bg="#F8F9FA")
        self.enable_windows_controls_toplevel(window)

        add_box = tk.Frame(window, bg="#FFFFFF", padx=self.scale_size(20), pady=self.scale_size(20), relief="raised", highlightbackground="#DEE2E6", highlightthickness=1)
        add_box.pack(pady=self.scale_size(20), padx=self.scale_size(20), fill="both", expand=True)

        tk.Label(add_box, text="Add New Item to Inventory", font=("Helvetica", self.scale_size(18), "bold"),
                bg="#FFFFFF", fg="#212529").grid(row=0, column=0, columnspan=4, pady=self.scale_size(15))

        fields = ["Item ID (Barcode)", "Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
        entries = {}

        vcmd_float = (self.root.register(lambda P: P == "" or P.replace(".", "", 1).isdigit()), "%P")
        vcmd_int = (self.root.register(lambda P: P.isdigit() or P == ""), "%P")

        for i, field in enumerate(fields):
            row = (i // 2) + 1
            col = (i % 2) * 2
            frame = tk.Frame(add_box, bg="#FFFFFF")
            frame.grid(row=row, column=col, columnspan=2, sticky="ew", pady=self.scale_size(5))
            tk.Label(frame, text=field, font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
            entry = tk.Entry(frame, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529")
            entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
            entries[field] = entry
            if field in ["Unit Price", "Retail Price"]:
                entry.config(validate="key", validatecommand=vcmd_float)
            elif field == "Quantity":
                entry.config(validate="key", validatecommand=vcmd_int)
            if field == "Item ID (Barcode)":
                entry.insert(0, f"ITEM-{str(uuid.uuid4())[:8]}")
                entry.config(state="readonly")
            else:
                # Bind Enter key to validate and submit
                entry.bind("<Return>", lambda event: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.add_item(
                    entries["Item ID (Barcode)"].get(), entries["Name"].get(),
                    custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
                    entries["Retail Price"].get(), entries["Unit Price"].get(),
                    entries["Quantity"].get(), entries["Supplier"].get(), window
                ))

        next_row = (len(fields) + 1) // 2 + 1

        type_frame = tk.Frame(add_box, bg="#FFFFFF")
        type_frame.grid(row=next_row, column=0, columnspan=4, sticky="ew", pady=self.scale_size(5))
        tk.Label(type_frame, text="Type", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
        categories = self.get_item_types() + ["Other"]
        type_var = tk.StringVar(value=categories[0] if categories else "Other")
        type_combobox = ttk.Combobox(type_frame, textvariable=type_var, values=categories, state="readonly", font=("Helvetica", self.scale_size(18)))
        type_combobox.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

        custom_type_entry = tk.Entry(type_frame, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529")
        custom_type_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
        custom_type_entry.pack_forget()
        # Bind Enter key to validate and submit
        custom_type_entry.bind("<Return>", lambda event: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.add_item(
            entries["Item ID (Barcode)"].get(), entries["Name"].get(),
            custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
            entries["Retail Price"].get(), entries["Unit Price"].get(),
            entries["Quantity"].get(), entries["Supplier"].get(), window
        ))

        def on_type_change(event):
            if type_var.get() == "Other":
                custom_type_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
                custom_type_entry.delete(0, tk.END)
            else:
                custom_type_entry.pack_forget()

        type_combobox.bind("<<ComboboxSelected>>", on_type_change)

        markup_frame = tk.Frame(add_box, bg="#FFFFFF")
        markup_frame.grid(row=next_row + 1, column=0, columnspan=2, sticky="ew", pady=self.scale_size(5))
        tk.Label(markup_frame, text="Markup %", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
        markup_label = tk.Label(markup_frame, text="0.00%", font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529", width=10, anchor="w")
        markup_label.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

        profitability_frame = tk.Frame(add_box, bg="#FFFFFF")
        profitability_frame.grid(row=next_row + 1, column=2, columnspan=2, sticky="ew", pady=self.scale_size(5))
        tk.Label(profitability_frame, text="Profitability", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
        profitability_label = tk.Label(profitability_frame, text="N/A", font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529", width=15, anchor="w")
        profitability_label.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

        price_error_label = tk.Label(add_box, text="", font=("Helvetica", self.scale_size(12)), bg="#FFFFFF", fg="#DC3545")
        price_error_label.grid(row=next_row + 2, column=0, columnspan=4, pady=self.scale_size(5))

        def validate_and_update(event: Optional[tk.Event] = None):
            try:
                retail_price = float(entries["Retail Price"].get()) if entries["Retail Price"].get().strip() else 0.0
                unit_price = float(entries["Unit Price"].get()) if entries["Unit Price"].get().strip() else 0.0
                if retail_price <= unit_price and retail_price != 0.0:
                    price_error_label.config(text="Retail Price must be greater than Unit Price", fg="#DC3545")
                else:
                    price_error_label.config(text="")
            except ValueError:
                price_error_label.config(text="Invalid price format", fg="#DC3545")
            self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

        entries["Retail Price"].bind("<KeyRelease>", validate_and_update)
        entries["Unit Price"].bind("<KeyRelease>", validate_and_update)
        self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

        button_frame = tk.Frame(add_box, bg="#FFFFFF")
        button_frame.grid(row=next_row + 3, column=0, columnspan=4, pady=self.scale_size(15))

        tk.Button(button_frame, text="✓ Submit",
                 command=lambda: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.add_item(
                    entries["Item ID (Barcode)"].get(), entries["Name"].get(),
                    custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
                    entries["Retail Price"].get(), entries["Unit Price"].get(),
                    entries["Quantity"].get(), entries["Supplier"].get(), window
                 ),
                 bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                 activebackground="#218838", activeforeground="#FFFFFF",
                 relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack()

        add_box.columnconfigure(0, weight=1)
        add_box.columnconfigure(2, weight=1)

    def add_item(self, item_id: str, name: str, item_type: str, retail_price: str, unit_price: str, quantity: str, supplier: str, window: tk.Toplevel):
        try:
            retail_price = float(retail_price) if retail_price.strip() else 0.0
            unit_price = float(unit_price) if retail_price.strip() else 0.0
            quantity = int(quantity) if quantity.strip() else 0

            if not name or retail_price <= 0:
                messagebox.showerror("Error", "Name and Retail Price are required", parent=self.root)
                return
            if item_type == "Other":
                messagebox.showerror("Error", "Please enter a custom type when 'Other' is selected", parent=self.root)
                return
            if unit_price < 0 or quantity < 0:
                messagebox.showerror("Error", "Unit Price and Quantity cannot be negative", parent=self.root)
                return

            name = name.capitalize()
            item_type = item_type.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else str(uuid.uuid4())

            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT item_id FROM inventory WHERE name = ? AND retail_price = ? AND supplier = ?", (name, retail_price, supplier))
                if cursor.fetchone():
                    messagebox.showerror("Error", f"Item '{name}' with same price and supplier already exists.", parent=self.root)
                    return

                cursor.execute("""
                    INSERT INTO inventory (item_id, name, type, retail_price, unit_price, quantity, supplier)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (item_id, name, item_type, retail_price, unit_price, quantity, supplier))

                cursor.execute("""
                    INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), "Add Item",
                    f"Added item {item_id}: {name}, {quantity} units, Supplier: {supplier}, Type: {item_type}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))

                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", "Item added successfully", parent=self.root)

                if quantity <= 5:
                    self.check_low_inventory()

                self.refresh_type_comboboxes()

        except ValueError:
            messagebox.showerror("Error", "Invalid retail price, unit price, or quantity", parent=self.root)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists", parent=self.root)

    def on_inventory_right_click(self, event: tk.Event):
        selected = self.inventory_table.selection()
        if len(selected) == 1:
            self.show_update_item_from_selection()
        else:
            messagebox.showinfo("Selection Error", "Please select exactly one item to update.", parent=self.root)

    def show_update_item_from_selection(self):
        selected_item = self.inventory_table.selection()
        if not selected_item:
            messagebox.showerror("Error", "No item selected", parent=self.root)
            return
        item_id = selected_item[0]
        self.show_update_item(item_id)

    def show_update_item(self, item_id: str):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id, name, type, retail_price, unit_price, quantity, supplier FROM inventory WHERE item_id = ?", (item_id,))
            item = cursor.fetchone()
            if item:
                window = tk.Toplevel(self.root)
                window.title("Update Item")
                window.geometry(f"{self.scale_size(800)}x{self.scale_size(520)}")
                window.configure(bg="#F8F9FA")
                self.enable_windows_controls_toplevel(window)

                update_box = tk.Frame(window, bg="#FFFFFF", padx=self.scale_size(20), pady=self.scale_size(20), relief="raised", highlightbackground="#DEE2E6", highlightthickness=1)
                update_box.pack(pady=self.scale_size(20), padx=self.scale_size(20), fill="both", expand=True)

                tk.Label(update_box, text="Update Item in Inventory", font=("Helvetica", self.scale_size(18), "bold"),
                        bg="#FFFFFF", fg="#212529").grid(row=0, column=0, columnspan=4, pady=self.scale_size(15))

                fields = ["Item ID (Barcode)", "Name", "Unit Price", "Retail Price", "Quantity", "Supplier"]
                entries = {}
                field_indices = {"Item ID (Barcode)": 0, "Name": 1, "Unit Price": 4, "Retail Price": 3, "Quantity": 5, "Supplier": 6}
                for i, field in enumerate(fields):
                    row = (i // 2) + 1
                    col = (i % 2) * 2
                    frame = tk.Frame(update_box, bg="#FFFFFF")
                    frame.grid(row=row, column=col, columnspan=2, sticky="ew", pady=self.scale_size(5))
                    tk.Label(frame, text=field, font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
                    entry = tk.Entry(frame, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529")
                    entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
                    entries[field] = entry
                    value = item[field_indices[field]] if field_indices[field] < len(item) and item[field_indices[field]] is not None else ""
                    entry.insert(0, str(value))
                    if field != "Item ID (Barcode)":  # Skip readonly field
                        # Bind Enter key to validate and submit
                        entry.bind("<Return>", lambda event: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.update_item(
                            entries["Item ID (Barcode)"].get(), entries["Name"].get(),
                            custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
                            entries["Retail Price"].get(), entries["Unit Price"].get(),
                            entries["Quantity"].get(), entries["Supplier"].get(), item[0], window
                        ))

                next_row = (len(fields) + 1) // 2 + 1

                type_frame = tk.Frame(update_box, bg="#FFFFFF")
                type_frame.grid(row=next_row, column=0, columnspan=4, sticky="ew", pady=self.scale_size(5))
                tk.Label(type_frame, text="Type", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
                categories = self.get_item_types() + ["Other"]
                type_var = tk.StringVar(value=item[2] if item[2] in self.get_item_types() else "Other")
                type_combobox = ttk.Combobox(type_frame, textvariable=type_var, values=categories, state="readonly", font=("Helvetica", self.scale_size(18)))
                type_combobox.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

                custom_type_entry = tk.Entry(type_frame, font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529")
                custom_type_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
                if type_var.get() != "Other":
                    custom_type_entry.pack_forget()
                else:
                    custom_type_entry.delete(0, tk.END)
                    custom_type_entry.insert(0, item[2] if item[2] else "")
                # Bind Enter key to validate and submit
                custom_type_entry.bind("<Return>", lambda event: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.update_item(
                    entries["Item ID (Barcode)"].get(), entries["Name"].get(),
                    custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
                    entries["Retail Price"].get(), entries["Unit Price"].get(),
                    entries["Quantity"].get(), entries["Supplier"].get(), item[0], window
                ))

                def on_type_change(event):
                    if type_var.get() == "Other":
                        custom_type_entry.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))
                        custom_type_entry.delete(0, tk.END)
                        if item[2] and item[2] not in self.get_item_types():
                            custom_type_entry.insert(0, item[2])
                    else:
                        custom_type_entry.pack_forget()

                type_combobox.bind("<<ComboboxSelected>>", on_type_change)

                markup_frame = tk.Frame(update_box, bg="#FFFFFF")
                markup_frame.grid(row=next_row + 1, column=0, columnspan=2, sticky="ew", pady=self.scale_size(5))
                tk.Label(markup_frame, text="Markup %", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
                markup_label = tk.Label(markup_frame, text="0.00%", font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529", width=10, anchor="w")
                markup_label.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

                profitability_frame = tk.Frame(update_box, bg="#FFFFFF")
                profitability_frame.grid(row=next_row + 1, column=2, columnspan=2, sticky="ew", pady=self.scale_size(5))
                tk.Label(profitability_frame, text="Profitability", font=("Helvetica", self.scale_size(18)), bg="#FFFFFF", fg="#212529").pack(side="left")
                profitability_label = tk.Label(profitability_frame, text="N/A", font=("Helvetica", self.scale_size(18)), bg="#F8F9FA", fg="#212529", width=15, anchor="w")
                profitability_label.pack(side="left", fill="x", expand=True, padx=self.scale_size(5))

                price_error_label = tk.Label(update_box, text="", font=("Helvetica", self.scale_size(12)), bg="#FFFFFF", fg="#DC3545")
                price_error_label.grid(row=next_row + 2, column=0, columnspan=4, pady=self.scale_size(5))

                def validate_and_update(event: Optional[tk.Event] = None):
                    try:
                        retail_price = float(entries["Retail Price"].get()) if entries["Retail Price"].get().strip() else 0.0
                        unit_price = float(entries["Unit Price"].get()) if entries["Unit Price"].get().strip() else 0.0
                        if retail_price <= unit_price and retail_price != 0.0:
                            price_error_label.config(text="Retail Price must be greater than Unit Price", fg="#DC3545")
                        else:
                            price_error_label.config(text="")
                    except ValueError:
                        price_error_label.config(text="Invalid price format", fg="#DC3545")
                    self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

                entries["Retail Price"].bind("<KeyRelease>", validate_and_update)
                entries["Unit Price"].bind("<KeyRelease>", validate_and_update)
                self.update_markup(entries["Unit Price"], entries["Retail Price"], markup_label, profitability_label, price_error_label)

                button_frame = tk.Frame(update_box, bg="#FFFFFF")
                button_frame.grid(row=next_row + 3, column=0, columnspan=4, pady=self.scale_size(15))

                tk.Button(button_frame, text="✏ Update Item",
                         command=lambda: self.validate_required_fields(entries, type_var, custom_type_entry, window) and self.update_item(
                            entries["Item ID (Barcode)"].get(), entries["Name"].get(),
                            custom_type_entry.get().strip().capitalize() if type_var.get() == "Other" else type_var.get(),
                            entries["Retail Price"].get(), entries["Unit Price"].get(),
                            entries["Quantity"].get(), entries["Supplier"].get(), item[0], window
                         ),
                         bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                         activebackground="#218838", activeforeground="#FFFFFF",
                         relief="flat", padx=self.scale_size(12), pady=self.scale_size(6)).pack()

                update_box.columnconfigure(0, weight=1)
                update_box.columnconfigure(2, weight=1)
            else:
                messagebox.showerror("Error", f"Item with ID {item_id} not found", parent=self.root)

    def update_item(self, item_id: str, name: str, item_type: str, retail_price: str, unit_price: str, quantity: str, supplier: str, original_item_id: str, window: tk.Toplevel):
        try:
            retail_price = float(retail_price) if retail_price.strip() else 0.0
            unit_price = float(unit_price) if unit_price.strip() else 0.0
            quantity = int(quantity) if quantity.strip() else 0

            if not name or retail_price <= 0:
                messagebox.showerror("Error", "Name and Retail Price are required", parent=self.root)
                return
            if item_type == "Other":
                messagebox.showerror("Error", "Please enter a custom type when 'Other' is selected", parent=self.root)
                return
            if unit_price < 0 or quantity < 0:
                messagebox.showerror("Error", "Unit Price and Quantity cannot be negative", parent=self.root)
                return

            name = name.capitalize()
            item_type = item_type.capitalize()
            supplier = supplier.strip() if supplier.strip() else "Unknown"
            item_id = item_id.strip() if item_id.strip() else original_item_id

            with self.conn:
                cursor = self.conn.cursor()
                if item_id != original_item_id:
                    cursor.execute("SELECT item_id FROM inventory WHERE item_id = ?", (item_id,))
                    if cursor.fetchone():
                        messagebox.showerror("Error", "Item ID already exists", parent=self.root)
                        return

                cursor.execute("SELECT item_id FROM inventory WHERE name = ? AND retail_price = ? AND supplier = ? AND item_id != ?",
                            (name, retail_price, supplier, original_item_id))
                if cursor.fetchone():
                    messagebox.showerror("Error", "Another item with the same name, price, and supplier already exists.", parent=self.root)
                    return

                cursor.execute("""
                    UPDATE inventory
                    SET item_id = ?, name = ?, type = ?, retail_price = ?, unit_price = ?, quantity = ?, supplier = ?
                    WHERE item_id = ?
                """, (item_id, name, item_type, retail_price, unit_price, quantity, supplier, original_item_id))

                cursor.execute("""
                    INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), "Update Item",
                    f"Updated item {item_id}: {name}, {quantity} units, Retail Price: {retail_price:.2f}, Supplier: {supplier}, Type: {item_type}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.current_user))

                self.conn.commit()
                self.update_inventory_table()
                window.destroy()
                messagebox.showinfo("Success", f"Item '{name}' updated successfully", parent=self.root)

                if quantity <= 5:
                    self.check_low_inventory()

                self.refresh_type_comboboxes()

        except ValueError:
            messagebox.showerror("Error", "Invalid retail price, unit_price, or quantity", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)

    def on_inventory_select(self, event: Optional[tk.Event] = None):
        selected = self.inventory_table.selection()
        state = "normal" if selected else "disabled"
        if self.update_item_btn and self.delete_item_btn:  # Ensure buttons exist
            self.update_item_btn.config(state=state)
            self.delete_item_btn.config(state=state)

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

    def update_inventory_table(self, event: Optional[tk.Event] = None):
        for item in self.inventory_table.get_children():
            self.inventory_table.delete(item)
        self.inventory_table.tag_configure('low_stock', background='#DC3545', foreground='#FFFFFF')
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
            if type_filter not in ["All", "Other"]:
                conditions.append("type = ?")
                params.append(type_filter)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            cursor.execute(sql, params)
            for item in cursor.fetchall():
                item_id, name, item_type, retail_price, quantity, supplier = item
                quantity = int(float(quantity)) if quantity is not None else 0
                tags = ('low_stock',) if quantity <= 5 else ()
                self.inventory_table.insert("", "end", iid=item_id, values=(
                    name, item_type, f"{retail_price:.2f}", quantity, supplier or "Unknown"
                ), tags=tags)

    def get_item_types(self):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT type FROM inventory WHERE type IS NOT NULL")
            types = sorted([row[0] for row in cursor.fetchall() if row[0]])
        return types

    def refresh_type_comboboxes(self):
        types = self.get_item_types()
        def update_comboboxes(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Combobox) and child.cget("state") == "readonly":
                    child.configure(values=types)
                update_comboboxes(child)
        update_comboboxes(self.root)

    def back_to_manager_dashboard(self):
        if self.back_callback:
            self.root.destroy()
            new_root = tk.Tk()
            self.back_callback(new_root, self.current_user, self.user_role)

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()