import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict
import sqlite3
import os
import logging
import uuid
import datetime
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

logging.basicConfig(level=logging.DEBUG)

class Dashboard:
    def __init__(self, root: tk.Tk, current_user: str, user_role: str):
        self.root = root
        self.current_user = current_user
        self.user_role = user_role
        self.root.title("Shinano POS")
        self.root.configure(bg="#F8F9FA")  # Bootstrap light background
        self.root.state('zoomed')  # Set window to maximized (windowed full-screen)
        self.root.resizable(True, True)  # Ensure window is resizable
        self.scaling_factor = self.get_scaling_factor()

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

        self.cart: List[Dict] = []
        self.selected_item_index: Optional[int] = None
        self.sidebar_visible: bool = True
        self.suggestion_window: Optional[tk.Toplevel] = None
        self.suggestion_listbox: Optional[tk.Listbox] = None
        self.customer_table: Optional[ttk.Treeview] = None
        self.discount_var = tk.BooleanVar(value=False)
        self.discount_authenticated = False
        self.main_frame = tk.Frame(self.root, bg="#FFFFFF", highlightthickness=1, highlightbackground="#DEE2E6")

        self.style_config()
        
        self.initialize_inventory_with_receipt()
        self.setup_gui()
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", lambda e: self.root.state('normal'))  # Exit maximized state
        self.root.bind("<F1>", self.edit_quantity_window)
        self.root.bind("<F2>", self.void_selected_items)
        self.root.bind("<F3>", self.void_order)
        self.root.bind("<F4>", self.mode_of_payment)
        self.root.bind("<F5>", self.select_customer)
        self.root.bind("<F6>", self.apply_discount)
        self.root.bind("<F12>", self.open_login_window)
        self.root.bind("<Shift_R>", self.focus_cash_paid)
        self.root.bind("<Shift-Return>", self.process_checkout)

    def get_scaling_factor(self) -> float:
        default_dpi = 96
        current_dpi = self.root.winfo_fpixels('1i')
        scaling_factor = current_dpi / default_dpi
        if scaling_factor >= 1.75:
            return scaling_factor
        return 1.0
    
    def open_login_window(self, event=None):
        """Temporarily disable User Dashboard and open login for Manager re-login."""
        from login import LoginApp
        from manager import ManagerDashboard

        # Disable the current User Dashboard while login is active
        self.root.attributes("-disabled", True)

        # Create the login popup
        login_window = tk.Toplevel(self.root)
        login_window.title("Re-Login")
        login_window.geometry("500x400")
        LoginApp(login_window)

        # --- Called by LoginApp when Manager successfully logs in ---
        def on_manager_login(username, role, db_path):
            login_window.destroy()
            # Open ManagerDashboard as a new top-level window
            manager_window = tk.Toplevel(self.root)
            ManagerDashboard(manager_window, username, role, db_path)

            # When Manager closes the window, re-enable the User Dashboard
            def on_manager_close():
                try:
                    self.root.attributes("-disabled", False)
                except Exception as e:
                    print("Re-enable failed:", e)
                manager_window.destroy()
                print("✅ User Dashboard re-enabled after Manager closed.")

            manager_window.protocol("WM_DELETE_WINDOW", on_manager_close)

        # Attach callback so LoginApp can call it
        login_window.on_manager_login = on_manager_login

        # If login window is closed without logging in, re-enable dashboard
        def on_close_login():
            self.root.attributes("-disabled", False)
            login_window.destroy()
            print("⚙️ Login window closed — Dashboard re-enabled.")

        login_window.protocol("WM_DELETE_WINDOW", on_close_login)
        login_window.grab_set()






    def scale_size(self, size: int) -> int:
        return int(size * self.scaling_factor)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, db_name)

    def style_config(self):
        style = ttk.Style()
        style.configure("Cart.Treeview", background="#FFFFFF", foreground="#343A40",
                        rowheight=self.scale_size(32), font=("Helvetica", self.scale_size(16)))
        style.map("Cart.Treeview", background=[("selected", "#007BFF")], foreground=[("selected", "#FFFFFF")])
        style.layout("Cart.Treeview", [('Cart.Treeview.treearea', {'sticky': 'nswe'})])
        style.configure("Cart.Treeview.Heading", font=("Helvetica", self.scale_size(16), "bold"), background="#E9ECEF", foreground="#343A40")

    

    def initialize_inventory_with_receipt(self):
        pass

    def get_user_role(self):
        return self.user_role

    def toggle_fullscreen(self, event=None):
        if self.root.state() == 'zoomed':
            self.root.state('normal')
        else:
            self.root.state('zoomed')

