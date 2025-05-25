import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import uuid

class PharmacyPOS:
    def __init__(self, root):
        self.root = root
        self.root.title("ARI Pharma POS")
        self.root.geometry("1000x600")
        self.conn = sqlite3.connect("pharmacy.db")
        self.create_database()
        self.current_user = None
        self.cart = []
        # Define style for consistent UI with green buttons
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 10), padding=5, background="#28a745", foreground="#ffffff")
        self.style.configure("TLabel", font=("Arial", 10), background="#f0f0f0")
        self.style.configure("TEntry", font=("Arial", 10))
        self.style.configure("Treeview.Heading", font=("Arial", 10, "bold"))
        self.style.configure("TFrame", background="#f0f0f0")
        self.setup_gui()

    def create_database(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT,
                role TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                item_id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                price REAL,
                quantity INTEGER
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
                status TEXT
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", 
                      ("admin", "admin123", "Drug Lord"))
        self.conn.commit()

    def setup_gui(self):
        self.root.configure(bg="#f0f0f0")
        self.main_frame = ttk.Frame(self.root, style="TFrame")
        self.main_frame.pack(fill="both", expand=True)
        self.show_login()

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def setup_navigation(self, parent):
        header_frame = ttk.Frame(parent, style="TFrame")
        header_frame.pack(side="top", fill="x", pady=10)
        ttk.Label(header_frame, text="ARI Pharma", font=("Arial", 16, "bold"), 
                 background="#f0f0f0").pack(side="left", padx=20)
        ttk.Label(header_frame, text=f"{datetime.now().strftime('%I:%M %p PST, %B %d, %Y')}", 
                 font=("Arial", 10), background="#f0f0f0").pack(side="right", padx=20)

        user_frame = ttk.Frame(parent, style="TFrame")
        user_frame.pack(side="top", fill="x", pady=5)
        ttk.Label(user_frame, text=f"{self.current_user} (Drug Lord)", 
                 font=("Arial", 12), background="#f0f0f0").pack(side="right", padx=20)

        nav_frame = ttk.Frame(parent, style="TFrame")
        nav_frame.pack(side="top", fill="x", pady=10)
        buttons = [
            ("Home", self.show_dashboard),
            ("Transactions", self.show_transactions),
            ("Inventory", self.show_inventory),
            ("Sales Summary", self.show_sales_summary),
            ("Log out", self.show_login)
        ]
        for text, command in buttons:
            ttk.Button(nav_frame, text=text, command=command, style="TButton").pack(side="left", padx=10)

    def show_login(self):
        self.clear_frame()
        login_frame = ttk.Frame(self.main_frame, padding=20, style="TFrame")
        login_frame.pack(fill="both", expand=True)

        ttk.Label(login_frame, text="MedKitPOS Login", font=("Arial", 20, "bold")).pack(pady=10)
        ttk.Label(login_frame, text="Welcome to ARI Pharma! Please enter your credentials.").pack(pady=10)

        ttk.Label(login_frame, text="Username").pack()
        username_entry = ttk.Entry(login_frame)
        username_entry.pack(pady=5)

        ttk.Label(login_frame, text="Password").pack()
        password_entry = ttk.Entry(login_frame, show="*")
        password_entry.pack(pady=5)

        show_password_var = tk.BooleanVar()
        ttk.Checkbutton(login_frame, text="Show Password", 
                       variable=show_password_var, 
                       command=lambda: password_entry.config(show="" if show_password_var.get() else "*")).pack()

        ttk.Button(login_frame, text="Login", style="TButton", 
                  command=lambda: self.validate_login(username_entry.get(), password_entry.get())).pack(pady=20)

    def validate_login(self, username, password):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        if cursor.fetchone():
            self.current_user = username
            self.show_dashboard()
        else:
            messagebox.showerror("Error", "Invalid credentials")

    def show_dashboard(self):
        self.clear_frame()
        dashboard_frame = ttk.Frame(self.main_frame, padding=20, style="TFrame")
        dashboard_frame.pack(fill="both", expand=True)
        self.setup_navigation(dashboard_frame)

        search_frame = ttk.Frame(dashboard_frame, style="TFrame")
        search_frame.pack(fill="x", pady=10)
        ttk.Label(search_frame, text="Search Item (Barcode or Name):").pack(side="left")
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", padx=5)
        ttk.Button(search_frame, text="🔍", style="TButton", 
                  command=lambda: self.select_suggestion()).pack(side="left")

        # Suggestion Listbox
        self.suggestion_listbox = tk.Listbox(dashboard_frame, height=5, font=("Arial", 10), 
                                           selectbackground="#28a745", selectforeground="#ffffff")
        self.suggestion_listbox.pack(fill="x", padx=20, pady=5)
        self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_suggestion)
        self.suggestion_listbox.bind("<Return>", self.select_suggestion)
        self.suggestion_listbox.bind("<FocusOut>", lambda e: self.suggestion_listbox.pack_forget())
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
        self.search_entry.bind("<FocusIn>", self.update_suggestions)

        cart_frame = ttk.Frame(dashboard_frame, style="TFrame")
        cart_frame.pack(fill="both", expand=True)
        self.cart_table = ttk.Treeview(cart_frame, 
                                      columns=("ID", "Name", "Price", "Quantity", "Subtotal", "Action"), 
                                      show="headings")
        self.cart_table.heading("ID", text="Item ID")
        self.cart_table.heading("Name", text="Name")
        self.cart_table.heading("Price", text="Price (PHP)")
        self.cart_table.heading("Quantity", text="Quantity")
        self.cart_table.heading("Subtotal", text="Subtotal (PHP)")
        self.cart_table.heading("Action", text="Action")
        self.cart_table.pack(fill="both", expand=True)
        self.cart_table.bind("<Double-1>", self.remove_cart_item)

        summary_frame = ttk.Frame(dashboard_frame, style="TFrame")
        summary_frame.pack(fill="x", pady=10)
        self.discount_var = tk.BooleanVar()
        ttk.Checkbutton(summary_frame, text="Apply 20% Discount (Senior/PWD)", 
                       variable=self.discount_var, command=self.update_cart_totals).pack(side="left")
        
        fields = ["Subtotal (PHP)", "Discount (PHP)", "Final Total (PHP)", "Cash Paid (PHP)", "Change (PHP)"]
        self.summary_entries = {}
        for field in fields:
            frame = ttk.Frame(summary_frame, style="TFrame")
            frame.pack(fill="x", pady=2)
            ttk.Label(frame, text=field).pack(side="left")
            entry = ttk.Entry(frame)
            entry.pack(side="left", padx=5)
            self.summary_entries[field] = entry

        ttk.Button(summary_frame, text="Clear Cart", style="TButton", 
                  command=self.confirm_clear_cart).pack(side="left", padx=5)
        ttk.Button(summary_frame, text="Checkout", style="TButton", 
                  command=self.confirm_checkout).pack(side="left", padx=5)

    def update_suggestions(self, event=None):
        query = self.search_entry.get().strip()
        self.suggestion_listbox.delete(0, tk.END)
        if query:
            cursor = self.conn.cursor()
            cursor.execute("SELECT item_id, name FROM inventory WHERE item_id LIKE ? OR name LIKE ?", 
                          (f"%{query}%", f"%{query}%"))
            suggestions = cursor.fetchall()
            for item_id, name in suggestions:
                self.suggestion_listbox.insert(tk.END, f"{item_id} - {name}")
            self.suggestion_listbox.pack(fill="x", padx=20, pady=5)
        else:
            self.suggestion_listbox.pack_forget()

    def select_suggestion(self, event=None):
        selection = self.suggestion_listbox.curselection()
        if not selection:
            return
        selected_text = self.suggestion_listbox.get(selection[0])
        item_id = selected_text.split(" - ")[0]
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inventory WHERE item_id = ?", (item_id,))
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
            self.suggestion_listbox.pack_forget()
            self.search_entry.delete(0, tk.END)

    def remove_cart_item(self, event):
        selected_item = self.cart_table.selection()
        if not selected_item:
            return
        item_id = self.cart_table.item(selected_item)["values"][0]
        self.cart = [item for item in self.cart if item["id"] != item_id]
        self.update_cart_table()

    def update_cart_table(self):
        for item in self.cart_table.get_children():
            self.cart_table.delete(item)
        for item in self.cart:
            self.cart_table.insert("", "end", values=(
                item["id"], item["name"], f"{item['price']:.2f}", 
                item["quantity"], f"{item['subtotal']:.2f}", "Remove"
            ))
        self.update_cart_totals()

    def update_cart_totals(self):
        subtotal = sum(item["subtotal"] for item in self.cart)
        discount = subtotal * 0.2 if self.discount_var.get() else 0
        final_total = subtotal - discount
        self.summary_entries["Subtotal (PHP)"].delete(0, tk.END)
        self.summary_entries["Subtotal (PHP)"].insert(0, f"{subtotal:.2f}")
        self.summary_entries["Discount (PHP)"].delete(0, tk.END)
        self.summary_entries["Discount (PHP)"].insert(0, f"{discount:.2f}")
        self.summary_entries["Final Total (PHP)"].delete(0, tk.END)
        self.summary_entries["Final Total (PHP)"].insert(0, f"{final_total:.2f}")

    def confirm_clear_cart(self):
        if messagebox.askyesno("Confirm Clear Cart", "Are you sure you want to clear the cart? This action cannot be undone."):
            self.cart = []
            self.update_cart_table()

    def confirm_checkout(self):
        cash_paid = self.summary_entries["Cash Paid (PHP)"].get()
        try:
            cash_paid = float(cash_paid)
            final_total = float(self.summary_entries["Final Total (PHP)"].get())
            if cash_paid < final_total:
                messagebox.showerror("Error", "Please enter a valid cash paid amount to proceed with checkout.")
                return
            if messagebox.askyesno("Confirm Checkout", "Are you sure you want to proceed with checkout?"):
                self.process_checkout(cash_paid, final_total)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid cash paid amount.")

    def process_checkout(self, cash_paid, final_total):
        transaction_id = str(uuid.uuid4())
        items = ";".join([f"{item['id']}:{item['quantity']}" for item in self.cart])
        change = cash_paid - final_total
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)", 
                      (transaction_id, items, final_total, cash_paid, change, timestamp, "Completed"))
        self.conn.commit()
        self.summary_entries["Change (PHP)"].delete(0, tk.END)
        self.summary_entries["Change (PHP)"].insert(0, f"{change:.2f}")
        messagebox.showinfo("Success", f"Transaction completed successfully! Transaction ID: {transaction_id}")
        self.cart = []
        self.update_cart_table()

    def show_inventory(self):
        self.clear_frame()
        inventory_frame = ttk.Frame(self.main_frame, padding=20, style="TFrame")
        inventory_frame.pack(fill="both", expand=True)
        self.setup_navigation(inventory_frame)

        button_frame = ttk.Frame(inventory_frame, style="TFrame")
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Add New Item", command=self.show_add_item, style="TButton").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Refresh Inventory", command=self.update_inventory_table, style="TButton").pack(side="left", padx=10)

        self.inventory_table = ttk.Treeview(inventory_frame, 
                                           columns=("ID", "Name", "Type", "Price", "Quantity", "Action"), 
                                           show="headings")
        self.inventory_table.heading("ID", text="Item ID")
        self.inventory_table.heading("Name", text="Name")
        self.inventory_table.heading("Type", text="Type")
        self.inventory_table.heading("Price", text="Price (PHP)")
        self.inventory_table.heading("Quantity", text="Quantity")
        self.inventory_table.heading("Action", text="Action")
        self.inventory_table.pack(fill="both", expand=True)
        self.inventory_table.bind("<Double-1>", self.on_inventory_table_click)
        self.update_inventory_table()

    def update_inventory_table(self):
        for item in self.inventory_table.get_children():
            self.inventory_table.delete(item)
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inventory")
        for item in cursor.fetchall():
            self.inventory_table.insert("", "end", values=(item[0], item[1], item[2], item[3], item[4], "Update"))

    def show_add_item(self):
        add_window = tk.Toplevel(self.root)
        add_window.title("Add New Item to Inventory")
        add_window.geometry("400x400")
        add_window.configure(bg="#f0f0f0")

        ttk.Label(add_window, text="Add New Item to Inventory", font=("Arial", 14, "bold")).pack(pady=20)

        fields = ["Item ID (Barcode)", "Product Name", "Price (PHP)", "Quantity"]
        entries = {}
        for field in fields:
            frame = ttk.Frame(add_window, style="TFrame")
            frame.pack(fill="x", padx=20, pady=5)
            ttk.Label(frame, text=field).pack(side="left")
            entry = ttk.Entry(frame)
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry

        type_var = tk.StringVar()
        ttk.Label(add_window, text="Type").pack(pady=5)
        ttk.Combobox(add_window, textvariable=type_var, 
                    values=["Medicine", "Supplement", "Medical Device", "Other"], 
                    state="readonly").pack(pady=5, padx=20)

        ttk.Button(add_window, text="Add Item", style="TButton", 
                  command=lambda: self.add_item(
                      entries["Item ID (Barcode)"].get(),
                      entries["Product Name"].get(),
                      type_var.get(),
                      entries["Price (PHP)"].get(),
                      entries["Quantity"].get(),
                      add_window
                  )).pack(pady=20)

    def add_item(self, item_id, name, item_type, price, quantity, window):
        try:
            price = float(price)
            quantity = int(quantity)
            if not item_id or not name or not item_type:
                messagebox.showerror("Error", "All fields are required")
                return
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", 
                          (item_id, name, item_type, price, quantity))
            self.conn.commit()
            self.update_inventory_table()
            window.destroy()
            messagebox.showinfo("Success", "Item added successfully")
        except ValueError:
            messagebox.showerror("Error", "Invalid price or quantity")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists")

    def on_inventory_table_click(self, event):
        selected_item = self.inventory_table.selection()
        if not selected_item:
            return
        item_id = self.inventory_table.item(selected_item)["values"][0]
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM inventory WHERE item_id = ?", (item_id,))
        item = cursor.fetchone()
        if item:
            self.show_update_item(item)

    def show_update_item(self, item):
        update_window = tk.Toplevel(self.root)
        update_window.title("Update Item in Inventory")
        update_window.geometry("400x400")
        update_window.configure(bg="#f0f0f0")

        ttk.Label(update_window, text="Update Item in Inventory", font=("Arial", 14, "bold")).pack(pady=20)

        fields = ["Item ID (Barcode)", "Product Name", "Price (PHP)", "Quantity"]
        entries = {}
        for i, field in enumerate(fields):
            frame = ttk.Frame(update_window, style="TFrame")
            frame.pack(fill="x", padx=20, pady=5)
            ttk.Label(frame, text=field).pack(side="left")
            entry = ttk.Entry(frame)
            entry.pack(side="left", fill="x", expand=True, padx=5)
            entries[field] = entry
            entry.insert(0, item[i] if i < 2 else item[i+1])

        type_var = tk.StringVar(value=item[2])
        ttk.Label(update_window, text="Type").pack(pady=5)
        ttk.Combobox(update_window, textvariable=type_var, 
                    values=["Medicine", "Supplement", "Medical Device", "Other"], 
                    state="readonly").pack(pady=5, padx=20)

        ttk.Button(update_window, text="Update Item", style="TButton", 
                  command=lambda: self.update_item(
                      entries["Item ID (Barcode)"].get(),
                      entries["Product Name"].get(),
                      type_var.get(),
                      entries["Price (PHP)"].get(),
                      entries["Quantity"].get(),
                      item[0],
                      update_window
                  )).pack(pady=20)

    def update_item(self, item_id, name, item_type, price, quantity, original_item_id, window):
        try:
            price = float(price)
            quantity = int(quantity)
            if not item_id or not name or not item_type:
                messagebox.showerror("Error", "All fields are required")
                return
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE inventory 
                SET item_id = ?, name = ?, type = ?, price = ?, quantity = ?
                WHERE item_id = ?
            """, (item_id, name, item_type, price, quantity, original_item_id))
            self.conn.commit()
            self.update_inventory_table()
            window.destroy()
            messagebox.showinfo("Success", "Item updated successfully")
        except ValueError:
            messagebox.showerror("Error", "Invalid price or quantity")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item ID already exists")

    def show_transactions(self):
        self.clear_frame()
        transactions_frame = ttk.Frame(self.main_frame, padding=20, style="TFrame")
        transactions_frame.pack(fill="both", expand=True)
        self.setup_navigation(transactions_frame)

        ttk.Button(transactions_frame, text="Refresh Transactions", style="TButton", 
                  command=self.update_transactions_table).pack(pady=10)

        self.transactions_table = ttk.Treeview(transactions_frame, 
                                              columns=("ID", "Items", "Total", "Cash", "Change", "Timestamp", "Status", "Action"), 
                                              show="headings")
        self.transactions_table.heading("ID", text="Transaction ID")
        self.transactions_table.heading("Items", text="Items")
        self.transactions_table.heading("Total", text="Total Amount (PHP)")
        self.transactions_table.heading("Cash", text="Cash Paid (PHP)")
        self.transactions_table.heading("Change", text="Change (PHP)")
        self.transactions_table.heading("Timestamp", text="Timestamp")
        self.transactions_table.heading("Status", text="Status")
        self.transactions_table.heading("Action", text="Actions")
        self.transactions_table.pack(fill="both", expand=True)
        self.update_transactions_table()

    def update_transactions_table(self):
        for item in self.transactions_table.get_children():
            self.transactions_table.delete(item)
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM transactions")
        for transaction in cursor.fetchall():
            self.transactions_table.insert("", "end", values=(
                transaction[0], transaction[1], f"{transaction[2]:.2f}", 
                f"{transaction[3]:.2f}", f"{transaction[4]:.2f}", 
                transaction[5], transaction[6], "Refund"
            ))

    def show_sales_summary(self):
        self.clear_frame()
        summary_frame = ttk.Frame(self.main_frame, padding=20, style="TFrame")
        summary_frame.pack(fill="both", expand=True)
        self.setup_navigation(summary_frame)

        ttk.Label(summary_frame, text="Monthly Sales Summary", font=("Arial", 14, "bold")).pack(pady=10)
        monthly_table = ttk.Treeview(summary_frame, columns=("Month", "Total"), show="headings")
        monthly_table.heading("Month", text="Month")
        monthly_table.heading("Total", text="Total Sales (PHP)")
        monthly_table.pack(fill="x", pady=5)

        ttk.Label(summary_frame, text="Daily Sales Summary", font=("Arial", 14, "bold")).pack(pady=10)
        daily_table = ttk.Treeview(summary_frame, columns=("Date", "Total"), show="headings")
        daily_table.heading("Date", text="Date")
        daily_table.heading("Total", text="Total Sales (PHP)")
        daily_table.pack(fill="x", pady=5)

        cursor = self.conn.cursor()
        cursor.execute("SELECT strftime('%Y-%m', timestamp) AS month, SUM(total_amount) FROM transactions GROUP BY month")
        for row in cursor.fetchall():
            monthly_table.insert("", "end", values=(row[0], f"{row[1]:.2f}" if row[1] else "0.00"))
        
        cursor.execute("SELECT strftime('%Y-%m-%d', timestamp) AS date, SUM(total_amount) FROM transactions GROUP BY date")
        for row in cursor.fetchall():
            daily_table.insert("", "end", values=(row[0], f"{row[1]:.2f}" if row[1] else "0.00"))

if __name__ == "__main__":
    root = tk.Tk()
    app = PharmacyPOS(root)
    root.mainloop()