#------------------Void Fucntion------------------------

    def void_selected_items(self, event=None):
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected or cart is empty", parent=self.root)
            return
        item = self.cart[self.selected_item_index]
        if messagebox.askyesno("Confirm Void",
                              f"Are you sure you want to void {item['name']} from the cart?",
                              parent=self.root):
            self.cart.pop(self.selected_item_index)
            self.update_cart_table()
            self.selected_item_index = None
            messagebox.showinfo("Success", "Item voided successfully", parent=self.root)

    def void_order(self, event=None):
        if not self.cart:
            messagebox.showerror("Error", "Cart is empty", parent=self.root)
            return
        if messagebox.askyesno("Confirm Void Order",
                              "Are you sure you want to void the entire order?",
                              parent=self.root):
            self.cart.clear()
            self.selected_item_index = None
            self.update_cart_table()
            messagebox.showinfo("Success", "Order voided successfully", parent=self.root)

    def setup_gui(self):
        self.show_dashboard()


     # ---------------------------
    #  DISCOUNT SYSTEM (F6)
    # ---------------------------
    def apply_discount(self, event=None):
        """Authenticate admin, then apply 20% discount to selected item."""
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected.", parent=self.root)
            return

        # Require password authentication
        self.create_password_auth_window(
            "Authenticate Discount",
            "Enter admin password to apply discount:",
            self.validate_discount_auth
        )

    def validate_discount_auth(self, password: str, window: tk.Toplevel):
        """Check if password belongs to admin, then apply discount."""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
                valid_passwords = [row[0] for row in cursor.fetchall()]
                if password in valid_passwords:
                    window.destroy()
                    self.discount_authenticated = True
                    self.apply_20_percent_discount()
                else:
                    window.destroy()
                    messagebox.showerror("Access Denied", "Invalid admin password.", parent=self.root)
        except sqlite3.Error as e:
            window.destroy()
            messagebox.showerror("Database Error", str(e), parent=self.root)

    def apply_20_percent_discount(self):
        if not self.discount_authenticated:
            messagebox.showerror("Error", "Discount not authenticated.", parent=self.root)
            return

        item = self.cart[self.selected_item_index]
        if item.get("discount_applied", False):
            messagebox.showinfo("Info", "Discount already applied to this item.", parent=self.root)
            return

        item["original_price"] = item["retail_price"]  # ✅ Keep original
        discounted_price = round(item["retail_price"] * 0.8, 2)
        item["discounted_price"] = discounted_price
        item["discount_applied"] = True
        item["discount_note"] = f"20% off (₱{item['retail_price'] - discounted_price:.2f})"
        item["subtotal"] = discounted_price * item["quantity"]

        self.discount_authenticated = False
        self.update_cart_table()
        messagebox.showinfo("Success", "20% discount applied.", parent=self.root)


     # ---------------------------
    #  PAYMENT MODE (F4)
    # ---------------------------
    def mode_of_payment(self, event=None):
        """Select the mode of payment using dropdowns."""
        import tkinter as tk
        from tkinter import ttk

        payment_window = tk.Toplevel(self.root)
        payment_window.title("Select Payment Method")
        payment_window.geometry("350x200")
        payment_window.transient(self.root)
        payment_window.grab_set()
        payment_window.configure(bg="#F8F9FA")

        tk.Label(payment_window, text="Payment Method:", font=("Helvetica", 12, "bold"), bg="#F8F9FA").pack(pady=10)
        payment_var = tk.StringVar(value="Cash")
        payment_dropdown = ttk.Combobox(
            payment_window,
            textvariable=payment_var,
            values=["Cash", "Credit", "Debit", "E-Wallet"],
            state="readonly",
            width=20,
            justify="center",
        )
        payment_dropdown.pack(pady=5)

        # --- E-Wallet Type Dropdown ---
        ewallet_var = tk.StringVar(value="")
        ewallet_dropdown = ttk.Combobox(
            payment_window,
            textvariable=ewallet_var,
            values=["GCash", "Maya", "PayMaya", "ShopeePay", "GrabPay"],
            state="readonly",
            width=20,
            justify="center",
        )
        ewallet_dropdown.pack(pady=5)
        ewallet_dropdown.pack_forget()  # hidden unless E-Wallet chosen

        def on_payment_change(event=None):
            if payment_var.get() == "E-Wallet":
                ewallet_dropdown.pack(pady=5)
            else:
                ewallet_dropdown.pack_forget()

        payment_dropdown.bind("<<ComboboxSelected>>", on_payment_change)

        def confirm_selection():
            selected_method = payment_var.get()
            if selected_method == "E-Wallet":
                wallet_type = ewallet_var.get()
                if not wallet_type:
                    tk.messagebox.showwarning("Missing Info", "Please select an E-Wallet type.", parent=payment_window)
                    return
                self.current_payment_method = f"E-Wallet ({wallet_type})"
            else:
                self.current_payment_method = selected_method

            tk.messagebox.showinfo("Payment Mode", f"✅ {self.current_payment_method} mode selected.", parent=self.root)
            payment_window.destroy()

        confirm_btn = tk.Button(
            payment_window,
            text="Confirm",
            command=confirm_selection,
            bg="#4DA8DA",
            fg="white",
            font=("Helvetica", 12, "bold"),
            relief="flat",
            cursor="hand2",
        )
        confirm_btn.pack(pady=15)

        payment_window.bind("<Return>", lambda e: confirm_selection())



    # ---------------------------
    #  CUSTOMER NAME (F5)
    # ---------------------------
    def select_customer(self, event=None):
        """Popup for entering customer name."""
        win = tk.Toplevel(self.root)
        win.title("Enter Customer Name")
        win.geometry("300x180")
        win.configure(bg="#FFFFFF")
        tk.Label(win, text="Customer Name:", bg="#FFFFFF", font=("Helvetica", 14, "bold")).pack(pady=10)
        entry = tk.Entry(win, font=("Helvetica", 14), bg="#E9ECEF")
        entry.pack(pady=10, fill="x", padx=20)
        entry.focus_set()

        def save_customer():
            name = entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Customer name cannot be empty.", parent=win)
                return
            customer_id = str(uuid.uuid4())
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT customer_id FROM customers WHERE name = ?", (name,))
                existing = cursor.fetchone()
                if existing:
                    customer_id = existing[0]
                else:
                    cursor.execute(
                        "INSERT INTO customers (customer_id, name, contact, address) VALUES (?, ?, ?, ?)",
                        (customer_id, name, "", "")
                    )
                self.conn.commit()
            self.current_customer_id = customer_id
            self.current_customer_name = name
            win.destroy()
            messagebox.showinfo("Customer Selected", f"Customer: {name}", parent=self.root)

        tk.Button(win, text="Save", command=save_customer,
                  bg="#28A745", fg="#FFFFFF", font=("Helvetica", 12, "bold"),
                  padx=15, pady=8, bd=0, relief="flat").pack(pady=15)
        entry.bind("<Return>", lambda e: save_customer())


    def focus_cash_paid(self, event=None):
        if "Cash Paid " in self.summary_entries:
            cash_entry = self.summary_entries["Cash Paid "]
            cash_entry.focus_set()
            cash_entry.select_range(0, tk.END)
            cash_entry.icursor(tk.END)

    def validate_cash_input(self, value_if_allowed: str, text: str) -> bool:
        if not text:
            return True
        try:
            if value_if_allowed == "":
                return True
            float(value_if_allowed)
            return bool(value_if_allowed.replace(".", "").isdigit() and value_if_allowed.count(".") <= 1)
        except ValueError:
            return False

    def clear_frame(self):
        if hasattr(self, 'main_frame') and self.main_frame.winfo_exists():
            for widget in self.main_frame.winfo_children():
                widget.destroy()

    def show_account_management(self):
        self.root.destroy()

    def setup_navigation(self, main_frame):
        nav_frame = tk.Frame(main_frame, bg="#343A40", highlightthickness=0)
        nav_frame.pack(fill="x")

        logout_btn = tk.Button(
            nav_frame,
            text="Logout",
            command=self.logout,
            bg="#DC3545",
            fg="#FFFFFF",
            font=("Helvetica", self.scale_size(14), "bold"),
            activebackground="#C82333",
            activeforeground="#FFFFFF",
            padx=self.scale_size(12),
            pady=self.scale_size(6),
            bd=0,
            relief="flat"
        )
        logout_btn.pack(side="right", padx=self.scale_size(10), pady=self.scale_size(5))


    def show_dashboard(self) -> None:
        if not self.current_user:
            self.root.destroy()
            return
        if self.get_user_role() == "Drug Lord":
            self.show_account_management()
            return
        self.clear_frame()
        self.main_frame.pack(fill="both", expand=True)
        self.style_config()
        main_frame = tk.Frame(self.main_frame, bg="#FFFFFF", highlightthickness=1, highlightbackground="#DEE2E6")
        main_frame.pack(fill="both", expand=True, padx=self.scale_size(10), pady=self.scale_size(10))
        self.setup_navigation(main_frame)

        content_frame = tk.Frame(main_frame, bg="#F8F9FA", padx=self.scale_size(20), pady=self.scale_size(20),
                                highlightthickness=1, highlightbackground="#DEE2E6")
        content_frame.pack(fill="both", expand=True)

        search_container = tk.Frame(content_frame, bg="#FFFFFF", padx=self.scale_size(10), pady=self.scale_size(10),
                                   highlightthickness=1, highlightbackground="#DEE2E6")
        search_container.pack(fill="x", pady=self.scale_size(10))

        search_frame = tk.Frame(search_container, bg="#FFFFFF", bd=0, relief="flat")
        search_frame.pack(fill="x", padx=self.scale_size(5), pady=self.scale_size(5))

        tk.Label(search_frame, text="Search Item:", font=("Helvetica", self.scale_size(18), "bold"),
                 bg="#FFFFFF", fg="#343A40").pack(side="left", padx=self.scale_size(12))

        entry_frame = tk.Frame(search_frame, bg="#FFFFFF")
        entry_frame.pack(side="left", fill="x", expand=True, padx=(0, self.scale_size(12)), pady=self.scale_size(5))

        self.search_entry = tk.Entry(entry_frame, font=("Helvetica", self.scale_size(18)), bg="#E9ECEF", fg="#343A40",
                                    bd=0, highlightthickness=1, highlightbackground="#CED4DA", relief="flat")
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=self.scale_size(8))
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
        self.search_entry.bind("<FocusOut>", self.on_entry_focus_out)
        self.search_entry.bind("<Down>", self.move_selection_down)
        self.search_entry.bind("<Up>", self.move_selection_up)
        self.search_entry.bind("<Return>", self.select_suggestion)

        self.clear_btn = tk.Button(entry_frame, text="✕", command=self.clear_search,
                                  bg="#E9ECEF", fg="#343A40", font=("Helvetica", self.scale_size(12), "bold"),
                                  activebackground="#DC3545", activeforeground="#FFFFFF",
                                  bd=0, padx=self.scale_size(8), pady=self.scale_size(4), relief="flat")
        self.clear_btn.pack(side="right", padx=(0, self.scale_size(5)))
        self.clear_btn.pack_forget()

        tk.Button(search_frame, text="🛒", command=self.select_suggestion,
                  bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                  activebackground="#218838", activeforeground="#FFFFFF",
                  padx=self.scale_size(12), pady=self.scale_size(6), bd=0, relief="flat").pack(side="left", padx=self.scale_size(5))

        if self.get_user_role() == "Drug Lord":
            tk.Button(search_frame, text="🗑️", command=lambda: self.create_password_auth_window(
                "Authenticate Deletion", "Enter admin password to delete item", self.validate_delete_item_auth),
                bg="#DC3545", fg="#FFFFFF", font=("Helvetica", self.scale_size(18), "bold"),
                activebackground="#C82333", activeforeground="#FFFFFF",
                padx=self.scale_size(12), pady=self.scale_size(6), bd=0, relief="flat").pack(side="left", padx=self.scale_size(5))

        if not self.suggestion_window:
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.wm_overrideredirect(True)
            self.suggestion_window.configure(bg="#FFFFFF")
            self.suggestion_window.withdraw()
            self.suggestion_listbox = tk.Listbox(self.suggestion_window, height=5, font=("Helvetica", self.scale_size(14)),
                                               bg="#FFFFFF", fg="#343A40", selectbackground="#007BFF",
                                               selectforeground="#FFFFFF", highlightthickness=1, highlightbackground="#DEE2E6", bd=0, relief="flat")
            self.suggestion_listbox.pack(fill="both", expand=True, padx=self.scale_size(5), pady=self.scale_size(5))
            self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_suggestion)
            self.suggestion_listbox.bind("<Return>", self.select_suggestion)
            self.suggestion_listbox.bind("<Up>", self.move_selection_up)
            self.suggestion_listbox.bind("<Down>", self.move_selection_down)
            self.suggestion_listbox.bind("<Motion>", self.highlight_on_hover)
            self.suggestion_listbox.bind("<FocusOut>", lambda e: self.hide_suggestion_window())

        main_content = tk.Frame(content_frame, bg="#F8F9FA")
        main_content.pack(fill="both", expand=True)
        main_content.grid_rowconfigure(0, weight=1)
        main_content.grid_columnconfigure(0, weight=3)
        main_content.grid_columnconfigure(1, weight=1)

        cart_frame = tk.Frame(main_content, bg="#FFFFFF", bd=1, relief="flat", highlightthickness=1, highlightbackground="#DEE2E6")
        cart_frame.grid(row=0, column=0, sticky="nsew", padx=self.scale_size(5), pady=self.scale_size(5))
        cart_frame.grid_rowconfigure(1, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        columns = ("Product", "RetailPrice", "Quantity", "Subtotal")
        headers = ("NAME", "SRP", "QTY", "SUBTOTAL")
        self.cart_table = ttk.Treeview(cart_frame, columns=columns, show="headings", style="Cart.Treeview")
        for col, head in zip(columns, headers):
            self.cart_table.heading(col, text=head)
            if col == "Product":
                width = self.scale_size(200)
            elif col == "RetailPrice":
                width = self.scale_size(120)
            elif col == "Quantity":
                width = self.scale_size(80)
            else:
                width = self.scale_size(120)
            self.cart_table.column(col, width=width, anchor="center" if col != "Product" else "w", stretch=True)
        self.cart_table.grid(row=1, column=0, columnspan=4, sticky="nsew")
        self.cart_table.bind("<<TreeviewSelect>>", self.on_item_select)

        scrollbar = ttk.Scrollbar(cart_frame, orient="vertical", command=self.cart_table.yview)
        scrollbar.grid(row=1, column=4, sticky="ns")
        self.cart_table.configure(yscrollcommand=scrollbar.set)

        self.summary_frame = tk.Frame(main_content, bg="#FFFFFF", bd=1, relief="flat",
                                     highlightthickness=1, highlightbackground="#DEE2E6")
        self.summary_frame.grid(row=0, column=1, sticky="ns", padx=(self.scale_size(10), 0))
        self.summary_frame.grid_propagate(False)
        self.summary_frame.configure(width=self.scale_size(350))

        fields = ["Final Total ", "Cash Paid ", "Change "]
        self.summary_entries = {}
        validate_cmd = self.root.register(self.validate_cash_input)
        for field in fields:
            tk.Label(self.summary_frame, text=field, font=("Helvetica", self.scale_size(24), "bold"),
                     bg="#FFFFFF", fg="#343A40").pack(pady=self.scale_size(5), anchor="w")
            entry = tk.Entry(self.summary_frame, font=("Helvetica", self.scale_size(28)), bg="#E9ECEF",
                            fg="#343A40", highlightthickness=1, highlightbackground="#CED4DA", relief="flat",
                            validate="key", validatecommand=(validate_cmd, '%P', '%S') if field == "Cash Paid " else None)
            entry.pack(pady=self.scale_size(5), fill="x", ipady=self.scale_size(10))
            self.summary_entries[field] = entry
            if field != "Cash Paid ":
                entry.config(state="readonly")
                entry.insert(0, "0.00")
            else:
                entry.insert(0, "0.00")
                entry.bind("<KeyRelease>", self.update_change)

        style = ttk.Style()
        style.configure("Cart.Treeview", background="#FFFFFF", foreground="#343A40", fieldbackground="#FFFFFF")
        print(f"Cart Table Font: {style.lookup('Cart.Treeview', 'font')}")
        print(f"Scaling Factor: {self.scaling_factor}")

        self.update_cart_table()

    def on_entry_focus_out(self, event):
        if self.suggestion_listbox and self.suggestion_listbox.winfo_exists():
            if self.root.focus_get() != self.suggestion_listbox:
                self.hide_suggestion_window()

    def clear_search(self) -> None:
        self.search_entry.delete(0, tk.END)
        self.hide_suggestion_window()
        self.clear_btn.pack_forget()

    def update_suggestions(self, event=None) -> None:
        if event and event.keysym in ("Up", "Down", "Return"):
            return
        query = self.search_entry.get().strip()
        if not self.suggestion_window or not self.suggestion_window.winfo_exists():
            self.suggestion_window = tk.Toplevel(self.root)
            self.suggestion_window.wm_overrideredirect(True)
            self.suggestion_window.configure(bg="#FFFFFF")
            self.suggestion_listbox = tk.Listbox(
                self.suggestion_window,
                height=5,
                font=("Helvetica", self.scale_size(14)),
                bg="#FFFFFF",
                fg="#343A40",
                selectbackground="#007BFF",
                selectforeground="#FFFFFF",
                highlightthickness=1,
                highlightbackground="#DEE2E6",
                bd=0,
                relief="flat"
            )
            self.suggestion_listbox.pack(fill="both", expand=True, padx=self.scale_size(5), pady=self.scale_size(5))
            self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_suggestion)
            self.suggestion_listbox.bind("<Return>", self.select_suggestion)
            self.suggestion_listbox.bind("<Up>", self.move_selection_up)
            self.suggestion_listbox.bind("<Down>", self.move_selection_down)
            self.suggestion_listbox.bind("<Motion>", self.highlight_on_hover)
            self.suggestion_listbox.bind("<FocusOut>", lambda e: self.hide_suggestion_window())

        self.suggestion_listbox.delete(0, tk.END)
        if query:
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "SELECT name, retail_price, quantity, supplier FROM inventory WHERE name LIKE ?",
                        (f"%{query}%",)
                    )
                    suggestions = cursor.fetchall()
                    if suggestions:
                        self.suggestion_listbox.selection_clear(0, tk.END)
                        self.suggestion_listbox.selection_set(0)
                        self.suggestion_listbox.activate(0)
                        self.suggestion_listbox.see(0)
                        for name, retail_price, quantity, supplier in suggestions:
                            display_text = f"{name} - ₱{retail_price:.2f} (Stock: {quantity}, Supplier: {supplier or 'Unknown'})"
                            self.suggestion_listbox.insert(tk.END, display_text)
                        search_width = self.search_entry.winfo_width()
                        self.suggestion_window.geometry(
                            f"{search_width}x{self.suggestion_listbox.winfo_reqheight()}+"
                            f"{self.search_entry.winfo_rootx()}+{self.search_entry.winfo_rooty() + self.search_entry.winfo_height()}"
                        )
                        self.suggestion_window.deiconify()
                        self.clear_btn.pack(side="right", padx=(0, self.scale_size(5)))
                    else:
                        self.hide_suggestion_window()
                        self.clear_btn.pack_forget()
            except sqlite3.Error as e:
                messagebox.showerror("Error", f"Database error: {e}", parent=self.root)

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
        if self.clear_btn and self.clear_btn.winfo_exists():
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

    def select_suggestion(self, event=None) -> None:
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            selection = self.suggestion_listbox.curselection()
            if selection:
                selected_text = self.suggestion_listbox.get(selection[0])
                item_name = selected_text.split(" - ")[0]
                try:
                    with self.conn:
                        cursor = self.conn.cursor()
                        cursor.execute("SELECT item_id, name, retail_price, quantity FROM inventory WHERE name = ?", (item_name,))
                        item = cursor.fetchone()
                        if item:
                            if item[3] <= 0:
                                messagebox.showerror("Error", f"Cannot add {item[1]} to cart: Out of stock", parent=self.root)
                                return
                            for cart_item in self.cart:
                                if cart_item["id"] == item[0]:
                                    if cart_item["quantity"] + 1 > item[3]:
                                        messagebox.showerror("Error", f"Cannot add more {item[1]}: Only {item[3]} in stock", parent=self.root)
                                        return
                                    cart_item["quantity"] += 1
                                    cart_item["subtotal"] = cart_item["retail_price"] * cart_item["quantity"]
                                    break
                            else:
                                self.cart.append({
                                    "id": item[0],
                                    "name": item[1],
                                    "retail_price": item[2],
                                    "quantity": 1,
                                    "subtotal": item[2]
                                })
                            self.update_cart_table()
                            self.search_entry.delete(0, tk.END)
                            self.hide_suggestion_window()
                            self.clear_btn.pack_forget()
                except sqlite3.Error as e:
                    messagebox.showerror("Error", f"Database error: {e}", parent=self.root)

    def update_change(self, event=None) -> None:
        try:
            cash_paid = float(self.summary_entries["Cash Paid "].get() or 0)
            final_total = float(self.summary_entries["Final Total "].get() or 0)
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

    def create_password_auth_window(self, title: str, prompt: str, callback, **kwargs):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(f"{self.scale_size(300)}x{self.scale_size(200)}")
        window.configure(bg="#FFFFFF")
        frame = tk.Frame(window, bg="#FFFFFF", padx=self.scale_size(20), pady=self.scale_size(20),
                         highlightthickness=1, highlightbackground="#DEE2E6")
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=prompt, font=("Helvetica", self.scale_size(12), "bold"), bg="#FFFFFF", fg="#343A40").pack(pady=self.scale_size(10))
        password_entry = tk.Entry(frame, show="*", font=("Helvetica", self.scale_size(12)), bg="#E9ECEF",
                                 fg="#343A40", highlightthickness=1, highlightbackground="#CED4DA", relief="flat")
        password_entry.pack(pady=self.scale_size(10), fill="x")
        password_entry.focus_set()
        tk.Button(frame, text="Submit", command=lambda: callback(password_entry.get(), window, **kwargs),
                 bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(12), "bold"),
                 activebackground="#218838", activeforeground="#FFFFFF",
                 padx=self.scale_size(12), pady=self.scale_size(6), bd=0, relief="flat").pack(pady=self.scale_size(10))
        password_entry.bind("<Return>", lambda e: callback(password_entry.get(), window, **kwargs))

    def validate_delete_item_auth(self, password: str, window: tk.Toplevel, **kwargs) -> None:
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT password FROM users WHERE role = 'Drug Lord'")
                admin_passwords = [row[0] for row in cursor.fetchall()]
                if password in admin_passwords:
                    if self.selected_item_index is not None and 0 <= self.selected_item_index < len(self.cart):
                        item = self.cart[self.selected_item_index]
                        cursor.execute("DELETE FROM inventory WHERE item_id = ?", (item['id'],))
                        self.conn.commit()
                        self.cart.pop(self.selected_item_index)
                        self.selected_item_index = None
                        self.update_cart_table()
                        messagebox.showinfo("Success", "Item deleted from inventory.", parent=self.root)
                    window.destroy()
                else:
                    window.destroy()
                    messagebox.showerror("Error", "Invalid admin password", parent=self.root)
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self.root)

    def update_cart_table(self) -> None:
        """Update cart UI, marking discounted items."""
        if hasattr(self, 'cart_table') and self.cart_table.winfo_exists():
            self.cart_table.delete(*self.cart_table.get_children())

            for item in self.cart:
                # Use discounted price if available
                price = item.get("discounted_price", item["retail_price"])
                subtotal = price * item["quantity"]
                item["subtotal"] = subtotal

                # ✅ Show "(discounted)" tag on item name
                display_name = item["name"]
                if item.get("discount_applied"):
                    display_name = f"{display_name} (discounted)"

                # Insert into cart table
                self.cart_table.insert(
                    "",
                    "end",
                    values=(
                        display_name,
                        f"{price:.2f}",
                        item["quantity"],
                        f"{subtotal:.2f}",
                    ),
                )

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

    def edit_quantity_window(self, event=None) -> None:
        if not self.cart or self.selected_item_index is None:
            messagebox.showerror("Error", "No item selected or cart is empty", parent=self.root)
            return

        item = self.cart[self.selected_item_index]
        window = tk.Toplevel(self.root)
        window.title(f"Edit Quantity for {item['name']}")
        window.configure(bg="#FFFFFF")

        # --- Center the popup ---
        win_w, win_h = self.scale_size(400), self.scale_size(250)
        scr_w, scr_h = window.winfo_screenwidth(), window.winfo_screenheight()
        x, y = (scr_w // 2) - (win_w // 2), (scr_h // 2) - (win_h // 2)
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # --- Larger fonts for readability ---
        font_label_big = ("Helvetica", max(self.scale_size(20), 20), "bold")
        font_label = ("Helvetica", max(self.scale_size(16), 16), "bold")
        font_entry = ("Helvetica", max(self.scale_size(18), 18))
        font_btn = ("Helvetica", max(self.scale_size(18), 18), "bold")

        edit_box = tk.Frame(window, bg="#FFFFFF", padx=self.scale_size(20), pady=self.scale_size(20),
                            bd=1, relief="flat", highlightthickness=1, highlightbackground="#DEE2E6")
        edit_box.pack(pady=self.scale_size(20), fill="both", expand=True)

        tk.Label(edit_box, text=f"Edit Quantity for {item['name']}",
                font=font_label_big, bg="#FFFFFF", fg="#343A40").pack(pady=self.scale_size(10))

        tk.Label(edit_box, text="Quantity",
                font=font_label, bg="#FFFFFF", fg="#343A40").pack()

        quantity_entry = tk.Entry(edit_box, font=font_entry, bg="#E9ECEF", fg="#343A40",
                                highlightthickness=1, highlightbackground="#CED4DA", relief="flat", justify="center")
        quantity_entry.pack(pady=self.scale_size(10), fill="x", ipadx=10, ipady=8)
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
                        messagebox.showerror(
                            "Error",
                            f"Insufficient stock for {item['name']}. Available: {inventory_qty}",
                            parent=window
                        )
                        return
                    item["quantity"] = new_quantity
                    item["subtotal"] = item["retail_price"] * new_quantity
                    if new_quantity == 0:
                        self.cart.pop(self.selected_item_index)
                    self.selected_item_index = None
                    self.update_cart_table()
                    window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid quantity.", parent=window)

        tk.Button(edit_box, text="✓ Update", command=update_quantity,
                bg="#28A745", fg="#FFFFFF", font=font_btn,
                activebackground="#218838", activeforeground="#FFFFFF",
                padx=15, pady=10, bd=0, relief="flat").pack(pady=self.scale_size(15))

        quantity_entry.bind("<Return>", lambda e: update_quantity())


    def update_cart_totals(self):
        """Recalculate total including discounts."""
        total = sum((item.get("discounted_price", item["retail_price"]) or 0) * (item["quantity"] or 0)
                    for item in self.cart)
        if "Final Total " in self.summary_entries:
            self.summary_entries["Final Total "].config(state="normal")
            self.summary_entries["Final Total "].delete(0, tk.END)
            self.summary_entries["Final Total "].insert(0, f"{total:.2f}")
            self.summary_entries["Final Total "].config(state="readonly")
        self.update_change()


    def confirm_clear_cart(self) -> None:
        if messagebox.askyesno("Confirm Clear Cart",
                              "Are you sure you want to clear the cart? This action cannot be undone.",
                              parent=self.root):
            self.cart.clear()
            self.selected_item_index = None
            self.update_cart_table()

    def process_checkout(self, event=None) -> None:
        logging.debug("Starting process_checkout")
        try:
            if not hasattr(self, 'summary_entries') or not all(
                key in self.summary_entries for key in ["Cash Paid ", "Final Total ", "Change "]
            ):
                logging.error("Summary entries not initialized")
                messagebox.showerror("Error", "Checkout fields not initialized. Please restart the application.", parent=self.root)
                return

            cash_paid_str = self.summary_entries["Cash Paid "].get().strip()
            final_total_str = self.summary_entries["Final Total "].get().strip()
            logging.debug(f"Cash Paid: '{cash_paid_str}', Final Total: '{final_total_str}'")

            if not cash_paid_str or not final_total_str:
                logging.error("Cash Paid or Final Total is empty")
                messagebox.showerror("Error", "Cash Paid or Final Total is empty", parent=self.root)
                return

            try:
                cash_paid = float(cash_paid_str)
                final_total = float(final_total_str)
            except ValueError as e:
                logging.error(f"Invalid input for cash_paid or final_total: {e}")
                messagebox.showerror("Error", "Invalid cash or total amount", parent=self.root)
                return

            if cash_paid < final_total:
                logging.error("Insufficient cash paid")
                messagebox.showerror("Error", "Insufficient cash paid.", parent=self.root)
                return

            if not hasattr(self, 'current_customer_id') or not self.current_customer_id:
                if not messagebox.askyesno(
                    "No Customer Information",
                    "No customer ID is selected. Proceed without customer details?",
                    parent=self.root
                ):
                    self.select_customer()
                    return

            if not messagebox.askyesno("Confirm Checkout", "Proceed with checkout?", parent=self.root):
                return

            now = datetime.datetime.now()
            prefix = now.strftime("%m-%Y")
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM transactions WHERE strftime('%m-%Y', timestamp) = ?",
                    (prefix,)
                )
                count = cursor.fetchone()[0] or 0
                sequence = str(count + 1).zfill(5)
            transaction_id = f"{prefix}-{sequence}"

            items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
            change = cash_paid - final_total
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            sale_date = now.strftime("%Y-%m-%d")
            payment_method = getattr(self, 'current_payment_method', 'Cash')
            customer_id = getattr(self, 'current_customer_id', None)

            unit_sales = sum(item["quantity"] for item in self.cart)
            net_profit = 0.0
            with self.conn:
                cursor = self.conn.cursor()
                for item in self.cart:
                    cursor.execute("SELECT retail_price, unit_price, quantity FROM inventory WHERE item_id = ?", (item["id"],))
                    result = cursor.fetchone()
                    if not result:
                        raise ValueError(f"Item {item['id']} not found in inventory")
                    retail_price, unit_price, current_quantity = result
                    if current_quantity < item["quantity"]:
                        raise ValueError(f"Insufficient stock for item {item['id']}: {current_quantity} available")
                    net_profit += (retail_price - unit_price) * item["quantity"]
                    cursor.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", (item["quantity"], item["id"]))

                cursor.execute('''
                    INSERT INTO transactions (transaction_id, items, total_amount, cash_paid, change_amount, timestamp, status, payment_method, customer_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (transaction_id, items, final_total, cash_paid, change, timestamp, "Completed", payment_method, customer_id))

                cursor.execute("SELECT total_sales, unit_sales, net_profit FROM daily_sales WHERE sale_date = ?", (sale_date,))
                existing_sale = cursor.fetchone()
                if existing_sale:
                    new_total_sales = existing_sale[0] + final_total
                    new_unit_sales = existing_sale[1] + unit_sales
                    new_net_profit = existing_sale[2] + net_profit
                    cursor.execute(
                        "UPDATE daily_sales SET total_sales = ?, unit_sales = ?, net_profit = ?, user = ? WHERE sale_date = ?",
                        (new_total_sales, new_unit_sales, new_net_profit, self.current_user, sale_date)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO daily_sales (sale_date, total_sales, unit_sales, net_profit, user) VALUES (?, ?, ?, ?, ?)",
                        (sale_date, final_total, unit_sales, net_profit, self.current_user)
                    )

                cursor.execute('''
                    INSERT INTO transaction_log (log_id, action, details, timestamp, user)
                    VALUES (?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), "Checkout", f"Completed transaction {transaction_id}", timestamp, self.current_user))

                self.conn.commit()

            # ✅ Make snapshot before clearing the cart for receipt
            cart_snapshot = [item.copy() for item in self.cart]

            # --- Clear cart and reset UI ---
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

            # ✅ Generate receipt using cart snapshot (not cleared cart)
            self.generate_receipt(transaction_id, timestamp, cart_snapshot, final_total, cash_paid, change)
            self.check_low_inventory()

        except (sqlite3.Error, ValueError) as e:
            logging.error(f"Checkout failed: {e}")
            messagebox.showerror("Error", f"Failed to process transaction: {e}", parent=self.root)
        except Exception as e:
            logging.error(f"Unexpected error in process_checkout: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.root)


    def generate_receipt(self, transaction_id: str, timestamp: str, cart_items: list, total_amount: float, cash_paid: float, change: float) -> None:
        """Generate a properly formatted PDF receipt with discount markings."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import os

        try:
            receipt_dir = os.path.join(os.path.dirname(self.db_path), "receipts")
            os.makedirs(receipt_dir, exist_ok=True)
            receipt_path = os.path.join(receipt_dir, f"receipt_{transaction_id}.pdf")

            c = canvas.Canvas(receipt_path, pagesize=letter)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(200, 770, "Shinano Pharmacy Receipt")

            c.setFont("Helvetica", 11)
            c.drawString(100, 745, f"Transaction ID: {transaction_id}")
            c.drawString(100, 730, f"Date: {timestamp}")
            if hasattr(self, "current_customer_name") and self.current_customer_name:
                c.drawString(100, 715, f"Customer: {self.current_customer_name}")
            c.drawString(100, 700, "-" * 60)

            # Table header
            y = 680
            c.setFont("Helvetica-Bold", 11)
            c.drawString(100, y, "Item")
            c.drawString(300, y, "Qty")
            c.drawString(360, y, "Price")
            c.drawString(440, y, "Subtotal")
            y -= 15
            c.line(100, y, 500, y)
            y -= 10

            c.setFont("Helvetica", 11)
            for item in cart_items:
                if y < 100:  # New page if space runs out
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = 750

                name = item["name"]
                qty = item["quantity"]
                price = item.get("discounted_price", item["retail_price"])
                subtotal = item["subtotal"]
                discount_flag = item.get("discount_applied", False)
                original_price = item.get("original_price", item["retail_price"])

                # Main item line
                c.drawString(100, y, f"{name[:25]}")  # limit name width
                c.drawRightString(330, y, f"{qty}")
                c.drawRightString(420, y, f"₱{price:.2f}")
                c.drawRightString(500, y, f"₱{subtotal:.2f}")
                y -= 15

                # Show discount note if applied
                if discount_flag:
                    discount_note = f"   → Discounted 20% (was ₱{original_price:.2f})"
                    c.setFont("Helvetica-Oblique", 10)
                    c.setFillColorRGB(0.2, 0.6, 0.2)  # green text
                    c.drawString(100, y, discount_note)
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont("Helvetica", 11)
                    y -= 15

            # Totals
            c.drawString(100, y - 5, "-" * 60)
            y -= 20
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(480, y, f"Total: ₱{total_amount:.2f}")
            y -= 15
            c.setFont("Helvetica", 11)
            c.drawRightString(480, y, f"Cash Paid: ₱{cash_paid:.2f}")
            y -= 15
            c.drawRightString(480, y, f"Change: ₱{change:.2f}")

            y -= 40
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(200, y, "Thank you for shopping at Shinano Pharmacy!")

            c.showPage()
            c.save()

            messagebox.showinfo("Receipt", f"Receipt saved:\n{receipt_path}", parent=self.root)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate receipt: {e}", parent=self.root)


    def check_low_inventory(self) -> None:
        try:
            threshold = 10
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT item_id, name, quantity FROM inventory WHERE quantity <= ?", (threshold,))
                low_items = cursor.fetchall()
                
                if low_items:
                    message = "The following items are low in stock:\n\n"
                    for item_id, name, quantity in low_items:
                        message += f"{name} (ID: {item_id}) - Quantity: {quantity}\n"
                    messagebox.showwarning("Low Inventory Alert", message, parent=self.root)

                cursor.execute(
                    "INSERT INTO transaction_log (log_id, action, details, timestamp, user) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        "Check Inventory",
                        f"Checked low inventory, found {len(low_items)} items",
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        self.current_user or "System"
                    )
                )
                self.conn.commit()
        except sqlite3.Error as e:
            print(f"Database error in check_low_inventory: {e}")
            messagebox.showerror("Database Error", f"Failed to check inventory: {e}", parent=self.root)
        except Exception as e:
            print(f"Unexpected error in check_low_inventory: {e}")
            messagebox.showerror("Error", f"Unexpected error checking inventory: {e}", parent=self.root)

    def logout(self):
        confirm = messagebox.askyesno("Logout", "Are you sure you want to logout?", parent=self.root)
        if confirm:
            self.root.destroy()
            import login  # Make sure you have a login.py file with your login UI
            login.main()  # Call the main function of your login screen


    




    def __del__(self):
        if self.conn:
            self.conn.close()